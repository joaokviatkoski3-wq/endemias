import json
from datetime import datetime

from flask import request, session

from app_core import auth as auth_core


def garantir_tabela_auditoria(get_db, conn=None):
    fechar = conn is None
    conn = conn or get_db()
    if getattr(conn, "backend", "sqlite") == "postgresql":
        if fechar:
            conn.close()
        return
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
    if fechar:
        conn.commit()
        conn.close()


def registrar_evento(
    get_db,
    acao,
    entidade=None,
    entidade_id=None,
    detalhes=None,
    conn=None,
):
    detalhes = detalhes or {}
    agora = datetime.now().isoformat()
    usuario_id = session.get("uid")
    usuario_nome = session.get("nome", "")
    ip = auth_core.client_ip()

    fechar = conn is None
    conn = conn or get_db()
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
        if fechar:
            conn.commit()
    except Exception:
        if fechar:
            conn.rollback()
        raise
    finally:
        if fechar:
            conn.close()


def registrar_evento_operacional(
    conn,
    acao,
    *,
    operador_nome,
    entidade=None,
    entidade_id=None,
    detalhes=None,
    criado_em=None,
):
    """Registra uma operacao supervisionada executada fora de uma requisicao."""
    operador_nome = str(operador_nome or "").strip()
    if not operador_nome:
        raise ValueError("Informe o nome do operador responsavel.")
    if len(operador_nome) > 120:
        raise ValueError("O nome do operador responsavel e muito longo.")
    garantir_tabela_auditoria(lambda: conn, conn)
    conn.execute(
        """
        INSERT INTO auditoria_eventos
            (acao, entidade, entidade_id, usuario_id, usuario_nome, ip,
             detalhes_json, criado_em)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            acao,
            entidade,
            str(entidade_id) if entidade_id is not None else None,
            None,
            operador_nome,
            "operacao-local-supervisionada",
            json.dumps(detalhes or {}, ensure_ascii=False, sort_keys=True),
            criado_em or datetime.now().isoformat(timespec="seconds"),
        ),
    )


def listar_eventos(get_db, filtros=None, limite=100):
    filtros = filtros or {}
    limite = max(1, min(int(limite or 100), 500))
    where = ["1=1"]
    params = []
    if filtros.get("acao"):
        where.append("acao LIKE ?")
        params.append(f"%{filtros['acao']}%")
    if filtros.get("usuario"):
        where.append("usuario_nome LIKE ?")
        params.append(f"%{filtros['usuario']}%")
    if filtros.get("entidade"):
        where.append("entidade = ?")
        params.append(filtros["entidade"])
    if filtros.get("d_ini"):
        where.append("substr(criado_em, 1, 10) >= ?")
        params.append(filtros["d_ini"])
    if filtros.get("d_fim"):
        where.append("substr(criado_em, 1, 10) <= ?")
        params.append(filtros["d_fim"])

    conn = get_db()
    try:
        garantir_tabela_auditoria(get_db, conn)
        rows = conn.execute(
            f"""
            SELECT *
              FROM auditoria_eventos
             WHERE {' AND '.join(where)}
             ORDER BY criado_em DESC, id_evento DESC
             LIMIT ?
            """,
            params + [limite],
        ).fetchall()
    finally:
        conn.close()

    eventos = []
    for row in rows:
        item = dict(row)
        try:
            item["detalhes"] = json.loads(item.get("detalhes_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["detalhes"] = {}
        eventos.append(item)
    return eventos
