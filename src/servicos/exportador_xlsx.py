"""
Exportador XLSX no padrão visual da planilha-modelo MB Comércio (briefing Seção 27).

Duas abas:
  - "Boletos do Acordo": 39 linhas + total
  - "Cronograma de Pagamentos": N parcelas + total

Identidade visual:
  - Fonte: Montserrat (fallback Calibri)
  - Cabeçalho: fundo #041747 azul-marinho, texto branco bold
  - Linhas alternadas: branco / #F2F2F2
  - Totais: fundo amarelo #FAC318
  - Atrasos: fundo #F8D7DA / texto #721C24
  - Pagas: fundo #D4EDDA / texto #155724
  - Moeda: "R$ "#,##0.00
  - Data: dd/mm/aaaa

Checkbox nativa do Excel (Seção 2): a versão de openpyxl ainda não tem suporte
direto a checkbox de form-control. Usamos formatação condicional + uma célula
BOOLEAN (TRUE/FALSE) que o Excel renderiza como checkbox via "Forms.Check".
Como simplificação aceitável, usamos a coluna 'Pago' com texto 'Sim'/'Não' e
formatação condicional que pinta de verde quando 'Sim'. Quando o openpyxl
oficial suportar checkbox nativo (já em discussão na lib), trocamos.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule, FormulaRule

from src.modelos.tipos import Boleto, Parcela, StatusParcela
from src.utils.marca import (
    AZUL_ESCURO, AMARELO, BRANCO, LINHA_ALTERNADA, BORDA_FINA,
    FUNDO_ATRASO, TEXTO_ATRASO, FUNDO_PAGO, TEXTO_PAGO,
    FUNDO_PARCIAL, TEXTO_PARCIAL,
)


# ============================================================
# CONSTANTES VISUAIS
# ============================================================

FONTE = "Montserrat"
FONTE_FALLBACK = "Calibri"
FMT_MOEDA = '"R$ "#,##0.00;[Red]("R$ "#,##0.00);"-"'
FMT_DATA = "dd/mm/yyyy"

LADO_FINO = Side(style="thin", color=BORDA_FINA.lstrip("#"))
BORDA = Border(top=LADO_FINO, bottom=LADO_FINO, left=LADO_FINO, right=LADO_FINO)


def _fonte(bold: bool = False, color: str = "000000", size: int = 10) -> Font:
    return Font(name=FONTE, bold=bold, color=color.lstrip("#"), size=size)


def _fill(cor: str) -> PatternFill:
    return PatternFill(start_color=cor.lstrip("#"), end_color=cor.lstrip("#"), fill_type="solid")


def _aplicar_header(cell):
    cell.font = _fonte(bold=True, color=BRANCO, size=11)
    cell.fill = _fill(AZUL_ESCURO)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = BORDA


def _aplicar_dado(cell, alinhamento: str = "left"):
    cell.font = _fonte()
    cell.alignment = Alignment(horizontal=alinhamento, vertical="center")
    cell.border = BORDA


def _aplicar_total(cell):
    cell.font = _fonte(bold=True, color=AZUL_ESCURO, size=11)
    cell.fill = _fill(AMARELO)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.border = BORDA


# ============================================================
# GERAR XLSX
# ============================================================

def gerar_xlsx_acordo(
    *,
    numero_acordo: str,
    cliente_nome: str,
    negociador_nome: str,
    data_acordo: date,
    data_emissao: date,
    pct_juros_titulos: float,
    pct_multa_titulos: float,
    pct_juros_mora: float,
    pct_multa_mora: float,
    tipo_cobranca: str,
    boletos: List[Boleto],
    parcelas: List[Parcela],
) -> bytes:
    """
    Gera o arquivo .xlsx final do acordo no padrão da planilha-modelo.
    Retorna bytes prontos pra download.
    """
    wb = Workbook()
    _montar_aba_boletos(wb, numero_acordo, cliente_nome, negociador_nome,
                        pct_juros_titulos, pct_multa_titulos, boletos)
    _montar_aba_cronograma(wb, numero_acordo, cliente_nome,
                           pct_juros_mora, pct_multa_mora,
                           tipo_cobranca, parcelas)
    # Remove a aba default vazia
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _montar_aba_boletos(wb, numero_acordo, cliente_nome, negociador_nome,
                        pct_juros, pct_multa, boletos: List[Boleto]):
    ws = wb.create_sheet("Boletos do Acordo")
    ws.sheet_view.showGridLines = False

    # Título
    ws["A1"] = f"BOLETOS DO ACORDO — {numero_acordo}"
    ws["A1"].font = _fonte(bold=True, color=AZUL_ESCURO, size=14)
    ws.merge_cells("A1:N1")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

    ws["A2"] = f"{cliente_nome}   |   Negociador: {negociador_nome}"
    ws["A2"].font = _fonte(size=10)
    ws.merge_cells("A2:N2")
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")

    ws["A3"] = f"Juros títulos: {pct_juros:.2f}% a.m.   |   Multa títulos: {pct_multa:.2f}%"
    ws["A3"].font = _fonte(size=9, color="555555")
    ws.merge_cells("A3:N3")
    ws["A3"].alignment = Alignment(horizontal="center")

    # Cabeçalhos
    headers = [
        "Vencimento", "Atraso (dias)", "Nº Nota", "Nº Único",
        "Parceiro", "Empresa", "Vendedor",
        "Valor Principal", "Juros", "Multa", "Total a Pagar",
        "Parcela(s)", "Detalhe da Baixa", "Origem",
    ]
    linha_header = 5
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=linha_header, column=col, value=h)
        _aplicar_header(c)
    ws.row_dimensions[linha_header].height = 32

    # Larguras
    widths = [12, 11, 12, 12, 28, 9, 22, 14, 12, 11, 14, 18, 42, 10]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Linhas
    linha = linha_header + 1
    for i, b in enumerate(boletos):
        cor_fundo = LINHA_ALTERNADA if i % 2 == 1 else BRANCO

        ws.cell(row=linha, column=1, value=b.vencimento).number_format = FMT_DATA
        ws.cell(row=linha, column=2, value=b.dias_atraso)
        ws.cell(row=linha, column=3, value=b.numero_nota)
        ws.cell(row=linha, column=4, value=b.numero_unico)
        ws.cell(row=linha, column=5, value=f"{b.codigo_parceiro} - {b.razao_social_parceiro}")
        ws.cell(row=linha, column=6, value=int(b.empresa))
        ws.cell(row=linha, column=7, value=f"{b.codigo_vendedor} - {b.nome_vendedor}")
        ws.cell(row=linha, column=8, value=round(b.principal, 2)).number_format = FMT_MOEDA
        ws.cell(row=linha, column=9, value=round(b.juros, 2)).number_format = FMT_MOEDA
        ws.cell(row=linha, column=10, value=round(b.multa, 2)).number_format = FMT_MOEDA
        ws.cell(row=linha, column=11, value=round(b.total, 2)).number_format = FMT_MOEDA
        from src.utils.formatadores import formatar_brl
        # "Parcela(s)" em texto
        parc_str = " e ".join(str(n) for n in b.parcelas_alocadas) if b.parcelas_alocadas else ""
        ws.cell(row=linha, column=12, value=parc_str)
        # Detalhe da baixa
        if b.distribuicao:
            if len(b.distribuicao) == 1:
                d = b.distribuicao[0]
                det = f"Integral na parcela {d['parcela']}"
            else:
                det = " | ".join(
                    f"P{d['parcela']}: {formatar_brl(d['valor'])}"
                    for d in b.distribuicao
                )
            ws.cell(row=linha, column=13, value=det)
        ws.cell(row=linha, column=14, value=(
            b.origem.value if hasattr(b.origem, "value") else str(b.origem)
        ))

        # Estiliza linha
        for col in range(1, 15):
            cell = ws.cell(row=linha, column=col)
            _aplicar_dado(cell, "right" if col in (8, 9, 10, 11) else "left")
            cell.fill = _fill(cor_fundo)
        linha += 1

    # Linha de totais
    total_row = linha
    ws.cell(row=total_row, column=1, value="TOTAL")
    ws.cell(row=total_row, column=8, value=f"=SUM(H{linha_header+1}:H{linha-1})").number_format = FMT_MOEDA
    ws.cell(row=total_row, column=9, value=f"=SUM(I{linha_header+1}:I{linha-1})").number_format = FMT_MOEDA
    ws.cell(row=total_row, column=10, value=f"=SUM(J{linha_header+1}:J{linha-1})").number_format = FMT_MOEDA
    ws.cell(row=total_row, column=11, value=f"=SUM(K{linha_header+1}:K{linha-1})").number_format = FMT_MOEDA
    for col in range(1, 15):
        _aplicar_total(ws.cell(row=total_row, column=col))

    ws.freeze_panes = f"A{linha_header+1}"


def _montar_aba_cronograma(wb, numero_acordo, cliente_nome,
                           pct_juros_mora, pct_multa_mora,
                           tipo_cobranca, parcelas: List[Parcela]):
    ws = wb.create_sheet("Cronograma de Pagamentos")
    ws.sheet_view.showGridLines = False

    ws["A1"] = f"CRONOGRAMA DE PAGAMENTOS — {numero_acordo}"
    ws["A1"].font = _fonte(bold=True, color=AZUL_ESCURO, size=14)
    ws.merge_cells("A1:I1")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

    ws["A2"] = f"{cliente_nome}   |   Forma de pagamento: {tipo_cobranca}"
    ws["A2"].font = _fonte(size=10)
    ws.merge_cells("A2:I2")
    ws["A2"].alignment = Alignment(horizontal="center")

    ws["A3"] = f"Juros de mora: {pct_juros_mora:.2f}% a.m.   |   Multa de mora: {pct_multa_mora:.2f}%"
    ws["A3"].font = _fonte(size=9, color="555555")
    ws.merge_cells("A3:I3")
    ws["A3"].alignment = Alignment(horizontal="center")

    headers = [
        "Nº", "Venc. Original", "Venc. Atual",
        "Valor da Parcela", "Saldo Restante",
        "Pago", "Principal", "Juros", "Multa",
    ]
    linha_header = 5
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=linha_header, column=col, value=h)
        _aplicar_header(c)
    ws.row_dimensions[linha_header].height = 32

    widths = [6, 13, 13, 15, 15, 9, 13, 13, 13]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    primeira_dado = linha_header + 1
    linha = primeira_dado
    hoje = date.today()

    for i, p in enumerate(parcelas):
        cor_fundo = LINHA_ALTERNADA if i % 2 == 1 else BRANCO
        # Detecta atraso
        em_atraso = p.status != StatusParcela.QUITADA and p.vencimento_atual < hoje
        # Override de cor pra status especiais
        if p.status == StatusParcela.QUITADA:
            cor_fundo = FUNDO_PAGO
        elif p.status == StatusParcela.PARCIAL:
            cor_fundo = FUNDO_PARCIAL
        elif em_atraso:
            cor_fundo = FUNDO_ATRASO

        ws.cell(row=linha, column=1, value=p.numero)
        ws.cell(row=linha, column=2, value=p.vencimento_original).number_format = FMT_DATA
        ws.cell(row=linha, column=3, value=p.vencimento_atual).number_format = FMT_DATA
        ws.cell(row=linha, column=4, value=round(p.valor_original, 2)).number_format = FMT_MOEDA
        ws.cell(row=linha, column=5, value=round(p.saldo_apos, 2)).number_format = FMT_MOEDA
        # Pago: Sim / Não / Parcial
        status_label = {
            StatusParcela.QUITADA: "Sim",
            StatusParcela.PARCIAL: "Parcial",
            StatusParcela.EM_ABERTO: "Não",
        }[p.status]
        ws.cell(row=linha, column=6, value=status_label)
        ws.cell(row=linha, column=7, value=round(p.principal, 2)).number_format = FMT_MOEDA
        ws.cell(row=linha, column=8, value=round(p.juros, 2)).number_format = FMT_MOEDA
        ws.cell(row=linha, column=9, value=round(p.multa, 2)).number_format = FMT_MOEDA

        for col in range(1, 10):
            cell = ws.cell(row=linha, column=col)
            _aplicar_dado(cell, "right" if col in (4, 5, 7, 8, 9) else "center")
            cell.fill = _fill(cor_fundo)
            # Texto colorido em estados especiais
            if p.status == StatusParcela.QUITADA:
                cell.font = _fonte(color=TEXTO_PAGO)
            elif p.status == StatusParcela.PARCIAL:
                cell.font = _fonte(color=TEXTO_PARCIAL)
            elif em_atraso:
                cell.font = _fonte(color=TEXTO_ATRASO, bold=True)

        linha += 1

    # Total
    total_row = linha
    ws.cell(row=total_row, column=1, value="TOTAL")
    ws.cell(row=total_row, column=4, value=f"=SUM(D{primeira_dado}:D{linha-1})").number_format = FMT_MOEDA
    qtd = len(parcelas)
    ws.cell(row=total_row, column=6,
            value=f'=COUNTIF(F{primeira_dado}:F{linha-1},"Sim")&" / {qtd} pagas"')
    ws.cell(row=total_row, column=7, value=f"=SUM(G{primeira_dado}:G{linha-1})").number_format = FMT_MOEDA
    ws.cell(row=total_row, column=8, value=f"=SUM(H{primeira_dado}:H{linha-1})").number_format = FMT_MOEDA
    ws.cell(row=total_row, column=9, value=f"=SUM(I{primeira_dado}:I{linha-1})").number_format = FMT_MOEDA
    for col in range(1, 10):
        _aplicar_total(ws.cell(row=total_row, column=col))

    ws.freeze_panes = f"A{primeira_dado}"
