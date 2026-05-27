"""
Repositório das tabelas de "valor agregado" pra cobrança:
  - comentario_acordo: notas livres / histórico de contatos
  - promessa_pagamento: cliente prometeu pagar tal dia
  - filtro_salvo: filtros personalizados de busca
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import List, Optional

from src.banco.conexao import obter_conexao, transacao


# ============================================================
# COMENTÁRIOS DO ACORDO
# ============================================================

def adicionar_comentario(
    acordo_id: int,
    usuario_id: int,
    usuario_nome: str,
    texto: str,
    tipo: str = "NOTA",
) -> int:
    """Adiciona comentário ao acordo. Retorna o id criado."""
    if not texto or not texto.strip():
        raise ValueError("Texto do comentário não pode estar vazio.")
    if tipo not in ("NOTA", "LIGACAO", "WHATSAPP", "EMAIL", "VISITA", "OUTRO"):
        tipo = "NOTA"
    with transacao() as conn:
        cur = conn.execute(
            """
            INSERT INTO comentario_acordo
            (acordo_id, usuario_id, usuario_nome_snapshot, tipo, texto)
            VALUES (?, ?, ?, ?, ?);
            """,
            (acordo_id, usuario_id, usuario_nome, tipo, texto.strip()),
        )
        return cur.lastrowid


def listar_comentarios(acordo_id: int) -> List[dict]:
    """Lista comentários do acordo, do mais recente pro mais antigo."""
    cur = obter_conexao().execute(
        """
        SELECT * FROM comentario_acordo
        WHERE acordo_id = ?
        ORDER BY criado_em DESC, id DESC;
        """,
        (acordo_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def excluir_comentario(comentario_id: int, usuario_id: int) -> bool:
    """
    Exclui um comentário SE pertence ao usuário (regra de segurança simples).
    Retorna True se excluiu, False se não pertence.
    """
    cur = obter_conexao().execute(
        "SELECT usuario_id FROM comentario_acordo WHERE id = ?;", (comentario_id,)
    )
    row = cur.fetchone()
    if not row or row["usuario_id"] != usuario_id:
        return False
    with transacao() as conn:
        conn.execute(
            "DELETE FROM comentario_acordo WHERE id = ?;", (comentario_id,)
        )
    return True


# ============================================================
# PROMESSAS DE PAGAMENTO
# ============================================================

def criar_promessa(
    acordo_id: int,
    data_prometida: date,
    usuario_id: int,
    usuario_nome: str,
    parcela_id: Optional[int] = None,
    valor_prometido: Optional[float] = None,
    observacao: Optional[str] = None,
) -> int:
    with transacao() as conn:
        cur = conn.execute(
            """
            INSERT INTO promessa_pagamento
            (acordo_id, parcela_id, data_prometida, valor_prometido,
             observacao, usuario_id, usuario_nome_snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                acordo_id, parcela_id, data_prometida.isoformat(),
                valor_prometido, observacao, usuario_id, usuario_nome,
            ),
        )
        return cur.lastrowid


def listar_promessas_do_acordo(acordo_id: int) -> List[dict]:
    cur = obter_conexao().execute(
        """
        SELECT * FROM promessa_pagamento
        WHERE acordo_id = ?
        ORDER BY data_prometida DESC, id DESC;
        """,
        (acordo_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def listar_promessas_para_data(
    data: date,
    negociador_id: Optional[int] = None,
    status: str = "AGUARDANDO",
) -> List[dict]:
    """
    Lista promessas pra uma data específica, opcionalmente filtrando
    por negociador (Erick - cada um vê só os seus).
    """
    sql = """
        SELECT pp.*, a.numero_interno AS acordo_numero,
               c.nome_principal AS cliente_nome, c.telefone, c.tem_whatsapp,
               u.nome AS negociador_nome, a.negociador_id
        FROM promessa_pagamento pp
        JOIN acordo a ON a.id = pp.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u ON u.id = a.negociador_id
        WHERE DATE(pp.data_prometida) = DATE(?)
          AND pp.status = ?
    """
    params = [data.isoformat(), status]
    if negociador_id:
        sql += " AND a.negociador_id = ?"
        params.append(negociador_id)
    sql += " ORDER BY c.nome_principal;"
    cur = obter_conexao().execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def listar_promessas_quebradas(
    negociador_id: Optional[int] = None,
) -> List[dict]:
    """Promessas com data vencida ainda AGUARDANDO (= quebradas)."""
    sql = """
        SELECT pp.*, a.numero_interno AS acordo_numero,
               c.nome_principal AS cliente_nome, c.telefone, c.tem_whatsapp,
               u.nome AS negociador_nome, a.negociador_id
        FROM promessa_pagamento pp
        JOIN acordo a ON a.id = pp.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u ON u.id = a.negociador_id
        WHERE pp.status = 'AGUARDANDO'
          AND DATE(pp.data_prometida) < DATE('now')
    """
    params: list = []
    if negociador_id:
        sql += " AND a.negociador_id = ?"
        params.append(negociador_id)
    sql += " ORDER BY pp.data_prometida ASC;"
    cur = obter_conexao().execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def atualizar_status_promessa(promessa_id: int, novo_status: str) -> None:
    if novo_status not in ("AGUARDANDO", "CUMPRIDA", "QUEBRADA", "CANCELADA"):
        raise ValueError(f"Status inválido: {novo_status}")
    with transacao() as conn:
        conn.execute(
            """
            UPDATE promessa_pagamento
            SET status = ?, atualizado_em = datetime('now')
            WHERE id = ?;
            """,
            (novo_status, promessa_id),
        )


# ============================================================
# FILTROS SALVOS
# ============================================================

def salvar_filtro(
    usuario_id: int,
    nome: str,
    configuracao: dict,
) -> int:
    if not nome or not nome.strip():
        raise ValueError("Nome do filtro é obrigatório.")
    with transacao() as conn:
        cur = conn.execute(
            """
            INSERT INTO filtro_salvo (usuario_id, nome, configuracao_json)
            VALUES (?, ?, ?);
            """,
            (
                usuario_id, nome.strip(),
                json.dumps(configuracao, default=str, ensure_ascii=False),
            ),
        )
        return cur.lastrowid


def listar_filtros(usuario_id: int) -> List[dict]:
    cur = obter_conexao().execute(
        "SELECT * FROM filtro_salvo WHERE usuario_id = ? ORDER BY nome;",
        (usuario_id,),
    )
    resultado = []
    for r in cur.fetchall():
        d = dict(r)
        try:
            d["configuracao"] = json.loads(d["configuracao_json"])
        except Exception:
            d["configuracao"] = {}
        resultado.append(d)
    return resultado


def excluir_filtro(filtro_id: int, usuario_id: int) -> bool:
    with transacao() as conn:
        cur = conn.execute(
            "DELETE FROM filtro_salvo WHERE id = ? AND usuario_id = ?;",
            (filtro_id, usuario_id),
        )
        return cur.rowcount > 0


# ============================================================
# HISTÓRICO DO CLIENTE (todos os acordos de um cliente)
# ============================================================

def listar_acordos_do_cliente(cliente_id: int) -> List[dict]:
    """Todos os acordos (ativos e finalizados) de um cliente, com métricas."""
    cur = obter_conexao().execute(
        """
        SELECT
            a.id, a.numero_interno, a.data_acordo, a.data_encerramento,
            a.status, a.valor_total, a.quantidade_parcelas,
            a.tipo_cobranca,
            u.nome AS negociador_nome,
            (SELECT COUNT(*) FROM parcela WHERE acordo_id = a.id AND status = 'QUITADA') AS qtd_pagas,
            (SELECT COALESCE(SUM(valor_original), 0) FROM parcela
              WHERE acordo_id = a.id AND status != 'QUITADA') AS saldo
        FROM acordo a
        JOIN usuario u ON u.id = a.negociador_id
        WHERE a.cliente_id = ?
        ORDER BY a.data_criacao DESC;
        """,
        (cliente_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def metricas_cliente(cliente_id: int) -> dict:
    """Indicadores agregados de um cliente (KPIs do histórico)."""
    acordos = listar_acordos_do_cliente(cliente_id)
    total = len(acordos)
    ativos = sum(1 for a in acordos if a["status"] == "ATIVO")
    quitados = sum(1 for a in acordos if a["status"] == "QUITADO")
    quebrados = sum(1 for a in acordos if a["status"] == "QUEBRADO")
    cancelados = sum(1 for a in acordos if a["status"] == "CANCELADO")
    valor_total = sum(a["valor_total"] for a in acordos)
    valor_pendente = sum(a["saldo"] for a in acordos if a["status"] == "ATIVO")
    return {
        "total": total,
        "ativos": ativos,
        "quitados": quitados,
        "quebrados": quebrados,
        "cancelados": cancelados,
        "valor_total_negociado": valor_total,
        "valor_pendente": valor_pendente,
        "taxa_quebra": (quebrados / total * 100) if total > 0 else 0,
        "taxa_quitacao": (quitados / total * 100) if total > 0 else 0,
    }
