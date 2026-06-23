"""
Tela "👥 Usuários" — consolidação de Negociadores + Aprovações.

Estrutura:
  - Aba "Todos os usuários": lista todos com filtros, pode alterar nome/cargo/senha
  - Aba "Pendentes": cadastros novos esperando aprovação

Permissões:
  - ADMIN: tudo (criar, aprovar, recusar, inativar, alterar cargo, redefinir senha)
  - DIRETORIA: aprovar/recusar pendentes (decisão Erick - 13/05/2026)
  - DIRETORIA: NÃO pode alterar cargo de outros, redefinir senhas, etc.
"""
from __future__ import annotations

import streamlit as st

from src.modelos.tipos import PerfilUsuario
from src.utils.feedback import drenar_mensagens
from src.utils.marca import AZUL_ESCURO


def renderizar_usuarios(usuario):
    drenar_mensagens()
    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO}'>👥 Usuários do Sistema</h1>",
        unsafe_allow_html=True,
    )

    eh_admin = usuario.perfil == PerfilUsuario.ADMIN
    eh_diretoria = usuario.perfil == PerfilUsuario.DIRETORIA

    if eh_admin:
        st.caption(
            "Como administrador, você pode aprovar cadastros, alterar cargos, "
            "redefinir senhas e gerenciar usuários."
        )
    elif eh_diretoria:
        st.caption(
            "Como diretoria, você pode aprovar/recusar cadastros novos e "
            "visualizar a lista de usuários."
        )

    # 2 abas
    aba_todos, aba_pend = st.tabs(["📋 Todos os usuários", "⏳ Aprovações pendentes"])

    with aba_todos:
        # Usa a função existente do demais.py
        from src.telas.demais import renderizar_negociadores
        renderizar_negociadores(usuario)

    with aba_pend:
        # Usa a função existente do demais.py
        from src.telas.demais import renderizar_aprovacoes
        renderizar_aprovacoes(usuario)
