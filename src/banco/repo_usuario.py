"""
Repositório de Usuário — CRUD + autenticação com bcrypt.

Implementa a regra de auto-bootstrap (P8): primeiro usuário cadastrado vira ADMIN.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import bcrypt

from src.banco.conexao import obter_conexao, transacao
from src.modelos.tipos import PerfilUsuario


@dataclass
class Usuario:
    """Dataclass de Usuário (representação em memória)."""
    id: int
    nome: str
    email: str
    perfil: PerfilUsuario
    ativo: bool
    deve_trocar_senha: bool
    criado_em: str
    chave_aprovacao: Optional[str] = None
    aprovado: bool = False
    ultimo_login: Optional[str] = None


# ============================================================
# CHAVE DE APROVAÇÃO (sistema de liberação via Secrets)
# ============================================================

def gerar_chave_aprovacao() -> str:
    """
    Gera uma chave aleatória de 12 caracteres em formato amigável:
    XXXX-XXXX-XXXX (letras maiúsculas + dígitos, sem ambiguidades).
    Exemplo: K7P4-N2X9-B5M1
    """
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0, O, 1, I
    partes = []
    for _ in range(3):
        partes.append("".join(secrets.choice(alfabeto) for _ in range(4)))
    return "-".join(partes)


def listar_chaves_aprovadas_do_secrets() -> set[str]:
    """
    Lê as chaves de usuários aprovados a partir do st.secrets.
    Formato esperado no Streamlit Secrets:

        [usuarios_aprovados]
        chaves = ["K7P4-N2X9-B5M1", "ABCD-EFGH-IJKL"]

    Quando o Erick recebe a chave de alguém, adiciona ela na lista acima.
    """
    try:
        import streamlit as st
        if "usuarios_aprovados" in st.secrets:
            chaves = st.secrets["usuarios_aprovados"].get("chaves", [])
            return {str(c).strip().upper() for c in chaves if c}
    except Exception:
        pass
    return set()


def chave_esta_aprovada(chave: str) -> bool:
    """Verifica se a chave do usuário está na lista do Secrets."""
    if not chave:
        return False
    return chave.strip().upper() in listar_chaves_aprovadas_do_secrets()


def _row_para_usuario(row) -> Usuario:
    return Usuario(
        id=row["id"],
        nome=row["nome"],
        email=row["email"],
        perfil=PerfilUsuario(row["perfil"]),
        ativo=bool(row["ativo"]),
        deve_trocar_senha=bool(row["deve_trocar_senha"]),
        criado_em=row["criado_em"],
        chave_aprovacao=row["chave_aprovacao"] if "chave_aprovacao" in row.keys() else None,
        aprovado=bool(row["aprovado"]) if "aprovado" in row.keys() else False,
        ultimo_login=row["ultimo_login"],
    )


def sincronizar_aprovacoes_com_secrets() -> int:
    """
    Lê o Secrets e atualiza o flag `aprovado` dos usuários cujas chaves
    estão na lista. Retorna quantos foram aprovados nesta passada.

    Chamado no startup do app pra propagar mudanças do Secrets.
    """
    aprovadas = listar_chaves_aprovadas_do_secrets()
    if not aprovadas:
        return 0
    with transacao() as conn:
        # Marca como aprovados todos cuja chave está no set
        placeholders = ",".join("?" * len(aprovadas))
        conn.execute(
            f"UPDATE usuario SET aprovado = 1 "
            f"WHERE UPPER(chave_aprovacao) IN ({placeholders});",
            list(aprovadas),
        )
        cur = conn.execute(
            f"SELECT COUNT(*) FROM usuario "
            f"WHERE aprovado = 1 AND UPPER(chave_aprovacao) IN ({placeholders});",
            list(aprovadas),
        )
        return int(cur.fetchone()[0])


# ============================================================
# HASH DE SENHA
# ============================================================

def gerar_hash_senha(senha: str) -> str:
    """Gera hash bcrypt da senha. Cada chamada produz hash diferente, todos válidos."""
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    """Verifica se a senha digitada bate com o hash bcrypt armazenado."""
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), hash_armazenado.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validar_senha_forte(senha: str) -> Optional[str]:
    """
    Retorna mensagem de erro se a senha não for forte. None se OK.
    Regra simples: pelo menos 8 caracteres.
    """
    if not senha or len(senha) < 8:
        return "A senha precisa ter pelo menos 8 caracteres."
    return None


# ============================================================
# CONSULTAS
# ============================================================

def existe_algum_usuario() -> bool:
    """True se já há ao menos um usuário cadastrado."""
    cur = obter_conexao().execute("SELECT 1 FROM usuario LIMIT 1;")
    return cur.fetchone() is not None


def buscar_por_email(email: str) -> Optional[Usuario]:
    cur = obter_conexao().execute(
        "SELECT * FROM usuario WHERE LOWER(email) = LOWER(?);", (email,)
    )
    row = cur.fetchone()
    return _row_para_usuario(row) if row else None


def buscar_por_id(usuario_id: int) -> Optional[Usuario]:
    cur = obter_conexao().execute("SELECT * FROM usuario WHERE id = ?;", (usuario_id,))
    row = cur.fetchone()
    return _row_para_usuario(row) if row else None


def listar_todos(perfil: Optional[PerfilUsuario] = None, apenas_ativos: bool = False) -> List[Usuario]:
    """Lista usuários. Filtros opcionais por perfil e/ou apenas ativos."""
    sql = "SELECT * FROM usuario WHERE 1=1"
    params: list = []
    if perfil is not None:
        sql += " AND perfil = ?"
        params.append(perfil.value)
    if apenas_ativos:
        sql += " AND ativo = 1"
    sql += " ORDER BY nome;"
    cur = obter_conexao().execute(sql, params)
    return [_row_para_usuario(r) for r in cur.fetchall()]


def listar_negociadores_ativos() -> List[Usuario]:
    """Para o dropdown do wizard (Seção 16 + 24): só COBRANÇA ativos. Inclui ADMINs."""
    cur = obter_conexao().execute("""
        SELECT * FROM usuario
        WHERE ativo = 1
          AND perfil IN ('COBRANCA', 'ADMIN')
        ORDER BY nome;
    """)
    return [_row_para_usuario(r) for r in cur.fetchall()]


# ============================================================
# AUTENTICAÇÃO
# ============================================================

def autenticar(email: str, senha: str) -> Optional[Usuario]:
    """
    Autentica usuário. Retorna o Usuario se sucesso, None se falha.
    Atualiza ultimo_login no sucesso.

    NOTA: NÃO bloqueia aqui se aprovado=0. Esse check é feito na camada
    de UI (tela_login em app.py), pra mostrar mensagem amigável com a chave.
    """
    cur = obter_conexao().execute(
        "SELECT * FROM usuario WHERE LOWER(email) = LOWER(?);", (email,)
    )
    row = cur.fetchone()
    if not row:
        return None
    if not row["ativo"]:
        return None
    if not verificar_senha(senha, row["senha_hash"]):
        return None

    # Atualiza último login (não-transacional, não é crítico)
    with transacao() as conn:
        conn.execute(
            "UPDATE usuario SET ultimo_login = datetime('now') WHERE id = ?;",
            (row["id"],),
        )
    return _row_para_usuario(row)


# ============================================================
# ESCRITA (CRUD)
# ============================================================

def criar_usuario(
    nome: str,
    email: str,
    senha: str,
    perfil: PerfilUsuario,
    forcar_admin_se_primeiro: bool = True,
) -> Usuario:
    """
    Cria novo usuário. Gera uma chave_aprovacao única que o Erick precisará
    inserir no Streamlit Secrets pra liberar o acesso.
    Se for o PRIMEIRO usuário, vira ADMIN automaticamente (regra P8).
    Lança ValueError se já existir usuário com o mesmo e-mail.
    """
    nome = (nome or "").strip()
    email = (email or "").strip().lower()
    if not nome:
        raise ValueError("Nome é obrigatório.")
    if not email or "@" not in email:
        raise ValueError("E-mail inválido.")
    err_senha = validar_senha_forte(senha)
    if err_senha:
        raise ValueError(err_senha)
    if buscar_por_email(email) is not None:
        raise ValueError(f"Já existe usuário cadastrado com o e-mail {email}.")

    # Regra de bootstrap: 1º usuário vira ADMIN E é auto-aprovado
    # (caso contrário ele não teria como entrar - é o galinha-ovo do sistema)
    perfil_efetivo = perfil
    eh_primeiro = not existe_algum_usuario()
    if forcar_admin_se_primeiro and eh_primeiro:
        perfil_efetivo = PerfilUsuario.ADMIN

    # Gera chave única (tenta até 5 vezes pra evitar colisão astronômica)
    chave = None
    for _ in range(5):
        candidata = gerar_chave_aprovacao()
        cur = obter_conexao().execute(
            "SELECT 1 FROM usuario WHERE chave_aprovacao = ?;", (candidata,)
        )
        if cur.fetchone() is None:
            chave = candidata
            break
    if not chave:
        raise RuntimeError("Não foi possível gerar chave única. Tente de novo.")

    # Auto-aprova:
    #   (a) se for o primeiro usuário (admin bootstrap, P8)
    #   (b) se a chave já estiver pré-listada no Secrets (caso ímpar mas possível)
    auto_aprovado = eh_primeiro or chave_esta_aprovada(chave)

    senha_hash = gerar_hash_senha(senha)
    with transacao() as conn:
        cur = conn.execute(
            """
            INSERT INTO usuario (
                nome, email, senha_hash, perfil, ativo, deve_trocar_senha,
                chave_aprovacao, aprovado
            )
            VALUES (?, ?, ?, ?, 1, 0, ?, ?);
            """,
            (
                nome, email, senha_hash, perfil_efetivo.value,
                chave, 1 if auto_aprovado else 0,
            ),
        )
        novo_id = cur.lastrowid

    novo = buscar_por_id(novo_id)
    assert novo is not None
    _invalidar_cache_usuario()
    return novo


def atualizar_usuario(
    usuario_id: int,
    nome: Optional[str] = None,
    email: Optional[str] = None,
    perfil: Optional[PerfilUsuario] = None,
) -> Usuario:
    """Atualiza dados do usuário (não atualiza senha — use alterar_senha)."""
    atual = buscar_por_id(usuario_id)
    if atual is None:
        raise ValueError(f"Usuário id={usuario_id} não encontrado.")

    sets = []
    params: list = []
    if nome is not None and nome.strip():
        sets.append("nome = ?")
        params.append(nome.strip())
    if email is not None and email.strip():
        novo_email = email.strip().lower()
        outro = buscar_por_email(novo_email)
        if outro and outro.id != usuario_id:
            raise ValueError(f"Já existe outro usuário com o e-mail {novo_email}.")
        sets.append("email = ?")
        params.append(novo_email)
    if perfil is not None:
        sets.append("perfil = ?")
        params.append(perfil.value)
    if not sets:
        return atual

    params.append(usuario_id)
    with transacao() as conn:
        conn.execute(f"UPDATE usuario SET {', '.join(sets)} WHERE id = ?;", params)

    return buscar_por_id(usuario_id)  # type: ignore


def alterar_senha(usuario_id: int, nova_senha: str, deve_trocar_no_proximo_login: bool = False) -> None:
    err = validar_senha_forte(nova_senha)
    if err:
        raise ValueError(err)
    senha_hash = gerar_hash_senha(nova_senha)
    with transacao() as conn:
        conn.execute(
            "UPDATE usuario SET senha_hash = ?, deve_trocar_senha = ? WHERE id = ?;",
            (senha_hash, 1 if deve_trocar_no_proximo_login else 0, usuario_id),
        )


def inativar_usuario(usuario_id: int) -> None:
    """Inativação não exclui (preserva histórico - Seção 24)."""
    with transacao() as conn:
        conn.execute("UPDATE usuario SET ativo = 0 WHERE id = ?;", (usuario_id,))
    _invalidar_cache_usuario()


def reativar_usuario(usuario_id: int) -> None:
    with transacao() as conn:
        conn.execute("UPDATE usuario SET ativo = 1 WHERE id = ?;", (usuario_id,))
    _invalidar_cache_usuario()


def aprovar_usuario(usuario_id: int) -> None:
    """
    Aprova um usuário diretamente no banco (sem precisar do Secrets).
    Usado pelo ADMIN na tela Negociadores quando o Supabase estiver ativo
    (pra não perder a aprovação em cada upload).
    """
    with transacao() as conn:
        conn.execute(
            "UPDATE usuario SET aprovado = 1 WHERE id = ?;", (usuario_id,)
        )
    _invalidar_cache_usuario()


def recusar_usuario(usuario_id: int) -> None:
    """
    Recusa um usuário: marca aprovado=0 E ativo=0 (impede login).
    Preserva o cadastro pra histórico de auditoria.
    """
    with transacao() as conn:
        conn.execute(
            "UPDATE usuario SET aprovado = 0, ativo = 0 WHERE id = ?;",
            (usuario_id,),
        )
    _invalidar_cache_usuario()


def revogar_aprovacao(usuario_id: int) -> None:
    """
    Revoga a aprovação de um usuário (volta pra status pendente).
    O usuário continua ativo mas não consegue logar até ser aprovado de novo.
    """
    with transacao() as conn:
        conn.execute(
            "UPDATE usuario SET aprovado = 0 WHERE id = ?;", (usuario_id,)
        )
    _invalidar_cache_usuario()


def alterar_nome(usuario_id: int, novo_nome: str) -> None:
    """
    Altera o nome de um usuário. Usado pelo ADMIN pra corrigir cadastros
    (ex: usuário se cadastrou com e-mail no campo nome).
    Também usado pelo próprio usuário NA PRIMEIRA VEZ que abre Meu Perfil
    se o nome dele estiver com e-mail.
    """
    novo_nome = (novo_nome or "").strip()
    if not novo_nome:
        raise ValueError("Nome não pode ficar vazio.")
    if "@" in novo_nome:
        raise ValueError("Nome não pode ser um e-mail. Digite seu nome completo.")
    with transacao() as conn:
        conn.execute(
            "UPDATE usuario SET nome = ? WHERE id = ?;",
            (novo_nome, usuario_id),
        )
    _invalidar_cache_usuario()


def alterar_perfil(usuario_id: int, novo_perfil: PerfilUsuario) -> None:
    """
    Altera o perfil (cargo) de um usuário.
    Usado pelo ADMIN pra promover ou rebaixar negociadores.

    Regras de segurança:
      - Não pode rebaixar o ÚLTIMO admin ativo (sistema ficaria sem admin)
      - Tem que ser um perfil válido
    """
    if not isinstance(novo_perfil, PerfilUsuario):
        raise ValueError("Perfil inválido.")

    # Pega usuário atual
    atual = buscar_por_id(usuario_id)
    if atual is None:
        raise ValueError(f"Usuário id={usuario_id} não encontrado.")

    # Se está REBAIXANDO um admin, verifica se ainda sobra pelo menos um
    if atual.perfil == PerfilUsuario.ADMIN and novo_perfil != PerfilUsuario.ADMIN:
        cur = obter_conexao().execute(
            "SELECT COUNT(*) FROM usuario WHERE perfil = 'ADMIN' AND ativo = 1 AND aprovado = 1;"
        )
        qtd_admins_ativos = int(cur.fetchone()[0])
        if qtd_admins_ativos <= 1:
            raise ValueError(
                "Você não pode rebaixar este usuário — ele é o ÚLTIMO administrador "
                "ativo do sistema. Promova outro usuário a admin antes de rebaixar este."
            )

    with transacao() as conn:
        conn.execute(
            "UPDATE usuario SET perfil = ? WHERE id = ?;",
            (novo_perfil.value, usuario_id),
        )
    _invalidar_cache_usuario()


def _invalidar_cache_usuario():
    """
    Helper interno: chama a invalidação do cache se o Streamlit estiver
    disponível. Em testes/scripts, simplesmente não faz nada (não quebra).
    """
    try:
        from src.utils.cache import limpar_cache_negociadores
        limpar_cache_negociadores()
    except Exception:
        # Streamlit não disponível ou cache ainda não inicializado - ignora.
        pass


def contar_acordos_do_negociador(usuario_id: int) -> int:
    """Quantos acordos esse negociador tem cadastrados (Seção 24 - listagem)."""
    cur = obter_conexao().execute(
        "SELECT COUNT(*) FROM acordo WHERE negociador_id = ?;", (usuario_id,)
    )
    return int(cur.fetchone()[0])
