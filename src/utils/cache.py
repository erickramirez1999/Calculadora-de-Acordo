"""
Cache de consultas frequentes ao banco.

Usa o `st.cache_data` do Streamlit, que guarda o resultado em memória da
sessão por um TTL configurável. Quando o TTL expira, a função é chamada de
novo e o resultado atualizado.

Importante:
  - Cache vale só pra DADOS QUE MUDAM POUCO (negociadores, parâmetros,
    clientes ativos). Não dá pra cachear dados sensíveis a tempo real
    (vencimentos do dia, status de acordos individuais).
  - Pra invalidar manualmente, chama `limpar_cache_*()`.
  - O cache é por sessão de usuário (cada um tem o seu).

TTL escolhido: 300s (5 minutos) — equilibra performance e atualização.
"""
from __future__ import annotations

from typing import List, Dict, Any

import streamlit as st

from src.banco import repo_usuario, repo_cliente, repo_extras


TTL_CURTO = 60          # 1 minuto — pra dados mais voláteis (rascunhos)
TTL_MEDIO = 300         # 5 minutos — pra negociadores, parâmetros
TTL_LONGO = 1800        # 30 minutos — pra parâmetros raríssimos


# ============================================================
# NEGOCIADORES (dropdowns)
# ============================================================

@st.cache_data(ttl=TTL_MEDIO, show_spinner=False)
def listar_negociadores_ativos_cached() -> List[Dict[str, Any]]:
    """
    Versão cacheada de listar_negociadores_ativos.
    Retorna dicts (não Usuario) pra ser serializável pelo cache.
    """
    usuarios = repo_usuario.listar_negociadores_ativos()
    return [
        {
            "id": u.id,
            "nome": u.nome,
            "email": u.email,
            "perfil": u.perfil.value,
            "ativo": u.ativo,
        }
        for u in usuarios
    ]


# ============================================================
# PARÂMETROS DO SISTEMA
# ============================================================

@st.cache_data(ttl=TTL_LONGO, show_spinner=False)
def obter_parametros_cached() -> Dict[str, Any]:
    """Versão cacheada de obter_parametros_sistema."""
    return repo_extras.obter_parametros_sistema()


# ============================================================
# CLIENTES ATIVOS
# ============================================================

@st.cache_data(ttl=TTL_MEDIO, show_spinner=False)
def listar_clientes_ativos_cached() -> List[Dict[str, Any]]:
    """Lista de clientes ativos (pra busca/dropdown). Retorna dicts."""
    clientes = repo_cliente.listar_todos()
    return [
        {
            "id": c.id,
            "nome_principal": c.nome_principal,
            "cnpj": c.cnpj,
            "telefone": c.telefone,
            "contato": c.contato,
            "ativo": c.ativo,
        }
        for c in clientes
        if c.ativo
    ]


# ============================================================
# USUÁRIOS POR ID (consultado muito em listagens)
# ============================================================

@st.cache_data(ttl=TTL_MEDIO, show_spinner=False)
def buscar_usuario_por_id_cached(usuario_id: int) -> Dict[str, Any] | None:
    """Versão cacheada de buscar_por_id."""
    u = repo_usuario.buscar_por_id(usuario_id)
    if not u:
        return None
    return {
        "id": u.id,
        "nome": u.nome,
        "email": u.email,
        "perfil": u.perfil.value,
        "ativo": u.ativo,
        "aprovado": u.aprovado,
    }


# ============================================================
# INVALIDAÇÃO MANUAL
# ============================================================

def limpar_cache_negociadores():
    """Chame depois de cadastrar/aprovar/inativar usuário."""
    listar_negociadores_ativos_cached.clear()
    buscar_usuario_por_id_cached.clear()


def limpar_cache_clientes():
    """Chame depois de cadastrar/editar cliente."""
    listar_clientes_ativos_cached.clear()


def limpar_cache_parametros():
    """Chame depois de alterar parâmetros do sistema."""
    obter_parametros_cached.clear()


def limpar_todos_caches():
    """Chame quando suspeitar de dados desatualizados."""
    limpar_cache_negociadores()
    limpar_cache_clientes()
    limpar_cache_parametros()
