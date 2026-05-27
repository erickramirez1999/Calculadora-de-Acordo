"""
Repositório do Portal do Cliente.
Decisão Erick 13/05/2026: MVP do portal de auto-atendimento.

3 entidades:
- titulo_avulso: títulos cadastrados sem acordo (cliente pode ver e propor acordo)
- portal_token: token único pra cliente acessar (sem login/cadastro)
- proposta_cliente: proposta enviada pelo cliente (equipe analisa)
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from src.banco.conexao import obter_conexao


# ============================================================
# TÍTULOS AVULSOS (cadastrados sem acordo)
# ============================================================

def cadastrar_titulo_avulso(
    cliente_id: int,
    codigo_parceiro: str,
    razao_social_parceiro: str,
    empresa: int,
    codigo_vendedor: str,
    nome_vendedor: str,
    vencimento: str,
    numero_nota: str,
    numero_unico: str,
    principal: float,
    cadastrado_por_id: int,
) -> int:
    """Cadastra 1 título avulso. Retorna o ID.
    
    Permite mesmo numero_unico em clientes diferentes.
    Não permite numero_unico duplicado no mesmo cliente.
    """
    # Verifica se já existe pro mesmo cliente
    cur_check = obter_conexao().execute(
        """
        SELECT id FROM titulo_avulso
        WHERE cliente_id = ? AND numero_unico = ?
        LIMIT 1;
        """,
        (cliente_id, numero_unico),
    )
    if cur_check.fetchone():
        raise ValueError(
            f"Título {numero_unico} já está cadastrado pra esse cliente."
        )

    cur = obter_conexao().execute(
        """
        INSERT INTO titulo_avulso (
            cliente_id, codigo_parceiro, razao_social_parceiro, empresa,
            codigo_vendedor, nome_vendedor, vencimento, numero_nota,
            numero_unico, principal, cadastrado_por_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            cliente_id, codigo_parceiro, razao_social_parceiro, empresa,
            codigo_vendedor, nome_vendedor, vencimento, numero_nota,
            numero_unico, principal, cadastrado_por_id,
        ),
    )
    return cur.lastrowid


def listar_titulos_avulsos_do_cliente(cliente_id: int) -> List[dict]:
    """Lista todos os títulos avulsos disponíveis pra negociar do cliente.
    
    Inclui títulos de TODOS os parceiros vinculados ao mesmo cliente.
    Usado pelo PORTAL pra mostrar pro cliente o que tá disponível.
    
    Considera status = 'EM_ABERTO' OU status NULL (defaults antigos sem valor).
    """
    cur = obter_conexao().execute(
        """
        SELECT id, codigo_parceiro, razao_social_parceiro, empresa,
               codigo_vendedor, nome_vendedor, vencimento, numero_nota,
               numero_unico, principal, status, cadastrado_em
        FROM titulo_avulso
        WHERE cliente_id = ?
          AND (status = 'EM_ABERTO' OR status IS NULL OR status = '')
        ORDER BY vencimento ASC;
        """,
        (cliente_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def listar_todos_titulos_avulsos_do_cliente(cliente_id: int) -> List[dict]:
    """Lista TODOS os títulos avulsos do cliente, qualquer status.
    
    Usado pela tela INTERNA da equipe pra mostrar o histórico completo
    (inclui EM_ABERTO, EM_PROPOSTA, etc).
    """
    cur = obter_conexao().execute(
        """
        SELECT id, codigo_parceiro, razao_social_parceiro, empresa,
               codigo_vendedor, nome_vendedor, vencimento, numero_nota,
               numero_unico, principal, status, cadastrado_em
        FROM titulo_avulso
        WHERE cliente_id = ?
        ORDER BY status ASC, vencimento ASC;
        """,
        (cliente_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def contar_titulos_avulsos_do_cliente(cliente_id: int) -> int:
    cur = obter_conexao().execute(
        """
        SELECT COUNT(*) FROM titulo_avulso
        WHERE cliente_id = ?
          AND (status = 'EM_ABERTO' OR status IS NULL OR status = '');
        """,
        (cliente_id,),
    )
    return int(cur.fetchone()[0])


def remover_titulo_avulso(titulo_id: int) -> None:
    obter_conexao().execute(
        "DELETE FROM titulo_avulso WHERE id = ?;", (titulo_id,),
    )


def marcar_titulos_em_proposta(titulos_ids: List[int]) -> None:
    """Marca os títulos como EM_PROPOSTA (cliente já propôs, aguardando equipe)."""
    if not titulos_ids:
        return
    placeholders = ",".join("?" * len(titulos_ids))
    obter_conexao().execute(
        f"UPDATE titulo_avulso SET status = 'EM_PROPOSTA' WHERE id IN ({placeholders});",
        tuple(titulos_ids),
    )


def restaurar_titulos_em_aberto(titulos_ids: List[int]) -> None:
    """Devolve títulos pra EM_ABERTO (quando proposta é recusada)."""
    if not titulos_ids:
        return
    placeholders = ",".join("?" * len(titulos_ids))
    obter_conexao().execute(
        f"UPDATE titulo_avulso SET status = 'EM_ABERTO' WHERE id IN ({placeholders});",
        tuple(titulos_ids),
    )


# ============================================================
# TOKEN DO PORTAL
# ============================================================

def gerar_token(cliente_id: int, criado_por_id: int, dias_validade: int = 30) -> str:
    """Gera um token único pra cliente acessar o portal. Retorna o token."""
    token = secrets.token_urlsafe(32)
    expira = (datetime.now() + timedelta(days=dias_validade)).isoformat()
    obter_conexao().execute(
        """
        INSERT INTO portal_token (token, cliente_id, criado_por_id, expira_em)
        VALUES (?, ?, ?, ?);
        """,
        (token, cliente_id, criado_por_id, expira),
    )
    return token


def contar_tokens_gerados_hoje(cliente_id: int) -> int:
    """Conta quantos tokens foram gerados HOJE pra esse cliente (independente de quem)."""
    cur = obter_conexao().execute(
        """
        SELECT COUNT(*) FROM portal_token
        WHERE cliente_id = ?
          AND DATE(criado_em) = DATE('now');
        """,
        (cliente_id,),
    )
    return int(cur.fetchone()[0])


def buscar_token(token: str) -> Optional[dict]:
    """Busca um token. Retorna None se não existir, expirado ou inativo.
    
    Robusto contra:
    - expira_em vindo como string ISO ('2026-06-12T...')
    - expira_em vindo como datetime (Postgres TIMESTAMPTZ)
    - datetime aware vs naive
    """
    cur = obter_conexao().execute(
        """
        SELECT pt.id, pt.token, pt.cliente_id, pt.criado_em, pt.expira_em,
               pt.usado_em, pt.ativo,
               c.nome_principal, c.cnpj, c.contato, c.email_cobranca,
               c.telefone, c.tem_whatsapp
        FROM portal_token pt
        JOIN cliente c ON c.id = pt.cliente_id
        WHERE pt.token = ?;
        """,
        (token,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)

    # Valida se ainda é válido
    ativo = d.get("ativo")
    # No Postgres pode vir como bool, no SQLite como int. Aceita ambos.
    if not ativo:
        return None

    expira_raw = d.get("expira_em")
    if expira_raw is None:
        return None

    # Converte pra datetime (pode vir como string ou datetime)
    expira_dt = None
    if isinstance(expira_raw, datetime):
        expira_dt = expira_raw
    elif isinstance(expira_raw, str):
        try:
            # Tira eventual timezone do final
            s = expira_raw[:19] if len(expira_raw) >= 19 else expira_raw
            expira_dt = datetime.fromisoformat(s)
        except Exception:
            return None
    else:
        return None

    # Compara apenas naive (sem timezone) pra evitar problema
    if expira_dt.tzinfo is not None:
        expira_dt = expira_dt.replace(tzinfo=None)
    if datetime.now() > expira_dt:
        return None

    return d


def listar_tokens_do_cliente(cliente_id: int) -> List[dict]:
    """Lista todos os tokens gerados pra um cliente (ativos e expirados)."""
    cur = obter_conexao().execute(
        """
        SELECT id, token, criado_em, expira_em, usado_em, ativo
        FROM portal_token
        WHERE cliente_id = ?
        ORDER BY criado_em DESC;
        """,
        (cliente_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def desativar_token(token_id: int) -> None:
    obter_conexao().execute(
        "UPDATE portal_token SET ativo = 0 WHERE id = ?;", (token_id,),
    )


def marcar_token_usado(token_id: int) -> None:
    obter_conexao().execute(
        "UPDATE portal_token SET usado_em = datetime('now'), ativo = 0 WHERE id = ?;",
        (token_id,),
    )


# ============================================================
# PROPOSTAS DO CLIENTE
# ============================================================

def criar_proposta(
    token_id: int,
    cliente_id: int,
    titulos_ids: List[int],
    periodicidade: str,
    qtd_parcelas: int,
    data_primeira_parcela: str,
    valor_parcela: float,
    valor_total: float,
    observacao_cliente: Optional[str] = None,
) -> int:
    """Cria uma proposta. Retorna o ID."""
    cur = obter_conexao().execute(
        """
        INSERT INTO proposta_cliente (
            token_id, cliente_id, titulos_ids, periodicidade,
            qtd_parcelas, data_primeira_parcela, valor_parcela, valor_total,
            observacao_cliente
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            token_id, cliente_id, json.dumps(titulos_ids), periodicidade,
            qtd_parcelas, data_primeira_parcela, valor_parcela, valor_total,
            observacao_cliente,
        ),
    )
    return cur.lastrowid


def listar_propostas_aceitas_sem_acordo(cliente_id: int) -> List[dict]:
    """Lista propostas ACEITAS de um cliente que ainda não geraram acordo."""
    cur = obter_conexao().execute(
        """
        SELECT p.id, p.cliente_id, p.titulos_ids, p.periodicidade,
               p.qtd_parcelas, p.data_primeira_parcela, p.valor_parcela,
               p.valor_total, p.observacao_cliente, p.enviado_em,
               c.nome_principal, c.cnpj
        FROM proposta_cliente p
        JOIN cliente c ON c.id = p.cliente_id
        WHERE p.cliente_id = ?
          AND p.status = 'ACEITA'
        ORDER BY p.enviado_em DESC;
        """,
        (cliente_id,),
    )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["titulos_ids"] = json.loads(d["titulos_ids"])
        rows.append(d)
    return rows


def listar_propostas_pendentes() -> List[dict]:
    """Lista todas as propostas com status PENDENTE."""
    cur = obter_conexao().execute(
        """
        SELECT p.id, p.cliente_id, p.titulos_ids, p.periodicidade,
               p.qtd_parcelas, p.data_primeira_parcela, p.valor_parcela,
               p.valor_total, p.observacao_cliente, p.enviado_em,
               c.nome_principal, c.cnpj
        FROM proposta_cliente p
        JOIN cliente c ON c.id = p.cliente_id
        WHERE p.status = 'PENDENTE'
        ORDER BY p.enviado_em ASC;
        """,
    )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["titulos_ids"] = json.loads(d["titulos_ids"])
        rows.append(d)
    return rows


def buscar_proposta(proposta_id: int) -> Optional[dict]:
    cur = obter_conexao().execute(
        """
        SELECT p.*, c.nome_principal, c.cnpj
        FROM proposta_cliente p
        JOIN cliente c ON c.id = p.cliente_id
        WHERE p.id = ?;
        """,
        (proposta_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["titulos_ids"] = json.loads(d["titulos_ids"])
    return d


def marcar_proposta_analisada(
    proposta_id: int,
    decisao: str,
    analisado_por_id: int,
    observacao: Optional[str] = None,
    acordo_gerado_id: Optional[int] = None,
) -> None:
    """decisao: 'ACEITA' | 'RECUSADA'"""
    obter_conexao().execute(
        """
        UPDATE proposta_cliente
        SET status = ?, analisado_por_id = ?, analisado_em = datetime('now'),
            decisao_observacao = ?, acordo_gerado_id = ?
        WHERE id = ?;
        """,
        (decisao, analisado_por_id, observacao, acordo_gerado_id, proposta_id),
    )


def contar_propostas_pendentes() -> int:
    cur = obter_conexao().execute(
        "SELECT COUNT(*) FROM proposta_cliente WHERE status = 'PENDENTE';",
    )
    return int(cur.fetchone()[0])


def listar_propostas_do_cliente(cliente_id: int, apenas_pendentes: bool = False) -> List[dict]:
    """Lista propostas de UM cliente específico.
    
    Args:
        cliente_id: id do cliente
        apenas_pendentes: se True, só PENDENTES; se False, todas (PENDENTE, ACEITA, RECUSADA)
    """
    sql_filtro = "AND p.status = 'PENDENTE'" if apenas_pendentes else ""
    cur = obter_conexao().execute(
        f"""
        SELECT p.id, p.cliente_id, p.titulos_ids, p.periodicidade,
               p.qtd_parcelas, p.data_primeira_parcela, p.valor_parcela,
               p.valor_total, p.observacao_cliente, p.enviado_em, p.status,
               p.analisado_em, p.decisao_observacao,
               c.nome_principal, c.cnpj
        FROM proposta_cliente p
        JOIN cliente c ON c.id = p.cliente_id
        WHERE p.cliente_id = ? {sql_filtro}
        ORDER BY p.enviado_em DESC;
        """,
        (cliente_id,),
    )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["titulos_ids"] = json.loads(d["titulos_ids"])
        rows.append(d)
    return rows


def contar_propostas_pendentes_do_cliente(cliente_id: int) -> int:
    cur = obter_conexao().execute(
        """
        SELECT COUNT(*) FROM proposta_cliente
        WHERE cliente_id = ? AND status = 'PENDENTE';
        """,
        (cliente_id,),
    )
    return int(cur.fetchone()[0])
