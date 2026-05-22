import json
from datetime import datetime

from flask import request, session


def garantir_tabela_auditoria(get_db, conn=None):
    fechar = conn is None
    conn = conn or get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auditoria_eventos (
            id_evento     INTEGER PRIMARY KEY AUTOINCREMENT,
            acao          TEXT    NOT NULL,
            entidade      TEXT,
            entidade_id   TEXT,
            usuario_id    INTEGER,
            usuario_nome  TEXT,
            ip            TEXT,
            detalhes_json TEXT    NOT NULL DEFAULT '{}',
            criado_em     TEXT    NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_criado ON auditoria_eventos(criado_em)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_acao ON auditoria_eventos(acao)")
    conn.commit()
    if fechar:
        conn.close()


def registrar_evento(get_db, acao, entidade=None, entidade_id=None, detalhes=None):
    detalhes = detalhes or {}
    agora = datetime.now().isoformat()
    usuario_id = session.get("uid")
    usuario_nome = session.get("nome", "")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    ip = ip.split(",", 1)[0].strip()

    conn = get_db()
    try:
        garantir_tabela_auditoria(get_db, conn)
        conn.execute(
            """
            INSERT INTO auditoria_eventos
                (acao, entidade, entidade_id, usuario_id, usuario_nome, ip, detalhes_json, criado_em)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                acao,
                entidade,
                str(entidade_id) if entidade_id is not None else None,
                usuario_id,
                usuario_nome,
                ip,
                json.dumps(detalhes, ensure_ascii=False, sort_keys=True),
                agora,
            ),
        )
        conn.commit()
    finally:
        conn.close()
