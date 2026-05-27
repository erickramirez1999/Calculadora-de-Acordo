"""
Importador de acordo pronto via XLSX.

Aceita arquivos no formato:
- Aba única com 2 áreas lado a lado:
  - Boletos (colunas A-F): Nome Parceiro, Nro Único, Nro Nota, Desdob, Vencimento, Valor
  - Cronograma (colunas I-L): Parcela, Data, Valor, Status

OU formato exportado pelo próprio sistema (2 abas: "Boletos do Acordo" + "Cronograma de Pagamentos")

Reconhece grupo econômico: cada nome de parceiro vira um cliente.

Não recalcula juros — usa valores exatos do arquivo.
CNPJ não vem no arquivo, fica em branco pra completar depois.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import BinaryIO

import pandas as pd


@dataclass
class BoletoImportado:
    """Um boleto extraído do arquivo de acordo."""
    nome_parceiro: str
    nro_unico: str
    nro_nota: str | None
    desdobramento: str | None
    vencimento: date
    valor_principal: float


@dataclass
class ParcelaImportada:
    """Uma parcela do cronograma."""
    numero: int
    data: date
    valor: float
    status: str  # "EM_ANDAMENTO" | "A_VENCER" | "PAGA"


@dataclass
class AcordoImportado:
    """Acordo completo importado do arquivo."""
    boletos: list[BoletoImportado] = field(default_factory=list)
    parcelas: list[ParcelaImportada] = field(default_factory=list)
    nomes_clientes: list[str] = field(default_factory=list)  # nomes únicos
    valor_total_boletos: float = 0.0
    valor_total_parcelas: float = 0.0
    aviso_diferenca: str | None = None  # se boletos != parcelas


def _parse_data(v) -> date | None:
    if pd.isna(v) or v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s.split()[0] if " " in s else s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_valor(v) -> float:
    if pd.isna(v) or v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").strip()
    # BR: "1.500,50" → US: "1500.50"
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _normalizar_nome(nome: str) -> str:
    """Remove asteriscos do começo, espaços extras, truncamento."""
    if not nome:
        return ""
    n = str(nome).strip()
    while n.startswith("*"):
        n = n[1:].strip()
    return n


def _normalizar_status(s) -> str:
    """Normaliza string de status pra valor canônico."""
    if pd.isna(s) or s in (None, ""):
        return "A_VENCER"
    s_up = str(s).strip().upper()
    if "ANDAMENTO" in s_up or "ATIVO" in s_up:
        return "EM_ANDAMENTO"
    if "PAGO" in s_up or "PAGA" in s_up or "QUITAD" in s_up:
        return "PAGA"
    return "A_VENCER"


def ler_acordo_xlsx(arquivo: BinaryIO | bytes | str) -> AcordoImportado:
    """
    Lê um arquivo XLSX de acordo e retorna os dados estruturados.
    
    Detecta automaticamente os 2 formatos:
    - Formato 1: 1 aba com boletos + cronograma lado a lado
    - Formato 2: 2 abas separadas ("Boletos do Acordo" + "Cronograma de Pagamentos")
    """
    if isinstance(arquivo, bytes):
        arquivo = BytesIO(arquivo)

    xl = pd.ExcelFile(arquivo)
    
    acordo = AcordoImportado()

    # Tenta detectar formato 2 (2 abas separadas)
    aba_boletos = next(
        (a for a in xl.sheet_names if "boleto" in a.lower()), None
    )
    aba_cronograma = next(
        (a for a in xl.sheet_names if "cronograma" in a.lower() or "parcela" in a.lower()), None
    )

    if aba_boletos and aba_cronograma:
        # Formato 2: abas separadas
        _ler_aba_boletos_separada(xl, aba_boletos, acordo)
        _ler_aba_cronograma_separada(xl, aba_cronograma, acordo)
    else:
        # Formato 1: aba única (boletos esquerda, cronograma direita)
        aba = xl.sheet_names[0]
        _ler_aba_unica(xl, aba, acordo)

    # Calcula totais
    acordo.valor_total_boletos = round(sum(b.valor_principal for b in acordo.boletos), 2)
    acordo.valor_total_parcelas = round(sum(p.valor for p in acordo.parcelas), 2)

    # Nomes únicos de clientes (grupo econômico)
    nomes_vistos = []
    for b in acordo.boletos:
        if b.nome_parceiro and b.nome_parceiro not in nomes_vistos:
            nomes_vistos.append(b.nome_parceiro)
    acordo.nomes_clientes = nomes_vistos

    # Aviso se boletos != parcelas (pode indicar juros embutidos nas parcelas)
    diferenca = acordo.valor_total_parcelas - acordo.valor_total_boletos
    if abs(diferenca) > 0.01:
        if diferenca > 0:
            acordo.aviso_diferenca = (
                f"Cronograma tem R$ {diferenca:,.2f} a mais que os boletos "
                f"(diferença pode ser juros/multa já embutidos)."
            )
        else:
            acordo.aviso_diferenca = (
                f"Cronograma tem R$ {abs(diferenca):,.2f} a MENOS que os boletos "
                f"(pode ter desconto aplicado)."
            )

    return acordo


def _ler_aba_unica(xl, aba_nome, acordo: AcordoImportado):
    """Formato 1: boletos à esquerda, cronograma à direita.
    
    O header de boletos e o header de cronograma podem estar em LINHAS
    DIFERENTES. Detecta cada um separadamente.
    """
    df = pd.read_excel(xl, sheet_name=aba_nome, header=None)

    # ===== BOLETOS (lado esquerdo) =====
    linha_header_bol = None
    col_nome = col_nro_unico = col_nro_nota = col_desdob = col_venc = col_valor = None

    for i in range(min(10, len(df))):
        row = df.iloc[i].tolist()
        row_low = [str(v).lower().strip() if pd.notna(v) else "" for v in row]
        joined = " ".join(row_low)
        if "nome parceiro" in joined or "parceiro" in joined:
            # Achou header de boletos
            linha_header_bol = i
            for idx, h in enumerate(row_low):
                if "nome parceiro" in h or h == "parceiro" or "cliente" in h:
                    col_nome = idx
                elif "nro único" in h or "nro unico" in h or "número único" in h:
                    col_nro_unico = idx
                elif "nro nota" in h or "número nota" in h or h == "nf":
                    col_nro_nota = idx
                elif "desdob" in h:
                    col_desdob = idx
                elif "vencimento" in h or "dt. venc" in h:
                    col_venc = idx
                elif h == "valor" or "valor principal" in h:
                    col_valor = idx
            break

    if linha_header_bol is not None and col_nome is not None:
        for i in range(linha_header_bol + 1, len(df)):
            row = df.iloc[i]
            try:
                nome = _normalizar_nome(row.iloc[col_nome]) if pd.notna(row.iloc[col_nome]) else ""
                if not nome:
                    continue
                vencimento = _parse_data(row.iloc[col_venc]) if col_venc is not None else None
                valor = _parse_valor(row.iloc[col_valor]) if col_valor is not None else 0.0
                if not vencimento or valor <= 0:
                    continue
                boleto = BoletoImportado(
                    nome_parceiro=nome,
                    nro_unico=str(row.iloc[col_nro_unico]).strip().split(".")[0] if col_nro_unico is not None and pd.notna(row.iloc[col_nro_unico]) else "",
                    nro_nota=str(row.iloc[col_nro_nota]).strip().split(".")[0] if col_nro_nota is not None and pd.notna(row.iloc[col_nro_nota]) else None,
                    desdobramento=str(row.iloc[col_desdob]).strip().split(".")[0] if col_desdob is not None and pd.notna(row.iloc[col_desdob]) else None,
                    vencimento=vencimento,
                    valor_principal=valor,
                )
                acordo.boletos.append(boleto)
            except (IndexError, ValueError):
                pass

    # ===== CRONOGRAMA (lado direito) =====
    # Procura header PARCELA | DATA | VALOR | STATUS (em qualquer linha)
    linha_header_cron = None
    col_parc = col_data = col_valor_p = col_status = None

    for i in range(min(15, len(df))):
        row = df.iloc[i].tolist()
        row_low = [str(v).lower().strip() if pd.notna(v) else "" for v in row]
        # O header de cronograma tem PARCELA + DATA + VALOR + STATUS
        if ("parcela" in row_low and ("data" in row_low or "data pagamento" in row_low)
                and ("status" in row_low or "situação" in row_low)):
            linha_header_cron = i
            for idx, h in enumerate(row_low):
                if h == "parcela":
                    col_parc = idx
                elif h == "data" or "data pagamento" in h:
                    col_data = idx
                elif h == "valor" or "valor da parcela" in h:
                    col_valor_p = idx
                elif h == "status" or h == "situação":
                    col_status = idx
            break

    if linha_header_cron is not None and col_parc is not None:
        for i in range(linha_header_cron + 1, len(df)):
            row = df.iloc[i]
            try:
                num_raw = row.iloc[col_parc] if col_parc is not None else None
                if pd.isna(num_raw):
                    continue
                num = int(float(str(num_raw).strip()))
                data = _parse_data(row.iloc[col_data]) if col_data is not None else None
                valor = _parse_valor(row.iloc[col_valor_p]) if col_valor_p is not None else 0.0
                status_raw = row.iloc[col_status] if col_status is not None else None
                if not data or valor <= 0:
                    continue
                acordo.parcelas.append(ParcelaImportada(
                    numero=num, data=data, valor=valor,
                    status=_normalizar_status(status_raw),
                ))
            except (IndexError, ValueError, TypeError):
                pass


def _ler_aba_boletos_separada(xl, aba_nome, acordo: AcordoImportado):
    """Formato 2 - aba de boletos. O nome do cliente pode vir no título (L0)."""
    df = pd.read_excel(xl, sheet_name=aba_nome, header=None)

    # Tenta pegar o nome do cliente no título da planilha (L0)
    nome_do_titulo = None
    if len(df) > 0:
        primeira = df.iloc[0]
        for v in primeira.tolist():
            if pd.notna(v) and isinstance(v, str) and len(v) > 10:
                # Remove prefixos tipo "ACORDO ", "ACORDO -"
                t = v.strip()
                for prefixo in ("ACORDO ", "ACORDO -", "ACORDO:"):
                    if t.upper().startswith(prefixo):
                        t = t[len(prefixo):].strip(" -:")
                        break
                # Se tem "— RELA..." ou similar (sufixo), corta
                for marcador in ("—", " - REL", " — REL"):
                    if marcador in t:
                        t = t.split(marcador)[0].strip()
                if t:
                    nome_do_titulo = t
                    break

    # Achar header
    linha_header = None
    for i in range(min(10, len(df))):
        row = df.iloc[i].tolist()
        row_low = [str(v).lower().strip() if pd.notna(v) else "" for v in row]
        joined = " ".join(row_low)
        if "vencimento" in joined and ("valor principal" in joined or "nº único" in joined or "nro único" in joined):
            linha_header = i
            break
    if linha_header is None:
        return

    header = df.iloc[linha_header].tolist()
    header_low = [str(v).lower().strip() if pd.notna(v) else "" for v in header]

    col_nome = col_nro_unico = col_nro_nota = col_venc = col_valor = None
    for idx, h in enumerate(header_low):
        if "nome parceiro" in h or h == "parceiro" or "cliente" in h:
            col_nome = idx
        elif "nº único" in h or "nro único" in h or "nro unico" in h or "número único" in h:
            col_nro_unico = idx
        elif "nº nota" in h or "nro nota" in h or "número nota" in h:
            col_nro_nota = idx
        elif "vencimento" in h:
            col_venc = idx
        elif "valor principal" in h:
            col_valor = idx

    for i in range(linha_header + 1, len(df)):
        row = df.iloc[i]
        try:
            if col_nome is not None and pd.notna(row.iloc[col_nome]):
                nome = _normalizar_nome(row.iloc[col_nome])
            else:
                nome = nome_do_titulo or ""

            vencimento = _parse_data(row.iloc[col_venc]) if col_venc is not None else None
            valor = _parse_valor(row.iloc[col_valor]) if col_valor is not None else 0.0
            if not nome or not vencimento or valor <= 0:
                continue

            boleto = BoletoImportado(
                nome_parceiro=nome,
                nro_unico=str(row.iloc[col_nro_unico]).strip().split(".")[0] if col_nro_unico is not None and pd.notna(row.iloc[col_nro_unico]) else "",
                nro_nota=str(row.iloc[col_nro_nota]).strip().split(".")[0] if col_nro_nota is not None and pd.notna(row.iloc[col_nro_nota]) else None,
                desdobramento=None,
                vencimento=vencimento,
                valor_principal=valor,
            )
            acordo.boletos.append(boleto)
        except (IndexError, ValueError):
            pass


def _ler_aba_cronograma_separada(xl, aba_nome, acordo: AcordoImportado):
    """Formato 2 - aba de cronograma."""
    df = pd.read_excel(xl, sheet_name=aba_nome, header=None)

    linha_header = None
    for i in range(min(10, len(df))):
        row = df.iloc[i].tolist()
        row_low = [str(v).lower().strip() if pd.notna(v) else "" for v in row]
        joined = " ".join(row_low)
        if "parcela" in joined and ("data" in joined or "valor" in joined):
            linha_header = i
            break
    if linha_header is None:
        return

    header_low = [str(v).lower().strip() if pd.notna(v) else "" for v in df.iloc[linha_header].tolist()]
    col_num = col_data = col_valor = col_pago = None
    for idx, h in enumerate(header_low):
        if h == "parcela":
            col_num = idx
        elif "data pagamento" in h or h == "data":
            col_data = idx
        elif "valor da parcela" in h or h == "valor":
            col_valor = idx
        elif h == "pago" or h == "status":
            col_pago = idx

    if col_num is None:
        return

    for i in range(linha_header + 1, len(df)):
        row = df.iloc[i]
        try:
            num_raw = row.iloc[col_num]
            if pd.isna(num_raw):
                continue
            num = int(float(str(num_raw).strip()))
            data = _parse_data(row.iloc[col_data]) if col_data is not None else None
            valor = _parse_valor(row.iloc[col_valor]) if col_valor is not None else 0.0
            pago_raw = row.iloc[col_pago] if col_pago is not None else None
            if isinstance(pago_raw, bool):
                status = "PAGA" if pago_raw else "A_VENCER"
            elif pd.notna(pago_raw):
                s = str(pago_raw).strip().lower()
                if s in ("true", "verdadeiro", "sim", "yes"):
                    status = "PAGA"
                elif s in ("false", "falso", "não", "nao", "no"):
                    status = "A_VENCER"
                else:
                    status = _normalizar_status(pago_raw)
            else:
                status = "A_VENCER"
            if data and valor > 0:
                acordo.parcelas.append(ParcelaImportada(
                    numero=num, data=data, valor=valor, status=status
                ))
        except (IndexError, ValueError, TypeError):
            pass


def _achar_coluna(header: list[str], keywords: list[str], excluir_indices: list = None) -> int | None:
    """Acha o índice da primeira coluna que casa com alguma keyword."""
    excluir = set(excluir_indices or [])
    for i, h in enumerate(header):
        if i in excluir:
            continue
        h_low = h.lower()
        for kw in keywords:
            if kw.lower() in h_low:
                return i
    return None
