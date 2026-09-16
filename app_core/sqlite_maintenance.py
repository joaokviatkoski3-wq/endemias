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


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _index_columns(conn, index_name):
    return tuple(row[2] for row in conn.execute(f'PRAGMA index_info("{index_name}")'))


def _foreign_key_tables(conn, table):
    return {row[2] for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')}


def _migrate_focos_historico_without_foreign_key(conn):
    table = "focos_historico"
    if not _table_exists(conn, table):
        return False
    if "focos_positivos" not in _foreign_key_tables(conn, table):
        return False

    columns = _table_columns(conn, table)
    expected = {
        "id",
        "id_foco",
        "campo",
        "valor_ant",
        "valor_novo",
        "usuario",
        "alterado_em",
    }
    if not expected.issubset(columns):
        raise RuntimeError(
            "Nao foi possivel corrigir focos_historico: estrutura inesperada."
        )

    legacy_table = "_focos_historico_com_fk"
    if _table_exists(conn, legacy_table):
        raise RuntimeError(
            "Nao foi possivel corrigir focos_historico: tabela temporaria existente."
        )

    total_antes = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    conn.execute(f'ALTER TABLE "{table}" RENAME TO "{legacy_table}"')
    conn.execute(
        """
        CREATE TABLE focos_historico (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            id_foco     TEXT    NOT NULL,
            campo       TEXT    NOT NULL,
            valor_ant   TEXT,
            valor_novo  TEXT,
            usuario     TEXT,
            alterado_em TEXT    NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO focos_historico
            (id, id_foco, campo, valor_ant, valor_novo, usuario, alterado_em)
        SELECT id, id_foco, campo, valor_ant, valor_novo, usuario, alterado_em
          FROM _focos_historico_com_fk
        """
    )
    conn.execute(f'DROP TABLE "{legacy_table}"')
    conn.execute("CREATE INDEX idx_hist_foco ON focos_historico(id_foco)")
    conn.execute("CREATE INDEX idx_hist_em ON focos_historico(alterado_em)")

    total_depois = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    if total_depois != total_antes:
        raise RuntimeError(
            "A correcao de focos_historico nao preservou todos os registros."
        )
    if _foreign_key_tables(conn, table):
        raise RuntimeError(
            "A correcao de focos_historico manteve uma chave estrangeira inesperada."
        )
    return True


def _ensure_visitas_acs_columns(conn):
    if not _table_exists(conn, "visitas"):
        return False

    columns = _table_columns(conn, "visitas")
    changed = False
    if "acs_presente" not in columns:
        conn.execute(
            "ALTER TABLE visitas ADD COLUMN acs_presente INTEGER "
            "CHECK(acs_presente IN (0,1))"
        )
        changed = True
    if "acs_nome" not in columns:
        conn.execute("ALTER TABLE visitas ADD COLUMN acs_nome TEXT")
        changed = True
    return changed


def _ensure_visita_acs_table(conn):
    if not _table_exists(conn, "visitas"):
        return False
    if _table_exists(conn, "visita_acs"):
        return False
    conn.execute(
        """
        CREATE TABLE visita_acs (
            id_visita TEXT NOT NULL REFERENCES visitas(id_visita) ON DELETE CASCADE,
            acs_codigo TEXT NOT NULL,
            PRIMARY KEY (id_visita, acs_codigo)
        )
        """
    )
    conn.execute("CREATE INDEX idx_visita_acs_codigo ON visita_acs(acs_codigo)")
    return True


def _ensure_usuarios_agente_column(conn):
    if not _table_exists(conn, "usuarios"):
        return False
    columns = _table_columns(conn, "usuarios")
    changed = False
    if "id_agente" not in columns:
        conn.execute(
            "ALTER TABLE usuarios ADD COLUMN id_agente INTEGER "
            "REFERENCES agentes(id_agente)"
        )
        changed = True
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_usuarios_agente "
        "ON usuarios(id_agente)"
    )
    return changed


def ensure_schema_compatibility(db_path):
    conn = db_core.connect(db_path)
    migrations = []
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        if _migrate_focos_historico_without_foreign_key(conn):
            migrations.append("focos_historico_sem_fk")
        if _ensure_visitas_acs_columns(conn):
            migrations.append("visitas_acs")
        if _ensure_visita_acs_table(conn):
            migrations.append("visita_acs")
        if _ensure_usuarios_agente_column(conn):
            migrations.append("usuarios_agente")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()
    return migrations


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
