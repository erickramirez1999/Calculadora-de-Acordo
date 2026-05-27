"""Página Novo Acordo — Wizard."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.estilo import aplicar_css_lle
from src.banco.schema import inicializar_banco

st.set_page_config(page_title="Novo Acordo · LLE", page_icon="➕", layout="wide")

if "banco_inicializado" not in st.session_state:
    inicializar_banco()
    st.session_state["banco_inicializado"] = True

aplicar_css_lle()

from src.utils.auth_guard import exigir_login_ou_parar
usuario = exigir_login_ou_parar()

from src.telas.wizard import renderizar_wizard
renderizar_wizard(usuario)
