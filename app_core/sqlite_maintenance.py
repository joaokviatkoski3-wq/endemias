from app_core import db as db_core


PERFORMANCE_INDEXES = {
    "idx_rg_imoveis_quarteirao_ordem": (
        "registro_geografico_imoveis",
        ("id_quarteirao", "ordem", "id_imovel"),
    ),
    "idx_visitas_localidade_data_tipo": (
        "visitas",
        ("id_localidade", "data", "tipo"),
    ),
}


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _index_columns(conn, index_name):
    return tuple(row[2] for row in conn.execute(f'PRAGMA index_info("{index_name}")'))


def ensure_performance_indexes(db_path):
    conn = db_core.connect(db_path)
    try:
        for index_name, (table, columns) in PERFORMANCE_INDEXES.items():
            if not set(columns).issubset(_table_columns(conn, table)):
                continue
            column_sql = ", ".join(columns)
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                f'ON "{table}" ({column_sql})'
            )

        visitas_columns = _table_columns(conn, "visitas")
        if "quarteirao" in visitas_columns:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_visitas_quarteirao ON visitas(quarteirao)"
            )
            if _index_columns(conn, "visitas_quarteirao_idx") == ("quarteirao",):
                conn.execute("DROP INDEX visitas_quarteirao_idx")

        conn.commit()
        conn.execute("PRAGMA optimize")
    finally:
        conn.close()


def performance_index_status(conn):
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
    }
    missing = [name for name in PERFORMANCE_INDEXES if name not in existing]
    return {
        "total": len(PERFORMANCE_INDEXES),
        "presentes": len(PERFORMANCE_INDEXES) - len(missing),
        "faltantes": missing,
        "ok": not missing,
    }
