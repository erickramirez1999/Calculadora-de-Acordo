"""
Repositório de Acordo — CRUD com salvamento atômico de boletos + parcelas + pagamentos.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from src.banco.conexao import obter_conexao, transacao
from src.modelos.tipos import (
    Boleto,
    Empresa,
    OrigemDado,
    PagamentoParcela,
    Parcela,
    Periodicidade,
    StatusAcordo,
    StatusParcela,
    TipoCobranca,
)


@dataclass
class AcordoResumo:
    """Linha resumida para listagens (Início, Finalizados)."""
    id: int
    numero_interno: str
    cliente_id: int
    cliente_nome: str
    negociador_id: int
    negociador_nome: str
    data_acordo: str
    data_criacao: str
    data_encerramento: Optional[str]
    valor_total: float
    quantidade_parcelas: int
    parcelas_pagas: int
    parcelas_em_atraso: int
    saldo_devedor: float
    proxima_parcela_data: Optional[str]
    status: StatusAcordo
    tipo_cobranca: TipoCobranca


@dataclass
class AcordoCompleto:
    """Acordo + boletos + parcelas + pagamentos para a tela de detalhe."""
    id: int
    numero_interno: str
    cliente_id: int
    cliente_nome: str
    negociador_id: int
    negociador_nome: str
    criado_por_id: int
    data_criacao: str
    data_acordo: date
    data_encerramento: Optional[str]
    pct_juros_mes_titulos: float
    pct_multa_titulos: float
    pct_juros_mora_mes: float
    pct_multa_mora: float
    pct_desconto: float
    tipo_cobranca: TipoCobranca
    periodicidade: Periodicidade
    intervalo_personalizado_dias: int
    valor_total: float
    quantidade_parcelas: int
    status: StatusAcordo
    observacoes: Optional[str]
    boletos: List[Boleto] = field(default_factory=list)
    parcelas: List[Parcela] = field(default_factory=list)


# ============================================================
# GERADOR DO NÚMERO INTERNO (P7)
# ============================================================

def gerar_proximo_numero_acordo(data_criacao: Optional[date] = None) -> str:
    """
    Gera número no formato ACO-AAAAMMDD-### (Padrão decidido em P7).
    Sequencial diário: reinicia a cada dia.
    """
    d = data_criacao or date.today()
    data_str = d.strftime("%Y-%m-%d")
    sufixo_data = d.strftime("%Y%m%d")
    with transacao() as conn:
        # Upsert atômico (sintaxe compatível SQLite + Postgres)
        # Em Postgres, no DO UPDATE precisa qualificar a coluna com tablename
        # SQLite aceita tanto qualificado como não, então sempre qualificamos.
        conn.execute(
            """
            INSERT INTO sequencia_acordo (data, proximo_numero) VALUES (?, 1)
            ON CONFLICT(data) DO UPDATE SET proximo_numero = sequencia_acordo.proximo_numero + 1;
            """,
            (data_str,),
        )
        cur = conn.execute(
            "SELECT proximo_numero FROM sequencia_acordo WHERE data = ?;",
            (data_str,),
        )
        proximo = cur.fetchone()[0]
    return f"ACO-{sufixo_data}-{proximo:03d}"


# ============================================================
# SALVAMENTO COMPLETO DO ACORDO
# ============================================================

def _serializar_lista_parcelas(parcelas_alocadas: List[int]) -> str:
    return json.dumps(parcelas_alocadas)


def _serializar_distribuicao(dist: List[dict]) -> str:
    return json.dumps(dist)


def _deserializar(texto: Optional[str], default):
    if not texto:
        return default
    try:
        return json.loads(texto)
    except Exception:
        return default


def salvar_acordo_completo(
    *,
    cliente_id: int,
    negociador_id: int,
    criado_por_id: int,
    data_acordo: date,
    pct_juros_mes_titulos: float,
    pct_multa_titulos: float,
    pct_juros_mora_mes: float,
    pct_multa_mora: float,
    pct_desconto: float = 0.0,
    tipo_cobranca: TipoCobranca,
    periodicidade: Periodicidade,
    intervalo_personalizado_dias: int,
    boletos: List[Boleto],
    parcelas: List[Parcela],
    status_inicial: StatusAcordo = StatusAcordo.ATIVO,
    observacoes: Optional[str] = None,
) -> int:
    """
    Persiste tudo numa transação só.
    Retorna o id do acordo criado.
    """
    valor_total = round(sum(p.valor_original for p in parcelas), 2)
    numero_interno = gerar_proximo_numero_acordo(date.today())

    with transacao() as conn:
        # 1. Acordo
        cur = conn.execute(
            """
            INSERT INTO acordo (
                numero_interno, cliente_id, negociador_id, criado_por_id,
                data_acordo,
                pct_juros_mes_titulos, pct_multa_titulos,
                pct_juros_mora_mes, pct_multa_mora, pct_desconto,
                tipo_cobranca, periodicidade, intervalo_personalizado_dias,
                valor_total, quantidade_parcelas,
                status, observacoes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                numero_interno, cliente_id, negociador_id, criado_por_id,
                data_acordo.isoformat(),
                pct_juros_mes_titulos, pct_multa_titulos,
                pct_juros_mora_mes, pct_multa_mora, pct_desconto,
                tipo_cobranca.value, periodicidade.value, intervalo_personalizado_dias,
                valor_total, len(parcelas),
                status_inicial.value, observacoes,
            ),
        )
        acordo_id = cur.lastrowid

        # 2. Parcelas
        for p in parcelas:
            conn.execute(
                """
                INSERT INTO parcela (
                    acordo_id, numero, vencimento_original, vencimento_atual,
                    valor_original, principal, juros, multa, saldo_apos, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    acordo_id, p.numero,
                    p.vencimento_original.isoformat(),
                    p.vencimento_atual.isoformat(),
                    round(p.valor_original, 2),
                    round(p.principal, 2),
                    round(p.juros, 2),
                    round(p.multa, 2),
                    round(p.saldo_apos, 2),
                    p.status.value,
                ),
            )

        # 3. Boletos
        for b in boletos:
            conn.execute(
                """
                INSERT INTO boleto (
                    acordo_id, codigo_parceiro, razao_social_parceiro, empresa,
                    codigo_vendedor, nome_vendedor,
                    vencimento, numero_nota, numero_unico, principal,
                    dias_atraso, fim_juros, juros, multa, total,
                    parcelas_alocadas, distribuicao, origem, titulo_sankhya_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    acordo_id, b.codigo_parceiro, b.razao_social_parceiro,
                    int(b.empresa) if hasattr(b.empresa, "value") else b.empresa,
                    b.codigo_vendedor, b.nome_vendedor,
                    b.vencimento.isoformat(),
                    b.numero_nota, b.numero_unico, round(b.principal, 2),
                    b.dias_atraso,
                    b.fim_juros.isoformat() if b.fim_juros else None,
                    round(b.juros, 2),
                    round(b.multa, 2),
                    round(b.total, 2),
                    _serializar_lista_parcelas(b.parcelas_alocadas),
                    _serializar_distribuicao(b.distribuicao),
                    (b.origem.value if hasattr(b.origem, "value") else "MANUAL"),
                    b.titulo_sankhya_id,
                ),
            )

    return acordo_id


# ============================================================
# CONSULTAS
# ============================================================

def buscar_resumo(acordo_id: int) -> Optional[AcordoResumo]:
    cur = obter_conexao().execute(
        """
        SELECT
            a.*,
            c.nome_principal AS cliente_nome,
            u.nome AS negociador_nome,
            (SELECT COUNT(*) FROM parcela WHERE acordo_id = a.id AND status = 'QUITADA') AS qtd_pagas,
            (SELECT COUNT(*) FROM parcela
              WHERE acordo_id = a.id
                AND status != 'QUITADA'
                AND DATE(vencimento_atual) < DATE('now')) AS qtd_atrasadas,
            (SELECT COALESCE(SUM(valor_original), 0) FROM parcela
              WHERE acordo_id = a.id AND status != 'QUITADA') AS saldo_dev,
            (SELECT MIN(vencimento_atual) FROM parcela
              WHERE acordo_id = a.id AND status != 'QUITADA') AS proxima_data
        FROM acordo a
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u ON u.id = a.negociador_id
        WHERE a.id = ?;
        """,
        (acordo_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return AcordoResumo(
        id=row["id"],
        numero_interno=row["numero_interno"],
        cliente_id=row["cliente_id"],
        cliente_nome=row["cliente_nome"],
        negociador_id=row["negociador_id"],
        negociador_nome=row["negociador_nome"],
        data_acordo=row["data_acordo"],
        data_criacao=row["data_criacao"],
        data_encerramento=row["data_encerramento"],
        valor_total=float(row["valor_total"]),
        quantidade_parcelas=int(row["quantidade_parcelas"]),
        parcelas_pagas=int(row["qtd_pagas"]),
        parcelas_em_atraso=int(row["qtd_atrasadas"]),
        saldo_devedor=float(row["saldo_dev"]),
        proxima_parcela_data=row["proxima_data"],
        status=StatusAcordo(row["status"]),
        tipo_cobranca=TipoCobranca(row["tipo_cobranca"]),
    )


def listar_resumos(
    status_em: Optional[List[StatusAcordo]] = None,
    negociador_id: Optional[int] = None,
    empresa: Optional[int] = None,
    incluir_encerrados: bool = False,
) -> List[AcordoResumo]:
    """Lista resumos de acordos para o Início ou Finalizados."""
    sql_base = """
        SELECT
            a.*,
            c.nome_principal AS cliente_nome,
            u.nome AS negociador_nome,
            (SELECT COUNT(*) FROM parcela WHERE acordo_id = a.id AND status = 'QUITADA') AS qtd_pagas,
            (SELECT COUNT(*) FROM parcela
              WHERE acordo_id = a.id
                AND status != 'QUITADA'
                AND DATE(vencimento_atual) < DATE('now')) AS qtd_atrasadas,
            (SELECT COALESCE(SUM(valor_original), 0) FROM parcela
              WHERE acordo_id = a.id AND status != 'QUITADA') AS saldo_dev,
            (SELECT MIN(vencimento_atual) FROM parcela
              WHERE acordo_id = a.id AND status != 'QUITADA') AS proxima_data
        FROM acordo a
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u ON u.id = a.negociador_id
        WHERE 1=1
    """
    params: list = []

    if status_em:
        placeholders = ",".join("?" for _ in status_em)
        sql_base += f" AND a.status IN ({placeholders})"
        params.extend([s.value for s in status_em])
    elif not incluir_encerrados:
        sql_base += " AND a.status IN ('ATIVO', 'PENDENTE_APROVACAO')"

    if negociador_id:
        sql_base += " AND a.negociador_id = ?"
        params.append(negociador_id)

    if empresa:
        sql_base += " AND EXISTS (SELECT 1 FROM boleto b WHERE b.acordo_id = a.id AND b.empresa = ?)"
        params.append(empresa)

    sql_base += " ORDER BY a.data_criacao DESC;"
    cur = obter_conexao().execute(sql_base, params)
    return [
        AcordoResumo(
            id=r["id"],
            numero_interno=r["numero_interno"],
            cliente_id=r["cliente_id"],
            cliente_nome=r["cliente_nome"],
            negociador_id=r["negociador_id"],
            negociador_nome=r["negociador_nome"],
            data_acordo=r["data_acordo"],
            data_criacao=r["data_criacao"],
            data_encerramento=r["data_encerramento"],
            valor_total=float(r["valor_total"]),
            quantidade_parcelas=int(r["quantidade_parcelas"]),
            parcelas_pagas=int(r["qtd_pagas"]),
            parcelas_em_atraso=int(r["qtd_atrasadas"]),
            saldo_devedor=float(r["saldo_dev"]),
            proxima_parcela_data=r["proxima_data"],
            status=StatusAcordo(r["status"]),
            tipo_cobranca=TipoCobranca(r["tipo_cobranca"]),
        )
        for r in cur.fetchall()
    ]


def buscar_completo(acordo_id: int) -> Optional[AcordoCompleto]:
    """Carrega acordo + todos os boletos + todas as parcelas + pagamentos."""
    cur = obter_conexao().execute(
        """
        SELECT a.*, c.nome_principal AS cliente_nome, u.nome AS negociador_nome
        FROM acordo a
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u ON u.id = a.negociador_id
        WHERE a.id = ?;
        """,
        (acordo_id,),
    )
    row = cur.fetchone()
    if not row:
        return None

    # Parcelas
    parcelas: List[Parcela] = []
    for pr in obter_conexao().execute(
        "SELECT * FROM parcela WHERE acordo_id = ? ORDER BY numero;", (acordo_id,)
    ).fetchall():
        p = Parcela(
            numero=pr["numero"],
            vencimento_original=datetime.fromisoformat(pr["vencimento_original"]).date(),
            vencimento_atual=datetime.fromisoformat(pr["vencimento_atual"]).date(),
            valor_original=float(pr["valor_original"]),
            principal=float(pr["principal"]),
            juros=float(pr["juros"]),
            multa=float(pr["multa"]),
            saldo_apos=float(pr["saldo_apos"]),
            status=StatusParcela(pr["status"]),
        )
        # Pagamentos da parcela
        for pg in obter_conexao().execute(
            "SELECT * FROM pagamento_parcela WHERE parcela_id = ? ORDER BY data_pagamento;",
            (pr["id"],),
        ).fetchall():
            p.pagamentos.append(
                PagamentoParcela(
                    data_pagamento=datetime.fromisoformat(pg["data_pagamento"]).date(),
                    valor=float(pg["valor"]),
                    observacao=pg["observacao"] or "",
                )
            )
        parcelas.append(p)

    # Boletos
    boletos: List[Boleto] = []
    for br in obter_conexao().execute(
        "SELECT * FROM boleto WHERE acordo_id = ? ORDER BY vencimento, numero_unico;",
        (acordo_id,),
    ).fetchall():
        b = Boleto(
            codigo_parceiro=br["codigo_parceiro"],
            razao_social_parceiro=br["razao_social_parceiro"],
            empresa=Empresa(int(br["empresa"])),
            codigo_vendedor=br["codigo_vendedor"],
            nome_vendedor=br["nome_vendedor"],
            vencimento=datetime.fromisoformat(br["vencimento"]).date(),
            numero_nota=br["numero_nota"],
            numero_unico=br["numero_unico"],
            principal=float(br["principal"]),
            dias_atraso=int(br["dias_atraso"]),
            fim_juros=(
                datetime.fromisoformat(br["fim_juros"]).date()
                if br["fim_juros"] else date.today()
            ),
            juros=float(br["juros"]),
            multa=float(br["multa"]),
            total=float(br["total"]),
            parcelas_alocadas=_deserializar(br["parcelas_alocadas"], []),
            distribuicao=_deserializar(br["distribuicao"], []),
            origem=OrigemDado(br["origem"]),
            titulo_sankhya_id=br["titulo_sankhya_id"],
        )
        boletos.append(b)

    return AcordoCompleto(
        id=row["id"],
        numero_interno=row["numero_interno"],
        cliente_id=row["cliente_id"],
        cliente_nome=row["cliente_nome"],
        negociador_id=row["negociador_id"],
        negociador_nome=row["negociador_nome"],
        criado_por_id=row["criado_por_id"],
        data_criacao=row["data_criacao"],
        data_acordo=datetime.fromisoformat(row["data_acordo"]).date(),
        data_encerramento=row["data_encerramento"],
        pct_juros_mes_titulos=float(row["pct_juros_mes_titulos"]),
        pct_multa_titulos=float(row["pct_multa_titulos"]),
        pct_juros_mora_mes=float(row["pct_juros_mora_mes"]),
        pct_multa_mora=float(row["pct_multa_mora"]),
        pct_desconto=float(row["pct_desconto"]) if row["pct_desconto"] is not None else 0.0,
        tipo_cobranca=TipoCobranca(row["tipo_cobranca"]),
        periodicidade=Periodicidade(row["periodicidade"]),
        intervalo_personalizado_dias=int(row["intervalo_personalizado_dias"] or 1),
        valor_total=float(row["valor_total"]),
        quantidade_parcelas=int(row["quantidade_parcelas"]),
        status=StatusAcordo(row["status"]),
        observacoes=row["observacoes"],
        boletos=boletos,
        parcelas=parcelas,
    )


# ============================================================
# MUDANÇAS DE STATUS E PAGAMENTOS
# ============================================================

def atualizar_status(acordo_id: int, novo_status: StatusAcordo) -> None:
    encerra = novo_status in (
        StatusAcordo.QUITADO, StatusAcordo.QUEBRADO, StatusAcordo.CANCELADO
    )
    with transacao() as conn:
        if encerra:
            conn.execute(
                "UPDATE acordo SET status = ?, data_encerramento = datetime('now') WHERE id = ?;",
                (novo_status.value, acordo_id),
            )
        else:
            conn.execute(
                "UPDATE acordo SET status = ?, data_encerramento = NULL WHERE id = ?;",
                (novo_status.value, acordo_id),
            )


def registrar_pagamento(
    parcela_id: int,
    valor: float,
    data_pagamento: date,
    registrado_por_id: int,
    observacao: str = "",
    confirmado_pelo_admin: bool = False,
) -> StatusParcela:
    """
    Registra um pagamento na parcela.

    Fluxo de dupla confirmação (Erick - decisão 13/05/2026):
      - Cobrança registra → confirmado_pelo_admin=False → parcela vai pra
        AGUARDANDO_CONFIRMACAO
      - Admin confirma depois → confirmado_pelo_admin=True → parcela vai pra
        QUITADA ou PARCIAL conforme valor pago
      - Admin pode chamar essa função diretamente com confirmado_pelo_admin=True
        pra "registrar e confirmar" num passo só

    Retorna o novo status da parcela.
    """
    if valor <= 0:
        raise ValueError("Valor do pagamento precisa ser > 0.")

    confirmado_em = datetime.now().isoformat() if confirmado_pelo_admin else None
    confirmado_por = registrado_por_id if confirmado_pelo_admin else None

    with transacao() as conn:
        conn.execute(
            """
            INSERT INTO pagamento_parcela
            (parcela_id, data_pagamento, valor, observacao, registrado_por_id,
             confirmado_pelo_admin, confirmado_por_id, confirmado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (parcela_id, data_pagamento.isoformat(), round(valor, 2),
             observacao or None, registrado_por_id,
             1 if confirmado_pelo_admin else 0,
             confirmado_por, confirmado_em),
        )
        novo_status = _recalcular_status_parcela(conn, parcela_id)
    return novo_status


def confirmar_pagamento_admin(
    pagamento_id: int,
    confirmado_por_id: int,
) -> StatusParcela:
    """
    Admin confirma um pagamento que a cobrança havia registrado.
    Marca confirmado_pelo_admin=True e recalcula status da parcela.
    """
    with transacao() as conn:
        cur = conn.execute(
            "SELECT parcela_id, confirmado_pelo_admin FROM pagamento_parcela WHERE id = ?;",
            (pagamento_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Pagamento {pagamento_id} não encontrado.")
        if row["confirmado_pelo_admin"]:
            raise ValueError("Esse pagamento já foi confirmado.")
        parcela_id = row["parcela_id"]

        conn.execute(
            """
            UPDATE pagamento_parcela
            SET confirmado_pelo_admin = 1,
                confirmado_por_id = ?,
                confirmado_em = ?
            WHERE id = ?;
            """,
            (confirmado_por_id, datetime.now().isoformat(), pagamento_id),
        )
        novo_status = _recalcular_status_parcela(conn, parcela_id)
    return novo_status


def desfazer_confirmacao_cobranca(pagamento_id: int) -> StatusParcela:
    """
    Cobrança/Admin desfaz um pagamento ainda NÃO confirmado pelo admin.
    Só funciona se confirmado_pelo_admin = 0.
    Apaga o pagamento e recalcula status.
    """
    with transacao() as conn:
        cur = conn.execute(
            "SELECT parcela_id, confirmado_pelo_admin FROM pagamento_parcela WHERE id = ?;",
            (pagamento_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Pagamento {pagamento_id} não encontrado.")
        if row["confirmado_pelo_admin"]:
            raise ValueError(
                "Esse pagamento já foi confirmado pelo admin — não pode ser "
                "desfeito pela cobrança. Peça pra um admin estornar."
            )
        parcela_id = row["parcela_id"]
        conn.execute("DELETE FROM pagamento_parcela WHERE id = ?;", (pagamento_id,))
        novo_status = _recalcular_status_parcela(conn, parcela_id)
    return novo_status


def _recalcular_status_parcela(conn, parcela_id: int) -> StatusParcela:
    """
    Calcula o status da parcela com base nos pagamentos confirmados e pendentes.

    Regras:
      - Não tem nenhum pagamento → EM_ABERTO
      - Tem pagamentos não-confirmados (cobrança registrou, admin ainda não confirmou)
        e a soma TOTAL (confirmados + pendentes) cobre o valor → AGUARDANDO_CONFIRMACAO
      - Tem pagamentos confirmados pelo admin >= valor → QUITADA
      - Tem pagamentos confirmados > 0 mas < valor → PARCIAL
      - Só pagamentos não-confirmados < valor → AGUARDANDO_CONFIRMACAO
    """
    cur = conn.execute(
        "SELECT valor_original FROM parcela WHERE id = ?;", (parcela_id,)
    )
    valor_original = float(cur.fetchone()[0])

    cur = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN confirmado_pelo_admin = 1 THEN valor ELSE 0 END), 0) AS pago_confirmado,
            COALESCE(SUM(valor), 0) AS pago_total,
            COUNT(*) AS total_pagamentos
        FROM pagamento_parcela
        WHERE parcela_id = ?;
        """,
        (parcela_id,),
    )
    row = cur.fetchone()
    pago_confirmado = float(row[0])
    pago_total = float(row[1])
    total_pagamentos = int(row[2])

    if total_pagamentos == 0:
        novo_status = StatusParcela.EM_ABERTO
    elif pago_confirmado >= valor_original - 0.005:
        novo_status = StatusParcela.QUITADA
    elif pago_confirmado > 0:
        # Tem pagamento confirmado mas não cobre tudo — PARCIAL
        # Mesmo que haja pagamentos pendentes, prevalece o PARCIAL
        novo_status = StatusParcela.PARCIAL
    else:
        # Só tem pagamentos não-confirmados ainda
        novo_status = StatusParcela.AGUARDANDO_CONFIRMACAO

    conn.execute(
        "UPDATE parcela SET status = ? WHERE id = ?;",
        (novo_status.value, parcela_id),
    )
    return novo_status


def listar_parcelas_confirmadas(
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    termo_busca: Optional[str] = None,
    apenas_hoje: bool = False,
    negociador_id: Optional[int] = None,
) -> List[dict]:
    """
    Lista parcelas com pagamentos CONFIRMADOS pelo admin.
    Suporta filtros: período, termo de busca (CNPJ, nome, código parceiro).
    Usado pela página "Parcelas Confirmadas" e pelo bloco "Hoje" no Início.
    """
    sql = """
        SELECT
            pp.id AS pagamento_id,
            pp.valor AS valor_pago,
            pp.data_pagamento,
            pp.observacao,
            pp.confirmado_em,
            pp.registrado_por_id,
            ureg.nome AS registrado_por_nome,
            uconf.nome AS confirmado_por_nome,
            p.id AS parcela_id,
            p.numero AS parcela_numero,
            p.valor_original AS parcela_valor_original,
            p.vencimento_atual AS parcela_vencimento,
            a.id AS acordo_id,
            a.numero_interno,
            c.nome_principal AS cliente_nome,
            c.cnpj AS cliente_cnpj,
            uneg.nome AS negociador_nome
        FROM pagamento_parcela pp
        JOIN parcela p ON p.id = pp.parcela_id
        JOIN acordo a ON a.id = p.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario ureg ON ureg.id = pp.registrado_por_id
        LEFT JOIN usuario uconf ON uconf.id = pp.confirmado_por_id
        JOIN usuario uneg ON uneg.id = a.negociador_id
        WHERE pp.confirmado_pelo_admin = 1
    """
    params: list = []

    if apenas_hoje:
        sql += " AND DATE(pp.confirmado_em) = DATE('now')"
    else:
        if data_inicio:
            sql += " AND DATE(pp.confirmado_em) >= ?"
            params.append(data_inicio.isoformat())
        if data_fim:
            sql += " AND DATE(pp.confirmado_em) <= ?"
            params.append(data_fim.isoformat())

    if negociador_id:
        sql += " AND a.negociador_id = ?"
        params.append(negociador_id)

    sql += " ORDER BY pp.confirmado_em DESC;"
    cur = obter_conexao().execute(sql, params)
    todos = [dict(r) for r in cur.fetchall()]

    # Filtro de termo (em memória, pra também buscar no código do parceiro)
    if termo_busca and termo_busca.strip():
        from src.utils.formatadores import normalizar_busca
        termo_norm = normalizar_busca(termo_busca)

        # Pra cada pagamento, busca códigos de parceiro do acordo
        def matcha(p_dict):
            campos = [
                p_dict.get("cliente_nome"),
                p_dict.get("cliente_cnpj"),
                p_dict.get("numero_interno"),
                p_dict.get("negociador_nome"),
            ]
            for c in campos:
                if c and termo_norm in normalizar_busca(str(c)):
                    return True
            # Busca em códigos de parceiro dos boletos
            cur2 = obter_conexao().execute(
                "SELECT codigo_parceiro, razao_social_parceiro FROM boleto WHERE acordo_id = ?;",
                (p_dict["acordo_id"],),
            )
            for row in cur2.fetchall():
                if termo_norm in normalizar_busca(str(row[0])):
                    return True
                if termo_norm in normalizar_busca(str(row[1])):
                    return True
            return False

        todos = [p for p in todos if matcha(p)]

    return todos


def listar_codigos_parceiro_do_acordo(acordo_id: int) -> List[dict]:
    """Pega lista distinta de códigos+razão social dos parceiros de um acordo."""
    cur = obter_conexao().execute(
        """
        SELECT DISTINCT codigo_parceiro, razao_social_parceiro, empresa
        FROM boleto WHERE acordo_id = ?
        ORDER BY codigo_parceiro;
        """,
        (acordo_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def listar_pagamentos_aguardando_confirmacao(
    negociador_id: Optional[int] = None,
) -> List[dict]:
    """
    Lista todos os pagamentos que a cobrança registrou mas o admin ainda não
    confirmou. Usado pelo bloco "Parcelas aguardando confirmação" no Início
    do admin.
    """
    sql = """
        SELECT
            pp.id AS pagamento_id,
            pp.valor,
            pp.data_pagamento,
            pp.observacao,
            pp.registrado_em,
            pp.registrado_por_id,
            ureg.nome AS registrado_por_nome,
            p.id AS parcela_id,
            p.numero AS parcela_numero,
            p.valor_original AS parcela_valor_original,
            p.vencimento_atual AS parcela_vencimento,
            a.id AS acordo_id,
            a.numero_interno,
            c.nome_principal AS cliente_nome,
            uneg.nome AS negociador_nome
        FROM pagamento_parcela pp
        JOIN parcela p ON p.id = pp.parcela_id
        JOIN acordo a ON a.id = p.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario ureg ON ureg.id = pp.registrado_por_id
        JOIN usuario uneg ON uneg.id = a.negociador_id
        WHERE pp.confirmado_pelo_admin = 0
    """
    params: list = []
    if negociador_id:
        sql += " AND a.negociador_id = ?"
        params.append(negociador_id)
    sql += " ORDER BY pp.registrado_em ASC;"
    cur = obter_conexao().execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def listar_pagamentos_da_parcela(parcela_id: int) -> List[dict]:
    """
    Lista todos os pagamentos de uma parcela (confirmados e pendentes).
    Usado pra mostrar histórico e botões de ação.
    """
    cur = obter_conexao().execute(
        """
        SELECT
            pp.id, pp.parcela_id, pp.valor, pp.data_pagamento, pp.observacao,
            pp.registrado_em, pp.registrado_por_id,
            pp.confirmado_pelo_admin, pp.confirmado_por_id, pp.confirmado_em,
            ureg.nome AS registrado_por_nome,
            uconf.nome AS confirmado_por_nome
        FROM pagamento_parcela pp
        LEFT JOIN usuario ureg ON ureg.id = pp.registrado_por_id
        LEFT JOIN usuario uconf ON uconf.id = pp.confirmado_por_id
        WHERE pp.parcela_id = ?
        ORDER BY pp.registrado_em ASC;
        """,
        (parcela_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def estornar_pagamento(pagamento_id: int) -> None:
    """
    Apaga um pagamento (mesmo se já confirmado) e recalcula o status.
    Use isso pra reverter um pagamento confirmado pelo admin.
    Se quiser apenas remover um pagamento que ainda não foi confirmado,
    use desfazer_confirmacao_cobranca().
    """
    with transacao() as conn:
        cur = conn.execute(
            "SELECT parcela_id FROM pagamento_parcela WHERE id = ?;", (pagamento_id,)
        )
        row = cur.fetchone()
        if not row:
            return
        parcela_id = row["parcela_id"]
        conn.execute("DELETE FROM pagamento_parcela WHERE id = ?;", (pagamento_id,))
        _recalcular_status_parcela(conn, parcela_id)


def remarcar_vencimento_parcela(
    parcela_id: int,
    nova_data: date,
    novo_valor_original: Optional[float] = None,
    acrescimo_juros: float = 0.0,
    acrescimo_multa: float = 0.0,
) -> None:
    """
    Remarca a data de uma parcela (Seção 18b - permitido, sem afetar outras).

    Erick — extensão: opcionalmente atualiza o valor da parcela aplicando
    juros e multa de mora calculados. Os acréscimos vão pra coluna juros/multa
    da parcela (somam aos existentes).

    Parâmetros:
      - parcela_id: id da parcela
      - nova_data: nova data de vencimento
      - novo_valor_original: se informado, atualiza o valor da parcela
      - acrescimo_juros: valor de juros a somar (em R$)
      - acrescimo_multa: valor de multa a somar (em R$)
    """
    with transacao() as conn:
        if novo_valor_original is not None:
            # Atualiza tudo: data + valor + componentes
            conn.execute(
                """
                UPDATE parcela SET
                    vencimento_atual = ?,
                    valor_original = ?,
                    juros = juros + ?,
                    multa = multa + ?
                WHERE id = ?;
                """,
                (
                    nova_data.isoformat(),
                    round(novo_valor_original, 2),
                    round(acrescimo_juros, 2),
                    round(acrescimo_multa, 2),
                    parcela_id,
                ),
            )
        else:
            # Só data (comportamento original)
            conn.execute(
                "UPDATE parcela SET vencimento_atual = ? WHERE id = ?;",
                (nova_data.isoformat(), parcela_id),
            )


def buscar_parcela_id(acordo_id: int, numero: int) -> Optional[int]:
    cur = obter_conexao().execute(
        "SELECT id FROM parcela WHERE acordo_id = ? AND numero = ?;",
        (acordo_id, numero),
    )
    row = cur.fetchone()
    return row["id"] if row else None


def listar_pagamentos_parcela(parcela_id: int) -> List[dict]:
    """Lista de pagamentos de uma parcela, do mais antigo pro mais recente."""
    cur = obter_conexao().execute(
        """
        SELECT pp.*, u.nome AS registrado_por_nome
        FROM pagamento_parcela pp
        LEFT JOIN usuario u ON u.id = pp.registrado_por_id
        WHERE parcela_id = ?
        ORDER BY data_pagamento, id;
        """,
        (parcela_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def listar_parcelas_vencendo_em(
    data: date,
    negociador_id: Optional[int] = None,
) -> List[dict]:
    """
    Lista parcelas que VENCEM no dia informado, opcionalmente filtrando
    pelo negociador (briefing - cada um vê só os seus).

    Considera apenas acordos ATIVOS e parcelas não-quitadas.
    """
    sql = """
        SELECT
            p.id AS parcela_id,
            p.numero AS numero_parcela,
            p.vencimento_atual,
            p.valor_original,
            p.status AS parcela_status,
            a.id AS acordo_id,
            a.numero_interno AS acordo_numero,
            a.tipo_cobranca,
            c.nome_principal AS cliente_nome,
            c.email_cobranca,
            c.telefone,
            u.id AS negociador_id,
            u.nome AS negociador_nome,
            (SELECT COALESCE(SUM(valor), 0) FROM pagamento_parcela WHERE parcela_id = p.id) AS valor_pago
        FROM parcela p
        JOIN acordo a ON a.id = p.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u ON u.id = a.negociador_id
        WHERE DATE(p.vencimento_atual) = DATE(?)
          AND p.status != 'QUITADA'
          AND a.status = 'ATIVO'
    """
    params: list = [data.isoformat()]
    if negociador_id:
        sql += " AND a.negociador_id = ?"
        params.append(negociador_id)
    sql += " ORDER BY c.nome_principal, p.numero;"

    cur = obter_conexao().execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


# ============================================================
# Filtros de carteira (negociadores)
# ============================================================

def listar_negociadores_com_acordos() -> list[dict]:
    """
    Retorna a lista de negociadores que TÊM ao menos um acordo no sistema,
    junto com a quantidade. Usado no filtro de carteira do Dashboard.
    
    Retorna: [{id, nome, qtd_acordos}, ...]
    """
    cur = obter_conexao().execute("""
        SELECT u.id, u.nome, COUNT(a.id) as qtd_acordos
        FROM usuario u
        JOIN acordo a ON a.negociador_id = u.id
        GROUP BY u.id, u.nome
        ORDER BY u.nome;
    """)
    return [
        {"id": r["id"], "nome": r["nome"], "qtd_acordos": r["qtd_acordos"]}
        for r in cur.fetchall()
    ]


def alterar_negociador_acordo(
    acordo_id: int,
    novo_negociador_id: int,
) -> dict:
    """
    Altera o negociador responsável por um acordo já existente.
    
    Retorna: {negociador_anterior_id, negociador_anterior_nome,
              negociador_novo_id, negociador_novo_nome}
    
    Raises:
        ValueError: se acordo ou negociador não existirem.
    """
    conn = obter_conexao()

    # Busca o negociador atual
    row_atual = conn.execute(
        "SELECT a.negociador_id, u.nome FROM acordo a "
        "JOIN usuario u ON u.id = a.negociador_id "
        "WHERE a.id = ?;",
        (acordo_id,)
    ).fetchone()
    if not row_atual:
        raise ValueError(f"Acordo {acordo_id} não encontrado.")

    # Busca o novo
    row_novo = conn.execute(
        "SELECT id, nome FROM usuario WHERE id = ? AND ativo = 1;",
        (novo_negociador_id,)
    ).fetchone()
    if not row_novo:
        raise ValueError(f"Usuário {novo_negociador_id} não existe ou está inativo.")

    if row_atual["negociador_id"] == novo_negociador_id:
        return {
            "negociador_anterior_id": row_atual["negociador_id"],
            "negociador_anterior_nome": row_atual["nome"],
            "negociador_novo_id": novo_negociador_id,
            "negociador_novo_nome": row_novo["nome"],
            "sem_mudanca": True,
        }

    conn.execute(
        "UPDATE acordo SET negociador_id = ? WHERE id = ?;",
        (novo_negociador_id, acordo_id),
    )

    return {
        "negociador_anterior_id": row_atual["negociador_id"],
        "negociador_anterior_nome": row_atual["nome"],
        "negociador_novo_id": novo_negociador_id,
        "negociador_novo_nome": row_novo["nome"],
        "sem_mudanca": False,
    }
