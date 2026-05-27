"""Página Início — lista de acordos ativos."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.estilo import aplicar_css_lle
from src.banco.schema import inicializar_banco

st.set_page_config(page_title="Início · LLE Acordos", page_icon="🏠", layout="wide")

if "banco_inicializado" not in st.session_state:
    inicializar_banco()
    st.session_state["banco_inicializado"] = True

aplicar_css_lle()

# Bloqueia acesso sem login
from src.utils.auth_guard import exigir_login_ou_parar
usuario = exigir_login_ou_parar()

# Se tem acordo aberto, mostra detalhe
if st.session_state.get("acordo_id_aberto"):
    from src.telas.detalhe_acordo import renderizar_detalhe
    renderizar_detalhe(usuario, st.session_state["acordo_id_aberto"])
else:
    from src.telas.inicio import renderizar_inicio
    renderizar_inicio(usuario)
