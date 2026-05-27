"""Repositório de Cliente."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.banco.conexao import obter_conexao, transacao


@dataclass
class Cliente:
    id: int
    nome_principal: str
    cnpj: Optional[str]
    contato: Optional[str]
    email_cobranca: Optional[str]
    telefone: Optional[str]
    tem_whatsapp: bool
    criado_em: str


def _row_para_cliente(row) -> Cliente:
    # Compatibilidade com bancos antigos (sem coluna tem_whatsapp)
    try:
        tem_whatsapp = bool(row["tem_whatsapp"]) if "tem_whatsapp" in row.keys() else False
    except (KeyError, IndexError):
        tem_whatsapp = False

    return Cliente(
        id=row["id"],
        nome_principal=row["nome_principal"],
        cnpj=row["cnpj"],
        contato=row["contato"],
        email_cobranca=row["email_cobranca"],
        telefone=row["telefone"],
        tem_whatsapp=tem_whatsapp,
        criado_em=row["criado_em"],
    )


def buscar_por_id(cliente_id: int) -> Optional[Cliente]:
    cur = obter_conexao().execute("SELECT * FROM cliente WHERE id = ?;", (cliente_id,))
    row = cur.fetchone()
    return _row_para_cliente(row) if row else None


def buscar_por_nome_ou_cnpj(termo: str) -> List[Cliente]:
    """Busca clientes por nome (LIKE) ou CNPJ exato."""
    cur = obter_conexao().execute(
        """
        SELECT * FROM cliente
        WHERE LOWER(nome_principal) LIKE LOWER(?)
           OR cnpj = ?
        ORDER BY nome_principal;
        """,
        (f"%{termo}%", termo),
    )
    return [_row_para_cliente(r) for r in cur.fetchall()]


def listar_todos() -> List[Cliente]:
    cur = obter_conexao().execute(
        "SELECT * FROM cliente ORDER BY nome_principal;"
    )
    return [_row_para_cliente(r) for r in cur.fetchall()]


def criar(
    nome_principal: str,
    cnpj: Optional[str] = None,
    contato: Optional[str] = None,
    email_cobranca: Optional[str] = None,
    telefone: Optional[str] = None,
    tem_whatsapp: bool = False,
) -> Cliente:
    if not nome_principal or not nome_principal.strip():
        raise ValueError("Nome do cliente é obrigatório.")
    with transacao() as conn:
        cur = conn.execute(
            """
            INSERT INTO cliente
            (nome_principal, cnpj, contato, email_cobranca, telefone, tem_whatsapp)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                nome_principal.strip(),
                cnpj.strip() if cnpj else None,
                contato.strip() if contato else None,
                email_cobranca.strip() if email_cobranca else None,
                telefone.strip() if telefone else None,
                1 if tem_whatsapp else 0,
            ),
        )
        novo_id = cur.lastrowid
    cliente = buscar_por_id(novo_id)
    assert cliente is not None
    _invalidar_cache_cliente()
    return cliente


def atualizar(
    cliente_id: int,
    nome_principal: Optional[str] = None,
    cnpj: Optional[str] = None,
    contato: Optional[str] = None,
    email_cobranca: Optional[str] = None,
    telefone: Optional[str] = None,
    tem_whatsapp: Optional[bool] = None,
) -> Cliente:
    """Atualiza dados do cliente. Permitido a todos os perfis (decidido pelo Erick)."""
    atual = buscar_por_id(cliente_id)
    if atual is None:
        raise ValueError(f"Cliente id={cliente_id} não encontrado.")

    if nome_principal is not None:
        nome_principal = nome_principal.strip()
        if not nome_principal:
            raise ValueError("Nome do cliente não pode ficar vazio.")

    with transacao() as conn:
        conn.execute(
            """
            UPDATE cliente
            SET nome_principal = COALESCE(?, nome_principal),
                cnpj = COALESCE(?, cnpj),
                contato = COALESCE(?, contato),
                email_cobranca = COALESCE(?, email_cobranca),
                telefone = COALESCE(?, telefone),
                tem_whatsapp = COALESCE(?, tem_whatsapp)
            WHERE id = ?;
            """,
            (
                nome_principal,
                cnpj.strip() if cnpj is not None else None,
                contato.strip() if contato is not None else None,
                email_cobranca.strip() if email_cobranca is not None else None,
                telefone.strip() if telefone is not None else None,
                (1 if tem_whatsapp else 0) if tem_whatsapp is not None else None,
                cliente_id,
            ),
        )

    atualizado = buscar_por_id(cliente_id)
    assert atualizado is not None
    _invalidar_cache_cliente()
    return atualizado


def excluir_cliente_completo(cliente_id: int) -> dict:
    """Exclui o cliente e TUDO relacionado a ele permanentemente.

    Remove em cascata (ordem que respeita FK):
      pagamento_parcela → parcela → boleto → aprovacao_acordo →
      comentario_acordo → promessa_pagamento → acordo →
      titulo_avulso → portal_token → proposta_cliente →
      anexo_cliente → log_auditoria (referências) → cliente

    Retorna um dict com contagens do que foi removido (pra log de auditoria).
    """
    conn = obter_conexao()

    # Coleta IDs dos acordos do cliente (necessário pra cascata manual)
    cur = conn.execute("SELECT id FROM acordo WHERE cliente_id = ?;", (cliente_id,))
    acordo_ids = [r[0] for r in cur.fetchall()]

    contagens = {}

    with transacao() as conn:
        if acordo_ids:
            placeholders = ",".join("?" * len(acordo_ids))

            # pagamento_parcela (via parcela)
            cur = conn.execute(
                f"SELECT id FROM parcela WHERE acordo_id IN ({placeholders});",
                acordo_ids,
            )
            parcela_ids = [r[0] for r in cur.fetchall()]
            if parcela_ids:
                p_ph = ",".join("?" * len(parcela_ids))
                cur = conn.execute(
                    f"DELETE FROM pagamento_parcela WHERE parcela_id IN ({p_ph});",
                    parcela_ids,
                )
                contagens["pagamentos"] = cur.rowcount

            # parcela
            cur = conn.execute(
                f"DELETE FROM parcela WHERE acordo_id IN ({placeholders});",
                acordo_ids,
            )
            contagens["parcelas"] = cur.rowcount

            # boleto
            cur = conn.execute(
                f"DELETE FROM boleto WHERE acordo_id IN ({placeholders});",
                acordo_ids,
            )
            contagens["boletos"] = cur.rowcount

            # aprovacao_acordo
            cur = conn.execute(
                f"DELETE FROM aprovacao_acordo WHERE acordo_id IN ({placeholders});",
                acordo_ids,
            )
            contagens["aprovacoes"] = cur.rowcount

            # comentario_acordo
            cur = conn.execute(
                f"DELETE FROM comentario_acordo WHERE acordo_id IN ({placeholders});",
                acordo_ids,
            )
            contagens["comentarios"] = cur.rowcount

            # promessa_pagamento
            cur = conn.execute(
                f"DELETE FROM promessa_pagamento WHERE acordo_id IN ({placeholders});",
                acordo_ids,
            )
            contagens["promessas"] = cur.rowcount

            # acordo
            cur = conn.execute(
                f"DELETE FROM acordo WHERE id IN ({placeholders});",
                acordo_ids,
            )
            contagens["acordos"] = cur.rowcount

        # titulo_avulso
        cur = conn.execute(
            "DELETE FROM titulo_avulso WHERE cliente_id = ?;", (cliente_id,)
        )
        contagens["titulos_avulsos"] = cur.rowcount

        # proposta_cliente (tem FK pra portal_token, então apaga primeiro)
        cur = conn.execute(
            "DELETE FROM proposta_cliente WHERE cliente_id = ?;", (cliente_id,)
        )
        contagens["propostas"] = cur.rowcount

        # portal_token
        cur = conn.execute(
            "DELETE FROM portal_token WHERE cliente_id = ?;", (cliente_id,)
        )
        contagens["tokens"] = cur.rowcount

        # anexo_cliente
        cur = conn.execute(
            "DELETE FROM anexo_cliente WHERE cliente_id = ?;", (cliente_id,)
        )
        contagens["anexos"] = cur.rowcount

        # cliente
        conn.execute("DELETE FROM cliente WHERE id = ?;", (cliente_id,))
        contagens["cliente"] = 1

    _invalidar_cache_cliente()
    return contagens


def _invalidar_cache_cliente():
    """Invalida cache de clientes se Streamlit disponível. Silenciso senão."""
    try:
        from src.utils.cache import limpar_cache_clientes
        limpar_cache_clientes()
    except Exception:
        pass


def buscar_ou_criar(
    nome_principal: str,
    cnpj: Optional[str] = None,
    **kwargs,
) -> Cliente:
    """Reutiliza cliente existente (por nome+cnpj) ou cria novo."""
    nome_normalizado = nome_principal.strip().lower()
    cur = obter_conexao().execute(
        """
        SELECT * FROM cliente
        WHERE LOWER(nome_principal) = ?
           AND COALESCE(cnpj, '') = COALESCE(?, '')
        LIMIT 1;
        """,
        (nome_normalizado, cnpj),
    )
    row = cur.fetchone()
    if row:
        return _row_para_cliente(row)
    return criar(nome_principal, cnpj=cnpj, **kwargs)
