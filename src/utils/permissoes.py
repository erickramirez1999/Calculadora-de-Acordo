"""
Helpers centralizados de permissões.

Centralizar aqui evita duplicar checagens espalhadas. Se uma regra mudar,
muda só num lugar.

Regras (decisões do Erick - 13/05/2026):
  - ADMIN: pode TUDO
  - DIRETORIA: pode quase tudo igual admin, EXCETO confirmar pagamento
    (parte do fluxo de dupla confirmação Cobrança → Admin)
  - COBRANCA: operacional (criar acordos, registrar pagamento sem confirmar)
"""
from __future__ import annotations

from src.modelos.tipos import PerfilUsuario


def eh_admin(usuario) -> bool:
    """Apenas administradores."""
    return usuario.perfil == PerfilUsuario.ADMIN


def eh_admin_ou_diretoria(usuario) -> bool:
    """Para tudo que Diretoria também pode fazer (acordos, usuários, parâmetros)."""
    return usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA)


def pode_confirmar_pagamento(usuario) -> bool:
    """
    Confirmar pagamento é restrito ao ADMIN (parte da dupla confirmação).
    Diretoria NÃO pode confirmar mesmo sendo "executiva".
    """
    return usuario.perfil == PerfilUsuario.ADMIN


def pode_gerenciar_acordos(usuario) -> bool:
    """Criar, cancelar, reabrir, registrar pagamento."""
    return usuario.perfil in (
        PerfilUsuario.ADMIN,
        PerfilUsuario.DIRETORIA,
        PerfilUsuario.COBRANCA,
    )


def pode_gerenciar_usuarios(usuario) -> bool:
    """Aprovar, recusar, inativar, alterar cargo/nome de outros usuários."""
    return usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA)


def pode_alterar_parametros(usuario) -> bool:
    """Editar parâmetros do sistema (taxas padrão, lembretes etc)."""
    return usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA)


def pode_ver_parcelas_confirmadas(usuario) -> bool:
    """Quem vê o histórico de parcelas confirmadas."""
    return usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.COBRANCA)
