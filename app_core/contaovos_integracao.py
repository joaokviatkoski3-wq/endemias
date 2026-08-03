"""Schema de controle da integracao Conta Ovos."""

from app_core import db as db_core


CURSOR_TABLE = "contaovos_sync_cursor"
EXECUTIONS_TABLE = "contaovos_execucoes"


def ensure_schema(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {CURSOR_TABLE} (
            fluxo TEXT PRIMARY KEY,
            ultimo_id_remoto TEXT,
            atualizado_em TEXT NOT NULL,
            em_execucao_desde TEXT,
            execucao_token TEXT
        );
        CREATE TABLE IF NOT EXISTS {EXECUTIONS_TABLE} (
            id_execucao INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            iniciado_em TEXT NOT NULL,
            finalizado_em TEXT,
            status TEXT NOT NULL
                CHECK(status IN ('executando','concluido','parcial','erro')),
            itens_ok INTEGER NOT NULL DEFAULT 0 CHECK(itens_ok >= 0),
            itens_erro INTEGER NOT NULL DEFAULT 0 CHECK(itens_erro >= 0),
            resumo_sanitizado TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_contaovos_execucoes_inicio
            ON {EXECUTIONS_TABLE}(iniciado_em DESC, id_execucao DESC);
        """
    )
    existing_columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({CURSOR_TABLE})")
    }
    for column in ("em_execucao_desde", "execucao_token"):
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE {CURSOR_TABLE} ADD COLUMN {column} TEXT")


def schema_status(conn):
    return {
        "cursor": db_core.table_exists(conn, CURSOR_TABLE),
        "execucoes": db_core.table_exists(conn, EXECUTIONS_TABLE),
    }
