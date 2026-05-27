"""
Testes unitários do algoritmo FIFO + cálculo de juros CASO 1.

Este é o módulo crítico do sistema (Briefing Seção 12 e Seção 3).
TODOS os testes precisam passar antes de qualquer deploy.

Cobertura:
  - Invariantes algébricas (P+J+M=Total em boletos e parcelas)
  - Casos extremos (1 boleto, 1 parcela, vencidos, a vencer)
  - FIFO sequencial e transbordo
  - Refinamento iterativo (CASO 1)
  - Validação contra a planilha-modelo MB Comércio
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Permite importar src/ a partir dos testes
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.modelos.tipos import Boleto, Empresa, Parcela, StatusParcela
from src.servicos.cronograma import (
    calcular_qtd_parcelas_para_valor_fixo,
    calcular_valores_parcelas,
    gerar_datas_parcelas,
)
from src.servicos.fifo import (
    calcular_acordo_completo,
    ratear_fifo,
    validar_consistencia,
)
from src.servicos.juros import (
    calcular_boleto_caso1,
    calcular_juros_titulo,
    calcular_mora_parcela,
    calcular_multa_titulo_se_aplicavel,
)
from src.modelos.tipos import Periodicidade


# ============================================================
# HELPERS
# ============================================================

def boleto_simples(
    venc: date,
    principal: float,
    nro_unico: str = "001",
    nro_nota: str = "100",
) -> Boleto:
    """Cria um boleto mínimo para testes."""
    return Boleto(
        codigo_parceiro="P1",
        razao_social_parceiro="Cliente Teste",
        empresa=Empresa.UM,
        codigo_vendedor="V1",
        nome_vendedor="Vendedor",
        vencimento=venc,
        numero_nota=nro_nota,
        numero_unico=nro_unico,
        principal=principal,
    )


def parcela_simples(numero: int, venc: date, valor: float) -> Parcela:
    return Parcela(
        numero=numero,
        vencimento_original=venc,
        vencimento_atual=venc,
        valor_original=valor,
    )


# ============================================================
# 1) CÁLCULO DE JUROS PURO (CASO 1)
# ============================================================

class TestCalculoJurosTitulo:
    def test_zero_dias_zero_juros(self):
        assert calcular_juros_titulo(1000, 0, 8.0) == 0.0

    def test_dias_negativos_zero_juros(self):
        assert calcular_juros_titulo(1000, -5, 8.0) == 0.0

    def test_principal_zero_zero_juros(self):
        assert calcular_juros_titulo(0, 30, 8.0) == 0.0

    def test_8_pct_30_dias_e_8_pct(self):
        """30 dias a 8%/mês sobre R$ 1000 = R$ 80."""
        assert calcular_juros_titulo(1000, 30, 8.0) == pytest.approx(80.0)

    def test_8_pct_15_dias_metade(self):
        """15 dias a 8%/mês sobre R$ 1000 = R$ 40 (metade)."""
        assert calcular_juros_titulo(1000, 15, 8.0) == pytest.approx(40.0)

    def test_referencia_planilha_modelo(self):
        """
        Caso real do exemplo MB Comércio:
        Boleto 16475942 (linha 4): P=971,93, atraso 48, juros calculado 124,40704.
        """
        assert calcular_juros_titulo(971.93, 48, 8.0) == pytest.approx(124.40704)


class TestCalculoMultaTitulo:
    def test_vencido_aplica_multa(self):
        """Título vencido: aplica multa direto."""
        m = calcular_multa_titulo_se_aplicavel(
            principal=1000,
            pct_multa=2.0,
            vencimento=date(2026, 1, 1),
            data_acordo=date(2026, 2, 1),  # acordo posterior ao vencimento
            data_fim_juros=date(2026, 3, 1),
        )
        assert m == pytest.approx(20.0)

    def test_a_vencer_paga_antes_nao_aplica(self):
        """Título a vencer, parcela quita ANTES do vencimento: SEM multa."""
        m = calcular_multa_titulo_se_aplicavel(
            principal=1000,
            pct_multa=2.0,
            vencimento=date(2026, 5, 20),
            data_acordo=date(2026, 5, 10),  # ainda não venceu
            data_fim_juros=date(2026, 5, 15),  # parcela paga antes do vencimento
        )
        assert m == 0.0

    def test_a_vencer_paga_depois_aplica(self):
        """Título a vencer, parcela quita DEPOIS do vencimento: COM multa."""
        m = calcular_multa_titulo_se_aplicavel(
            principal=1000,
            pct_multa=2.0,
            vencimento=date(2026, 5, 20),
            data_acordo=date(2026, 5, 10),
            data_fim_juros=date(2026, 5, 25),
        )
        assert m == pytest.approx(20.0)

    def test_multa_zero_quando_pct_zero(self):
        m = calcular_multa_titulo_se_aplicavel(1000, 0, date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1))
        assert m == 0.0


# ============================================================
# 2) CALCULAR BOLETO COMPLETO (CASO 1)
# ============================================================

class TestCalcularBoletoCaso1:
    def test_boleto_vencido_referencia_planilha(self):
        """Replica linha 4 da planilha MB: P=971,93, venc 19/02/2026, acordo "08/04/2026"."""
        b = boleto_simples(date(2026, 2, 19), 971.93)
        data_acordo = date(2026, 4, 8)
        data_quitacao = date(2026, 4, 8)  # 48 dias depois
        calcular_boleto_caso1(b, data_acordo, 8.0, 2.0, data_quitacao)
        assert b.dias_atraso == 48
        assert b.juros == pytest.approx(124.40704)
        assert b.multa == pytest.approx(19.4386)
        assert b.total == pytest.approx(1115.77564)

    def test_boleto_a_vencer_sem_multa(self):
        b = boleto_simples(date(2026, 5, 20), 1000)
        # Acordo 10/05, parcela 15/05 — paga antes do vencimento
        calcular_boleto_caso1(b, date(2026, 5, 10), 8.0, 2.0, date(2026, 5, 15))
        # Dias = 15/05 - 10/05 = 5 dias
        assert b.dias_atraso == 5
        # Juros: 1000 × 8%/30 × 5 = 13,333...
        assert b.juros == pytest.approx(13.333333, rel=1e-3)
        # Multa: 0 (paga antes do vencimento)
        assert b.multa == 0.0

    def test_boleto_a_vencer_com_multa(self):
        b = boleto_simples(date(2026, 5, 20), 1000)
        # Acordo 10/05, parcela 25/05 — paga DEPOIS do vencimento
        calcular_boleto_caso1(b, date(2026, 5, 10), 8.0, 2.0, date(2026, 5, 25))
        # Dias = 25/05 - 10/05 = 15
        assert b.dias_atraso == 15
        assert b.juros == pytest.approx(40.0)
        assert b.multa == pytest.approx(20.0)
        assert b.total == pytest.approx(1060.0)


# ============================================================
# 3) FIFO PURO (rateio sem refinamento)
# ============================================================

class TestFifoBasico:
    def test_um_boleto_uma_parcela_exato(self):
        b = boleto_simples(date(2026, 1, 1), 1000.0)
        b.total = 1000.0
        b.principal = 1000.0
        b.juros = 0.0
        b.multa = 0.0
        p = parcela_simples(1, date(2026, 2, 1), 1000.0)
        ratear_fifo([b], [p])
        assert p.principal == 1000.0
        assert b.parcelas_alocadas == [1]
        assert len(b.distribuicao) == 1
        assert b.distribuicao[0]["valor"] == 1000.0

    def test_um_boleto_transborda_duas_parcelas(self):
        """Boleto de R$ 1500 com parcelas de R$ 1000."""
        b = boleto_simples(date(2026, 1, 1), 1500.0)
        b.total = 1500.0
        b.principal = 1500.0
        p1 = parcela_simples(1, date(2026, 2, 1), 1000.0)
        p2 = parcela_simples(2, date(2026, 3, 1), 1000.0)
        ratear_fifo([b], [p1, p2])
        # P1 enche com R$ 1000, sobra R$ 500 pra P2
        assert b.parcelas_alocadas == [1, 2]
        assert p1.principal == pytest.approx(1000.0)
        assert p2.principal == pytest.approx(500.0)

    def test_dois_boletos_uma_parcela(self):
        """Dois boletos de R$ 400 cabem inteiros em uma parcela de R$ 1000."""
        b1 = boleto_simples(date(2026, 1, 1), 400, "001")
        b1.total = 400; b1.principal = 400
        b2 = boleto_simples(date(2026, 1, 2), 400, "002")
        b2.total = 400; b2.principal = 400
        p = parcela_simples(1, date(2026, 2, 1), 1000.0)
        ratear_fifo([b1, b2], [p])
        assert b1.parcelas_alocadas == [1]
        assert b2.parcelas_alocadas == [1]
        assert p.principal == pytest.approx(800.0)
        # Sobra: parcela tinha capacidade 1000, usou 800

    def test_ordem_fifo_respeitada(self):
        """Boletos com vencimentos diferentes: o mais antigo entra primeiro."""
        # Mesmo passando fora de ordem, o FIFO ordena por (vencimento, nro_unico) ANTES
        # mas ratear_fifo() já assume ordem feita. Aqui passo em ordem.
        b_antigo = boleto_simples(date(2026, 1, 1), 500, "001")
        b_antigo.total = 500; b_antigo.principal = 500
        b_novo = boleto_simples(date(2026, 1, 15), 700, "002")
        b_novo.total = 700; b_novo.principal = 700
        p1 = parcela_simples(1, date(2026, 2, 1), 600)
        p2 = parcela_simples(2, date(2026, 3, 1), 600)
        ratear_fifo([b_antigo, b_novo], [p1, p2])
        # P1: 500 do antigo + 100 do novo
        assert p1.principal == pytest.approx(600.0)
        # P2: 600 do novo (restante)
        assert p2.principal == pytest.approx(600.0)
        assert b_antigo.parcelas_alocadas == [1]
        assert b_novo.parcelas_alocadas == [1, 2]


class TestRateioPJM:
    def test_proporcao_pjm_preservada(self):
        """
        Boleto P=800, J=180, M=20, Total=1000.
        Transborda em duas parcelas de 500 cada.
        Cada parcela deve ter P=400, J=90, M=10 (proporção mantida).
        """
        b = boleto_simples(date(2026, 1, 1), 800)
        b.principal = 800; b.juros = 180; b.multa = 20; b.total = 1000
        p1 = parcela_simples(1, date(2026, 2, 1), 500)
        p2 = parcela_simples(2, date(2026, 3, 1), 500)
        ratear_fifo([b], [p1, p2])
        assert p1.principal == pytest.approx(400.0)
        assert p1.juros == pytest.approx(90.0)
        assert p1.multa == pytest.approx(10.0)
        assert p2.principal == pytest.approx(400.0)
        assert p2.juros == pytest.approx(90.0)
        assert p2.multa == pytest.approx(10.0)


# ============================================================
# 4) INVARIANTES (briefing Seção 3 - validações cruzadas)
# ============================================================

class TestInvariantes:
    def test_invariante_boleto_pjm_total(self):
        """Em cada boleto: P + J + M = Total."""
        b = boleto_simples(date(2026, 1, 1), 1000)
        calcular_boleto_caso1(b, date(2026, 1, 1), 8.0, 2.0, date(2026, 2, 1))
        assert b.principal + b.juros + b.multa == pytest.approx(b.total)

    def test_invariante_parcela_pjm_valor(self):
        """Em cada parcela: P + J + M = Valor (exceto última se houver sobra)."""
        b = boleto_simples(date(2026, 1, 1), 1000)
        b.principal = 800; b.juros = 180; b.multa = 20; b.total = 1000
        p = parcela_simples(1, date(2026, 2, 1), 1000)
        ratear_fifo([b], [p])
        assert p.principal + p.juros + p.multa == pytest.approx(p.valor_original)

    def test_validacao_consistencia_ok(self):
        """validar_consistencia retorna lista vazia se tudo está coerente."""
        b = boleto_simples(date(2026, 1, 1), 1000)
        b.principal = 800; b.juros = 180; b.multa = 20; b.total = 1000
        p = parcela_simples(1, date(2026, 2, 1), 1000)
        ratear_fifo([b], [p])
        erros = validar_consistencia([b], [p])
        assert erros == []

    def test_validacao_detecta_inconsistencia(self):
        """Se forçarmos P+J+M ≠ Total, a validação detecta."""
        b = boleto_simples(date(2026, 1, 1), 1000)
        b.principal = 800; b.juros = 100; b.multa = 20; b.total = 1000  # 800+100+20 ≠ 1000
        p = parcela_simples(1, date(2026, 2, 1), 1000)
        ratear_fifo([b], [p])
        erros = validar_consistencia([b], [p])
        assert len(erros) > 0
        assert "16475942" in erros[0] or "Boleto" in erros[0]


# ============================================================
# 5) REFINAMENTO ITERATIVO (calcular_acordo_completo)
# ============================================================

class TestRefinamentoIterativo:
    def test_um_boleto_uma_parcela_converge(self):
        """1 boleto + 1 parcela com folga: converge e fecha tudo."""
        from src.servicos.fifo import montar_acordo_qtd_fixa
        boletos = [boleto_simples(date(2026, 1, 1), 1000)]
        parcelas = montar_acordo_qtd_fixa(
            boletos,
            data_acordo=date(2026, 1, 1),
            pct_juros_mes=8.0, pct_multa=2.0,
            qtd_parcelas=1,
            data_primeira_parcela=date(2026, 2, 2),  # 32 dias depois
            periodicidade=Periodicidade.MENSAL,
        )
        # Validação: tudo bate
        erros = validar_consistencia(boletos, parcelas)
        assert erros == []
        # 1 boleto deve ser alocado na parcela 1
        assert boletos[0].parcelas_alocadas == [1]

    def test_muitos_boletos_convergem(self):
        """Vários boletos: ainda assim converge."""
        from src.servicos.fifo import montar_acordo_qtd_fixa
        boletos = [
            boleto_simples(date(2026, 1, 1), 500, "001"),
            boleto_simples(date(2026, 1, 5), 700, "002"),
            boleto_simples(date(2026, 1, 10), 300, "003"),
        ]
        parcelas = montar_acordo_qtd_fixa(
            boletos,
            data_acordo=date(2026, 1, 1),
            pct_juros_mes=8.0, pct_multa=2.0,
            qtd_parcelas=3,
            data_primeira_parcela=date(2026, 2, 2),
            periodicidade=Periodicidade.MENSAL,
        )
        erros = validar_consistencia(boletos, parcelas)
        assert erros == []
        # Cada boleto foi alocado em pelo menos uma parcela
        for b in boletos:
            assert len(b.parcelas_alocadas) >= 1


# ============================================================
# 6) GERAÇÃO DE CRONOGRAMA (cronograma.py)
# ============================================================

class TestCronograma:
    def test_mensal_a_partir_de_dia_util(self):
        """Mensal a partir de 08/05/2026 (sexta): pula meses normalmente."""
        datas = gerar_datas_parcelas(date(2026, 5, 8), 3, Periodicidade.MENSAL)
        assert datas[0] == date(2026, 5, 8)
        assert datas[1] == date(2026, 6, 8)
        assert datas[2] == date(2026, 7, 8)

    def test_pula_fim_de_semana(self):
        """Se a data cair em sábado/domingo, vai pra segunda."""
        # 02/05/2026 é sábado
        datas = gerar_datas_parcelas(date(2026, 5, 2), 1, Periodicidade.MENSAL)
        assert datas[0] == date(2026, 5, 4)  # segunda

    def test_personalizada_diaria_modelo_planilha(self):
        """
        Replica EXATAMENTE o cronograma da planilha MB Comércio:
        41 parcelas diárias começando 08/05/2026.
        """
        datas = gerar_datas_parcelas(
            date(2026, 5, 8), 41, Periodicidade.PERSONALIZADA, intervalo_personalizado_dias=1
        )
        esperadas = [
            date(2026, 5, 8),  date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13),
            date(2026, 5, 14), date(2026, 5, 15), date(2026, 5, 18), date(2026, 5, 19),
            date(2026, 5, 20), date(2026, 5, 21), date(2026, 5, 22), date(2026, 5, 25),
            date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29),
            date(2026, 6, 1),  date(2026, 6, 2),  date(2026, 6, 3),  date(2026, 6, 4),
            date(2026, 6, 5),  date(2026, 6, 8),  date(2026, 6, 9),  date(2026, 6, 10),
            date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 15), date(2026, 6, 16),
            date(2026, 6, 17), date(2026, 6, 18), date(2026, 6, 19), date(2026, 6, 22),
            date(2026, 6, 23), date(2026, 6, 24), date(2026, 6, 25), date(2026, 6, 26),
            date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1),  date(2026, 7, 2),
            date(2026, 7, 3),
        ]
        assert datas == esperadas

    def test_semanal(self):
        datas = gerar_datas_parcelas(date(2026, 5, 8), 3, Periodicidade.SEMANAL)
        assert datas[0] == date(2026, 5, 8)
        assert datas[1] == date(2026, 5, 15)
        assert datas[2] == date(2026, 5, 22)

    def test_quinzenal_pula_sabado(self):
        # 08/05 sexta + 15 = 23/05 sábado → vai pra 25/05 segunda
        datas = gerar_datas_parcelas(date(2026, 5, 8), 2, Periodicidade.QUINZENAL)
        assert datas[1] == date(2026, 5, 25)


class TestCalculoValoresParcelas:
    def test_modelo_planilha_40x2400_1x1948(self):
        """Modelo da planilha: 97948 / parcelas redondas de 2400 + sobra na última."""
        qtd, valores = calcular_qtd_parcelas_para_valor_fixo(97948.00, 2400.0)
        assert qtd == 41
        assert valores[0] == 2400.0
        assert valores[-1] == pytest.approx(1948.0)
        assert sum(valores) == pytest.approx(97948.0)

    def test_qtd_fixa_divisao_exata(self):
        valores = calcular_valores_parcelas(1000.0, 10)
        assert len(valores) == 10
        assert all(v == 100.0 for v in valores)
        assert sum(valores) == pytest.approx(1000.0)

    def test_qtd_fixa_com_resto_na_ultima(self):
        valores = calcular_valores_parcelas(1000.0, 3)
        assert len(valores) == 3
        assert sum(valores) == pytest.approx(1000.0)
        # Última absorve diferença
        assert valores[-1] != valores[0]


# ============================================================
# 7) CASO 2 - MORA DE PARCELA ATRASADA
# ============================================================

class TestMoraParcela:
    def test_parcela_em_dia_sem_mora(self):
        j, m = calcular_mora_parcela(2400, 0, 5.0, 2.0)
        assert j == 0.0
        assert m == 0.0

    def test_parcela_3_dias_atraso(self):
        """P3 do briefing: mora sobre VALOR TOTAL. 2400 × 5%/30 × 3 = 12, multa 2% = 48."""
        j, m = calcular_mora_parcela(2400, 3, 5.0, 2.0)
        assert j == pytest.approx(12.0)
        assert m == pytest.approx(48.0)

    def test_mora_sobre_saldo_parcial(self):
        """P4.1 do briefing: mora incide sobre o saldo restante."""
        # Cliente pagou parte; resta 960. Mora 5%/mês × 7 dias + 2% multa
        j, m = calcular_mora_parcela(960, 7, 5.0, 2.0)
        # j = 960 × 0,05 / 30 × 7 = 11,20
        assert j == pytest.approx(11.20)
        # m = 960 × 0,02 = 19,20
        assert m == pytest.approx(19.20)


# ============================================================
# 8) TESTE-MONSTRO: PLANILHA-MODELO MB COMÉRCIO
# ============================================================

def montar_boletos_mb_comercio():
    """Reproduz os 39 boletos da planilha-modelo. Usado em testes de integração."""
    dados = [
        (date(2026, 2, 19), "2291668", "16475942", 971.93),
        (date(2026, 2, 19), "2291661", "16475912", 1077.65),
        (date(2026, 2, 19), "2291666", "16475932", 1322.23),
        (date(2026, 2, 19), "2291607", "16475791", 1365.52),
        (date(2026, 2, 19), "2291667", "16475937", 1580.89),
        (date(2026, 2, 19), "2291669", "16475947", 1752.99),
        (date(2026, 2, 19), "2291660", "16475907", 1778.65),
        (date(2026, 2, 19), "2291450", "16475356", 2192.23),
        (date(2026, 2, 19), "2281473", "16418735", 4505.45),
        (date(2026, 2, 23), "2293902", "16487463", 6282.94),
        (date(2026, 2, 25), "2276028", "16384152", 3169.26),
        (date(2026, 2, 26), "2276849", "16389072", 4427.16),
        (date(2026, 2, 27), "2277801", "16394941", 1239.78),
        (date(2026, 2, 27), "2277802", "16394946", 1362.03),
        (date(2026, 2, 27), "2277712", "16394609", 1765.10),
        (date(2026, 2, 27), "2277704", "16394586", 1770.08),
        (date(2026, 2, 27), "2277764", "16394812", 1979.06),
        (date(2026, 2, 27), "2277766", "16394818", 2610.34),
        (date(2026, 3, 2),  "2278744", "16401016", 1090.81),
        (date(2026, 3, 2),  "2278739", "16401002", 2802.38),
        (date(2026, 3, 5),  "2291668", "16475943", 971.93),
        (date(2026, 3, 5),  "2291661", "16475913", 1077.65),
        (date(2026, 3, 5),  "2291666", "16475933", 1322.23),
        (date(2026, 3, 5),  "2291607", "16475792", 1365.52),
        (date(2026, 3, 5),  "2291667", "16475938", 1580.89),
        (date(2026, 3, 5),  "2291669", "16475948", 1752.99),
        (date(2026, 3, 5),  "2291660", "16475908", 1778.65),
        (date(2026, 3, 5),  "2291450", "16475357", 2192.23),
        (date(2026, 3, 5),  "2281473", "16418736", 4505.45),
        (date(2026, 3, 9),  "2293902", "16487464", 6282.94),
        (date(2026, 3, 19), "2291668", "16475944", 971.94),
        (date(2026, 3, 19), "2291661", "16475914", 1077.64),
        (date(2026, 3, 19), "2291666", "16475934", 1322.23),
        (date(2026, 3, 19), "2291607", "16475793", 1365.53),
        (date(2026, 3, 19), "2291667", "16475939", 1580.87),
        (date(2026, 3, 19), "2291669", "16475949", 1752.99),
        (date(2026, 3, 19), "2291660", "16475909", 1778.67),
        (date(2026, 3, 19), "2291450", "16475358", 2192.23),
        (date(2026, 3, 23), "2293902", "16487465", 6282.95),
    ]
    boletos = []
    for venc, nota, unico, principal in dados:
        b = boleto_simples(venc, principal, unico, nota)
        boletos.append(b)
    return boletos


class TestPlanilhaModeloMBComercio:
    """
    Reproduz o cenário REAL da planilha ACORDO_MB_COMERCIO_COPIA2.xlsx.
    Os totais esperados são os da planilha.
    """

    def test_total_principal_dos_39_boletos(self):
        boletos = montar_boletos_mb_comercio()
        soma = sum(b.principal for b in boletos)
        assert soma == pytest.approx(86202.01, abs=0.01)
        assert len(boletos) == 39

    def test_acordo_completo_converge_e_valida(self):
        """Usa o orquestrador montar_acordo_valor_fixo que ajusta a quantidade
        de parcelas conforme o total muda durante o refinamento."""
        from src.servicos.fifo import montar_acordo_valor_fixo
        boletos = montar_boletos_mb_comercio()
        parcelas = montar_acordo_valor_fixo(
            boletos,
            data_acordo=date(2026, 4, 8),
            pct_juros_mes=8.0,
            pct_multa=2.0,
            valor_parcela=2400.0,
            data_primeira_parcela=date(2026, 5, 8),
            periodicidade=Periodicidade.PERSONALIZADA,
            intervalo_personalizado_dias=1,
        )

        # Validação cruzada: tudo deve bater (tolerância de R$ 0,05 para arredondamento)
        erros = validar_consistencia(boletos, parcelas, tolerancia=0.05)
        assert erros == [], f"Erros: {erros}"

        # Cada boleto tem distribuição preenchida e tem juros/multa
        for b in boletos:
            assert len(b.parcelas_alocadas) >= 1
            assert b.total > b.principal  # tem juros e/ou multa

    def test_soma_principal_boletos_igual_parcelas(self):
        """Soma de P dos boletos = soma de P das parcelas (CRÍTICO)."""
        from src.servicos.fifo import montar_acordo_valor_fixo
        boletos = montar_boletos_mb_comercio()
        parcelas = montar_acordo_valor_fixo(
            boletos,
            data_acordo=date(2026, 4, 8),
            pct_juros_mes=8.0,
            pct_multa=2.0,
            valor_parcela=2400.0,
            data_primeira_parcela=date(2026, 5, 8),
            periodicidade=Periodicidade.PERSONALIZADA,
            intervalo_personalizado_dias=1,
        )

        # Tolerância de R$ 0,05 cobre arredondamento de centavos em 39 boletos
        tp_b = sum(b.principal for b in boletos)
        tp_p = sum(p.principal for p in parcelas)
        assert tp_b == pytest.approx(tp_p, abs=0.05)

        # Idem para juros e multa
        tj_b = sum(b.juros for b in boletos)
        tj_p = sum(p.juros for p in parcelas)
        assert tj_b == pytest.approx(tj_p, abs=0.05)
        tm_b = sum(b.multa for b in boletos)
        tm_p = sum(p.multa for p in parcelas)
        assert tm_b == pytest.approx(tm_p, abs=0.05)

    def test_quantidade_parcelas_e_valor_ultima(self):
        """Com o orquestrador, a quantidade de parcelas é estável após convergência."""
        from src.servicos.fifo import montar_acordo_valor_fixo
        boletos = montar_boletos_mb_comercio()
        parcelas = montar_acordo_valor_fixo(
            boletos,
            data_acordo=date(2026, 4, 8),
            pct_juros_mes=8.0,
            pct_multa=2.0,
            valor_parcela=2400.0,
            data_primeira_parcela=date(2026, 5, 8),
            periodicidade=Periodicidade.PERSONALIZADA,
            intervalo_personalizado_dias=1,
        )
        # Pelo menos 40 parcelas (com os juros até a quitação final, pode ser mais que 41)
        assert len(parcelas) >= 40
        # Última parcela pode ser menor que as outras (sobra do arredondamento)
        assert parcelas[-1].valor_original <= 2400.0
        assert parcelas[0].valor_original == 2400.0
