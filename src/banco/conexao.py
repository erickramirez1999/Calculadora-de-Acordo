"""
Camada de banco de dados com adapter SQLite ↔ Postgres (Supabase).

ESTRATÉGIA:
  - Se NÃO houver [supabase] nos Secrets → usa SQLite local (.streamlit/data/lle.db)
  - Se HOUVER [supabase] nos Secrets → conecta no Postgres do Supabase

O adapter traduz as queries SQLite pra Postgres em tempo de execução, então o
RESTO DO CÓDIGO continua igual (telas, repositórios, serviços).

Tradução feita pelo adapter:
  - Placeholders: `?` → `%s`
  - `datetime('now')` → `NOW()`
  - `AUTOINCREMENT` → `GENERATED ALWAYS AS IDENTITY`
  - `INTEGER PRIMARY KEY` → `SERIAL PRIMARY KEY`
  - `lastrowid` → busca via `RETURNING id` adicionado automaticamente
  - PRAGMAs SQLite → ignorados (não existem em Postgres)
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

# ============================================================
# CAMINHOS
# ============================================================
PASTA_DADOS = Path(".streamlit/data")
ARQUIVO_BANCO = PASTA_DADOS / "lle.db"

# Lock para escritas concorrentes (Streamlit pode ter múltiplas threads)
_LOCK_ESCRITA = threading.RLock()

# Cache da conexão por thread
_CONEXOES_THREAD: dict[int, Any] = {}

# Cache da string de conexão Supabase (carregada uma vez)
_CONEXAO_STRING_SUPABASE: Optional[str] = None


def garantir_pasta_dados() -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)


# ============================================================
# DETECÇÃO DO MODO DE BANCO
# ============================================================

def usar_supabase() -> bool:
    """
    Decide se vai usar Supabase ou SQLite.

    Ativa Supabase se:
      - Existe [supabase] nos Secrets do Streamlit, OU
      - Existe variável de ambiente SUPABASE_CONNECTION_STRING

    Senão, cai no SQLite local.
    """
    global _CONEXAO_STRING_SUPABASE

    if _CONEXAO_STRING_SUPABASE is not None:
        return True

    # Tentar Streamlit Secrets primeiro
    try:
        import streamlit as st
        if "supabase" in st.secrets:
            cs = st.secrets["supabase"].get("connection_string")
            if cs:
                _CONEXAO_STRING_SUPABASE = cs
                return True
    except Exception:
        pass

    # Fallback: variável de ambiente (útil pra testes locais)
    env = os.environ.get("SUPABASE_CONNECTION_STRING")
    if env:
        _CONEXAO_STRING_SUPABASE = env
        return True

    return False


# ============================================================
# ADAPTER POSTGRES — Tradução automática SQLite ↔ Postgres
# ============================================================

class _RowDict(dict):
    """
    Dict que também aceita acesso por índice (igual sqlite3.Row).
    Faz o código existente continuar funcionando: row[0], row["nome"], etc.
    """
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = list(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class _CursorPostgres:
    """
    Cursor adaptador. Faz o resto do código achar que tá falando com sqlite3,
    mas por baixo dos panos é Postgres.
    """

    def __init__(self, pg_cursor):
        self._cur = pg_cursor
        self.lastrowid: Optional[int] = None

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._cur.description]
        return _RowDict(cols, row)

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in self._cur.description]
        return [_RowDict(cols, r) for r in rows]

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        self._cur.close()


class _ConexaoPostgres:
    """
    Conexão adaptadora. Implementa a mesma interface que sqlite3.Connection,
    mas executa Postgres por baixo.

    Principais coisas que ela faz:
      1. Traduz queries SQLite pra Postgres (placeholders, funções de data)
      2. Captura o id gerado em INSERTs (lastrowid) via RETURNING
      3. Faz controle de transação manual (BEGIN/COMMIT/ROLLBACK)
      4. Ignora PRAGMAs do SQLite (não existem em Postgres)
    """

    def __init__(self, dsn: str):
        import psycopg
        self._dsn = dsn  # guarda pra poder reconectar se cair
        self._psycopg = psycopg  # cache do módulo
        # autocommit=True pra ter mesmo comportamento do nosso SQLite
        # prepare_threshold=None pra desabilitar prepared statements (necessário
        # pro Transaction Pooler do Supabase, que reutiliza conexões e não
        # permite que prepared statements persistam entre transações)
        self._conn = psycopg.connect(
            dsn,
            autocommit=True,
            prepare_threshold=None,
        )
        self.row_factory = None  # pra compatibilidade com sqlite3

    def _garantir_conexao_viva(self):
        """
        Reconecta automaticamente se a conexão tiver morrido.
        Streamlit Cloud + Neon/Supabase deixam conexão idle e o servidor
        descarta — isso evita o erro 'the connection is closed'.
        """
        try:
            # broken=True significa conexão quebrada; closed=True significa fechada
            if self._conn.closed or self._conn.broken:
                self._conn = self._psycopg.connect(
                    self._dsn,
                    autocommit=True,
                    prepare_threshold=None,
                )
        except Exception:
            # Se nem consegue checar status, força reconexão
            try:
                self._conn = self._psycopg.connect(
                    self._dsn,
                    autocommit=True,
                    prepare_threshold=None,
                )
            except Exception:
                pass

    def execute(self, sql: str, params: tuple = ()) -> _CursorPostgres:
        """
        Executa uma query traduzida. Equivalente a sqlite3.Connection.execute().
        Reconecta sozinha se a conexão tiver caído.
        """
        self._garantir_conexao_viva()
        sql_pg, params_pg = _traduzir_sql(sql, params)

        # Ignora PRAGMAs do SQLite (não existem em Postgres)
        if sql_pg is None:
            cur = self._conn.cursor()
            return _CursorPostgres(cur)

        try:
            cur = self._conn.cursor()
            cur.execute(sql_pg, params_pg)
        except self._psycopg.OperationalError:
            # Conexão caiu no meio — tenta uma vez mais reconectando
            self._conn = self._psycopg.connect(
                self._dsn,
                autocommit=True,
                prepare_threshold=None,
            )
            cur = self._conn.cursor()
            cur.execute(sql_pg, params_pg)

        wrapper = _CursorPostgres(cur)

        # Se foi um INSERT, captura o id criado (lastrowid)
        if "RETURNING" in sql_pg.upper() and cur.description:
            try:
                row = cur.fetchone()
                if row and len(row) > 0:
                    wrapper.lastrowid = row[0]
                # Reseta o cursor pra próxima query não pegar essa linha já lida
                cur._description = None  # type: ignore
            except Exception:
                pass

        return wrapper

    def executemany(self, sql: str, seq_params: list) -> None:
        """
        Executa a mesma query várias vezes com parâmetros diferentes.
        Útil pra inserts em lote.
        """
        self._garantir_conexao_viva()
        sql_pg, _ = _traduzir_sql(sql, ())
        if sql_pg is None:
            return
        try:
            cur = self._conn.cursor()
            cur.executemany(sql_pg, seq_params)
        except self._psycopg.OperationalError:
            self._conn = self._psycopg.connect(
                self._dsn,
                autocommit=True,
                prepare_threshold=None,
            )
            cur = self._conn.cursor()
            cur.executemany(sql_pg, seq_params)

    def executescript(self, sql: str) -> None:
        """
        Executa múltiplos statements de uma vez (usado por migrations).
        Em Postgres, basta passar a string toda.
        """
        self._garantir_conexao_viva()
        sql_pg, _ = _traduzir_sql(sql, ())
        if sql_pg is None:
            return
        try:
            cur = self._conn.cursor()
            cur.execute(sql_pg)
            cur.close()
        except self._psycopg.OperationalError:
            self._conn = self._psycopg.connect(
                self._dsn,
                autocommit=True,
                prepare_threshold=None,
            )
            cur = self._conn.cursor()
            cur.execute(sql_pg)
            cur.close()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


# ============================================================
# TRADUTOR DE QUERIES
# ============================================================

def _traduzir_sql(sql: str, params: tuple) -> tuple[Optional[str], tuple]:
    """
    Recebe (query SQLite, params) e devolve (query Postgres, params).
    Se retornar (None, _) significa que a query deve ser IGNORADA
    (caso dos PRAGMAs).
    """
    sql_clean = sql.strip()
    sql_upper = sql_clean.upper()

    # 1) PRAGMAs do SQLite não existem em Postgres - ignora
    if sql_upper.startswith("PRAGMA "):
        return None, ()

    # 2) Comandos de controle de transação que Postgres aceita
    if sql_upper in ("BEGIN;", "COMMIT;", "ROLLBACK;",
                     "BEGIN", "COMMIT", "ROLLBACK"):
        return sql_clean.rstrip(";"), ()

    sql_pg = sql

    # 3) Traduz tipos SQLite → Postgres em CREATE TABLE
    if "CREATE TABLE" in sql_upper:
        sql_pg = _traduzir_create_table(sql_pg)

    # 4) Traduz funções de data
    #    SQLite: datetime('now')  →  Postgres: NOW()
    #    SQLite: DATE('now')      →  Postgres: CURRENT_DATE
    sql_pg = re.sub(r"datetime\s*\(\s*'now'\s*\)", "NOW()", sql_pg, flags=re.IGNORECASE)
    sql_pg = re.sub(r"DATE\s*\(\s*'now'\s*\)", "CURRENT_DATE", sql_pg, flags=re.IGNORECASE)

    # 4.1) julianday('now') - julianday(coluna) → diferença em dias
    #      SQLite: julianday('A') - julianday('B') dá diferença em dias.
    #      Postgres: (CURRENT_DATE - data::date) já dá inteiro de dias.
    sql_pg = re.sub(
        r"julianday\s*\(\s*'now'\s*\)\s*-\s*julianday\s*\(\s*([^)]+?)\s*\)",
        r"(CURRENT_DATE - (\1)::date)",
        sql_pg, flags=re.IGNORECASE,
    )
    # 4.2) julianday(A) - julianday(B) → (A::date - B::date)
    sql_pg = re.sub(
        r"julianday\s*\(\s*([^)]+?)\s*\)\s*-\s*julianday\s*\(\s*([^)]+?)\s*\)",
        r"((\1)::date - (\2)::date)",
        sql_pg, flags=re.IGNORECASE,
    )

    # 4.3) IFNULL → COALESCE (Postgres aceita IFNULL como alias mas é mais seguro traduzir)
    sql_pg = re.sub(r"\bIFNULL\b", "COALESCE", sql_pg, flags=re.IGNORECASE)

    # 5) Em SELECTs com DATE(coluna): mantém - Postgres tem DATE()
    # nada a fazer aqui

    # 5.5) INSERT OR IGNORE (SQLite) → INSERT ... ON CONFLICT DO NOTHING (Postgres)
    #      INSERT OR REPLACE (SQLite) → INSERT ... ON CONFLICT DO UPDATE (mais complexo,
    #      por enquanto traduzimos como OR IGNORE também — quase nunca usamos REPLACE)
    eh_or_ignore = False
    if re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", sql_pg, flags=re.IGNORECASE):
        sql_pg = re.sub(
            r"INSERT\s+OR\s+IGNORE\s+INTO",
            "INSERT INTO",
            sql_pg, flags=re.IGNORECASE,
        )
        eh_or_ignore = True
    elif re.search(r"INSERT\s+OR\s+REPLACE\s+INTO", sql_pg, flags=re.IGNORECASE):
        sql_pg = re.sub(
            r"INSERT\s+OR\s+REPLACE\s+INTO",
            "INSERT INTO",
            sql_pg, flags=re.IGNORECASE,
        )
        eh_or_ignore = True

    # 6) INSERT precisa devolver o id criado: adiciona RETURNING id
    #    EXCETO em:
    #      - tabelas onde a PK não é "id"
    #      - queries com ON CONFLICT (que podem não retornar linha)
    #      - queries que já têm ON CONFLICT DO NOTHING que adicionamos
    tem_on_conflict = "ON CONFLICT" in sql_pg.upper()

    if sql_upper.lstrip().startswith("INSERT") and "RETURNING" not in sql_upper:
        TABELAS_SEM_ID = {
            "schema_versao", "parametros_sistema", "sequencia_acordo",
        }
        m = re.match(r"\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                     sql_pg, flags=re.IGNORECASE)
        nome_tabela = m.group(1).lower() if m else ""

        if eh_or_ignore and not tem_on_conflict:
            sql_pg = sql_pg.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        elif (nome_tabela not in TABELAS_SEM_ID
              and not eh_or_ignore
              and not tem_on_conflict):
            sql_pg = sql_pg.rstrip().rstrip(";") + " RETURNING id"

    # 7) Placeholders: SQLite usa ?, Postgres usa %s
    sql_pg = sql_pg.replace("?", "%s")

    return sql_pg, params


def _traduzir_create_table(sql: str) -> str:
    """
    Traduz CREATE TABLE do SQLite pra Postgres.

    Diferenças tratadas:
      - INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
      - REAL → DOUBLE PRECISION
      - TEXT DEFAULT NOW() → TIMESTAMPTZ DEFAULT NOW()
      - TEXT DEFAULT CURRENT_DATE → DATE DEFAULT CURRENT_DATE
    """
    # INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    sql = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        sql, flags=re.IGNORECASE,
    )
    # REAL → DOUBLE PRECISION
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql, flags=re.IGNORECASE)

    # Antes desta tradução, datetime('now') já virou NOW() em outra etapa.
    # Aqui ajustamos o tipo: TEXT que tem DEFAULT NOW() vira TIMESTAMPTZ
    # Pattern: "campo TEXT [NOT NULL] DEFAULT (NOW())" ou "campo TEXT ... DEFAULT (datetime('now'))"
    sql = re.sub(
        r"\bTEXT\b(\s+NOT\s+NULL)?\s+DEFAULT\s+\(\s*NOW\(\)\s*\)",
        lambda m: f"TIMESTAMPTZ{m.group(1) or ''} DEFAULT NOW()",
        sql, flags=re.IGNORECASE,
    )
    sql = re.sub(
        r"\bTEXT\b(\s+NOT\s+NULL)?\s+DEFAULT\s+NOW\(\)",
        lambda m: f"TIMESTAMPTZ{m.group(1) or ''} DEFAULT NOW()",
        sql, flags=re.IGNORECASE,
    )
    # TEXT com DEFAULT CURRENT_DATE → DATE
    sql = re.sub(
        r"\bTEXT\b(\s+NOT\s+NULL)?\s+DEFAULT\s+CURRENT_DATE",
        lambda m: f"DATE{m.group(1) or ''} DEFAULT CURRENT_DATE",
        sql, flags=re.IGNORECASE,
    )

    return sql


# ============================================================
# FUNÇÕES PÚBLICAS (interface usada pelo resto do projeto)
# ============================================================

def obter_conexao():
    """
    Devolve uma conexão pra thread atual.
    - SQLite: sqlite3.Connection
    - Supabase: _ConexaoPostgres (adapter)

    Em ambos os casos, o resto do código pode usar conn.execute() normalmente.
    """
    thread_id = threading.get_ident()

    if thread_id in _CONEXOES_THREAD:
        return _CONEXOES_THREAD[thread_id]

    if usar_supabase():
        # Modo SUPABASE: cria conexão Postgres adaptada
        conn = _ConexaoPostgres(_CONEXAO_STRING_SUPABASE)
        _CONEXOES_THREAD[thread_id] = conn
        return conn

    # Modo SQLITE (padrão)
    garantir_pasta_dados()
    conn = sqlite3.connect(
        ARQUIVO_BANCO,
        check_same_thread=False,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    _CONEXOES_THREAD[thread_id] = conn
    return conn


@contextmanager
def transacao() -> Generator:
    """
    Context manager pra transação. Commit no sucesso, rollback em erro.
    Funciona igual em SQLite e Postgres.
    """
    conn = obter_conexao()
    with _LOCK_ESCRITA:
        try:
            conn.execute("BEGIN;")
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            raise


def fechar_conexoes() -> None:
    for conn in _CONEXOES_THREAD.values():
        try:
            conn.close()
        except Exception:
            pass
    _CONEXOES_THREAD.clear()
