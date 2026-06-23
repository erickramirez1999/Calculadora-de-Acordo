"""
Tela "⚙ Configurações" — consolidação de Parâmetros + Dashboard + Auditoria.

3 abas:
  - 📊 Dashboard (KPIs, gráficos)
  - 📜 Auditoria (logs do sistema)
  - ⚙ Parâmetros (taxas padrão, configurações)

Permissões:
  - ADMIN: tudo (incluindo alterar parâmetros)
  - DIRETORIA: tudo também (decisão Erick - 13/05/2026)
"""
from __future__ import annotations

import streamlit as st

from src.modelos.tipos import PerfilUsuario
from src.utils.feedback import drenar_mensagens
from src.utils.marca import AZUL_ESCURO


def renderizar_admin_config(usuario):
    drenar_mensagens()
    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO}'>⚙ Configurações</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Painel administrativo com Dashboard, Auditoria e Parâmetros.")

    aba_dash, aba_audit, aba_param = st.tabs([
        "📊 Dashboard",
        "📜 Auditoria",
        "⚙ Parâmetros",
    ])

    with aba_dash:
        from src.telas.demais import renderizar_dashboard
        renderizar_dashboard(usuario)

    with aba_audit:
        from src.telas.demais import renderizar_auditoria
        renderizar_auditoria(usuario)

    with aba_param:
        from src.telas.demais import renderizar_parametros
        renderizar_parametros(usuario)
