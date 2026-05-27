"""
Repositório de Anexos do Cliente.
Decisão Erick 13/05/2026: armazenar comprovantes PDF em Base64 no banco.

Limites:
- 5 MB por arquivo
- Apenas PDFs aceitos (pode estender pra imagem depois)
"""
from __future__ import annotations

import base64
from typing import List, Optional

from src.banco.conexao import obter_conexao


LIMITE_TAMANHO_BYTES = 5 * 1024 * 1024  # 5 MB
MIMES_PERMITIDOS = {"application/pdf"}


def adicionar_anexo(
    cliente_id: int,
    nome_arquivo: str,
    conteudo_bytes: bytes,
    upload_por_id: int,
    descricao: Optional[str] = None,
    mime_type: str = "application/pdf",
) -> int:
    """Adiciona 1 anexo. Retorna o ID.
    
    Raises:
        ValueError: se o arquivo for muito grande ou tipo não permitido.
    """
    tamanho = len(conteudo_bytes)
    if tamanho > LIMITE_TAMANHO_BYTES:
        raise ValueError(
            f"Arquivo muito grande ({tamanho / 1024 / 1024:.1f} MB). "
            f"Limite: {LIMITE_TAMANHO_BYTES / 1024 / 1024:.0f} MB."
        )
    if mime_type not in MIMES_PERMITIDOS:
        raise ValueError(
            f"Tipo de arquivo não permitido. Apenas PDFs são aceitos."
        )

    conteudo_b64 = base64.b64encode(conteudo_bytes).decode("ascii")

    cur = obter_conexao().execute(
        """
        INSERT INTO anexo_cliente (
            cliente_id, nome_arquivo, descricao, mime_type,
            tamanho_bytes, conteudo_base64, upload_por_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (cliente_id, nome_arquivo, descricao, mime_type,
         tamanho, conteudo_b64, upload_por_id),
    )
    return cur.lastrowid


def listar_anexos_do_cliente(cliente_id: int) -> List[dict]:
    """Lista anexos (sem o conteúdo, pra ser leve)."""
    cur = obter_conexao().execute(
        """
        SELECT a.id, a.nome_arquivo, a.descricao, a.mime_type,
               a.tamanho_bytes, a.upload_em, a.upload_por_id,
               u.nome AS upload_por_nome
        FROM anexo_cliente a
        LEFT JOIN usuario u ON u.id = a.upload_por_id
        WHERE a.cliente_id = ?
        ORDER BY a.upload_em DESC;
        """,
        (cliente_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def buscar_conteudo_anexo(anexo_id: int) -> Optional[dict]:
    """Busca o conteúdo de 1 anexo pra download."""
    cur = obter_conexao().execute(
        """
        SELECT nome_arquivo, mime_type, conteudo_base64
        FROM anexo_cliente
        WHERE id = ?;
        """,
        (anexo_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["conteudo_bytes"] = base64.b64decode(d["conteudo_base64"])
    del d["conteudo_base64"]
    return d


def remover_anexo(anexo_id: int) -> None:
    obter_conexao().execute(
        "DELETE FROM anexo_cliente WHERE id = ?;", (anexo_id,),
    )


def contar_anexos_do_cliente(cliente_id: int) -> int:
    cur = obter_conexao().execute(
        "SELECT COUNT(*) FROM anexo_cliente WHERE cliente_id = ?;",
        (cliente_id,),
    )
    return int(cur.fetchone()[0])
