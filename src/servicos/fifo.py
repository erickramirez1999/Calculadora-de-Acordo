"""
Algoritmo FIFO (First In, First Out) de rateio de boletos em parcelas.

REGRAS DO BRIEFING SEÇÃO 3:
1) Boletos ordenados por vencimento (mais antigo primeiro).
2) Cada parcela "consome" seu valor em boletos, na ordem.
3) Quando um boleto não cabe inteiro numa parcela, transborda para a próxima.
4) Decomposição P/J/M de cada parcela: rateio proporcional sobre o valor consumido,
   mantendo a proporção P:J:M do(s) boleto(s) de origem.
5) Validação cruzada: Principal + Juros + Multa = Total em cada boleto E em cada parcela.

REFINAMENTO ITERATIVO (decisão P2):
O cálculo dos juros do CASO 1 (juros.py) precisa da data da parcela que quita cada boleto.
Mas o FIFO depende do TOTAL de cada boleto, que depende dos juros, que depende da data...
Resolvemos rodando o ciclo até convergir:

  iter 1: aproxima juros usando data do 1º pagamento → faz FIFO → descobre as datas reais
  iter 2: recalcula juros com datas reais → refaz FIFO → datas podem mudar
  iter 3: ... repete até nada mais mudar (geralmente 2-4 iterações).

O resultado FINAL é equivalente a "juros = pro-rata até a(s) parcela(s) que quita(m)
o título", como pedido na decisão P2.
"""
from __future__ import annotations

from datetime import date
from typing import List

from src.modelos.tipos import Boleto, Parcela
from src.servicos.juros import calcular_boleto_caso1


# ============================================================
# FIFO PURO (sem refinamento de juros)
# ============================================================

def ratear_fifo(
    boletos: List[Boleto],
    parcelas: List[Parcela],
    tolerancia_centavos: float = 0.01,
) -> None:
    """
    Distribui os totais dos boletos pelas parcelas (FIFO).
    Mutaciona em sequência:
      - cada parcela recebe sua decomposição P/J/M proporcional
      - cada boleto recebe lista de parcelas_alocadas e detalhe de distribuição
      - saldo_apos de cada parcela é atualizado

    Pré-condição: boletos JÁ ordenados por (vencimento, numero_unico) e com
    total já calculado. Quem chama é responsável por isso.

    A última parcela pode ficar com sobra de centavos se o total dos boletos for
    ligeiramente menor que o valor total das parcelas (devido a arredondamento).
    """
    # Zera estado anterior
    for b in boletos:
        b.parcelas_alocadas = []
        b.distribuicao = []
    for p in parcelas:
        p.principal = 0.0
        p.juros = 0.0
        p.multa = 0.0

    if not parcelas or not boletos:
        return

    capacidade_restante = [p.valor_original for p in parcelas]
    idx_parcela = 0
    n_parcelas = len(parcelas)

    for boleto in boletos:
        if boleto.total <= 0:
            continue
        a_distribuir = boleto.total

        while a_distribuir > tolerancia_centavos and idx_parcela < n_parcelas:
            cap = capacidade_restante[idx_parcela]
            if cap <= tolerancia_centavos:
                idx_parcela += 1
                continue

            usado = min(a_distribuir, cap)
            capacidade_restante[idx_parcela] -= usado
            a_distribuir -= usado

            num_parcela = parcelas[idx_parcela].numero
            if num_parcela not in boleto.parcelas_alocadas:
                boleto.parcelas_alocadas.append(num_parcela)
            boleto.distribuicao.append({
                "parcela": num_parcela,
                "valor": round(usado, 2),
            })

            # Rateio proporcional do P/J/M
            proporcao = usado / boleto.total
            parcelas[idx_parcela].principal += boleto.principal * proporcao
            parcelas[idx_parcela].juros += boleto.juros * proporcao
            parcelas[idx_parcela].multa += boleto.multa * proporcao

    # Atualiza saldo_apos (saldo total devedor após cada parcela)
    soma_totais = sum(b.total for b in boletos)
    acumulado = 0.0
    for p in parcelas:
        acumulado += p.valor_original
        p.saldo_apos = max(0.0, round(soma_totais - acumulado, 4))

    # Arredonda os P/J/M finais a 2 casas
    for p in parcelas:
        p.principal = round(p.principal, 2)
        p.juros = round(p.juros, 2)
        p.multa = round(p.multa, 2)


# ============================================================
# REFINAMENTO ITERATIVO
# ============================================================

def calcular_acordo_completo(
    boletos: List[Boleto],
    parcelas: List[Parcela],
    data_acordo: date,
    pct_juros_mes: float,
    pct_multa: float,
    max_iteracoes: int = 8,
    tolerancia: float = 0.01,
) -> int:
    """
    Calcula o acordo completo (juros CASO 1 + rateio FIFO) com refinamento iterativo.

    Retorna o número de iterações necessárias até convergir.

    Algoritmo:
      0) Ordena boletos por (vencimento, numero_unico) — determinístico.
      1) Define data_quitacao_inicial = data da 1ª parcela para todos os boletos.
      2) Calcula juros e multa de cada boleto usando essa data.
      3) Faz FIFO → descobre quais parcelas realmente quitam cada boleto.
      4) Para cada boleto, atualiza data_quitacao = data da última parcela alocada.
      5) Recalcula juros e multa com a nova data.
      6) Se algum total mudou, repete o FIFO. Senão, convergiu.

    Convergência: tipicamente em 2-4 iterações.
    """
    if not parcelas:
        raise ValueError("Não há parcelas para alocar")
    if not boletos:
        return 0

    # Ordenação determinística (vencimento, numero_unico)
    boletos.sort(key=lambda b: (b.vencimento, b.numero_unico))

    # iter 0: usa data da 1ª parcela como aproximação inicial
    data_aprox = parcelas[0].vencimento_original
    for b in boletos:
        calcular_boleto_caso1(b, data_acordo, pct_juros_mes, pct_multa, data_aprox)

    ratear_fifo(boletos, parcelas)

    for it in range(1, max_iteracoes + 1):
        mudou = False
        for b in boletos:
            if not b.parcelas_alocadas:
                continue
            ultima_num = max(b.parcelas_alocadas)
            ultima_parcela = next(
                (p for p in parcelas if p.numero == ultima_num), None
            )
            if ultima_parcela is None:
                continue
            nova_data = ultima_parcela.vencimento_original
            if nova_data != b.fim_juros:
                total_antigo = b.total
                calcular_boleto_caso1(
                    b, data_acordo, pct_juros_mes, pct_multa, nova_data
                )
                if abs(b.total - total_antigo) > tolerancia:
                    mudou = True
        if not mudou:
            return it
        ratear_fifo(boletos, parcelas)

    return max_iteracoes


# ============================================================
# ORQUESTRADOR DE ALTO NÍVEL
# ============================================================

def montar_acordo_valor_fixo(
    boletos: List[Boleto],
    data_acordo: date,
    pct_juros_mes: float,
    pct_multa: float,
    valor_parcela: float,
    data_primeira_parcela: date,
    periodicidade,
    intervalo_personalizado_dias: int = 1,
    max_iteracoes: int = 12,
    tolerancia: float = 0.01,
) -> List[Parcela]:
    """
    Monta um acordo completo no modo VALOR FIXO POR PARCELA.

    Resolve o paradoxo da dependência circular:
      - Total muda → muda número de parcelas → muda última data → muda juros → muda total

    Algoritmo:
      1. Calcula juros iniciais usando data do acordo como aproximação
      2. Loop até convergir:
         a) Recalcula quantidade de parcelas e datas com o total ATUAL
         b) Recalcula juros de cada boleto com a data da última parcela que o quitaria
            (FIFO virtual rápido pra descobrir alocação)
         c) Se algum total mudou, refaz tudo. Senão, sai do loop.
      3. Faz FIFO final e retorna parcelas.
    """
    from src.servicos.cronograma import (
        calcular_qtd_parcelas_para_valor_fixo,
        gerar_datas_parcelas,
    )
    from src.servicos.juros import calcular_boleto_caso1

    if not boletos:
        return []

    # Garante ordem determinística
    boletos.sort(key=lambda b: (b.vencimento, b.numero_unico))

    # ITERAÇÃO 0 — aproximação inicial: juros usando data do acordo
    for b in boletos:
        calcular_boleto_caso1(b, data_acordo, pct_juros_mes, pct_multa, data_acordo)

    parcelas: List[Parcela] = []

    for iteracao in range(max_iteracoes):
        # 1. Calcula quantas parcelas precisamos com o total atual
        total_atual = sum(b.total for b in boletos)
        qtd, valores = calcular_qtd_parcelas_para_valor_fixo(total_atual, valor_parcela)
        # 2. Gera datas
        datas = gerar_datas_parcelas(
            data_primeira_parcela, qtd, periodicidade, intervalo_personalizado_dias
        )
        # 3. Cria parcelas com os valores
        parcelas = [
            Parcela(
                numero=i + 1,
                vencimento_original=datas[i],
                vencimento_atual=datas[i],
                valor_original=valores[i],
            )
            for i in range(qtd)
        ]
        # 4. FIFO simples (com os totais atuais) - apenas pra descobrir alocação
        ratear_fifo(boletos, parcelas)
        # 5. Pra cada boleto, descobre a data da última parcela que o quita
        #    e recalcula juros + multa com essa data
        algum_total_mudou = False
        for b in boletos:
            if not b.parcelas_alocadas:
                continue
            ultima_num = max(b.parcelas_alocadas)
            ultima_parc = next((p for p in parcelas if p.numero == ultima_num), None)
            if ultima_parc is None:
                continue
            total_antigo = b.total
            calcular_boleto_caso1(
                b, data_acordo, pct_juros_mes, pct_multa,
                ultima_parc.vencimento_original,
            )
            if abs(b.total - total_antigo) > tolerancia:
                algum_total_mudou = True

        if not algum_total_mudou:
            # Estável — sai do loop
            # Refaz FIFO final pra garantir consistência das parcelas
            ratear_fifo(boletos, parcelas)
            return parcelas

    # Saiu por timeout — refaz FIFO final mesmo assim
    ratear_fifo(boletos, parcelas)
    return parcelas


def montar_acordo_qtd_fixa(
    boletos: List[Boleto],
    data_acordo: date,
    pct_juros_mes: float,
    pct_multa: float,
    qtd_parcelas: int,
    data_primeira_parcela: date,
    periodicidade,
    intervalo_personalizado_dias: int = 1,
    max_iteracoes: int = 10,
    tolerancia: float = 0.01,
) -> List[Parcela]:
    """
    Monta um acordo no modo QUANTIDADE FIXA DE PARCELAS.

    Mais simples: número de parcelas e datas são fixos desde o início.
    Iteramos só os juros até estabilizar.
    """
    from src.servicos.cronograma import (
        calcular_valores_parcelas,
        gerar_datas_parcelas,
    )
    from src.servicos.juros import calcular_boleto_caso1

    if not boletos:
        return []
    if qtd_parcelas <= 0:
        raise ValueError("Quantidade de parcelas precisa ser >= 1")

    # Garante ordem determinística
    boletos.sort(key=lambda b: (b.vencimento, b.numero_unico))

    # Datas fixas
    datas = gerar_datas_parcelas(
        data_primeira_parcela, qtd_parcelas, periodicidade, intervalo_personalizado_dias
    )

    # iter 0: aproxima juros até data da última parcela (chute mais próximo da realidade)
    for b in boletos:
        calcular_boleto_caso1(b, data_acordo, pct_juros_mes, pct_multa, datas[-1])

    parcelas: List[Parcela] = []
    for iteracao in range(max_iteracoes):
        total = sum(b.total for b in boletos)
        valores = calcular_valores_parcelas(total, qtd_parcelas)
        parcelas = [
            Parcela(
                numero=i + 1,
                vencimento_original=datas[i],
                vencimento_atual=datas[i],
                valor_original=valores[i],
            )
            for i in range(qtd_parcelas)
        ]
        ratear_fifo(boletos, parcelas)

        # Recalcula juros de cada boleto com a data da última parcela que ele alcança
        mudou = False
        for b in boletos:
            if not b.parcelas_alocadas:
                continue
            ultima_num = max(b.parcelas_alocadas)
            ultima_parc = next((p for p in parcelas if p.numero == ultima_num), None)
            if ultima_parc is None:
                continue
            total_antigo = b.total
            calcular_boleto_caso1(
                b, data_acordo, pct_juros_mes, pct_multa,
                ultima_parc.vencimento_original,
            )
            if abs(b.total - total_antigo) > tolerancia:
                mudou = True
        if not mudou:
            # Refaz FIFO final pra atualizar valores das parcelas
            total = sum(b.total for b in boletos)
            valores = calcular_valores_parcelas(total, qtd_parcelas)
            for i, p in enumerate(parcelas):
                p.valor_original = valores[i]
            ratear_fifo(boletos, parcelas)
            return parcelas

    # Timeout — refaz FIFO final
    ratear_fifo(boletos, parcelas)
    return parcelas



# ============================================================
# VALIDAÇÕES CRUZADAS (briefing Seção 3 - obrigatórias)
# ============================================================

def validar_consistencia(
    boletos: List[Boleto],
    parcelas: List[Parcela],
    tolerancia: float = 0.05,
) -> List[str]:
    """
    Valida que os cálculos batem. Retorna lista de erros (vazia se tudo OK).

    Verifica:
      - Em cada boleto: Principal + Juros + Multa = Total
      - Em cada parcela: Principal + Juros + Multa = Valor (com tolerância de centavos)
      - Soma do Principal dos boletos = soma do Principal das parcelas
      - Idem para Juros e Multa
    """
    erros: List[str] = []

    for b in boletos:
        soma = b.principal + b.juros + b.multa
        if abs(soma - b.total) > tolerancia:
            erros.append(
                f"Boleto {b.numero_unico}: P+J+M ({soma:.4f}) ≠ Total ({b.total:.4f})"
            )

    for p in parcelas:
        soma_componentes = p.principal + p.juros + p.multa
        # Última parcela pode ter sobra se total_boletos < total_parcelas
        ultima = parcelas[-1] if parcelas else None
        if p is ultima:
            # Aceita que a última pode ter componentes menores que o valor
            if soma_componentes > p.valor_original + tolerancia:
                erros.append(
                    f"Parcela {p.numero}: P+J+M ({soma_componentes:.4f}) "
                    f"> Valor ({p.valor_original:.4f})"
                )
        else:
            if abs(soma_componentes - p.valor_original) > tolerancia:
                erros.append(
                    f"Parcela {p.numero}: P+J+M ({soma_componentes:.4f}) "
                    f"≠ Valor ({p.valor_original:.4f})"
                )

    # Totais agregados
    tp_b = round(sum(b.principal for b in boletos), 2)
    tj_b = round(sum(b.juros for b in boletos), 2)
    tm_b = round(sum(b.multa for b in boletos), 2)
    tp_p = round(sum(p.principal for p in parcelas), 2)
    tj_p = round(sum(p.juros for p in parcelas), 2)
    tm_p = round(sum(p.multa for p in parcelas), 2)

    if abs(tp_b - tp_p) > tolerancia:
        erros.append(f"Total Principal: boletos {tp_b} ≠ parcelas {tp_p}")
    if abs(tj_b - tj_p) > tolerancia:
        erros.append(f"Total Juros: boletos {tj_b} ≠ parcelas {tj_p}")
    if abs(tm_b - tm_p) > tolerancia:
        erros.append(f"Total Multa: boletos {tm_b} ≠ parcelas {tm_p}")

    return erros


def montar_acordo_qtd_e_valor_livre(
    boletos: List[Boleto],
    data_acordo: date,
    pct_juros_mes: float,
    pct_multa: float,
    qtd_parcelas: int,
    valor_parcela: float,
    data_primeira_parcela: date,
    periodicidade,
    intervalo_personalizado_dias: int = 1,
) -> List[Parcela]:
    """
    Modo LIVRE: o usuário define QUANTAS parcelas E o VALOR de cada uma.
    
    NÃO recalcula nada baseado em juros — o usuário escolheu o valor explicitamente,
    mesmo que dê um total diferente do que o sistema calcularia automaticamente.
    
    Útil quando o negociador quer fechar acordo com valor "redondo" (ex: 12 parcelas
    de R$ 500), mesmo que isso ultrapasse a dívida calculada com juros.
    
    Aplica FIFO igual aos outros modos pra rastrear quais parcelas quitam quais boletos.
    """
    from src.servicos.cronograma import gerar_datas_parcelas
    from src.servicos.juros import calcular_boleto_caso1

    if not boletos:
        return []
    if qtd_parcelas <= 0:
        raise ValueError("Quantidade de parcelas precisa ser >= 1")
    if valor_parcela <= 0:
        raise ValueError("Valor da parcela precisa ser > 0")

    boletos.sort(key=lambda b: (b.vencimento, b.numero_unico))

    # Datas fixas
    datas = gerar_datas_parcelas(
        data_primeira_parcela, qtd_parcelas, periodicidade, intervalo_personalizado_dias
    )

    # Aproxima juros uma vez (usando data da última parcela)
    for b in boletos:
        calcular_boleto_caso1(b, data_acordo, pct_juros_mes, pct_multa, datas[-1])

    # Cria parcelas com valor FIXO escolhido pelo usuário
    parcelas = [
        Parcela(
            numero=i + 1,
            vencimento_original=datas[i],
            vencimento_atual=datas[i],
            valor_original=round(valor_parcela, 2),
        )
        for i in range(qtd_parcelas)
    ]

    # Faz FIFO pra rastrear vínculo (mesmo que sobre/falte dinheiro)
    ratear_fifo(boletos, parcelas)

    return parcelas
