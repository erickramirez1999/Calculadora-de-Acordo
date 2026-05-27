"""
Tradutor central de códigos internos pra nomes amigáveis.

O banco/código usa convenção CAIXA_ALTA com underscore (ex: 'PENDENTE_APROVACAO',
'EXPORTAR_TERMO_ACORDO') porque é mais robusto pra busca/filtro/análise/audit.

Mas na UI a gente mostra texto humano. Esse módulo é o ponto único de tradução.
"""
from __future__ import annotations

# ============================================================
# AÇÕES DE AUDITORIA
# ============================================================
ACOES = {
    # Acordos
    "CRIAR_ACORDO": "Criou acordo",
    "ALTERAR_STATUS_ATIVO": "Acordo ativado",
    "ALTERAR_STATUS_QUITADO": "Acordo quitado",
    "ALTERAR_STATUS_QUEBRADO": "Acordo quebrado",
    "ALTERAR_STATUS_CANCELADO": "Acordo cancelado",
    "ALTERAR_STATUS_PENDENTE_APROVACAO": "Acordo enviado para aprovação",
    "REABRIR_ACORDO": "Reabriu acordo encerrado",
    "QUITAR_AUTO": "Acordo quitado automaticamente",
    # Parcelas
    "PAGAMENTO": "Registrou pagamento",
    "CONFIRMAR_PAGAMENTO_ADMIN": "Confirmou pagamento (admin)",
    "DESFAZER_CONFIRMACAO_COBRANCA": "Desfez confirmação de pagamento",
    "ESTORNAR_PAGAMENTO": "Estornou pagamento",
    "REMARCAR_PARCELA": "Remarcou data da parcela",
    # Documentos
    "EXPORTAR_TERMO_ACORDO": "Exportou Termo de Acordo",
    "EXPORTAR_TERMO_CONFISSAO": "Exportou Termo de Confissão",
    "EXPORTAR_CARTA_QUITACAO": "Exportou Carta de Quitação",
    "EXPORTAR_PROPOSTA": "Exportou Proposta de Acordo",
    "EXPORTAR_XLSX": "Exportou planilha (XLSX)",
    "EXPORTAR_PDF": "Exportou PDF do acordo",
    # Cliente
    "EDITAR_CLIENTE": "Editou cadastro do cliente",
    "CRIAR_CLIENTE_INDEPENDENTE": "Cadastrou cliente",
    # Usuários
    "APROVAR_USUARIO": "Aprovou usuário",
    "RECUSAR_USUARIO": "Recusou usuário",
    "REVOGAR_APROVACAO": "Revogou aprovação",
    "INATIVAR_USUARIO": "Inativou usuário",
    "REATIVAR_USUARIO": "Reativou usuário",
    "ALTERAR_NOME_USUARIO": "Alterou nome do usuário",
    "ALTERAR_PROPRIO_NOME": "Alterou o próprio nome",
    "ALTERAR_PERFIL_USUARIO": "Alterou cargo do usuário",
    "REDEFINIR_SENHA_USUARIO": "Redefiniu senha de usuário",
    "TROCAR_PROPRIA_SENHA": "Alterou a própria senha",
    "CRIAR_USUARIO": "Cadastrou usuário",
    "RESETAR_SENHA": "Redefiniu senha",
    # Outros
    "EDITAR_PARAMETROS": "Editou parâmetros do sistema",
}


# ============================================================
# STATUS DE ACORDOS
# ============================================================
STATUS_ACORDO = {
    "RASCUNHO": "Rascunho",
    "PENDENTE_APROVACAO": "Pendente de aprovação",
    "ATIVO": "Ativo",
    "QUITADO": "Quitado",
    "QUEBRADO": "Quebrado",
    "CANCELADO": "Cancelado",
}


# ============================================================
# STATUS DE PARCELAS
# ============================================================
STATUS_PARCELA = {
    "EM_ABERTO": "Em aberto",
    "AGUARDANDO_CONFIRMACAO": "Aguardando confirmação",
    "PARCIAL": "Pago parcial",
    "QUITADA": "Quitada",
}


# ============================================================
# PERFIS DE USUÁRIO
# ============================================================
PERFIS = {
    "ADMIN": "Administrador",
    "COBRANCA": "Cobrança",
    "DIRETORIA": "Diretoria",
}


# ============================================================
# TIPOS DE COMENTÁRIO
# ============================================================
TIPOS_COMENTARIO = {
    "NOTA": "📝 Nota",
    "LIGACAO": "📞 Ligação",
    "WHATSAPP": "💬 WhatsApp",
    "EMAIL": "📧 E-mail",
    "VISITA": "🚪 Visita",
    "OUTRO": "📎 Outro",
}


# ============================================================
# STATUS DE PROMESSAS
# ============================================================
STATUS_PROMESSA = {
    "AGUARDANDO": "Aguardando",
    "CUMPRIDA": "Cumprida",
    "QUEBRADA": "Quebrada",
    "CANCELADA": "Cancelada",
}


# ============================================================
# TIPOS DE COBRANÇA
# ============================================================
TIPOS_COBRANCA = {
    "BOLETO": "Boleto",
    "PIX": "Pix",
}


# ============================================================
# PERIODICIDADES
# ============================================================
PERIODICIDADES = {
    "MENSAL": "Mensal",
    "QUINZENAL": "Quinzenal",
    "SEMANAL": "Semanal",
    "PERSONALIZADA": "Personalizada",
}


# ============================================================
# FUNÇÕES PÚBLICAS
# ============================================================

def traduzir_acao(codigo: str) -> str:
    """Converte código de auditoria pra nome amigável."""
    return ACOES.get(codigo, _humanizar(codigo))


def traduzir_status_acordo(codigo: str) -> str:
    return STATUS_ACORDO.get(codigo, _humanizar(codigo))


def traduzir_status_parcela(codigo: str) -> str:
    return STATUS_PARCELA.get(codigo, _humanizar(codigo))


def traduzir_perfil(codigo: str) -> str:
    return PERFIS.get(codigo, _humanizar(codigo))


def traduzir_tipo_comentario(codigo: str) -> str:
    return TIPOS_COMENTARIO.get(codigo, _humanizar(codigo))


def traduzir_status_promessa(codigo: str) -> str:
    return STATUS_PROMESSA.get(codigo, _humanizar(codigo))


def traduzir_tipo_cobranca(codigo: str) -> str:
    return TIPOS_COBRANCA.get(codigo, _humanizar(codigo))


def traduzir_periodicidade(codigo: str) -> str:
    return PERIODICIDADES.get(codigo, _humanizar(codigo))


def _humanizar(codigo: str) -> str:
    """
    Fallback genérico: converte CAIXA_ALTA_COM_UNDERSCORE em Texto Normal.
    Ex: 'EXPORTAR_TERMO_ACORDO' -> 'Exportar Termo Acordo'
    """
    if not codigo:
        return ""
    palavras = str(codigo).replace("_", " ").lower().split()
    return " ".join(p.capitalize() for p in palavras)
