"""
Tela Calculadora — duas modalidades de simulação (Erick).

ABA 1 — "Cálculo de Juros (avulso)":
    Sobe a planilha de títulos e vê quanto fica de juros e multa.
    Não simula parcelamento, é só o CASO 1 puro.

ABA 2 — "Simulação de Acordo Parcelado":
    Sobe a planilha + define parâmetros do acordo (parcelamento, periodicidade,
    valor/qtd parcelas) e vê o cronograma completo. Igual ao Novo Acordo mas
    SEM cadastrar nada — é só pra visualizar.

    Ao final tem o botão "→ Criar acordo com esta simulação" que leva pro wizard
    já com tudo preenchido. Aí basta clicar Avançar até salvar.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.modelos.tipos import Periodicidade
from src.servicos.fifo import (
    montar_acordo_qtd_fixa,
    montar_acordo_valor_fixo,
    validar_consistencia,
)
from src.servicos.juros import calcular_boleto_caso1
from src.servicos.leitor_xlsx import (
    gerar_template_xlsx,
    importar_xlsx_titulos,
    montar_relatorio_importacao,
)
from src.utils.formatadores import formatar_brl, formatar_data
from src.utils.marca import AZUL_ESCURO


def _mostrar_feedback_upload(res):
    """
    Mostra o resultado da importação de XLSX de forma visual e bonita,
    usando os componentes nativos do Streamlit (sem bloco de código cru
    que se sobrepunha ao file_uploader).
    """
    # Erros bloqueantes
    if res.tem_erros_bloqueantes:
        msg = "❌ **Não foi possível importar o arquivo:**\n\n"
        for e in res.erros:
            msg += f"- {e}\n"
        st.error(msg)
        return

    # Sucesso
    st.success(
        f"✅ **Arquivo lido com sucesso!**\n\n"
        f"- Total de linhas no arquivo: **{res.total_linhas}**\n"
        f"- Importados como boletos válidos: **{res.qtd_validas}**"
    )

    # Avisos gerais (ex: títulos filtrados por tipo)
    if hasattr(res, "avisos_gerais") and res.avisos_gerais:
        for av in res.avisos_gerais:
            st.info(av)

    # Avisos por linha (se houver)
    if res.qtd_invalidas > 0:
        msg_aviso = (
            f"⚠ **{res.qtd_invalidas} linha(s) ignorada(s) por inconsistência:**\n\n"
        )
        # Mostra até 10 pra não estourar
        for linha, erro in res.avisos_linhas[:10]:
            msg_aviso += f"- Linha {linha}: {erro}\n"
        if len(res.avisos_linhas) > 10:
            msg_aviso += f"\n_(e mais {len(res.avisos_linhas) - 10} linhas com problemas)_"
        st.warning(msg_aviso)


def renderizar_calculadora(usuario):
    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO}'>🧮 Calculadora</h1>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Simule cenários sem precisar criar acordo. Nada é salvo no banco — "
        "é apenas visualização."
    )

    aba_juros, aba_acordo = st.tabs([
        "📊 Cálculo de Juros (avulso)",
        "📋 Simulação de Acordo Parcelado",
    ])

    with aba_juros:
        _aba_calculo_juros(usuario)

    with aba_acordo:
        _aba_simulacao_acordo(usuario)


# ============================================================
# ABA 1 — CÁLCULO DE JUROS PURO
# ============================================================

def _aba_calculo_juros(usuario):
    st.markdown("### Calcular juros e multa de títulos")
    st.caption(
        "Sobe o arquivo .xlsx e calcula quanto cada título tem de juros e multa, "
        "considerando o atraso. Não simula parcelamento."
    )

    # Parâmetros
    col1, col2, col3 = st.columns(3)
    with col1:
        data_acordo = st.date_input(
            "Data do acordo",
            value=date.today(),
            format="DD/MM/YYYY",
            key="calc_juros_data",
        )
    with col2:
        pct_juros = st.number_input(
            "% Juros a.m. dos títulos",
            min_value=0.0, max_value=50.0,
            value=8.0, step=0.1, format="%.2f",
            key="calc_juros_pct",
        )
    with col3:
        pct_multa = st.number_input(
            "% Multa fixa dos títulos",
            min_value=0.0, max_value=50.0,
            value=2.0, step=0.1, format="%.2f",
            key="calc_multa_pct",
        )

    # Upload
    st.markdown("### Títulos")
    tab_up, tab_tpl = st.tabs(["📤 Upload .xlsx", "📋 Template"])

    with tab_up:
        arq = st.file_uploader(
            "Selecione o arquivo de títulos",
            type=["xls", "xlsx"],
            key="calc_juros_upload",
        )
        if arq:
            bytes_arq = arq.read()
            res = importar_xlsx_titulos(bytes_arq, arq.name)
            # Espaçamento pra evitar sobreposição com o file_uploader
            st.markdown("<br>", unsafe_allow_html=True)
            _mostrar_feedback_upload(res)
            if not res.tem_erros_bloqueantes:
                st.session_state["calc_juros_boletos"] = res.boletos

    with tab_tpl:
        st.caption("Baixe o modelo de arquivo .xlsx com as colunas certinhas.")
        st.download_button(
            "📥 Baixar template",
            data=gerar_template_xlsx(),
            file_name="template_titulos_lle.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="calc_juros_download_tpl",
        )

    boletos = st.session_state.get("calc_juros_boletos", [])
    if not boletos:
        st.info("👆 Faça o upload de um arquivo .xls ou .xlsx pra começar a simulação.")
        return

    pct_desconto_calc = st.number_input(
        "% Desconto sobre o principal (requer aprovação do admin se > 0)",
        min_value=0.0, max_value=100.0,
        value=0.0, step=0.5, format="%.2f",
        key="calc_pct_desconto",
        help="Desconto aplicado sobre o principal antes do cálculo de juros e multa.",
    )

    # Aplica desconto e CASO 1
    if pct_desconto_calc > 0:
        for b in boletos:
            b.principal = round(b.principal * (1 - pct_desconto_calc / 100), 2)
        st.info(f"💡 Desconto de **{pct_desconto_calc:.2f}%** aplicado sobre o principal.")

    for b in boletos:
        calcular_boleto_caso1(b, data_acordo, pct_juros, pct_multa, data_acordo)

    # Tabela
    st.markdown("### Resultado")
    rows = []
    for b in boletos:
        rows.append({
            "Cód. Parceiro": b.codigo_parceiro,
            "Razão Social": b.razao_social_parceiro,
            "Emp": int(b.empresa),
            "Vendedor": f"{b.codigo_vendedor} {b.nome_vendedor}",
            "Vencimento": formatar_data(b.vencimento),
            "Atraso (d)": b.dias_atraso,
            "Principal": formatar_brl(b.principal),
            "Juros": formatar_brl(b.juros),
            "Multa": formatar_brl(b.multa),
            "Total": formatar_brl(b.total),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    t_p = sum(b.principal for b in boletos)
    t_j = sum(b.juros for b in boletos)
    t_m = sum(b.multa for b in boletos)
    t_t = sum(b.total for b in boletos)

    st.markdown("### Totais")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Principal", formatar_brl(t_p))
    c2.metric("Juros", formatar_brl(t_j))
    c3.metric("Multa", formatar_brl(t_m))
    c4.metric("Total a pagar", formatar_brl(t_t))

    col_clr, _ = st.columns([1, 4])
    with col_clr:
        if st.button("🗑 Limpar", use_container_width=True, key="calc_juros_limpar"):
            if "calc_juros_boletos" in st.session_state:
                del st.session_state["calc_juros_boletos"]
            st.rerun()


# ============================================================
# ABA 2 — SIMULAÇÃO COMPLETA DE ACORDO
# ============================================================

def _aba_simulacao_acordo(usuario):
    st.markdown("### Simular acordo parcelado")
    st.caption(
        "Sobe o arquivo de títulos + define parcelamento e veja o cronograma "
        "completo. Sem cadastrar nada. Se gostar, clica em 'Criar acordo' que "
        "vai direto pro Novo Acordo já preenchido."
    )

    # ============ Upload de títulos ============
    st.markdown("#### 1. Títulos")
    tab_up, tab_tpl = st.tabs(["📤 Upload .xlsx", "📋 Template"])

    with tab_up:
        arq = st.file_uploader(
            "Selecione o arquivo de títulos",
            type=["xls", "xlsx"],
            key="sim_acordo_upload",
        )
        if arq:
            bytes_arq = arq.read()
            res = importar_xlsx_titulos(bytes_arq, arq.name)
            st.markdown("<br>", unsafe_allow_html=True)
            _mostrar_feedback_upload(res)
            if not res.tem_erros_bloqueantes:
                st.session_state["sim_acordo_boletos"] = res.boletos

    with tab_tpl:
        st.download_button(
            "📥 Baixar template",
            data=gerar_template_xlsx(),
            file_name="template_titulos_lle.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="sim_acordo_download_tpl",
        )

    boletos = st.session_state.get("sim_acordo_boletos", [])
    if not boletos:
        st.info("👆 Faça o upload de um arquivo .xls ou .xlsx pra simular o acordo.")
        return

    # ============ Parâmetros financeiros ============
    st.markdown("#### 2. Parâmetros financeiros")
    col_d, _ = st.columns([1, 2])
    with col_d:
        data_acordo = st.date_input(
            "Data do acordo",
            value=date.today(),
            format="DD/MM/YYYY",
            key="sim_data_acordo",
        )

    c1, c2 = st.columns(2)
    with c1:
        pct_juros = st.number_input(
            "% Juros ao mês (títulos)",
            min_value=0.0, max_value=50.0, value=8.0, step=0.1, format="%.2f",
            key="sim_pct_juros",
        )
    with c2:
        pct_multa = st.number_input(
            "% Multa fixa (títulos)",
            min_value=0.0, max_value=50.0, value=2.0, step=0.1, format="%.2f",
            key="sim_pct_multa",
        )

    c3, c4 = st.columns(2)
    with c3:
        pct_juros_mora = st.number_input(
            "% Juros de mora a.m. (se parcela atrasar)",
            min_value=0.0, max_value=50.0, value=5.0, step=0.1, format="%.2f",
            key="sim_pct_juros_mora",
        )
    with c4:
        pct_multa_mora = st.number_input(
            "% Multa de mora (se parcela atrasar)",
            min_value=0.0, max_value=50.0, value=2.0, step=0.1, format="%.2f",
            key="sim_pct_multa_mora",
        )

    pct_desconto = st.number_input(
        "% Desconto sobre o principal (requer aprovação do admin se > 0)",
        min_value=0.0, max_value=100.0, value=0.0, step=0.5, format="%.2f",
        key="sim_pct_desconto",
        help="Desconto aplicado sobre o principal antes do cálculo de juros e multa.",
    )

    # ============ Configuração do parcelamento ============
    st.markdown("#### 3. Parcelamento")
    col_a, col_b = st.columns(2)
    with col_a:
        tipo = st.selectbox(
            "Tipo de cobrança",
            ["BOLETO", "PIX"],
            key="sim_tipo_cobranca",
        )
        periodicidade = st.selectbox(
            "Periodicidade",
            ["MENSAL", "QUINZENAL", "SEMANAL", "PERSONALIZADA"],
            key="sim_periodicidade",
        )
        intervalo_pers = 1
        if periodicidade == "PERSONALIZADA":
            intervalo_pers = st.number_input(
                "A cada quantos dias?",
                min_value=1, max_value=365, value=1,
                key="sim_intervalo_pers",
            )

    with col_b:
        modo = st.radio(
            "Definir por:",
            ["Quantidade de parcelas", "Valor da parcela", "Personalizado (Qtd + Valor)"],
            horizontal=True,
            key="sim_modo_parcelamento",
        )
        if modo == "Quantidade de parcelas":
            qtd_parcelas = st.number_input(
                "Quantidade",
                min_value=1, max_value=240, value=12,
                key="sim_qtd",
            )
            valor_parcela = 0.0
        elif modo == "Valor da parcela":
            valor_parcela = st.number_input(
                "Valor de cada parcela (R$)",
                min_value=0.01, value=2400.0, step=100.0, format="%.2f",
                key="sim_valor",
            )
            qtd_parcelas = 0
        else:  # Personalizado (Qtd + Valor)
            st.caption(
                "💡 **Modo livre:** o total pode ultrapassar a dívida calculada com juros."
            )
            qtd_parcelas = st.number_input(
                "Quantidade",
                min_value=1, max_value=240, value=12,
                key="sim_qtd_livre",
            )
            valor_parcela = st.number_input(
                "Valor de cada parcela (R$)",
                min_value=0.01, value=2400.0, step=100.0, format="%.2f",
                key="sim_valor_livre",
            )

        data_primeira = st.date_input(
            "Data da 1ª parcela",
            value=date.today(),
            format="DD/MM/YYYY",
            key="sim_data_primeira",
        )

    # ============ Simular ============
    st.markdown("---")
    if st.button(
        "▶ Simular acordo",
        type="primary",
        use_container_width=True,
        key="sim_simular_btn",
    ):
        try:
            # Aplica desconto sobre o principal antes do cálculo
            if pct_desconto > 0:
                for b in boletos:
                    b.principal = round(b.principal * (1 - pct_desconto / 100), 2)
                st.info(f"💡 Desconto de {pct_desconto:.2f}% aplicado sobre o principal.")

            if modo == "Quantidade de parcelas":
                parcelas_sim = montar_acordo_qtd_fixa(
                    boletos=boletos,
                    data_acordo=data_acordo,
                    pct_juros_mes=pct_juros,
                    pct_multa=pct_multa,
                    qtd_parcelas=int(qtd_parcelas),
                    data_primeira_parcela=data_primeira,
                    periodicidade=Periodicidade(periodicidade),
                    intervalo_personalizado_dias=int(intervalo_pers),
                )
            elif modo == "Valor da parcela":
                parcelas_sim = montar_acordo_valor_fixo(
                    boletos=boletos,
                    data_acordo=data_acordo,
                    pct_juros_mes=pct_juros,
                    pct_multa=pct_multa,
                    valor_parcela=float(valor_parcela),
                    data_primeira_parcela=data_primeira,
                    periodicidade=Periodicidade(periodicidade),
                    intervalo_personalizado_dias=int(intervalo_pers),
                )
            else:  # Personalizado (Qtd + Valor)
                from src.servicos.fifo import montar_acordo_qtd_e_valor_livre
                parcelas_sim = montar_acordo_qtd_e_valor_livre(
                    boletos=boletos,
                    data_acordo=data_acordo,
                    pct_juros_mes=pct_juros,
                    pct_multa=pct_multa,
                    qtd_parcelas=int(qtd_parcelas),
                    valor_parcela=float(valor_parcela),
                    data_primeira_parcela=data_primeira,
                    periodicidade=Periodicidade(periodicidade),
                    intervalo_personalizado_dias=int(intervalo_pers),
                )
            st.session_state["sim_acordo_parcelas"] = parcelas_sim
            st.session_state["sim_acordo_boletos_calc"] = boletos
        except Exception as e:
            st.error(f"Erro no cálculo: {e}")
            return

    # ============ Resultado da simulação ============
    parcelas_sim = st.session_state.get("sim_acordo_parcelas")
    if not parcelas_sim:
        return

    erros = validar_consistencia(boletos, parcelas_sim, tolerancia=0.05)
    if erros:
        st.warning(
            "⚠ Pequenas diferenças de arredondamento detectadas:\n"
            + "\n".join(f"- {e}" for e in erros)
        )

    st.markdown("#### 📅 Cronograma simulado")
    rows = []
    for p in parcelas_sim:
        rows.append({
            "Nº": p.numero,
            "Vencimento": formatar_data(p.vencimento_atual),
            "Valor": formatar_brl(p.valor_original),
            "Principal": formatar_brl(p.principal),
            "Juros": formatar_brl(p.juros),
            "Multa": formatar_brl(p.multa),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # IMPORTANTE: usar a lista de boletos JÁ CALCULADA (com juros aplicados),
    # não a original do upload. A lista calculada está no session_state.
    boletos_calc = st.session_state.get("sim_acordo_boletos_calc", boletos)

    total_geral = sum(p.valor_original for p in parcelas_sim)
    t_p = sum(b.principal for b in boletos_calc)
    t_j = sum(b.juros for b in boletos_calc)
    t_m = sum(b.multa for b in boletos_calc)

    # Diferença entre o total das parcelas e a soma boletos.total
    # = juros/encargos "embutidos" pelo usuário (modo livre ou diferença de arredondamento)
    soma_boletos_total = t_p + t_j + t_m
    juros_embutidos = round(total_geral - soma_boletos_total, 2)

    st.markdown("#### Totais")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Parcelas", str(len(parcelas_sim)))
    c2.metric("Principal", formatar_brl(t_p))
    # Mostra juros calculados + diferença embutida pelo usuário (modo livre)
    juros_total_mostrado = t_j + max(0, juros_embutidos)
    c3.metric("Juros", formatar_brl(juros_total_mostrado))
    c4.metric("Multa", formatar_brl(t_m))
    c5.metric("Total a pagar", formatar_brl(total_geral))

    # Aviso quando há juros embutidos (modo livre) — pra usuário entender de onde vem
    if abs(juros_embutidos) > 0.10:
        if juros_embutidos > 0:
            st.caption(
                f"💡 **{formatar_brl(juros_embutidos)} de juros foram embutidos** "
                f"no valor das parcelas (você escolheu um valor superior ao calculado com juros e multa)."
            )
        else:
            st.caption(
                f"💡 **Desconto de {formatar_brl(abs(juros_embutidos))}** aplicado "
                f"(você escolheu um valor inferior ao calculado)."
            )

    # ============ Botão de baixar Proposta de Acordo (PDF) ============
    st.markdown("---")
    st.markdown("#### 📄 Documentos disponíveis nesta etapa")
    st.caption(
        "Nesta fase de simulação você pode gerar uma **Proposta de Acordo** "
        "(PDF) pra enviar ao cliente antes de criar o acordo de verdade."
    )

    col_prop_btn, _ = st.columns([2, 3])
    with col_prop_btn:
        if st.button(
            "📥 Gerar Proposta de Acordo (PDF)",
            use_container_width=True,
            key="sim_proposta_btn",
        ):
            from src.servicos.exportador_pdf import gerar_pdf_proposta_acordo
            from src.utils.formatadores import slugificar
            from datetime import datetime

            # Pega o cliente do primeiro boleto (se disponível) — proposta
            # serve pra mostrar a simulação antes mesmo de cadastrar
            cliente_nome = "CLIENTE A SER DEFINIDO"
            if boletos:
                cliente_nome = boletos[0].razao_social_parceiro

            pdf_bytes = gerar_pdf_proposta_acordo(
                cliente_nome=cliente_nome,
                cliente_cnpj=None,
                cliente_endereco=None,
                cliente_bairro=None,
                cliente_cidade=None,
                cliente_uf=None,
                parcelas=parcelas_sim,
            )
            st.session_state["sim_proposta_pdf"] = pdf_bytes
            st.session_state["sim_proposta_nome"] = (
                f"PropostaAcordo_{slugificar(cliente_nome)}_"
                f"{datetime.now().strftime('%Y%m%d')}.pdf"
            )

    if "sim_proposta_pdf" in st.session_state:
        col_dl, _ = st.columns([2, 3])
        with col_dl:
            st.download_button(
                "⬇ Baixar Proposta",
                data=st.session_state["sim_proposta_pdf"],
                file_name=st.session_state["sim_proposta_nome"],
                mime="application/pdf",
                use_container_width=True,
                key="sim_proposta_dl",
            )

    # ============ Botão de virar acordo de verdade ============
    st.markdown("---")
    col_criar, col_limpar = st.columns([3, 1])
    with col_criar:
        if st.button(
            "✅ Criar acordo com esta simulação",
            type="primary",
            use_container_width=True,
            key="sim_criar_acordo_btn",
        ):
            # Empacota TUDO no session_state pra ser consumido pelo Wizard
            # IMPORTANTE: passamos os boletos JÁ CALCULADOS (com juros/multa preenchidos
            # pelo montar_acordo_*), não os originais — senão o wizard começa sem juros.
            boletos_calc = st.session_state.get("sim_acordo_boletos_calc", boletos)
            st.session_state["pre_calc_boletos"] = boletos_calc
            st.session_state["pre_calc_data_acordo"] = data_acordo
            st.session_state["pre_calc_juros"] = pct_juros
            st.session_state["pre_calc_multa"] = pct_multa
            st.session_state["pre_calc_juros_mora"] = pct_juros_mora
            st.session_state["pre_calc_multa_mora"] = pct_multa_mora
            st.session_state["pre_calc_desconto"] = pct_desconto
            st.session_state["pre_calc_tipo_cobranca"] = tipo
            st.session_state["pre_calc_periodicidade"] = periodicidade
            st.session_state["pre_calc_intervalo_pers"] = int(intervalo_pers)
            # Mapeia o modo da calculadora pro modo do wizard
            if modo == "Quantidade de parcelas":
                modo_wizard = "QTD"
            elif modo == "Valor da parcela":
                modo_wizard = "VALOR"
            else:  # Personalizado
                modo_wizard = "LIVRE"
            st.session_state["pre_calc_modo"] = modo_wizard
            st.session_state["pre_calc_qtd_parcelas"] = int(qtd_parcelas) if qtd_parcelas else 12
            st.session_state["pre_calc_valor_parcela"] = float(valor_parcela)
            st.session_state["pre_calc_data_primeira"] = data_primeira
            # Marca que tem simulação pra consumir
            st.session_state["pre_calc_disponivel"] = True
            # Limpa wizard anterior se houver, pra começar com a simulação
            if "wizard" in st.session_state:
                del st.session_state["wizard"]

            st.success(
                "✓ Simulação carregada! Clicando em 'Novo Acordo' no menu lateral "
                "os campos virão preenchidos. Só preencha os dados do cliente e avance."
            )
            # Tenta navegar automaticamente pro Wizard
            try:
                st.switch_page("pages/2_➕_Novo_Acordo.py")
            except Exception:
                pass

    with col_limpar:
        if st.button("🗑 Limpar", use_container_width=True, key="sim_limpar_btn"):
            for k in ("sim_acordo_boletos", "sim_acordo_parcelas",
                      "sim_acordo_boletos_calc"):
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
