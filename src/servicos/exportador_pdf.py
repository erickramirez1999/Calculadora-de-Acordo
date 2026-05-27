"""
Geração dos 4 PDFs oficiais do sistema LLE Acordos.

Modelos fornecidos pelo Erick (em 12/05/2026):
  1. Proposta de Acordo — gerada na Calculadora, antes do acordo virar real
  2. Termo de Acordo — gerado no detalhe do acordo, depois de criado
  3. Termo de Confissão — modelo 1 (cláusula penal 20%, devedor solidário)
  4. Carta de Quitação — gerada só quando o acordo está QUITADO

Regras fixas:
  - Endereço da LLE Ferragens: Av. Londres, 260 - Bonsucesso - Rio de Janeiro/RJ
  - Coluna ESPÉCIE da tabela = "Boleto" (automático)
  - Empresa 1 → PISA DISTRIBUIDORA (CNPJ 05.953.543/0001-47)
  - Empresa 2 → FERRAGENS KING OURO (CNPJ 05.953.543/0002-28)
  - Se acordo tem títulos das DUAS empresas, Quitação lista as duas
"""
from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Set

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from src.utils.formatadores import formatar_brl, formatar_data
from src.utils.marca import AMARELO, AZUL_ESCURO, BRANCO


# ============================================================
# CONSTANTES (regras fixas decididas pelo Erick)
# ============================================================

CREDOR_GRUPO_LLE = {
    "nome": "GRUPO LLE",
    "cnpj": "05.953.543/0001-47",
}

LLE_FERRAGENS = {
    "nome": "L.L.E. FERRAGENS LTDA",
    "cnpj": "05.953.543/0001-47",
    "endereco": "Av. Londres, 260",
    "bairro": "Bonsucesso",
    "cidade": "Rio de Janeiro",
    "uf": "RJ",
    "cep": "21.041-030",
}

EMPRESAS_CREDORAS = {
    1: {"nome": "PISA DISTRIBUIDORA", "cnpj": "05.953.543/0001-47"},
    2: {"nome": "FERRAGENS KING OURO", "cnpj": "05.953.543/0002-28"},
}

LINHA_ALTERNADA = "#F8F9FA"


# ============================================================
# UTILITÁRIOS
# ============================================================

def _cor(hex_):
    return colors.HexColor(hex_)


def _valor_extenso(valor: float) -> str:
    """Converte número em extenso simplificado (R$ 12.192,00 -> 'doze mil...')."""
    try:
        from num2words import num2words
        return num2words(valor, lang="pt_BR", to="currency").replace("real", "reais") \
            .replace("reais", "reais", 1)
    except Exception:
        # Fallback simples: se não tiver biblioteca, devolve só valor formatado
        return formatar_brl(valor).replace("R$", "").strip()


def _logo_path() -> Optional[str]:
    """Caminho da logo do Grupo LLE (colorida com fundo transparente)."""
    base = Path(__file__).parent.parent.parent / "assets"
    candidatos = [base / "logo_lle.png"]
    for c in candidatos:
        if c.exists():
            return str(c)
    return None


def _estilos():
    """Estilos comuns a todos os PDFs."""
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            name="Titulo", parent=base["Heading1"],
            alignment=TA_CENTER, fontSize=14, fontName="Helvetica-Bold",
            textColor=_cor(AZUL_ESCURO), spaceAfter=6,
        ),
        "data_topo": ParagraphStyle(
            name="DataTopo", parent=base["Normal"],
            alignment=TA_RIGHT, fontSize=10, spaceAfter=12,
        ),
        "paragrafo": ParagraphStyle(
            name="Paragrafo", parent=base["Normal"],
            alignment=TA_JUSTIFY, fontSize=10, leading=14, spaceAfter=10,
        ),
        "clausula": ParagraphStyle(
            name="Clausula", parent=base["Normal"],
            alignment=TA_JUSTIFY, fontSize=10, leading=14, spaceAfter=8,
            fontName="Helvetica-Bold",
        ),
        "assinatura": ParagraphStyle(
            name="Assinatura", parent=base["Normal"],
            alignment=TA_CENTER, fontSize=9, spaceBefore=20,
        ),
        "rodape": ParagraphStyle(
            name="Rodape", parent=base["Normal"],
            alignment=TA_CENTER, fontSize=8, textColor=_cor("#666"),
            spaceBefore=20,
        ),
        "celula_pequena": ParagraphStyle(
            name="CelulaPequena", parent=base["Normal"],
            fontSize=8, leading=10,
        ),
    }


def _cabecalho_logo(estilos):
    """Cria a logo + linha de data pra topo do documento."""
    elementos = []
    logo_str = _logo_path()
    if logo_str:
        try:
            elementos.append(Image(logo_str, width=4.5 * cm, height=2.2 * cm))
        except Exception:
            pass
    data_str = f"Rio de Janeiro, {formatar_data(date.today())}"
    elementos.append(Paragraph(data_str, estilos["data_topo"]))
    return elementos


def _rodape_lle(estilos):
    """Rodapé padrão LLE."""
    return Paragraph(
        f"{LLE_FERRAGENS['nome']}<br/>"
        f"CNPJ: {LLE_FERRAGENS['cnpj']}<br/>"
        f"{LLE_FERRAGENS['endereco']} - {LLE_FERRAGENS['bairro']}<br/>"
        f"CEP: {LLE_FERRAGENS['cep']} - {LLE_FERRAGENS['cidade']}/{LLE_FERRAGENS['uf']}",
        estilos["rodape"],
    )


def _tabela_titulos(boletos: List, estilos):
    """
    Tabela de títulos originais (usada em Termo, Confissão, etc).
    Colunas: ESPÉCIE, TÍTULO, PARCELA, VENCIMENTO, ATRASO, VALOR ORIGINAL, TOTAL
    Espécie = "Boleto" (regra Erick)
    """
    cab = ["ESPÉCIE", "TÍTULO", "PARCELA", "VENCIMENTO", "ATRASO",
           "VALOR ORIGINAL", "TOTAL"]
    dados = [cab]
    for b in boletos:
        # No briefing original, "PARCELA" no termo é o "desdobramento" do título
        # (não as parcelas do acordo). Vamos usar o numero_unico se disponível,
        # senão deixa "1".
        parcela_titulo = getattr(b, "parcela_desdobramento", None) or "1"
        atraso = b.dias_atraso if hasattr(b, "dias_atraso") else 0
        dados.append([
            "Boleto",
            str(b.numero_nota),
            str(parcela_titulo),
            formatar_data(b.vencimento),
            str(atraso),
            formatar_brl(b.principal),
            formatar_brl(b.principal),  # No termo, valor = total (sem juros/multa)
        ])

    t = Table(dados, colWidths=[
        2.0 * cm, 2.4 * cm, 1.8 * cm, 2.4 * cm, 1.8 * cm, 3.0 * cm, 2.5 * cm,
    ], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, _cor("#444")),
        ("BACKGROUND", (0, 0), (-1, 0), _cor("#FFFFFF")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 1), (-1, -1), "CENTER"),
        ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _tabela_parcelas(parcelas: List, total_parcelas: int, estilos):
    """Tabela das parcelas do acordo (PARCELA · VENCIMENTO · VALOR)."""
    cab = ["PARCELA", "VENCIMENTO", "VALOR"]
    dados = [cab]
    for p in parcelas:
        dados.append([
            f"{p.numero:02d}/{total_parcelas:02d}",
            formatar_data(p.vencimento_atual),
            formatar_brl(p.valor_original),
        ])

    t = Table(dados, colWidths=[3.0 * cm, 3.5 * cm, 3.5 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, _cor("#444")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _detectar_empresas_credoras(boletos: List) -> List[dict]:
    """Detecta quais empresas (1 ou 2) aparecem nos títulos do acordo."""
    ids: Set[int] = set()
    for b in boletos:
        try:
            ids.add(int(b.empresa))
        except (TypeError, ValueError):
            pass
    resultado = []
    for empresa_id in sorted(ids):
        if empresa_id in EMPRESAS_CREDORAS:
            resultado.append(EMPRESAS_CREDORAS[empresa_id])
    return resultado or [EMPRESAS_CREDORAS[1]]  # default empresa 1


def _bloco_assinaturas(devedor_nome: str, devedor_cnpj: str,
                       cidade_data: str, estilos):
    """Bloco padrão de assinatura (devedor + LLE + testemunhas)."""
    elementos = []
    elementos.append(Spacer(1, 0.5 * cm))
    elementos.append(Paragraph(cidade_data, estilos["paragrafo"]))
    elementos.append(Spacer(1, 1 * cm))

    # Linha de assinaturas (devedor e credor)
    assinaturas = [
        [
            Paragraph(
                f"___________________________________<br/>"
                f"<b>{devedor_nome}</b><br/>"
                f"CNPJ/CPF: {devedor_cnpj}",
                estilos["assinatura"],
            ),
            Paragraph(
                f"___________________________________<br/>"
                f"<b>{LLE_FERRAGENS['nome']}</b><br/>"
                f"CNPJ/CPF: {LLE_FERRAGENS['cnpj']}<br/>"
                f"Por procuração de GRUPO LLE",
                estilos["assinatura"],
            ),
        ],
    ]
    t = Table(assinaturas, colWidths=[8 * cm, 8 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elementos.append(t)

    elementos.append(Spacer(1, 1.5 * cm))

    # Testemunhas
    testemunhas = [
        [
            Paragraph("___________________________________<br/>Testemunha 1",
                      estilos["assinatura"]),
            Paragraph("___________________________________<br/>Testemunha 2",
                      estilos["assinatura"]),
        ],
    ]
    t2 = Table(testemunhas, colWidths=[8 * cm, 8 * cm])
    t2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elementos.append(t2)

    return elementos


# ============================================================
# 1. PROPOSTA DE ACORDO
# ============================================================

def gerar_pdf_proposta_acordo(
    cliente_nome: str,
    cliente_cnpj: Optional[str],
    cliente_endereco: Optional[str],
    cliente_bairro: Optional[str],
    cliente_cidade: Optional[str],
    cliente_uf: Optional[str],
    parcelas: List,
) -> bytes:
    """
    Proposta de Acordo — gerada na Calculadora, antes do acordo virar real.
    Não tem títulos originais, só as parcelas propostas.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1 * cm, bottomMargin=1.5 * cm,
    )
    estilos = _estilos()
    el = []

    el.extend(_cabecalho_logo(estilos))
    el.append(Paragraph("PROPOSTA DE ACORDO", estilos["titulo"]))
    el.append(Spacer(1, 0.5 * cm))

    end_devedor = (
        f"{cliente_endereco or ''}, Bairro {cliente_bairro or ''}, "
        f"na cidade de {cliente_cidade or ''}/{cliente_uf or ''}"
    ).strip(", ").strip()

    end_credor = (
        f"{LLE_FERRAGENS['endereco']}, Bairro {LLE_FERRAGENS['bairro']}, "
        f"na cidade de {LLE_FERRAGENS['cidade']}/{LLE_FERRAGENS['uf']}"
    )

    el.append(Paragraph(
        f"Pela presente, a empresa <b>{CREDOR_GRUPO_LLE['nome']}</b>, pessoa jurídica, "
        f"inscrita no CNPJ sob n° {CREDOR_GRUPO_LLE['cnpj']} estabelecido a "
        f"{end_credor}, do outro lado devedor <b>{cliente_nome}</b>, "
        f"inscrito no CPF/CNPJ sob n° {cliente_cnpj or '—'} "
        f"estabelecido a {end_devedor}, vem por meio deste propor um acordo de "
        f"pagamento dos débitos constantes em aberto:",
        estilos["paragrafo"],
    ))
    el.append(Spacer(1, 0.3 * cm))

    # Tabela de parcelas
    el.append(_tabela_parcelas(parcelas, len(parcelas), estilos))
    el.append(Spacer(1, 0.5 * cm))

    total = sum(p.valor_original for p in parcelas)
    el.append(Paragraph(
        f"<b>Total: {formatar_brl(total)}</b> - {_valor_extenso(total)}",
        estilos["paragrafo"],
    ))
    el.append(Spacer(1, 0.5 * cm))

    el.append(Paragraph(
        "A liberação dos órgãos de restrição de crédito, bem como a liberação "
        "das cartas de anuências e cheques somente ocorrerão após a quitação "
        "total do débito.",
        estilos["paragrafo"],
    ))
    el.append(Paragraph(
        "O não pagamento implicará na correção de juros, multas e demais "
        "encargos sobre o valor total do débito.",
        estilos["paragrafo"],
    ))
    el.append(Paragraph(
        "<b>A proposta é meramente demonstrativa, não formalizando o acordo.</b>",
        estilos["paragrafo"],
    ))

    el.append(_rodape_lle(estilos))

    doc.build(el)
    return buf.getvalue()


# ============================================================
# 2. TERMO DE ACORDO
# ============================================================

def gerar_pdf_termo_acordo(
    cliente_nome: str,
    cliente_cnpj: Optional[str],
    cliente_endereco: Optional[str],
    cliente_bairro: Optional[str],
    cliente_cidade: Optional[str],
    cliente_uf: Optional[str],
    boletos: List,
    parcelas: List,
    tipo_cobranca: str = "BOLETO",
) -> bytes:
    """Termo de Acordo — gerado no detalhe do acordo, após confirmação."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1 * cm, bottomMargin=1.5 * cm,
    )
    estilos = _estilos()
    el = []

    el.extend(_cabecalho_logo(estilos))
    el.append(Paragraph("TERMO DE ACORDO", estilos["titulo"]))
    el.append(Spacer(1, 0.5 * cm))

    end_devedor = (
        f"{cliente_endereco or ''}, Bairro {cliente_bairro or ''}, "
        f"na cidade de {cliente_cidade or ''}/{cliente_uf or ''}"
    ).strip(", ").strip()

    end_credor = (
        f"{LLE_FERRAGENS['endereco']}, Bairro {LLE_FERRAGENS['bairro']}, "
        f"na cidade de {LLE_FERRAGENS['cidade']}/{LLE_FERRAGENS['uf']}"
    )

    el.append(Paragraph(
        f"Pela presente, a empresa <b>{CREDOR_GRUPO_LLE['nome']}</b>, pessoa jurídica, "
        f"inscrita no CNPJ sob n° {CREDOR_GRUPO_LLE['cnpj']} estabelecido a "
        f"{end_credor}, do outro lado devedor <b>{cliente_nome}</b>, "
        f"inscrito no CPF/CNPJ sob n° {cliente_cnpj or '—'} "
        f"estabelecido a {end_devedor}, tendo em vista o acordo firmado, "
        f"através de pagamentos parciais, de seu débito descrito:",
        estilos["paragrafo"],
    ))
    el.append(Spacer(1, 0.3 * cm))

    # Tabela de títulos originais
    el.append(_tabela_titulos(boletos, estilos))
    el.append(Spacer(1, 0.5 * cm))

    # Total
    total = sum(p.valor_original for p in parcelas)
    el.append(Paragraph(
        f"A devedora compromete-se resgatar seu débito em {len(parcelas)} "
        f"parcela(s), totalizando <b>{formatar_brl(total)}</b> "
        f"({_valor_extenso(total)}) conforme tabela abaixo, "
        f"por via de <b>{tipo_cobranca}</b>.",
        estilos["paragrafo"],
    ))

    # Tabela de parcelas
    el.append(_tabela_parcelas(parcelas, len(parcelas), estilos))
    el.append(Spacer(1, 0.5 * cm))

    el.append(Paragraph(
        "<b>Cláusula única.</b> O inadimplemento de qualquer parcela implicará "
        "o vencimento antecipado de todas as parcelas vincendas, acrescidas de "
        "atualização de juros, multa e demais encargos sobre o valor total do débito.",
        estilos["paragrafo"],
    ))

    el.append(Paragraph(
        "E, por estarem justas e contratadas, a DEVEDORA declara aceitar as "
        "disposições estabelecidas neste instrumento, assinando-o em duas vias "
        "de igual teor e forma na presença de duas testemunhas para que surta "
        "seus jurídicos e legais efeitos.",
        estilos["paragrafo"],
    ))

    el.extend(_bloco_assinaturas(
        cliente_nome, cliente_cnpj or "—",
        f"Rio de Janeiro, {formatar_data(date.today())}.",
        estilos,
    ))

    el.append(_rodape_lle(estilos))

    doc.build(el)
    return buf.getvalue()


# ============================================================
# 3. TERMO DE CONFISSÃO DE DÍVIDA (Modelo 1)
# ============================================================

def gerar_pdf_termo_confissao(
    cliente_nome: str,
    cliente_cnpj: Optional[str],
    cliente_endereco: Optional[str],
    cliente_bairro: Optional[str],
    cliente_cidade: Optional[str],
    cliente_uf: Optional[str],
    boletos: List,
    parcelas: List,
    tipo_cobranca: str = "Boleto Bancário",
) -> bytes:
    """
    Termo de Confissão de Dívida — Modelo 1 (4 págs).
    Cláusula penal de 20%, devedor solidário, cláusulas detalhadas.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1 * cm, bottomMargin=1.5 * cm,
    )
    estilos = _estilos()
    el = []

    el.extend(_cabecalho_logo(estilos))
    el.append(Paragraph("TERMO DE CONFISSÃO DE DÍVIDA", estilos["titulo"]))
    el.append(Spacer(1, 0.5 * cm))

    end_credor_completo = (
        f"{LLE_FERRAGENS['endereco']}, Bairro {LLE_FERRAGENS['bairro']}, "
        f"Município de {LLE_FERRAGENS['cidade']}/{LLE_FERRAGENS['uf']}, "
        f"CEP: {LLE_FERRAGENS['cep']}"
    )
    end_devedor_completo = (
        f"{cliente_endereco or '—'}, Bairro {cliente_bairro or '—'}, "
        f"Município de {cliente_cidade or '—'}/{cliente_uf or '—'}"
    )

    # Parágrafo introdutório - CREDOR
    el.append(Paragraph(
        f"<b>CREDOR(A):</b> {CREDOR_GRUPO_LLE['nome']}, pessoa jurídica de direito "
        f"privado, inscrita no CNPJ n° {CREDOR_GRUPO_LLE['cnpj']}, neste ato "
        f"representado pela empresa <b>{LLE_FERRAGENS['nome']}</b>, pessoa jurídica "
        f"de direito privado, inscrita no CNPJ sob o n.º {LLE_FERRAGENS['cnpj']}, "
        f"localizada no endereço: {end_credor_completo}.",
        estilos["paragrafo"],
    ))

    # DEVEDOR
    el.append(Paragraph(
        f"<b>DEVEDOR:</b> {cliente_nome}, CPF/CNPJ n° {cliente_cnpj or '—'}, "
        f"residente e domiciliado no endereço: {end_devedor_completo}.",
        estilos["paragrafo"],
    ))

    el.append(Paragraph(
        "AJUSTAM ENTRE SI, O PRESENTE CONTRATO DE CONFISSÃO DE DÍVIDA, QUE SE "
        "REGERÁ PELAS CLÁUSULAS SEGUINTES E PELAS CONDIÇÕES DESCRITAS NO PRESENTE.",
        estilos["paragrafo"],
    ))

    # Cálculo dos totais
    total_original = sum(b.principal for b in boletos)
    total_acordo = sum(p.valor_original for p in parcelas)

    # Cláusula Primeira
    el.append(Paragraph(
        f"<b>Cláusula Primeira</b> – Através do presente, reconhece expressamente "
        f"o DEVEDOR(A) que possui uma dívida a ser paga ao CREDOR(A), "
        f"consubstanciada no montante total de <b>{formatar_brl(total_original)}</b> "
        f"({_valor_extenso(total_original)}), sendo o acordo entre as partes "
        f"citadas acima, no valor atualizado de <b>{formatar_brl(total_acordo)}</b> "
        f"({_valor_extenso(total_acordo)}), e que quitará este valor conforme as "
        f"condições previstas neste contrato.",
        estilos["paragrafo"],
    ))

    el.append(Paragraph(
        "<b>Parágrafo primeiro</b> – O crédito que o CREDOR(A) possui contra o "
        "DEVEDOR(A) é originário da compra conforme as duplicatas abaixo mencionadas:",
        estilos["paragrafo"],
    ))

    # Tabela de títulos originais
    el.append(_tabela_titulos(boletos, estilos))
    el.append(Spacer(1, 0.4 * cm))

    el.append(Paragraph(
        f"<b>Parágrafo segundo</b> – Por outro lado, o CREDOR(A) compromete-se a "
        f"dar baixa no que diz respeito exclusivamente ao débito ora confessado, "
        f"excluindo o nome da {cliente_nome} dos cadastros de restrição ao crédito.",
        estilos["paragrafo"],
    ))

    # Cláusula Segunda
    el.append(Paragraph(
        f"<b>Cláusula Segunda</b> – Por este instrumento e na melhor forma de "
        f"direito, o DEVEDOR(A) reconhece e se confessa expressamente devedor da "
        f"credora {CREDOR_GRUPO_LLE['nome']} da importância constante da Cláusula "
        f"Primeira, obrigando-se a pagá-la no prazo e sob as condições neste ato "
        f"adiante estabelecidas.",
        estilos["paragrafo"],
    ))

    # DO CRÉDITO
    el.append(Paragraph("DO CRÉDITO", estilos["clausula"]))

    # Cláusula Terceira
    el.append(Paragraph(
        f"<b>Cláusula Terceira</b> – O DEVEDOR(A) neste ato, declara que o débito "
        f"total será pago, inteiramente nos termos do presente instrumento, "
        f"obrigando-se a efetuar o pagamento em <b>{len(parcelas)}</b> parcela(s), "
        f"através de {tipo_cobranca}, conforme descrito a seguir:",
        estilos["paragrafo"],
    ))

    el.append(_tabela_parcelas(parcelas, len(parcelas), estilos))
    el.append(Spacer(1, 0.4 * cm))

    # Cláusula Quarta - cláusula penal 20%
    el.append(Paragraph(
        "<b>Cláusula Quarta</b> – As partes convencionam que o não pagamento de "
        "qualquer das parcelas assumidas no presente instrumento importará no "
        "pagamento de cláusula penal na ordem de 20% (vinte por cento) sobre o "
        "valor do saldo devedor, conforme previsto no art. 408 e seguintes do "
        "Código Civil, sem prejuízo da atualização monetária, incidência de 1% "
        "(um por cento) ao mês e honorários advocatícios de 20% (vinte por cento).",
        estilos["paragrafo"],
    ))

    el.append(Paragraph(
        "<b>Parágrafo Único:</b> Em caso de inadimplemento do presente contrato "
        "o CREDOR(A) poderá, ainda, efetuar a inscrição do nome do DEVEDOR(A) e "
        "também do DEVEDOR SOLIDÁRIO(A) em órgão de proteção ao crédito, no "
        "montante da dívida vencida.",
        estilos["paragrafo"],
    ))

    # Cláusula Quinta - devedor solidário
    el.append(Paragraph(
        "<b>Cláusula Quinta</b> - Assina, a presente, o DEVEDOR(A) SOLIDÁRIO(A), "
        "o qual, nessa qualidade, responsabiliza-se solidariamente, com o "
        "DEVEDOR(A), pelo cumprimento de todas as obrigações, principais e "
        "acessórias, que o mesmo ora assumirá, aceitando, expressamente, os "
        "termos e condições deste instrumento de confissão de dívida.",
        estilos["paragrafo"],
    ))

    # CONDIÇÕES GERAIS
    el.append(Paragraph("CONDIÇÕES GERAIS", estilos["clausula"]))

    el.append(Paragraph(
        "<b>Cláusula Sexta</b> – O presente contrato passa a vigorar entre as "
        "partes a partir da assinatura do mesmo.",
        estilos["paragrafo"],
    ))

    el.append(Paragraph(
        "<b>Cláusula Sétima</b> – O presente contrato é realizado em caráter "
        "irrevogável, irretratável e intransferível, o qual obrigam as partes a "
        "cumpri-lo, a qualquer título, bem como seus herdeiros e sucessores.",
        estilos["paragrafo"],
    ))

    # Assinaturas
    el.extend(_bloco_assinaturas(
        cliente_nome, cliente_cnpj or "—",
        f"Rio de Janeiro, {formatar_data(date.today())}.",
        estilos,
    ))

    el.append(_rodape_lle(estilos))

    doc.build(el)
    return buf.getvalue()


# ============================================================
# 4. CARTA DE QUITAÇÃO DE DÉBITOS
# ============================================================

def gerar_pdf_carta_quitacao(
    cliente_nome: str,
    cliente_cnpj: Optional[str],
    boletos: List,
    nome_signatario: Optional[str] = None,
) -> bytes:
    """
    Carta de Quitação — gerada quando o acordo está QUITADO.
    A empresa credora é detectada dos títulos:
      - Empresa 1 → PISA DISTRIBUIDORA
      - Empresa 2 → FERRAGENS KING OURO
      - Se misturado → lista as duas
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1 * cm, bottomMargin=1.5 * cm,
    )
    estilos = _estilos()
    el = []

    el.extend(_cabecalho_logo(estilos))

    el.append(Spacer(1, 1.5 * cm))
    el.append(Paragraph("DECLARAÇÃO DE QUITAÇÃO DE DÉBITOS",
                        estilos["titulo"]))
    el.append(Spacer(1, 1 * cm))

    # Detecta empresas dos títulos
    empresas = _detectar_empresas_credoras(boletos)

    # Texto principal
    if len(empresas) == 1:
        emp = empresas[0]
        texto_empresas = (
            f"A empresa <b>{emp['nome']}</b>, CNPJ <b>{emp['cnpj']}</b>"
        )
    else:
        nomes = " e ".join(f"<b>{e['nome']}</b> (CNPJ {e['cnpj']})" for e in empresas)
        texto_empresas = f"As empresas {nomes}"

    el.append(Paragraph(
        f"{texto_empresas} certifica que o cliente <b>{cliente_nome}</b>"
        f"{', CNPJ <b>' + cliente_cnpj + '</b>' if cliente_cnpj else ''} possui "
        f"todos os débitos quitados, não havendo débitos a vencer.",
        estilos["paragrafo"],
    ))

    el.append(Spacer(1, 2.5 * cm))

    # Bloco de assinatura — Erick (13/05/2026): tirou nome do cobrador.
    # Agora aparece só "Atenciosamente," + as empresas credoras.
    el.append(Paragraph("Atenciosamente,", estilos["assinatura"]))
    el.append(Spacer(1, 0.5 * cm))

    # Mostra todas as empresas no rodapé do bloco
    for emp in empresas:
        el.append(Paragraph(f"<b>{emp['nome']}</b>", estilos["assinatura"]))
        el.append(Paragraph(f"CNPJ: {emp['cnpj']}", estilos["assinatura"]))

    el.append(Spacer(1, 1.5 * cm))
    el.append(Paragraph(
        f"Rio de Janeiro, {formatar_data(date.today())}",
        estilos["assinatura"],
    ))

    el.append(_rodape_lle(estilos))

    doc.build(el)
    return buf.getvalue()
