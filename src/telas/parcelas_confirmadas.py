"""
Tela "✅ Parcelas Confirmadas" — histórico completo de pagamentos confirmados.

Filtros disponíveis:
  - 🔍 Termo de busca (CNPJ, nome, código do parceiro)
  - 📅 Período (data início + fim da confirmação)

Permissões: ADMIN e COBRANÇA (Diretoria não acessa).
"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.banco import repo_acordo
from src.modelos.tipos import PerfilUsuario
from src.utils.formatadores import formatar_brl, formatar_data, formatar_hora
from src.utils.marca import AZUL_ESCURO, VERDE, AMARELO


def renderizar_parcelas_confirmadas(usuario):
    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO}'>✅ Parcelas Confirmadas</h1>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Histórico de todas as parcelas confirmadas pelo administrador. "
        "Use os filtros pra encontrar pagamentos específicos."
    )

    # ============ FILTROS ============
    col_t, col_dini, col_dfim, col_atalho = st.columns([3, 1.3, 1.3, 1.4])
    with col_t:
        termo = st.text_input(
            "🔍 Pesquisar",
            placeholder="CNPJ, nome, código do parceiro, vendedor...",
            label_visibility="collapsed",
            key="pc_termo",
        )
    with col_dini:
        data_ini = st.date_input(
            "Data inicial",
            value=None,
            format="DD/MM/YYYY",
            key="pc_data_ini",
        )
    with col_dfim:
        data_fim = st.date_input(
            "Data final",
            value=None,
            format="DD/MM/YYYY",
            key="pc_data_fim",
        )
    with col_atalho:
        atalho = st.selectbox(
            "Período rápido",
            ["—", "Hoje", "Últimos 7 dias", "Últimos 30 dias", "Este mês"],
            label_visibility="collapsed",
        )

    # Aplicar atalhos (sobrescreve data_ini/fim)
    if atalho == "Hoje":
        data_ini = date.today()
        data_fim = date.today()
    elif atalho == "Últimos 7 dias":
        data_ini = date.today() - timedelta(days=7)
        data_fim = date.today()
    elif atalho == "Últimos 30 dias":
        data_ini = date.today() - timedelta(days=30)
        data_fim = date.today()
    elif atalho == "Este mês":
        data_ini = date.today().replace(day=1)
        data_fim = date.today()

    # ============ BUSCA ============
    confirmadas = repo_acordo.listar_parcelas_confirmadas(
        data_inicio=data_ini,
        data_fim=data_fim,
        termo_busca=termo,
    )

    # ============ RESUMO ============
    if not confirmadas:
        st.info("Nenhuma parcela confirmada com esses filtros.")
        return

    total = sum(c["valor_pago"] for c in confirmadas)
    qtd_acordos = len(set(c["acordo_id"] for c in confirmadas))

    st.markdown("<br>", unsafe_allow_html=True)
    col_q, col_a, col_v = st.columns(3)
    with col_q:
        _kpi("Pagamentos", str(len(confirmadas)), AZUL_ESCURO)
    with col_a:
        _kpi("Acordos diferentes", str(qtd_acordos), AZUL_ESCURO)
    with col_v:
        _kpi("Valor total", formatar_brl(total), VERDE)

    st.markdown("<br>", unsafe_allow_html=True)

    # ============ LISTA ============
    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:12px;'>"
        f"Pagamentos ({len(confirmadas)})</h3>",
        unsafe_allow_html=True,
    )

    for c in confirmadas:
        col_info, col_valor, col_btn = st.columns([4, 2, 1.5])
        with col_info:
            cnpj_str = f" · CNPJ {c['cliente_cnpj']}" if c.get("cliente_cnpj") else ""
            data_conf = formatar_data(c.get("confirmado_em"))
            hora_conf = formatar_hora(c.get("confirmado_em"))
            st.markdown(
                f"<div style='background:#F8F9FA; border-left:4px solid {VERDE}; "
                f"padding:10px 14px; border-radius:4px; margin-bottom:8px;'>"
                f"<div style='font-size:15px; font-weight:700; color:{AZUL_ESCURO};'>"
                f"{c['cliente_nome']}{cnpj_str}</div>"
                f"<div style='font-size:13px; color:#555; margin-top:4px;'>"
                f"{c['numero_interno']} · Parcela {c['parcela_numero']} · "
                f"Vencimento {formatar_data(c['parcela_vencimento'])}"
                f"</div>"
                f"<div style='font-size:12px; color:#666; margin-top:4px;'>"
                f"Pago em {formatar_data(c['data_pagamento'])} · "
                f"Confirmado em {data_conf} {hora_conf} por "
                f"<b>{c.get('confirmado_por_nome') or '—'}</b>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_valor:
            st.markdown(
                f"<div style='text-align:right; padding-top:18px;'>"
                f"<div style='font-size:12px; color:#666;'>Valor pago</div>"
                f"<div style='font-size:18px; font-weight:700; color:{VERDE};'>"
                f"{formatar_brl(c['valor_pago'])}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button(
                "👁 Ver acordo",
                key=f"pc_ver_{c['pagamento_id']}",
                use_container_width=True,
            ):
                st.session_state["acordo_id_aberto"] = c["acordo_id"]
                st.switch_page("pages/4_📊_Acordos.py")


def _kpi(titulo: str, valor: str, cor: str):
    """Card pequeno de KPI."""
    st.markdown(
        f"<div style='background:#FFFFFF; border:1px solid #E5E7EB; "
        f"border-radius:6px; padding:12px 16px; text-align:center;'>"
        f"<div style='font-size:12px; color:#666;'>{titulo}</div>"
        f"<div style='font-size:22px; font-weight:700; color:{cor};'>{valor}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
