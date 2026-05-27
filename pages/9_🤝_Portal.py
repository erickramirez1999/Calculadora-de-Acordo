"""
Página pública do Portal do Cliente.
Cliente acessa via link único com token e pode propor um acordo.

URL: /Portal?token=XXX

NÃO usa o menu lateral da equipe (esconde sidebar).
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.banco.schema import inicializar_banco
from src.utils.estilo import aplicar_css_lle

st.set_page_config(
    page_title="Acordo · LLE",
    page_icon="🤝",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Esconde a sidebar (cliente não vê menu da equipe)
st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] { display: none !important; }
        button[kind="header"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        header[data-testid="stHeader"] { display: none !important; }
        .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 760px; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "banco_inicializado" not in st.session_state:
    inicializar_banco()
    st.session_state["banco_inicializado"] = True

aplicar_css_lle()

from src.telas.portal_cliente import renderizar_portal
renderizar_portal()
