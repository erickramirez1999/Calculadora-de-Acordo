"""
Calendário de dias úteis e geração do cronograma de parcelas.

Regras (briefing Seção 14):
- A CONTAGEM do intervalo é sempre em dias CORRIDOS.
- A DATA FINAL, se cair em sábado ou domingo, vai pra próxima segunda.
- Feriados nacionais NÃO são considerados nesta versão.

Para periodicidade DIÁRIA (personalizada com intervalo=1) ou outras periodicidades
curtas onde múltiplas datas-base podem cair na mesma segunda após o pulo de fim de semana,
o cálculo é encadeado: a próxima data parte da ANTERIOR já ajustada, evitando empilhamento.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

from src.modelos.tipos import Periodicidade


# ============================================================
# DIAS ÚTEIS
# ============================================================

def eh_dia_util(d: date) -> bool:
    """Considera apenas segunda(0)..sexta(4) como dia útil. Feriados ignorados."""
    return d.weekday() < 5


def proximo_dia_util(d: date) -> date:
    """Se d é sáb/dom, empurra para a próxima segunda. Senão, devolve d."""
    while not eh_dia_util(d):
        d += timedelta(days=1)
    return d


# ============================================================
# AVANÇO POR PERIODICIDADE
# ============================================================

def adicionar_meses(d: date, n: int) -> date:
    """
    Soma n meses preservando o dia (com fallback pro último dia do mês).
    Ex: 31/01 + 1 mês = 28/02 (ou 29/02 em ano bissexto).
    """
    if n == 0:
        return d
    novo_mes_zero_based = d.month - 1 + n
    novo_ano = d.year + novo_mes_zero_based // 12
    novo_mes = novo_mes_zero_based % 12 + 1
    # Último dia do mês destino
    if novo_mes == 12:
        ultimo_dia = (date(novo_ano + 1, 1, 1) - timedelta(days=1)).day
    else:
        ultimo_dia = (date(novo_ano, novo_mes + 1, 1) - timedelta(days=1)).day
    return date(novo_ano, novo_mes, min(d.day, ultimo_dia))


def avancar_uma_unidade(
    base: date,
    periodicidade: Periodicidade,
    intervalo_personalizado_dias: int = 1,
) -> date:
    """
    Avança UMA unidade da periodicidade a partir de `base`. Sem ajuste de dia útil.
    O ajuste é feito por gerar_datas_parcelas() ao final.
    """
    if periodicidade == Periodicidade.MENSAL:
        return adicionar_meses(base, 1)
    if periodicidade == Periodicidade.QUINZENAL:
        return base + timedelta(days=15)
    if periodicidade == Periodicidade.SEMANAL:
        return base + timedelta(days=7)
    if periodicidade == Periodicidade.PERSONALIZADA:
        if intervalo_personalizado_dias < 1:
            raise ValueError("intervalo personalizado precisa ser >= 1")
        return base + timedelta(days=intervalo_personalizado_dias)
    raise ValueError(f"Periodicidade desconhecida: {periodicidade}")


# ============================================================
# GERAÇÃO DO CRONOGRAMA
# ============================================================

def gerar_datas_parcelas(
    data_primeira: date,
    quantidade: int,
    periodicidade: Periodicidade,
    intervalo_personalizado_dias: int = 1,
) -> List[date]:
    """
    Gera as datas de cada parcela aplicando a regra do briefing Seção 14.

    A próxima parcela é calculada a partir da ANTERIOR JÁ AJUSTADA (não da data-base
    original), evitando empilhamento de várias parcelas no mesmo dia útil quando
    o intervalo é pequeno.

    Exemplo personalizada=1, começando sexta 08/05:
      P1 = 08/05 (sex)
      P2 = 09/05 → cai sábado → empurra pra 11/05 (seg)
      P3 = parte de 11/05 + 1 = 12/05 (ter)
      P4 = 13/05 (qua) ... etc.

    Se contássemos sempre da data-base original (08/05 + N), várias parcelas
    cairiam todas em sáb/dom e seriam todas empurradas pra mesma segunda,
    causando duplicidade.
    """
    if quantidade <= 0:
        return []
    if quantidade > 10000:
        raise ValueError(f"Quantidade absurda de parcelas: {quantidade}")

    datas: List[date] = []
    anterior = proximo_dia_util(data_primeira)
    datas.append(anterior)

    for _ in range(1, quantidade):
        candidata = avancar_uma_unidade(
            anterior, periodicidade, intervalo_personalizado_dias
        )
        anterior = proximo_dia_util(candidata)
        datas.append(anterior)

    return datas


def calcular_valores_parcelas(
    total: float,
    quantidade: int,
) -> List[float]:
    """
    Distribui o total em parcelas redondas, com a última absorvendo a diferença
    (briefing Seção 19b - modelo da planilha MB Comércio: 40x2400 + 1x1948).
    """
    if quantidade <= 0:
        raise ValueError("Quantidade de parcelas precisa ser >= 1")
    if total <= 0:
        raise ValueError("Total precisa ser > 0")

    base = round(total / quantidade, 2)
    valores: List[float] = []
    soma_parciais = 0.0
    for i in range(quantidade):
        if i < quantidade - 1:
            valores.append(base)
            soma_parciais += base
        else:
            # Última absorve a diferença pra fechar o total exato
            valores.append(round(total - soma_parciais, 2))
    return valores


def calcular_qtd_parcelas_para_valor_fixo(
    total: float,
    valor_parcela_alvo: float,
) -> tuple[int, List[float]]:
    """
    Modo "valor fixo por parcela": quantas parcelas saem e qual o valor de cada uma.
    A última parcela pode ser MENOR (modelo da planilha MB: 40x2400 + 1x1948).
    """
    if valor_parcela_alvo <= 0:
        raise ValueError("Valor da parcela precisa ser > 0")
    if total <= 0:
        raise ValueError("Total precisa ser > 0")

    qtd_cheias = int(total // valor_parcela_alvo)
    resto = round(total - qtd_cheias * valor_parcela_alvo, 2)

    if resto > 0.005:
        qtd_total = qtd_cheias + 1
        valores = [valor_parcela_alvo] * qtd_cheias + [resto]
    else:
        qtd_total = qtd_cheias
        valores = [valor_parcela_alvo] * qtd_cheias

    return qtd_total, valores
