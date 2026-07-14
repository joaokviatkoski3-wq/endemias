from datetime import datetime

from app_core import db as db_core


STATUS_TABLE = "laboratorio_coletas_status"


def _columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def ensure_schema(db_path):
    conn = db_core.connect(db_path)
    try:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        usuarios = _columns(conn, "usuarios") if "usuarios" in tables else set()
        if usuarios and "acesso_laboratorio" not in usuarios:
            conn.execute(
                "ALTER TABLE usuarios ADD COLUMN acesso_laboratorio INTEGER NOT NULL DEFAULT 0 "
                "CHECK(acesso_laboratorio IN (0,1))"
            )

        resultados = (
            _columns(conn, "resultados_laboratorio")
            if "resultados_laboratorio" in tables else set()
        )
        additions = {
            "id_laboratorista": "INTEGER REFERENCES agentes(id_agente)",
            "origem": "TEXT NOT NULL DEFAULT 'kobo' CHECK(origem IN ('kobo','sistema'))",
            "criado_em": "TEXT",
            "atualizado_em": "TEXT",
        }
        for column, definition in additions.items():
            if column not in resultados:
                if not resultados:
                    break
                conn.execute(
                    f'ALTER TABLE resultados_laboratorio ADD COLUMN "{column}" {definition}'
                )

        if {"usuarios", "coletas"}.issubset(tables):
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {STATUS_TABLE} (
                id_coleta       TEXT PRIMARY KEY REFERENCES coletas(id_coleta),
                status          TEXT NOT NULL CHECK(status IN ('sem_resultado')),
                motivo          TEXT NOT NULL,
                encerrado_em    TEXT NOT NULL,
                encerrado_por   INTEGER REFERENCES usuarios(id_usuario)
                )
            """)
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_lab_status_status ON {STATUS_TABLE}(status)"
            )
        if resultados:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_resultado_lab_coleta_unico "
                "ON resultados_laboratorio(id_coleta)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_resultado_lab_leitura "
                "ON resultados_laboratorio(data_leitura DESC, id_resultado DESC)"
            )
        conn.commit()
    finally:
        conn.close()


def pode_lancar(usuario):
    if not usuario:
        return False
    return usuario.get("nivel") == "admin" or bool(usuario.get("acesso_laboratorio"))


def encerrar_sem_resultado(conn, id_coleta, motivo, usuario_id=None, agora=None):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Informe o motivo do encerramento.")
    existe = conn.execute(
        "SELECT 1 FROM coletas WHERE id_coleta=?", (id_coleta,)
    ).fetchone()
    if not existe:
        raise ValueError("Coleta não encontrada.")
    if conn.execute(
        "SELECT 1 FROM resultados_laboratorio WHERE id_coleta=?", (id_coleta,)
    ).fetchone():
        raise ValueError("A coleta já possui resultado.")
    conn.execute(
        f"""INSERT INTO {STATUS_TABLE}
               (id_coleta, status, motivo, encerrado_em, encerrado_por)
             VALUES (?, 'sem_resultado', ?, ?, ?)
             ON CONFLICT(id_coleta) DO UPDATE SET
               status=excluded.status, motivo=excluded.motivo,
               encerrado_em=excluded.encerrado_em, encerrado_por=excluded.encerrado_por""",
        (id_coleta, motivo, agora or datetime.now().isoformat(), usuario_id),
    )
