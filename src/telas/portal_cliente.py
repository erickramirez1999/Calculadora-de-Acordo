"""
Tela do Portal do Cliente.
Acesso público via token.
Cliente vê os títulos cadastrados, monta uma proposta e envia pra equipe.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List

import streamlit as st

from src.banco import repo_portal, repos_auxiliares
from src.utils.formatadores import formatar_brl, formatar_data
from src.utils.marca import AZUL_ESCURO, AMARELO, VERDE


def renderizar_portal():
    """Ponto de entrada do portal público."""
    # Pega token da URL
    qparams = st.query_params
    token = qparams.get("token", "")

    if not token:
        _tela_token_invalido("Link inválido. Por favor, use o link enviado pela LLE.")
        return

    # Busca o token no banco
    info = repo_portal.buscar_token(token)
    if not info:
        _tela_token_invalido(
            "Esse link expirou ou já foi utilizado. Entre em contato com a "
            "equipe da LLE pra receber um novo."
        )
        return

    # Tudo OK, mostra o portal
    cliente_id = info["cliente_id"]
    cliente_nome = info["nome_principal"]

    # Cabeçalho LLE
    _cabecalho_lle()

    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO}; margin-bottom:4px;'>"
        f"Olá, {cliente_nome}! 👋</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Aqui você pode montar uma proposta de acordo pra sua dívida com a LLE.")

    # Verifica se já enviou proposta com esse token
    if st.session_state.get(f"proposta_enviada_{token}"):
        _tela_proposta_enviada()
        return

    # Busca títulos do cliente
    titulos = repo_portal.listar_titulos_avulsos_do_cliente(cliente_id)

    if not titulos:
        st.warning(
            "Não encontramos títulos em aberto pra negociar. "
            "Entre em contato com a equipe da LLE pra mais informações."
        )
        return

    # === BLOCO 1: SELEÇÃO DE TÍTULOS ===
    st.markdown("---")
    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:6px;'>"
        f"📋 Selecione os títulos que deseja negociar</h3>",
        unsafe_allow_html=True,
    )

    chave_sel = f"portal_sel_{token}"
    if chave_sel not in st.session_state:
        st.session_state[chave_sel] = {t["id"]: True for t in titulos}

    sel = st.session_state[chave_sel]

    # Controles
    col_marcar, col_resumo = st.columns([2, 3])
    with col_marcar:
        ca, cb = st.columns(2)
        with ca:
            if st.button("☑ Marcar todos", use_container_width=True, key="port_marcar"):
                for t in titulos:
                    st.session_state[chave_sel][t["id"]] = True
                    widget_key = f"port_chk_{t['id']}"
                    if widget_key in st.session_state:
                        del st.session_state[widget_key]
                st.rerun()
        with cb:
            if st.button("☐ Desmarcar todos", use_container_width=True, key="port_desmarcar"):
                for t in titulos:
                    st.session_state[chave_sel][t["id"]] = False
                    widget_key = f"port_chk_{t['id']}"
                    if widget_key in st.session_state:
                        del st.session_state[widget_key]
                st.rerun()

    qtd_sel = sum(1 for v in sel.values() if v)
    total_sel = sum(t["principal"] for t in titulos if sel.get(t["id"], False))

    with col_resumo:
        cor = VERDE if qtd_sel > 0 else "#DC3545"
        st.markdown(
            f"<div style='text-align:right; padding-top:6px;'>"
            f"<b style='color:{cor}; font-size:16px;'>"
            f"{qtd_sel} de {len(titulos)} título(s) marcados</b><br>"
            f"<span style='font-size:13px; color:#444;'>"
            f"Total: <b>{formatar_brl(total_sel)}</b></span></div>",
            unsafe_allow_html=True,
        )

    # Lista
    container = st.container(height=350 if len(titulos) > 6 else None)
    with container:
        for t in titulos:
            col_chk, col_info, col_val = st.columns([0.5, 5, 2])
            with col_chk:
                marcado = st.checkbox(
                    " ", value=sel.get(t["id"], True),
                    key=f"port_chk_{t['id']}",
                    label_visibility="collapsed",
                )
                st.session_state[chave_sel][t["id"]] = marcado
            with col_info:
                cor = "#222" if marcado else "#999"
                st.markdown(
                    f"<div style='color:{cor}; font-size:13px; padding-top:4px;'>"
                    f"<b>{t['codigo_parceiro']}</b> · "
                    f"{t['razao_social_parceiro'][:40]}<br>"
                    f"<span style='font-size:11px;'>"
                    f"Vencimento: {formatar_data(t['vencimento'])} · "
                    f"Nota {t['numero_nota']}"
                    f"</span></div>",
                    unsafe_allow_html=True,
                )
            with col_val:
                cor = AZUL_ESCURO if marcado else "#999"
                st.markdown(
                    f"<div style='text-align:right; color:{cor}; "
                    f"font-weight:700; padding-top:8px;'>"
                    f"{formatar_brl(t['principal'])}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("<hr style='margin:2px 0; border-color:#EEE;'>", unsafe_allow_html=True)

    if qtd_sel == 0:
        st.info("👆 Marque os títulos que deseja negociar pra continuar.")
        return

    titulos_sel = [t for t in titulos if sel.get(t["id"], False)]
    titulos_ids_sel = [t["id"] for t in titulos_sel]

    # === BLOCO 2: PARÂMETROS DO ACORDO ===
    st.markdown("---")
    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:6px;'>"
        f"💰 Como você quer pagar?</h3>",
        unsafe_allow_html=True,
    )

    # Pega parâmetros do sistema
    params = _carregar_parametros_portal()

    col_per, col_parc = st.columns(2)
    with col_per:
        periodicidade = st.selectbox(
            "Periodicidade",
            options=["SEMANAL", "QUINZENAL", "MENSAL"],
            format_func=lambda x: {"SEMANAL": "Semanal", "QUINZENAL": "Quinzenal", "MENSAL": "Mensal"}[x],
            key="port_periodicidade",
        )

    # Define limites baseado na periodicidade
    if periodicidade == "SEMANAL":
        max_parc = int(params["max_parcelas_semanal"])
        min_parcela = float(params["parcela_minima_semanal"])
        dias_prazo = int(params["prazo_primeira_parcela_semanal_dias"])
    elif periodicidade == "QUINZENAL":
        max_parc = int(params["max_parcelas_quinzenal"])
        min_parcela = float(params["parcela_minima_quinzenal"])
        dias_prazo = int(params["prazo_primeira_parcela_quinzenal_dias"])
    else:
        max_parc = int(params["max_parcelas_mensal"])
        min_parcela = float(params["parcela_minima_mensal"])
        dias_prazo = int(params["prazo_primeira_parcela_mensal_dias"])

    with col_parc:
        qtd_parcelas = st.number_input(
            f"Quantidade de parcelas (até {max_parc})",
            min_value=1, max_value=max_parc, value=min(10, max_parc),
            step=1, key="port_qtd_parcelas",
        )

    # Data da primeira parcela
    hoje = date.today()
    data_max = hoje + timedelta(days=dias_prazo)
    data_primeira = st.date_input(
        f"Quando você quer pagar a primeira parcela? (até {data_max.strftime('%d/%m/%Y')})",
        value=hoje + timedelta(days=min(7, dias_prazo)),
        min_value=hoje,
        max_value=data_max,
        key="port_data_primeira",
        format="DD/MM/YYYY",
    )

    # === CÁLCULO DA PARCELA ===
    # Aplica juros/multa do parâmetro padrão (cliente NÃO vê esses números)
    pct_juros_mes = float(params.get("pct_juros_titulos_default", 8.0))
    pct_multa = float(params.get("pct_multa_titulos_default", 2.0))

    # Calculo simplificado: principal + multa + juros proporcionais
    # (versão simples pro portal, sistema vai recalcular no acordo final)
    valor_com_juros_multa = _calcular_valor_total_portal(
        titulos_sel, data_primeira, pct_juros_mes, pct_multa,
    )
    valor_parcela = round(valor_com_juros_multa / qtd_parcelas, 2)

    # Mostra resumo
    st.markdown(
        f"<div style='background:#F4F6FA; border-left:5px solid {AZUL_ESCURO}; "
        f"padding:16px; border-radius:6px; margin-top:16px;'>"
        f"<div style='font-size:13px; color:#666;'>Sua proposta</div>"
        f"<div style='font-size:28px; font-weight:800; color:{AZUL_ESCURO};'>"
        f"{qtd_parcelas}x de {formatar_brl(valor_parcela)}</div>"
        f"<div style='font-size:13px; color:#666; margin-top:4px;'>"
        f"Total: {formatar_brl(valor_parcela * qtd_parcelas)} · "
        f"{periodicidade.capitalize().replace('Mensal', 'Mensal')} · "
        f"1ª em {data_primeira.strftime('%d/%m/%Y')}"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # === VALIDAÇÃO DE PARÂMETROS ===
    dentro_parametros = valor_parcela >= min_parcela
    if not dentro_parametros:
        st.warning(
            f"⚠ A parcela mínima para {periodicidade.lower()} é "
            f"**{formatar_brl(min_parcela)}**. "
            f"Sua proposta está abaixo. Mesmo assim você pode enviar a proposta "
            f"para análise da nossa equipe."
        )

    # Observação do cliente
    observacao = st.text_area(
        "💬 Quer deixar alguma observação para a equipe? (opcional)",
        placeholder="Ex: Estou em recuperação financeira... / Posso adiantar pagamentos...",
        max_chars=500,
        key="port_obs",
    )

    # === ENVIAR PROPOSTA ===
    st.markdown("---")
    if st.button(
        "📨 Enviar proposta para análise",
        type="primary", use_container_width=True,
        key="port_enviar",
    ):
        # Cria a proposta
        repo_portal.criar_proposta(
            token_id=info["id"],
            cliente_id=cliente_id,
            titulos_ids=titulos_ids_sel,
            periodicidade=periodicidade,
            qtd_parcelas=int(qtd_parcelas),
            data_primeira_parcela=data_primeira.isoformat(),
            valor_parcela=valor_parcela,
            valor_total=valor_parcela * qtd_parcelas,
            observacao_cliente=observacao if observacao else None,
        )
        # Marca títulos como EM_PROPOSTA
        repo_portal.marcar_titulos_em_proposta(titulos_ids_sel)
        # Invalida o token (já foi usado)
        repo_portal.marcar_token_usado(info["id"])
        # Marca na sessão
        st.session_state[f"proposta_enviada_{token}"] = True
        st.rerun()


# ============================================================
# HELPERS
# ============================================================

def _cabecalho_lle():
    """Cabeçalho LLE no topo do portal."""
    st.markdown(
        f"""
<div style='background:{AZUL_ESCURO}; padding:14px 20px; border-radius:8px;
            margin-bottom:24px; border-left:5px solid {AMARELO};'>
    <div style='color:{AMARELO}; font-size:12px; font-weight:700; letter-spacing:2px;'>
        GRUPO LLE
    </div>
    <div style='color:#FFFFFF; font-size:18px; font-weight:700;'>
        Portal de Acordos
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _tela_token_invalido(msg):
    _cabecalho_lle()
    st.error(msg)
    st.markdown(
        "<p style='text-align:center; margin-top:30px; color:#666;'>"
        "📞 Em caso de dúvidas, entre em contato com a LLE."
        "</p>",
        unsafe_allow_html=True,
    )


def _tela_proposta_enviada():
    st.markdown(
        f"""
<div style='background:#D4EDDA; border-left:5px solid {VERDE};
            padding:24px; border-radius:8px; margin-top:24px;'>
    <div style='font-size:48px; text-align:center; margin-bottom:16px;'>✅</div>
    <h2 style='color:{AZUL_ESCURO}; text-align:center; margin-bottom:8px;'>
        Sua proposta foi enviada!
    </h2>
    <p style='text-align:center; color:#1A1D2E; font-size:15px;'>
        Nossa equipe vai analisar e entrar em contato em breve via WhatsApp.
    </p>
</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center; margin-top:30px; color:#666;'>"
        "Você já pode fechar essa página."
        "</p>",
        unsafe_allow_html=True,
    )


def _carregar_parametros_portal() -> dict:
    """Carrega os parâmetros do portal do banco, com defaults caso não exista."""
    # Defaults pra caso o banco ainda não tenha os parâmetros (migrations antigas)
    defaults = {
        "parcela_minima_semanal": "250.00",
        "max_parcelas_semanal": "40",
        "prazo_primeira_parcela_semanal_dias": "15",
        "parcela_minima_quinzenal": "500.00",
        "max_parcelas_quinzenal": "20",
        "prazo_primeira_parcela_quinzenal_dias": "30",
        "parcela_minima_mensal": "2000.00",
        "max_parcelas_mensal": "12",
        "prazo_primeira_parcela_mensal_dias": "20",
        "pct_juros_titulos_default": "8.00",
        "pct_multa_titulos_default": "2.00",
    }

    chaves = [
        "portal.parcela_minima_semanal", "portal.max_parcelas_semanal",
        "portal.prazo_primeira_parcela_semanal_dias",
        "portal.parcela_minima_quinzenal", "portal.max_parcelas_quinzenal",
        "portal.prazo_primeira_parcela_quinzenal_dias",
        "portal.parcela_minima_mensal", "portal.max_parcelas_mensal",
        "portal.prazo_primeira_parcela_mensal_dias",
        "calculo.pct_juros_titulos_default", "calculo.pct_multa_titulos_default",
    ]
    valores = dict(defaults)  # começa com defaults
    for chave in chaves:
        try:
            v = repos_auxiliares.get_parametro(chave)
            if v is not None:
                # Tira "portal." e "calculo." do prefixo
                nome_curto = chave.replace("portal.", "").replace("calculo.", "")
                valores[nome_curto] = v
        except Exception:
            pass
    return valores


def _calcular_valor_total_portal(titulos, data_primeira, pct_juros_mes, pct_multa):
    """Cálculo simples pro portal mostrar o valor estimado.

    O valor real será recalculado quando o acordo for criado pela equipe.
    """
    from datetime import datetime as _dt
    total = 0.0
    hoje = date.today()
    for t in titulos:
        principal = float(t["principal"])
        # Multa fixa
        valor = principal * (1 + pct_multa / 100)
        # Juros proporcionais aos dias entre vencimento e data primeira parcela
        try:
            venc = _dt.fromisoformat(t["vencimento"][:10]).date()
        except Exception:
            venc = hoje
        if data_primeira > venc:
            dias = (data_primeira - venc).days
            meses = dias / 30
            valor = valor * (1 + (pct_juros_mes / 100) * meses)
        total += valor
    return round(total, 2)
