"""
Schema do banco de dados.

Modela todas as entidades da Seção 11 do briefing:
  - usuario
  - cliente
  - acordo
  - parcela
  - pagamento_parcela (NOVO: suporta pagamento parcial - P4)
  - boleto
  - rascunho_acordo
  - aprovacao_acordo (NOVO: fluxo de aprovação - P5)
  - log_auditoria
  - parametros_sistema
  - sequencia_acordo (gera o número ACO-AAAAMMDD-###)
"""
from __future__ import annotations

import sqlite3
from typing import List

# Migrations em ordem. Cada migration roda 1 vez. Versão atual = len(MIGRATIONS).
MIGRATIONS: List[str] = []


# ============================================================
# MIGRATION 001 — Tabelas base
# ============================================================

MIGRATIONS.append("""
-- Controle de versão
CREATE TABLE IF NOT EXISTS schema_versao (
    versao INTEGER PRIMARY KEY,
    aplicada_em TEXT NOT NULL DEFAULT (datetime('now'))
);

-- USUÁRIOS (briefing Seção 11 e 24)
CREATE TABLE IF NOT EXISTS usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,         -- bcrypt hash
    perfil TEXT NOT NULL CHECK(perfil IN ('ADMIN', 'COBRANCA', 'DIRETORIA')),
    ativo INTEGER NOT NULL DEFAULT 1, -- 0/1 (SQLite não tem bool nativo)
    deve_trocar_senha INTEGER NOT NULL DEFAULT 0,
    -- Sistema de aprovação por chave (Erick joga a chave no Secrets pra liberar)
    chave_aprovacao TEXT,             -- token único gerado no cadastro
    aprovado INTEGER NOT NULL DEFAULT 0,  -- 0=pendente, 1=aprovado via secrets
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    ultimo_login TEXT
);

CREATE INDEX IF NOT EXISTS idx_usuario_email ON usuario(email);
CREATE INDEX IF NOT EXISTS idx_usuario_perfil_ativo ON usuario(perfil, ativo);

-- CLIENTE (entidade independente do acordo; permite histórico futuro - briefing Seção 8)
CREATE TABLE IF NOT EXISTS cliente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_principal TEXT NOT NULL,
    cnpj TEXT,                        -- pode ser nulo no MVP
    contato TEXT,
    email_cobranca TEXT,
    telefone TEXT,
    tem_whatsapp INTEGER NOT NULL DEFAULT 0,   -- 0=não, 1=sim
    sankhya_id TEXT,                  -- gancho integração futura
    origem TEXT NOT NULL DEFAULT 'MANUAL' CHECK(origem IN ('MANUAL', 'SANKHYA')),
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cliente_nome ON cliente(nome_principal);
CREATE INDEX IF NOT EXISTS idx_cliente_sankhya ON cliente(sankhya_id);

-- ACORDO (briefing Seção 11)
CREATE TABLE IF NOT EXISTS acordo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_interno TEXT NOT NULL UNIQUE,   -- ACO-AAAAMMDD-###
    cliente_id INTEGER NOT NULL REFERENCES cliente(id),
    negociador_id INTEGER NOT NULL REFERENCES usuario(id),
    criado_por_id INTEGER NOT NULL REFERENCES usuario(id),
    -- Datas
    data_criacao TEXT NOT NULL DEFAULT (datetime('now')),
    data_acordo TEXT NOT NULL,
    data_encerramento TEXT,
    -- Configuração financeira (4 percentuais INDEPENDENTES - P3 e Seção 13)
    pct_juros_mes_titulos REAL NOT NULL,
    pct_multa_titulos REAL NOT NULL,
    pct_juros_mora_mes REAL NOT NULL,
    pct_multa_mora REAL NOT NULL,
    pct_desconto REAL NOT NULL DEFAULT 0.0,
    tipo_cobranca TEXT NOT NULL CHECK(tipo_cobranca IN ('BOLETO', 'PIX')),
    -- Parcelamento
    periodicidade TEXT NOT NULL CHECK(periodicidade IN ('MENSAL', 'QUINZENAL', 'SEMANAL', 'PERSONALIZADA')),
    intervalo_personalizado_dias INTEGER DEFAULT 1,
    valor_total REAL NOT NULL,
    quantidade_parcelas INTEGER NOT NULL,
    -- Status (Seção 19c + P5: PENDENTE_APROVACAO)
    status TEXT NOT NULL DEFAULT 'ATIVO'
        CHECK(status IN ('RASCUNHO', 'PENDENTE_APROVACAO', 'ATIVO', 'QUITADO', 'QUEBRADO', 'CANCELADO')),
    -- Observação livre
    observacoes TEXT
);

CREATE INDEX IF NOT EXISTS idx_acordo_cliente ON acordo(cliente_id);
CREATE INDEX IF NOT EXISTS idx_acordo_negociador ON acordo(negociador_id);
CREATE INDEX IF NOT EXISTS idx_acordo_status ON acordo(status);
CREATE INDEX IF NOT EXISTS idx_acordo_data ON acordo(data_acordo);

-- PARCELA do cronograma do acordo (briefing Seção 11 + P4 pagamento parcial)
CREATE TABLE IF NOT EXISTS parcela (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acordo_id INTEGER NOT NULL REFERENCES acordo(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    vencimento_original TEXT NOT NULL,
    vencimento_atual TEXT NOT NULL,        -- pode ser remarcada (Seção 18b)
    valor_original REAL NOT NULL,
    -- Decomposição via FIFO
    principal REAL NOT NULL DEFAULT 0,
    juros REAL NOT NULL DEFAULT 0,
    multa REAL NOT NULL DEFAULT 0,
    saldo_apos REAL NOT NULL DEFAULT 0,
    -- Status (P4 - 4 estados após dupla confirmação)
    status TEXT NOT NULL DEFAULT 'EM_ABERTO'
        CHECK(status IN ('EM_ABERTO', 'AGUARDANDO_CONFIRMACAO', 'PARCIAL', 'QUITADA')),
    UNIQUE(acordo_id, numero)
);

CREATE INDEX IF NOT EXISTS idx_parcela_acordo ON parcela(acordo_id);
CREATE INDEX IF NOT EXISTS idx_parcela_vencimento ON parcela(vencimento_atual);
CREATE INDEX IF NOT EXISTS idx_parcela_status ON parcela(status);

-- PAGAMENTO_PARCELA — suporta pagamento parcial (P4)
-- Uma parcela pode ter múltiplos pagamentos. Soma deles == valor_pago.
CREATE TABLE IF NOT EXISTS pagamento_parcela (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parcela_id INTEGER NOT NULL REFERENCES parcela(id) ON DELETE CASCADE,
    data_pagamento TEXT NOT NULL,
    valor REAL NOT NULL,
    observacao TEXT,
    registrado_por_id INTEGER NOT NULL REFERENCES usuario(id),
    registrado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pagamento_parcela ON pagamento_parcela(parcela_id);

-- BOLETO (título original que entrou no acordo - briefing Seção 11 e 17)
CREATE TABLE IF NOT EXISTS boleto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acordo_id INTEGER NOT NULL REFERENCES acordo(id) ON DELETE CASCADE,
    -- Identificação do parceiro/vendedor (Seção 17)
    codigo_parceiro TEXT NOT NULL,
    razao_social_parceiro TEXT NOT NULL,
    empresa INTEGER NOT NULL CHECK(empresa IN (1, 2)),
    codigo_vendedor TEXT NOT NULL,
    nome_vendedor TEXT NOT NULL,
    -- Dados do título
    vencimento TEXT NOT NULL,
    numero_nota TEXT NOT NULL,
    numero_unico TEXT NOT NULL,
    principal REAL NOT NULL,
    -- Calculados (CASO 1)
    dias_atraso INTEGER NOT NULL DEFAULT 0,
    fim_juros TEXT,
    juros REAL NOT NULL DEFAULT 0,
    multa REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    -- Vínculo com parcelas (lista CSV "1,2,3" + JSON com detalhe)
    parcelas_alocadas TEXT,           -- JSON: [1, 2, 3]
    distribuicao TEXT,                -- JSON: [{"parcela": 1, "valor": 47.08}, ...]
    -- Gancho integração
    titulo_sankhya_id TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL' CHECK(origem IN ('MANUAL', 'SANKHYA')),
    UNIQUE(acordo_id, numero_unico)   -- briefing Seção 20: nº único é a chave
);

CREATE INDEX IF NOT EXISTS idx_boleto_acordo ON boleto(acordo_id);
CREATE INDEX IF NOT EXISTS idx_boleto_parceiro ON boleto(codigo_parceiro);
CREATE INDEX IF NOT EXISTS idx_boleto_vendedor ON boleto(codigo_vendedor);
CREATE INDEX IF NOT EXISTS idx_boleto_nota ON boleto(numero_nota);
CREATE INDEX IF NOT EXISTS idx_boleto_unico ON boleto(numero_unico);

-- RASCUNHO_ACORDO (briefing Seção 16b)
-- Estado do wizard salvo num JSON único, sem precisar normalizar.
CREATE TABLE IF NOT EXISTS rascunho_acordo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_por_id INTEGER NOT NULL REFERENCES usuario(id),
    titulo TEXT NOT NULL,             -- nome do cliente ou identificador
    passo_atual INTEGER NOT NULL DEFAULT 1,
    estado_json TEXT NOT NULL,        -- snapshot do wizard
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rascunho_usuario ON rascunho_acordo(criado_por_id);

-- APROVACAO_ACORDO (P5 - fluxo de aprovação)
CREATE TABLE IF NOT EXISTS aprovacao_acordo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acordo_id INTEGER NOT NULL REFERENCES acordo(id) ON DELETE CASCADE,
    solicitado_por_id INTEGER NOT NULL REFERENCES usuario(id),
    justificativa_solicitacao TEXT NOT NULL,
    solicitado_em TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'PENDENTE'
        CHECK(status IN ('PENDENTE', 'APROVADO', 'RECUSADO')),
    revisado_por_id INTEGER REFERENCES usuario(id),
    justificativa_revisao TEXT,
    revisado_em TEXT
);

CREATE INDEX IF NOT EXISTS idx_aprovacao_status ON aprovacao_acordo(status);

-- LOG_AUDITORIA (briefing Seção 18e)
CREATE TABLE IF NOT EXISTS log_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER REFERENCES usuario(id),
    usuario_nome_snapshot TEXT,       -- preserva nome mesmo se usuário for inativado
    acao TEXT NOT NULL,
    entidade TEXT NOT NULL,           -- "acordo", "parcela", "usuario", etc.
    entidade_id INTEGER,
    contexto TEXT,                    -- ex: "Acordo ACO-... | Parcela 6"
    antes_json TEXT,                  -- snapshot antes (JSON)
    depois_json TEXT,                 -- snapshot depois (JSON)
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_usuario ON log_auditoria(usuario_id);
CREATE INDEX IF NOT EXISTS idx_audit_entidade ON log_auditoria(entidade, entidade_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON log_auditoria(timestamp);

-- PARAMETROS_SISTEMA — chave-valor genérico pra config (lembretes, templates, limites)
CREATE TABLE IF NOT EXISTS parametros_sistema (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_por_id INTEGER REFERENCES usuario(id)
);

-- COMENTARIO_ACORDO — histórico de tentativas de contato e anotações livres
CREATE TABLE IF NOT EXISTS comentario_acordo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acordo_id INTEGER NOT NULL REFERENCES acordo(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    usuario_nome_snapshot TEXT,
    tipo TEXT NOT NULL DEFAULT 'NOTA'
        CHECK(tipo IN ('NOTA', 'LIGACAO', 'WHATSAPP', 'EMAIL', 'VISITA', 'OUTRO')),
    texto TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_coment_acordo ON comentario_acordo(acordo_id, criado_em DESC);

-- PROMESSA_PAGAMENTO — cliente prometeu pagar tal dia
CREATE TABLE IF NOT EXISTS promessa_pagamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acordo_id INTEGER NOT NULL REFERENCES acordo(id) ON DELETE CASCADE,
    parcela_id INTEGER REFERENCES parcela(id),
    data_prometida TEXT NOT NULL,
    valor_prometido REAL,
    observacao TEXT,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    usuario_nome_snapshot TEXT,
    status TEXT NOT NULL DEFAULT 'AGUARDANDO'
        CHECK(status IN ('AGUARDANDO', 'CUMPRIDA', 'QUEBRADA', 'CANCELADA')),
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT
);

CREATE INDEX IF NOT EXISTS idx_promessa_acordo ON promessa_pagamento(acordo_id);
CREATE INDEX IF NOT EXISTS idx_promessa_data ON promessa_pagamento(data_prometida, status);

-- FILTRO_SALVO — filtros personalizados de busca de acordo
CREATE TABLE IF NOT EXISTS filtro_salvo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    nome TEXT NOT NULL,
    configuracao_json TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_filtro_usuario ON filtro_salvo(usuario_id);

-- SEQUENCIA_ACORDO — gera o número interno ACO-AAAAMMDD-### (P7)
-- Uma linha por dia. Incrementa o sequencial atomicamente.
CREATE TABLE IF NOT EXISTS sequencia_acordo (
    data TEXT PRIMARY KEY,            -- YYYY-MM-DD
    proximo_numero INTEGER NOT NULL DEFAULT 1
);
""")


# ============================================================
# MIGRATION 002 — Colunas adicionadas após o lançamento
# ============================================================
# Cliente: tem_whatsapp (Erick - tela Cadastro)
# Usuário: chave_aprovacao e aprovado (já existem na criação,
#          mas pode ter banco antigo sem esses campos)
#
# Usamos ALTER TABLE ADD COLUMN com tratamento de exceção
# (SQLite não tem "IF NOT EXISTS" pra colunas).

MIGRATIONS.append("""
-- Tentativas idempotentes (ignoram erro se coluna já existe)
-- Cada ALTER em statement separado, com tratamento via Python

-- Marcador apenas - os ALTERs são feitos via Python na função aplicar_migrations
SELECT 1;
""")


# ============================================================
# MIGRATION 003 — Tabelas novas (comentários, promessas, filtros)
# ============================================================

MIGRATIONS.append("""
CREATE TABLE IF NOT EXISTS comentario_acordo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acordo_id INTEGER NOT NULL REFERENCES acordo(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    usuario_nome_snapshot TEXT,
    tipo TEXT NOT NULL DEFAULT 'NOTA'
        CHECK(tipo IN ('NOTA', 'LIGACAO', 'WHATSAPP', 'EMAIL', 'VISITA', 'OUTRO')),
    texto TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_coment_acordo ON comentario_acordo(acordo_id, criado_em DESC);

CREATE TABLE IF NOT EXISTS promessa_pagamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acordo_id INTEGER NOT NULL REFERENCES acordo(id) ON DELETE CASCADE,
    parcela_id INTEGER REFERENCES parcela(id),
    data_prometida TEXT NOT NULL,
    valor_prometido REAL,
    observacao TEXT,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    usuario_nome_snapshot TEXT,
    status TEXT NOT NULL DEFAULT 'AGUARDANDO'
        CHECK(status IN ('AGUARDANDO', 'CUMPRIDA', 'QUEBRADA', 'CANCELADA')),
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT
);

CREATE INDEX IF NOT EXISTS idx_promessa_acordo ON promessa_pagamento(acordo_id);
CREATE INDEX IF NOT EXISTS idx_promessa_data ON promessa_pagamento(data_prometida, status);

CREATE TABLE IF NOT EXISTS filtro_salvo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    nome TEXT NOT NULL,
    configuracao_json TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_filtro_usuario ON filtro_salvo(usuario_id);
""")


# ============================================================
# MIGRATION 004 — Confirmação dupla de pagamento (Cobrança → Admin)
# ============================================================
MIGRATIONS.append("""
-- Coluna pra marcar se um pagamento já foi confirmado pelo admin.
-- 0 = aguardando confirmação do admin (registrado pela cobrança)
-- 1 = confirmado pelo admin (pagamento "fechado")
-- Quando vira 1, o status da parcela vai pra QUITADA ou PARCIAL.
-- Quando ainda é 0, o status da parcela é AGUARDANDO_CONFIRMACAO.
""")


# ============================================================
# Migration 5: Portal do Cliente (decisão Erick 13/05/2026)
# Permite cadastrar títulos sem acordo, gerar tokens únicos
# e receber propostas de acordo do próprio cliente.
# ============================================================
MIGRATIONS.append("""
-- Tabela: títulos cadastrados SEM acordo (ficam disponíveis pro cliente
-- ver no portal e propor acordo, OU pra equipe usar no wizard depois)
CREATE TABLE IF NOT EXISTS titulo_avulso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    codigo_parceiro TEXT NOT NULL,
    razao_social_parceiro TEXT NOT NULL,
    empresa INTEGER NOT NULL,
    codigo_vendedor TEXT NOT NULL,
    nome_vendedor TEXT NOT NULL,
    vencimento TEXT NOT NULL,
    numero_nota TEXT NOT NULL,
    numero_unico TEXT NOT NULL UNIQUE,
    principal REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'EM_ABERTO',
    cadastrado_por_id INTEGER NOT NULL,
    cadastrado_em TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cliente_id) REFERENCES cliente(id),
    FOREIGN KEY (cadastrado_por_id) REFERENCES usuario(id)
);

CREATE INDEX IF NOT EXISTS idx_titulo_avulso_cliente ON titulo_avulso(cliente_id);
CREATE INDEX IF NOT EXISTS idx_titulo_avulso_status ON titulo_avulso(status);

-- Tabela: token único pra cliente acessar o portal
CREATE TABLE IF NOT EXISTS portal_token (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL UNIQUE,
    cliente_id INTEGER NOT NULL,
    criado_por_id INTEGER NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    expira_em TEXT NOT NULL,
    usado_em TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (cliente_id) REFERENCES cliente(id),
    FOREIGN KEY (criado_por_id) REFERENCES usuario(id)
);

CREATE INDEX IF NOT EXISTS idx_portal_token_token ON portal_token(token);
CREATE INDEX IF NOT EXISTS idx_portal_token_cliente ON portal_token(cliente_id);

-- Tabela: proposta de acordo enviada pelo cliente via portal
CREATE TABLE IF NOT EXISTS proposta_cliente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id INTEGER NOT NULL,
    cliente_id INTEGER NOT NULL,
    titulos_ids TEXT NOT NULL,
    periodicidade TEXT NOT NULL,
    qtd_parcelas INTEGER NOT NULL,
    data_primeira_parcela TEXT NOT NULL,
    valor_parcela REAL NOT NULL,
    valor_total REAL NOT NULL,
    observacao_cliente TEXT,
    status TEXT NOT NULL DEFAULT 'PENDENTE',
    enviado_em TEXT NOT NULL DEFAULT (datetime('now')),
    analisado_por_id INTEGER,
    analisado_em TEXT,
    decisao_observacao TEXT,
    acordo_gerado_id INTEGER,
    FOREIGN KEY (token_id) REFERENCES portal_token(id),
    FOREIGN KEY (cliente_id) REFERENCES cliente(id),
    FOREIGN KEY (analisado_por_id) REFERENCES usuario(id),
    FOREIGN KEY (acordo_gerado_id) REFERENCES acordo(id)
);

CREATE INDEX IF NOT EXISTS idx_proposta_cliente_status ON proposta_cliente(status);
CREATE INDEX IF NOT EXISTS idx_proposta_cliente_cliente ON proposta_cliente(cliente_id);
""")


# ============================================================
# Migration 6: Anexos do Cliente (decisão Erick 13/05/2026)
# Armazenar PDFs de comprovantes bancários em Base64 no banco.
# ============================================================
MIGRATIONS.append("""
CREATE TABLE IF NOT EXISTS anexo_cliente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    nome_arquivo TEXT NOT NULL,
    descricao TEXT,
    mime_type TEXT NOT NULL DEFAULT 'application/pdf',
    tamanho_bytes INTEGER NOT NULL,
    conteudo_base64 TEXT NOT NULL,
    upload_por_id INTEGER NOT NULL,
    upload_em TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cliente_id) REFERENCES cliente(id),
    FOREIGN KEY (upload_por_id) REFERENCES usuario(id)
);

CREATE INDEX IF NOT EXISTS idx_anexo_cliente ON anexo_cliente(cliente_id);
""")


# ============================================================
# Migration 7: numero_unico só é único POR CLIENTE (não globalmente)
# Decisão Erick 13/05/2026: o mesmo número pode existir em clientes
# diferentes, mas não duplicado no mesmo cliente.
# ============================================================
MIGRATIONS.append("""
-- Em Postgres e SQLite a estratégia de remover UNIQUE difere.
-- Esta migration tem post-processing no aplicar_migrations() pra cuidar disso.
SELECT 1;
""")


# ============================================================

def aplicar_migrations(conn: sqlite3.Connection) -> int:
    """
    Aplica todas as migrations pendentes. Retorna a versão final.
    Idempotente — pode rodar várias vezes sem problema.
    """
    # Garante tabela de versão
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_versao (
            versao INTEGER PRIMARY KEY,
            aplicada_em TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)

    cur = conn.execute("SELECT COALESCE(MAX(versao), 0) FROM schema_versao;")
    versao_atual = cur.fetchone()[0]

    for i, sql in enumerate(MIGRATIONS, start=1):
        if i > versao_atual:
            conn.executescript(sql)
            # Migration 2: adiciona colunas em bancos pré-existentes
            if i == 2:
                _adicionar_coluna_se_nao_existe(
                    conn, "cliente", "tem_whatsapp",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                _adicionar_coluna_se_nao_existe(
                    conn, "usuario", "chave_aprovacao", "TEXT",
                )
                _adicionar_coluna_se_nao_existe(
                    conn, "usuario", "aprovado",
                    "INTEGER NOT NULL DEFAULT 0",
                )
            # Migration 4: confirmação dupla de pagamento
            if i == 4:
                _adicionar_coluna_se_nao_existe(
                    conn, "pagamento_parcela", "confirmado_pelo_admin",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                _adicionar_coluna_se_nao_existe(
                    conn, "pagamento_parcela", "confirmado_por_id",
                    "INTEGER",
                )
                _adicionar_coluna_se_nao_existe(
                    conn, "pagamento_parcela", "confirmado_em",
                    "TEXT",
                )
                # Pagamentos antigos (pré-migration) eram já confirmados
                # automaticamente. Vamos marcar todos como confirmados:
                conn.execute(
                    "UPDATE pagamento_parcela SET confirmado_pelo_admin = 1 "
                    "WHERE confirmado_pelo_admin = 0 OR confirmado_pelo_admin IS NULL;"
                )
                # Alterar o CHECK constraint da tabela parcela pra incluir
                # o novo estado AGUARDANDO_CONFIRMACAO.
                # Em Postgres: DROP CONSTRAINT + ADD CONSTRAINT
                # Em SQLite: o CHECK é validado mas alteração é mais complexa,
                # então ignoramos erros (SQLite criado depois desta versão
                # já vai ter o constraint correto).
                from src.banco.conexao import usar_supabase
                if usar_supabase():
                    try:
                        conn.execute(
                            "ALTER TABLE parcela DROP CONSTRAINT IF EXISTS parcela_status_check;"
                        )
                        conn.execute(
                            "ALTER TABLE parcela ADD CONSTRAINT parcela_status_check "
                            "CHECK (status IN ('EM_ABERTO', 'AGUARDANDO_CONFIRMACAO', 'PARCIAL', 'QUITADA'));"
                        )
                    except Exception:
                        pass
            # Migration 7: trocar UNIQUE global de numero_unico por UNIQUE composto
            # (cliente_id, numero_unico). Permite mesmo número em clientes diferentes.
            if i == 7:
                from src.banco.conexao import usar_supabase
                if usar_supabase():
                    # Postgres
                    try:
                        # Remove o constraint antigo (nome padrão: <tabela>_<coluna>_key)
                        conn.execute(
                            "ALTER TABLE titulo_avulso "
                            "DROP CONSTRAINT IF EXISTS titulo_avulso_numero_unico_key;"
                        )
                    except Exception:
                        pass
                    try:
                        # Cria UNIQUE composto (idempotente via IF NOT EXISTS no índice)
                        conn.execute(
                            "CREATE UNIQUE INDEX IF NOT EXISTS "
                            "idx_titulo_avulso_cliente_unico "
                            "ON titulo_avulso(cliente_id, numero_unico);"
                        )
                    except Exception:
                        pass
                else:
                    # SQLite: recria tabela sem UNIQUE global em numero_unico
                    try:
                        conn.executescript("""
                            CREATE TABLE titulo_avulso_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                cliente_id INTEGER NOT NULL,
                                codigo_parceiro TEXT NOT NULL,
                                razao_social_parceiro TEXT NOT NULL,
                                empresa INTEGER NOT NULL,
                                codigo_vendedor TEXT NOT NULL,
                                nome_vendedor TEXT NOT NULL,
                                vencimento TEXT NOT NULL,
                                numero_nota TEXT NOT NULL,
                                numero_unico TEXT NOT NULL,
                                principal REAL NOT NULL,
                                status TEXT NOT NULL DEFAULT 'EM_ABERTO',
                                cadastrado_por_id INTEGER NOT NULL,
                                cadastrado_em TEXT NOT NULL DEFAULT (datetime('now')),
                                FOREIGN KEY (cliente_id) REFERENCES cliente(id),
                                FOREIGN KEY (cadastrado_por_id) REFERENCES usuario(id),
                                UNIQUE (cliente_id, numero_unico)
                            );
                            INSERT INTO titulo_avulso_new
                                SELECT * FROM titulo_avulso;
                            DROP TABLE titulo_avulso;
                            ALTER TABLE titulo_avulso_new RENAME TO titulo_avulso;
                            CREATE INDEX IF NOT EXISTS idx_titulo_avulso_cliente ON titulo_avulso(cliente_id);
                            CREATE INDEX IF NOT EXISTS idx_titulo_avulso_status ON titulo_avulso(status);
                        """)
                    except Exception:
                        pass
            # Insere versão de forma idempotente. Se já existe no banco
            # (raça com outra instância ou migration parcial), ignora.
            from src.banco.conexao import usar_supabase
            if usar_supabase():
                # Postgres: usa ON CONFLICT DO NOTHING (mais limpo)
                conn.execute(
                    "INSERT INTO schema_versao(versao) VALUES (%s) ON CONFLICT DO NOTHING;",
                    (i,)
                )
            else:
                # SQLite: INSERT OR IGNORE
                conn.execute(
                    "INSERT OR IGNORE INTO schema_versao(versao) VALUES (?);",
                    (i,)
                )

    return len(MIGRATIONS)


def _adicionar_coluna_se_nao_existe(
    conn,
    tabela: str,
    coluna: str,
    tipo_sql: str,
) -> None:
    """
    ALTER TABLE ADD COLUMN ignorando erro se a coluna já existir.
    Funciona em SQLite (PRAGMA) e Postgres (information_schema).
    """
    from src.banco.conexao import usar_supabase

    try:
        if usar_supabase():
            # Postgres: usa information_schema
            cur = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ?;",
                (tabela,),
            )
            colunas_existentes = {row[0] for row in cur.fetchall()}
        else:
            # SQLite: usa PRAGMA
            cur = conn.execute(f"PRAGMA table_info({tabela});")
            colunas_existentes = {row[1] for row in cur.fetchall()}
    except Exception:
        colunas_existentes = set()

    if coluna not in colunas_existentes:
        try:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo_sql};")
        except Exception:
            pass


def inicializar_banco() -> None:
    """Chamado no startup do app. Aplica migrations e cria parâmetros default."""
    from src.banco.conexao import obter_conexao
    conn = obter_conexao()
    aplicar_migrations(conn)
    _criar_parametros_default(conn)


def _criar_parametros_default(conn: sqlite3.Connection) -> None:
    """Insere parâmetros padrão se ainda não existirem."""
    defaults = {
        "lembrete.gatilhos": '["D-5", "D-2", "D0", "D+1"]',
        "lembrete.canais": '["EMAIL"]',
        "lembrete.horario_envio": "09:00",
        "lembrete.template_assunto": "Lembrete: parcela {{numero_parcela}} - {{cliente}}",
        "lembrete.template_corpo": (
            "Olá,\n\n"
            "Esta é uma comunicação automática referente ao acordo "
            "{{numero_acordo}} com {{cliente}}.\n\n"
            "Parcela: {{numero_parcela}}\n"
            "Valor: {{valor}}\n"
            "Vencimento: {{data_vencimento}}\n"
            "Forma de pagamento: {{tipo_cobranca}}\n\n"
            "{{instrucoes_pagamento}}\n\n"
            "Em caso de dúvidas, fale com {{negociador}}.\n\n"
            "Atenciosamente,\n"
            "Equipe LLE Ferragens"
        ),
        "limites.quinzenal_max_sem_aprovacao": "20",
        "limites.semanal_max_sem_aprovacao": "40",
        "limites.mensal_exige_aprovacao": "1",
        "limites.valor_minimo_parcela": "0",
        "calculo.pct_juros_titulos_default": "8.00",
        "calculo.pct_multa_titulos_default": "2.00",
        "calculo.pct_juros_mora_default": "5.00",
        "calculo.pct_multa_mora_default": "2.00",
        # Portal do cliente (decisão Erick 13/05/2026)
        "portal.parcela_minima_semanal": "250.00",
        "portal.max_parcelas_semanal": "40",
        "portal.prazo_primeira_parcela_semanal_dias": "15",
        "portal.parcela_minima_quinzenal": "500.00",
        "portal.max_parcelas_quinzenal": "20",
        "portal.prazo_primeira_parcela_quinzenal_dias": "30",
        "portal.parcela_minima_mensal": "2000.00",
        "portal.max_parcelas_mensal": "12",
        "portal.prazo_primeira_parcela_mensal_dias": "20",
        "portal.dias_validade_token": "30",
    }
    for chave, valor in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO parametros_sistema (chave, valor) VALUES (?, ?);",
            (chave, valor),
        )
