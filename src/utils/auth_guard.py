"""
Função utilitária para proteção de páginas.

Deve ser chamada NO TOPO de cada página em pages/ — antes de renderizar
qualquer conteúdo. Se o usuário não estiver logado, esconde a navegação,
mostra uma mensagem e PARA a execução.
"""
from __future__ import annotations

import streamlit as st


CSS_SIDEBAR_FIXA = """
<style>
    /* === SIDEBAR FIXA — não permite fechar de jeito nenhum === */
    section[data-testid="stSidebar"] {
        min-width: 260px !important;
        max-width: 260px !important;
        width: 260px !important;
        transform: translateX(0px) !important;
        visibility: visible !important;
        margin-left: 0 !important;
    }

    /* Esconde TODOS os botões que poderiam fechar/abrir a sidebar */
    section[data-testid="stSidebar"] button[kind="header"],
    section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
    section[data-testid="stSidebar"] [data-testid="stSidebarCollapseControl"],
    button[data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarUserContent"] button[kind="header"] {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
    }

    /* Esconde a lista automática de pages do Streamlit (deixamos menu manual) */
    [data-testid="stSidebarNav"] { display: none !important; }

    /* Header limpo */
    header[data-testid="stHeader"] { display: none !important; }

    /* Padding ajustado */
    .main .block-container {
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
</style>
"""


def exigir_login_ou_parar():
    """
    Se não há usuário logado:
      - Esconde a sidebar inteira (incluindo menu de pages)
      - Mostra mensagem com link pra tela de login
      - Para a execução da página (st.stop)

    Se há usuário logado:
      - Aplica CSS de sidebar fixa (esconde aba "app" duplicada)
      - Renderiza o menu manual na sidebar
      - Retorna o usuário
    """
    usuario = st.session_state.get("usuario_atual")
    if usuario is None:
        # CSS pra esconder navegação durante a tela de bloqueio
        st.markdown(
            """
            <style>
                section[data-testid="stSidebar"] { display: none !important; }
                [data-testid="stSidebarNav"] { display: none !important; }
                button[kind="header"] { display: none !important; }
                button[data-testid="collapsedControl"] { display: none !important; }
                header[data-testid="stHeader"] { display: none !important; }
                div[data-testid="stToolbar"] { display: none !important; }
                .block-container {
                    padding-top: 4rem !important;
                    max-width: 600px !important;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.warning("🔒 **Acesso restrito.** Faça login para acessar essa página.")
        st.page_link("app.py", label="← Ir para o login", icon="🏠")
        st.stop()

    # Logado: aplica CSS de sidebar fixa e renderiza o menu manual
    st.markdown(CSS_SIDEBAR_FIXA, unsafe_allow_html=True)
    _renderizar_menu_sidebar(usuario)
    return usuario


def _renderizar_menu_sidebar(usuario):
    """Menu manual na sidebar (chamado em todas as páginas)."""
    from pathlib import Path
    from src.modelos.tipos import PerfilUsuario

    LOGO_BRANCO = Path(__file__).parent.parent.parent / "assets" / "logo_lle_branco.png"
    LOGO_COR = Path(__file__).parent.parent.parent / "assets" / "logo_lle.png"
    logo_a_usar = LOGO_BRANCO if LOGO_BRANCO.exists() else LOGO_COR

    with st.sidebar:
        if logo_a_usar.exists():
            st.image(str(logo_a_usar), use_container_width=True)
        st.markdown("---")
        st.markdown(f"👤 **{usuario.nome}**")
        from src.utils.traducoes import traduzir_perfil
        st.caption(f"Perfil: {traduzir_perfil(usuario.perfil.value)}")
        # Atalho destacado pra Meu Perfil
        st.page_link("pages/0_👤_Meu_Perfil.py", label="👤 Meu Perfil")
        st.markdown("---")

        st.markdown("**Menu**")
        st.page_link("pages/1_🏠_Início.py", label="🏠 Início")
        # "Novo Acordo" foi removido do menu (decisão Erick 13/05/2026)
        # Agora se cria acordo pela tela do cliente: Clientes → Cliente → Novo Acordo
        st.page_link("pages/3_🧮_Calculadora.py", label="🧮 Calculadora")
        st.page_link("pages/2b_📥_Importar_Acordo.py", label="📥 Importar Acordo")
        st.page_link("pages/4_📊_Acordos.py", label="📊 Acordos")
        st.page_link("pages/5_🏢_Clientes.py", label="🏢 Clientes")

        # Parcelas Confirmadas: Admin e Cobrança
        if usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.COBRANCA):
            st.page_link(
                "pages/6_✅_Parcelas_Confirmadas.py",
                label="✅ Parcelas Confirmadas",
            )

        # Admin e Diretoria têm acesso à administração
        if usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA):
            st.markdown("---")
            st.markdown("**Administração**")
            st.page_link("pages/7_👥_Usuários.py", label="👥 Usuários")
            st.page_link("pages/8_⚙_Admin.py", label="⚙ Configurações")

        st.markdown("---")
        if st.button("🚪 Sair", use_container_width=True, key=f"sair_sidebar_{usuario.id}"):
            for k in list(st.session_state.keys()):
                if k not in ("banco_inicializado",):
                    del st.session_state[k]
            st.rerun()
