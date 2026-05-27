"""
Motor de cálculo de juros e multa.

CASO 1 — JUROS DOS TÍTULOS (briefing Seção 13)
  Calculado UMA VEZ na criação do acordo. Embutido no Total via FIFO.
  - Título vencido (vencimento < data_acordo):
      juros = principal × (%juros_mês / 30) × dias_corridos(vencimento → data_parcela_que_quita)
  - Título a vencer (vencimento >= data_acordo):
      juros = principal × (%juros_mês / 30) × dias_corridos(data_acordo → data_parcela_que_quita)
  - Multa:
      Vencido: aplica imediatamente sobre o principal
      A vencer: aplica SOMENTE SE a data da parcela for posterior ao vencimento original

CASO 2 — MORA DE PARCELA ATRASADA (briefing Seção 18a + P3 + P4.1)
  Calculado SE/QUANDO uma parcela atrasa, sobre o SALDO RESTANTE da parcela.
  - juros_mora = saldo × (%juros_mora_mês / 30) × dias_atraso
  - multa_mora = saldo × %multa_mora
  Os percentuais são INDEPENDENTES dos do CASO 1.

A dependência circular do CASO 1 (juros do título depende da data da parcela
que o quita, que depende do total do título que depende dos juros) é resolvida
por REFINAMENTO ITERATIVO no módulo fifo.py.
"""
from __future__ import annotations

from datetime import date

from src.modelos.tipos import Boleto, Parcela


# ============================================================
# CASO 1 — TÍTULOS
# ============================================================

def calcular_juros_titulo(
    principal: float,
    dias_corridos: int,
    pct_juros_mes: float,
) -> float:
    """
    Juros pro-rata diário (taxa mensal ÷ 30).
    Briefing Seção 13(a): "Principal × %Juros_mes/30 × dias_corridos"
    """
    if dias_corridos <= 0 or principal <= 0:
        return 0.0
    return principal * (pct_juros_mes / 100) / 30 * dias_corridos


def calcular_multa_titulo_se_aplicavel(
    principal: float,
    pct_multa: float,
    vencimento: date,
    data_acordo: date,
    data_fim_juros: date,
) -> float:
    """
    Multa fixa sobre o principal, com regra de aplicabilidade do briefing Seção 13(b):
    - Vencido (vencimento < data_acordo): aplica.
    - A vencer (vencimento >= data_acordo): aplica SOMENTE SE data_fim_juros > vencimento.
    """
    if principal <= 0 or pct_multa <= 0:
        return 0.0
    if vencimento < data_acordo:
        # Já vencido na data do acordo: aplica multa direto
        return principal * (pct_multa / 100)
    # A vencer: só aplica se a quitação for posterior ao vencimento
    if data_fim_juros > vencimento:
        return principal * (pct_multa / 100)
    return 0.0


def calcular_boleto_caso1(
    boleto: Boleto,
    data_acordo: date,
    pct_juros_mes: float,
    pct_multa: float,
    data_quitacao: date,
) -> None:
    """
    Calcula juros, multa e total de UM título usando a regra do CASO 1.
    Mutaciona o boleto in-place.

    data_quitacao é a data da ÚLTIMA parcela que quita este boleto. Para boletos
    parcelados em múltiplas parcelas, é a data da última delas.
    """
    boleto.fim_juros = data_quitacao

    if boleto.vencimento < data_acordo:
        # Vencido: conta do vencimento até a quitação
        dias = (data_quitacao - boleto.vencimento).days
    else:
        # A vencer: conta da data do acordo até a quitação
        dias = (data_quitacao - data_acordo).days

    boleto.dias_atraso = max(0, dias)
    boleto.juros = round(
        calcular_juros_titulo(boleto.principal, boleto.dias_atraso, pct_juros_mes),
        6,
    )
    boleto.multa = round(
        calcular_multa_titulo_se_aplicavel(
            boleto.principal,
            pct_multa,
            boleto.vencimento,
            data_acordo,
            data_quitacao,
        ),
        6,
    )
    boleto.total = round(boleto.principal + boleto.juros + boleto.multa, 6)


# ============================================================
# CASO 2 — MORA DE PARCELA ATRASADA
# ============================================================

def calcular_mora_parcela(
    saldo_restante: float,
    dias_atraso: int,
    pct_juros_mora_mes: float,
    pct_multa_mora: float,
) -> tuple[float, float]:
    """
    Calcula juros de mora e multa de mora de uma parcela atrasada.
    Briefing Seção 18a + decisão P3 (mora sobre valor TOTAL) + P4.1 (sobre saldo restante).

    Retorna: (juros_mora, multa_mora)

    NOTA SOBRE P3 vs P4.1: o valor de entrada `saldo_restante` é o saldo após
    eventuais pagamentos parciais (P4.1). Se a parcela está intacta, saldo == valor
    total da parcela (P3).
    """
    if saldo_restante <= 0 or dias_atraso <= 0:
        return 0.0, 0.0

    juros_mora = saldo_restante * (pct_juros_mora_mes / 100) / 30 * dias_atraso
    multa_mora = saldo_restante * (pct_multa_mora / 100)
    return round(juros_mora, 2), round(multa_mora, 2)


def calcular_valor_atualizado_parcela(
    parcela: Parcela,
    hoje: date,
    pct_juros_mora_mes: float,
    pct_multa_mora: float,
) -> tuple[float, float, float, int]:
    """
    Calcula o valor atualizado de uma parcela considerando atraso + pagamentos parciais.

    Retorna: (valor_atualizado, juros_mora, multa_mora, dias_atraso)

    Se a parcela está em dia ou já quitada, retorna o saldo restante sem acréscimos.
    """
    saldo = parcela.valor_restante
    if saldo <= 0:
        return 0.0, 0.0, 0.0, 0

    dias_atraso = max(0, (hoje - parcela.vencimento_atual).days)
    juros_mora, multa_mora = calcular_mora_parcela(
        saldo, dias_atraso, pct_juros_mora_mes, pct_multa_mora
    )
    valor_atualizado = round(saldo + juros_mora + multa_mora, 2)
    return valor_atualizado, juros_mora, multa_mora, dias_atraso
