"""
Parser de PDF — Termo de Acordo do Grupo LLE.

Lê o PDF gerado pelo sistema interno (ou similar) e extrai:
- Dados do devedor (nome + CNPJ + endereço)
- Tabela 1: títulos negociados (principal)
- Tabela 2: cronograma de parcelas do acordo

Funciona com múltiplos PDFs (grupo econômico) — quando você sobe vários,
o sistema soma o principal e soma o valor das parcelas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import BinaryIO

CNPJ_LLE = "05.953.543/0001-47"  # CNPJ próprio do Grupo LLE — ignorar


@dataclass
class TituloPDF:
    """Um título da Tabela 1 (negociados)."""
    numero_titulo: str
    parcela: int
    vencimento: date
    atraso: int
    valor_original: float
    total: float


@dataclass
class ParcelaPDF:
    """Uma parcela da Tabela 2 (cronograma do acordo)."""
    numero: int
    vencimento: date
    valor: float


@dataclass
class TermoAcordoPDF:
    """Termo de acordo completo extraído do PDF."""
    nome_devedor: str = ""
    cnpj_devedor: str = ""
    endereco: str = ""
    cidade: str = ""
    titulos: list[TituloPDF] = field(default_factory=list)
    parcelas: list[ParcelaPDF] = field(default_factory=list)
    qtd_parcelas_declarada: int = 0
    valor_total_declarado: float = 0.0

    @property
    def total_principal(self) -> float:
        """Soma dos VALOR ORIGINAL dos títulos negociados."""
        return round(sum(t.valor_original for t in self.titulos), 2)

    @property
    def total_parcelas(self) -> float:
        """Soma das parcelas do cronograma (acordo)."""
        return round(sum(p.valor for p in self.parcelas), 2)

    @property
    def juros_embutidos(self) -> float:
        """Diferença entre total das parcelas e total do principal."""
        return round(self.total_parcelas - self.total_principal, 2)


def _parse_valor_br(s: str) -> float:
    """'1.057,75' → 1057.75"""
    s = s.replace("R$", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def _parse_data_br(s: str) -> date:
    """'02/02/2024' → date(2024, 2, 2)"""
    return datetime.strptime(s.strip(), "%d/%m/%Y").date()


def ler_termo_acordo_pdf(arquivo: BinaryIO | bytes | str) -> TermoAcordoPDF:
    """
    Lê um PDF de Termo de Acordo LLE e retorna estrutura com:
    - dados do devedor
    - lista de títulos (Tabela 1)
    - cronograma de parcelas (Tabela 2)
    
    Raises:
        ImportError: se pdfplumber não estiver instalado
        ValueError: se o PDF não parecer ser um Termo de Acordo
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "Pra importar PDF instale: pip install pdfplumber"
        )

    if isinstance(arquivo, bytes):
        arquivo = BytesIO(arquivo)

    termo = TermoAcordoPDF()

    with pdfplumber.open(arquivo) as pdf:
        texto = ""
        for page in pdf.pages:
            t = page.extract_text() or ""
            texto += t + "\n"

    # Extrai CNPJ do devedor (não o do LLE)
    cnpjs = re.findall(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", texto)
    for c in cnpjs:
        if c != CNPJ_LLE:
            termo.cnpj_devedor = c
            break

    # Extrai nome do devedor — pattern: "outro lado devedor NOME, inscrito"
    m_nome = re.search(
        r"outro lado devedor\s+(.+?)\s*,\s*inscrito",
        texto, re.IGNORECASE
    )
    if m_nome:
        termo.nome_devedor = m_nome.group(1).strip()

    # Extrai endereço — "estabelecido a ENDERECO, Bairro BAIRRO, na cidade de CIDADE/UF"
    # A primeira ocorrência fica em branco (do LLE), a segunda é a do devedor.
    # Regex permite que a primeira tenha tudo vazio entre vírgulas.
    matches = list(re.finditer(
        r"estabelecido\s+a\s+([^\n]*?),\s*Bairro\s+([^\n,]*?),\s*na\s+cidade\s+de\s+([^\n/]*?)/?\s*([A-Z]{0,2})\s+",
        texto
    ))
    if len(matches) >= 2:
        m_end = matches[1]
        rua = m_end.group(1).strip()
        bairro = m_end.group(2).strip()
        cidade = m_end.group(3).strip()
        uf = m_end.group(4).strip()
        termo.endereco = f"{rua}, {bairro}" if bairro else rua
        termo.cidade = f"{cidade}/{uf}" if uf else cidade

    # Extrai qtd de parcelas declarada e valor total declarado
    # "compromete-se resgatar seu débito em 75 parcela(s), totalizando R$ 75.047,36"
    m_decl = re.search(
        r"em\s+(\d+)\s+parcela\(s\),?\s+totalizando\s+R\$\s*([\d.,]+)",
        texto
    )
    if m_decl:
        termo.qtd_parcelas_declarada = int(m_decl.group(1))
        termo.valor_total_declarado = _parse_valor_br(m_decl.group(2))

    # ============ TABELA 1: Títulos negociados ============
    # Padrão linha: NRO_TITULO PARCELA DD/MM/AAAA ATRASO R$ VALOR R$ TOTAL
    # Para antes de "compromete-se"
    parou_tabela1 = False
    for linha in texto.split("\n"):
        if not parou_tabela1 and "compromete-se" in linha.lower():
            parou_tabela1 = True
            continue
        if parou_tabela1:
            break

        m = re.match(
            r"^\s*(\d{6,8})\s+(\d+)\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+R\$\s*([\d.,]+)\s+R\$\s*([\d.,]+)\s*$",
            linha
        )
        if m:
            try:
                termo.titulos.append(TituloPDF(
                    numero_titulo=m.group(1),
                    parcela=int(m.group(2)),
                    vencimento=_parse_data_br(m.group(3)),
                    atraso=int(m.group(4)),
                    valor_original=_parse_valor_br(m.group(5)),
                    total=_parse_valor_br(m.group(6)),
                ))
            except (ValueError, IndexError):
                pass

    # ============ TABELA 2: Cronograma do acordo ============
    # Padrão: "01/75 20/03/2025 R$ 1.000,00"
    # Começa depois do "compromete-se"
    iniciou_tabela2 = False
    for linha in texto.split("\n"):
        if not iniciou_tabela2:
            if "compromete-se" in linha.lower():
                iniciou_tabela2 = True
            continue

        m = re.match(
            r"^\s*(\d+)/\d+\s+(\d{2}/\d{2}/\d{4})\s+R\$\s*([\d.,]+)\s*$",
            linha
        )
        if m:
            try:
                termo.parcelas.append(ParcelaPDF(
                    numero=int(m.group(1)),
                    vencimento=_parse_data_br(m.group(2)),
                    valor=_parse_valor_br(m.group(3)),
                ))
            except (ValueError, IndexError):
                pass

    if not termo.titulos and not termo.parcelas:
        raise ValueError(
            "Não foi possível extrair tabelas do PDF. "
            "Esse PDF parece não ser um Termo de Acordo do Grupo LLE."
        )

    return termo


# ============================================================
# Junção de múltiplos termos (grupo econômico)
# ============================================================

@dataclass
class GrupoAcordo:
    """Resultado de juntar 1+ termos num único acordo."""
    termos: list[TermoAcordoPDF] = field(default_factory=list)
    
    @property
    def nome_devedor_principal(self) -> str:
        if not self.termos:
            return ""
        return self.termos[0].nome_devedor
    
    @property
    def cnpjs(self) -> list[str]:
        return [t.cnpj_devedor for t in self.termos if t.cnpj_devedor]
    
    @property
    def total_principal(self) -> float:
        """Soma do principal de TODOS os termos."""
        return round(sum(t.total_principal for t in self.termos), 2)
    
    @property
    def total_parcelas_acordo(self) -> float:
        """Soma do valor das parcelas (pode ser diferente do principal — diferença é juros)."""
        return round(sum(t.total_parcelas for t in self.termos), 2)
    
    @property
    def juros_total_embutido(self) -> float:
        """Diferença total entre acordo e principal = juros embutidos."""
        return round(self.total_parcelas_acordo - self.total_principal, 2)
    
    @property
    def qtd_parcelas(self) -> int:
        """Quantidade de parcelas (usa do primeiro termo; pressupõe que são iguais)."""
        if not self.termos:
            return 0
        return len(self.termos[0].parcelas)
    
    @property
    def juros_por_parcela(self) -> float:
        """Quanto de juros está embutido em cada parcela (média)."""
        if self.qtd_parcelas == 0:
            return 0.0
        return round(self.juros_total_embutido / self.qtd_parcelas, 2)
    
    @property
    def todos_titulos(self) -> list[tuple[str, TituloPDF]]:
        """Retorna [(cnpj_devedor, titulo)] de todos os termos."""
        resultado = []
        for t in self.termos:
            for titulo in t.titulos:
                resultado.append((t.cnpj_devedor, titulo))
        return resultado
    
    @property
    def cronograma_somado(self) -> list[ParcelaPDF]:
        """
        Soma as parcelas dos termos por número (1 + 1, 2 + 2, ...).
        Se os termos têm cronogramas com datas iguais e quantidades iguais,
        retorna parcelas únicas com valor somado.
        """
        if not self.termos:
            return []
        
        # Usar o cronograma do 1º termo como referência
        base = self.termos[0].parcelas
        if len(self.termos) == 1:
            return base
        
        # Cria mapa por número → soma de valores
        resultado = []
        for i, p_base in enumerate(base):
            valor_total = p_base.valor
            for termo_extra in self.termos[1:]:
                if i < len(termo_extra.parcelas):
                    valor_total += termo_extra.parcelas[i].valor
            resultado.append(ParcelaPDF(
                numero=p_base.numero,
                vencimento=p_base.vencimento,
                valor=round(valor_total, 2),
            ))
        return resultado


def juntar_termos(termos: list[TermoAcordoPDF]) -> GrupoAcordo:
    """Junta múltiplos termos num grupo econômico."""
    grupo = GrupoAcordo()
    grupo.termos = termos
    return grupo
