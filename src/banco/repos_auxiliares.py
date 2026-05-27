"""
Repositórios auxiliares.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional

from src.banco.conexao import obter_conexao, transacao


# ============================================================
# AUDITORIA (Seção 18e)
# ============================================================

def registrar_log(
    usuario_id: Optional[int],
    usuario_nome: Optional[str],
    acao: str,
    entidade: str,
    entidade_id: Optional[int] = None,
    contexto: Optional[str] = None,
    antes: Optional[Any] = None,
    depois: Optional[Any] = None,
) -> None:
    """
    Grava uma entrada no log de auditoria.
    `antes` e `depois` podem ser dict/list/scalar — são serializados como JSON.
    """
    def _to_json(v):
        if v is None:
            return None
        try:
            return json.dumps(v, default=str, ensure_ascii=False)
        except Exception:
            return str(v)

    with transacao() as conn:
        conn.execute(
            """
            INSERT INTO log_auditoria (
                usuario_id, usuario_nome_snapshot, acao, entidade,
                entidade_id, contexto, antes_json, depois_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                usuario_id, usuario_nome, acao, entidade,
                entidade_id, contexto, _to_json(antes), _to_json(depois),
            ),
        )


def listar_logs(
    usuario_id: Optional[int] = None,
    entidade: Optional[str] = None,
    desde: Optional[str] = None,
    ate: Optional[str] = None,
    limite: int = 500,
) -> List[dict]:
    """Lista logs com filtros opcionais. Retorna dicts (mais simples pra UI)."""
    sql = "SELECT * FROM log_auditoria WHERE 1=1"
    params: list = []
    if usuario_id is not None:
        sql += " AND usuario_id = ?"
        params.append(usuario_id)
    if entidade:
        sql += " AND entidade = ?"
        params.append(entidade)
    if desde:
        sql += " AND timestamp >= ?"
        params.append(desde)
    if ate:
        sql += " AND timestamp <= ?"
        params.append(ate)
    sql += " ORDER BY timestamp DESC LIMIT ?;"
    params.append(limite)
    cur = obter_conexao().execute(sql, params)
    resultado = []
    for r in cur.fetchall():
        d = dict(r)
        d["antes"] = json.loads(d["antes_json"]) if d.get("antes_json") else None
        d["depois"] = json.loads(d["depois_json"]) if d.get("depois_json") else None
        resultado.append(d)
    return resultado


# ============================================================
# RASCUNHO DE ACORDO (Seção 16b)
# ============================================================

def salvar_rascunho(
    usuario_id: int,
    titulo: str,
    passo_atual: int,
    estado: dict,
    rascunho_id: Optional[int] = None,
) -> int:
    """Cria ou atualiza rascunho. Retorna o id."""
    estado_json = json.dumps(estado, default=str, ensure_ascii=False)
    with transacao() as conn:
        if rascunho_id:
            conn.execute(
                """
                UPDATE rascunho_acordo
                SET titulo = ?, passo_atual = ?, estado_json = ?, atualizado_em = datetime('now')
                WHERE id = ? AND criado_por_id = ?;
                """,
                (titulo, passo_atual, estado_json, rascunho_id, usuario_id),
            )
            return rascunho_id
        cur = conn.execute(
            """
            INSERT INTO rascunho_acordo (criado_por_id, titulo, passo_atual, estado_json)
            VALUES (?, ?, ?, ?);
            """,
            (usuario_id, titulo, passo_atual, estado_json),
        )
        return cur.lastrowid


def listar_rascunhos(usuario_id: int) -> List[dict]:
    """Lista de rascunhos do usuário pra seção 'Meus Rascunhos' do Início."""
    cur = obter_conexao().execute(
        """
        SELECT id, titulo, passo_atual, criado_em, atualizado_em
        FROM rascunho_acordo
        WHERE criado_por_id = ?
        ORDER BY atualizado_em DESC;
        """,
        (usuario_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def listar_rascunhos_todos() -> List[dict]:
    """
    Lista TODOS os rascunhos do sistema, com o nome do criador.
    Usado pelo bloco "Rascunhos" do Início (visível pra Cobrança/Admin/Diretoria).
    """
    cur = obter_conexao().execute(
        """
        SELECT r.id, r.titulo, r.passo_atual, r.criado_em, r.atualizado_em,
               r.criado_por_id, u.nome AS criado_por_nome
        FROM rascunho_acordo r
        JOIN usuario u ON u.id = r.criado_por_id
        ORDER BY r.atualizado_em DESC;
        """,
    )
    return [dict(r) for r in cur.fetchall()]


def buscar_rascunho(rascunho_id: int, usuario_id: int = None) -> Optional[dict]:
    """
    Busca um rascunho. Se usuario_id for None, retorna qualquer rascunho
    (usado pra exibição). Se for fornecido, restringe ao criador
    (usado pra retomar com segurança).
    """
    if usuario_id is None:
        cur = obter_conexao().execute(
            "SELECT * FROM rascunho_acordo WHERE id = ?;",
            (rascunho_id,),
        )
    else:
        cur = obter_conexao().execute(
            "SELECT * FROM rascunho_acordo WHERE id = ? AND criado_por_id = ?;",
            (rascunho_id, usuario_id),
        )
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["estado"] = json.loads(d["estado_json"]) if d["estado_json"] else {}
    return d


def excluir_rascunho(rascunho_id: int, usuario_id: int, eh_admin: bool = False) -> bool:
    """
    Exclui rascunho. Quem pode excluir:
      - O criador
      - Admin (qualquer rascunho)
    Retorna True se excluiu, False se não tinha permissão.
    """
    with transacao() as conn:
        if eh_admin:
            cur = conn.execute(
                "DELETE FROM rascunho_acordo WHERE id = ?;",
                (rascunho_id,),
            )
        else:
            cur = conn.execute(
                "DELETE FROM rascunho_acordo WHERE id = ? AND criado_por_id = ?;",
                (rascunho_id, usuario_id),
            )
        return cur.rowcount > 0


# ============================================================
# PARÂMETROS DO SISTEMA
# ============================================================

def get_parametro(chave: str, default: Optional[str] = None) -> Optional[str]:
    cur = obter_conexao().execute(
        "SELECT valor FROM parametros_sistema WHERE chave = ?;", (chave,)
    )
    row = cur.fetchone()
    return row["valor"] if row else default


def set_parametro(chave: str, valor: str, usuario_id: Optional[int] = None) -> None:
    with transacao() as conn:
        conn.execute(
            """
            INSERT INTO parametros_sistema (chave, valor, atualizado_por_id)
            VALUES (?, ?, ?)
            ON CONFLICT(chave) DO UPDATE SET
                valor = excluded.valor,
                atualizado_em = datetime('now'),
                atualizado_por_id = excluded.atualizado_por_id;
            """,
            (chave, valor, usuario_id),
        )


def listar_parametros() -> dict:
    cur = obter_conexao().execute("SELECT chave, valor FROM parametros_sistema;")
    return {r["chave"]: r["valor"] for r in cur.fetchall()}


# ============================================================
# APROVAÇÃO (P5)
# ============================================================

def criar_solicitacao_aprovacao(
    acordo_id: int,
    solicitado_por_id: int,
    justificativa: str,
) -> int:
    with transacao() as conn:
        cur = conn.execute(
            """
            INSERT INTO aprovacao_acordo (acordo_id, solicitado_por_id, justificativa_solicitacao)
            VALUES (?, ?, ?);
            """,
            (acordo_id, solicitado_por_id, justificativa),
        )
        return cur.lastrowid


def listar_aprovacoes_pendentes() -> List[dict]:
    cur = obter_conexao().execute(
        """
        SELECT ap.*,
               a.numero_interno, a.valor_total, a.quantidade_parcelas, a.periodicidade,
               c.nome_principal AS cliente_nome,
               u_sol.nome AS solicitante_nome
        FROM aprovacao_acordo ap
        JOIN acordo a ON a.id = ap.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u_sol ON u_sol.id = ap.solicitado_por_id
        WHERE ap.status = 'PENDENTE'
        ORDER BY ap.solicitado_em;
        """
    )
    return [dict(r) for r in cur.fetchall()]


def revisar_aprovacao(
    aprovacao_id: int,
    revisor_id: int,
    aprovado: bool,
    justificativa: str,
) -> None:
    novo_status = "APROVADO" if aprovado else "RECUSADO"
    with transacao() as conn:
        conn.execute(
            """
            UPDATE aprovacao_acordo
            SET status = ?, revisado_por_id = ?, justificativa_revisao = ?,
                revisado_em = datetime('now')
            WHERE id = ?;
            """,
            (novo_status, revisor_id, justificativa, aprovacao_id),
        )
