import json
from datetime import datetime

from flask import has_request_context, session

from app_core import auth as auth_core
from app_core import setores
from app_core import db as db_core
from app_core import logging_rastreamento
from app_core.logging_seguranca import limitar_detalhes


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
    detalhes = limitar_detalhes(detalhes or {})
    if not isinstance(detalhes, dict):
        detalhes = {"dados": detalhes}
    if has_request_context():
        contexto = logging_rastreamento.contexto()
        detalhes["_rastro"] = {k: contexto[k] for k in ("correlacao", "rota", "endpoint", "metodo") if contexto.get(k)}
    agora = datetime.now().isoformat()
    usuario_id = session.get("uid")
    usuario_nome = session.get("nome", "")
    ip = auth_core.client_ip()

    fechar = conn is None
    conn = conn or get_db()
    try:
        garantir_tabela_auditoria(get_db, conn)
        sector=setores.atual()
        extra_column=', setor' if sector else ''
        extra_value=',?' if sector else ''
        params=(acao,entidade,str(entidade_id) if entidade_id is not None else None,
            usuario_id,usuario_nome,ip,json.dumps(detalhes,ensure_ascii=False,sort_keys=True),agora)
        if sector:params+= (sector,)
        conn.execute(
            f"""
            INSERT INTO auditoria_eventos
                (acao, entidade, entidade_id, usuario_id, usuario_nome, ip, detalhes_json, criado_em{extra_column})
            VALUES (?,?,?,?,?,?,?,?{extra_value})
            """,params,
        )
        logging_rastreamento.referencia_auditoria(acao, entidade, entidade_id, detalhes)
        if fechar:
            conn.commit()
    except Exception:
        if fechar:
            conn.rollback()
        raise
    finally:
        if fechar:
            conn.close()


def listar_eventos(get_db, filtros=None, limite=100, *, todos_setores=False):
    filtros = filtros or {}
    limite = max(1, min(int(limite or 100), 500))
    where, params = _where_eventos(filtros, todos_setores)
    conn = get_db()
    try:
        if getattr(conn, "backend", "sqlite") == "sqlite" and not db_core.table_exists(conn, "auditoria_eventos"):
            return []
        rows = conn.execute(
            f"SELECT * FROM auditoria_eventos WHERE {' AND '.join(where)} ORDER BY criado_em DESC, id_evento DESC LIMIT ?",
            params + [limite],
        ).fetchall()
    finally:
        conn.close()
    return _eventos(rows)


def _where_eventos(filtros, todos_setores=False):
    where = ["1=1"]
    params = []
    if setores.atual() and not todos_setores:
        where.append('setor=?');params.append(setores.atual())
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
    if filtros.get("correlacao"):
        where.append("detalhes_json LIKE ?")
        params.append('%"correlacao": "' + filtros["correlacao"] + '"%')
    if filtros.get("entidade_id"):
        where.append("entidade_id=?")
        params.append(filtros["entidade_id"])
    return where, params


def consultar_eventos(get_db, filtros=None, pagina=1, por_pagina=50, limite=None):
    """Somente SELECT; exportação detecta excedentes em vez de truncar."""
    where, params = _where_eventos(filtros or {})
    conn = get_db()
    try:
        if getattr(conn, "backend", "sqlite") == "sqlite" and not db_core.table_exists(conn, "auditoria_eventos"):
            return {"registros": [], "total": 0}
        total = conn.execute(f"SELECT COUNT(*) FROM auditoria_eventos WHERE {' AND '.join(where)}", params).fetchone()[0]
        if limite and total > limite:
            return {"registros": [], "total": total}
        offset = 0 if limite else (pagina-1)*por_pagina
        quantidade = limite+1 if limite else por_pagina
        rows = conn.execute(
            f"""
            SELECT *
              FROM auditoria_eventos
             WHERE {' AND '.join(where)}
             ORDER BY criado_em DESC, id_evento DESC
             LIMIT ? OFFSET ?
            """,
            params + [quantidade, offset],
        ).fetchall()
    finally:
        conn.close()

    if limite and len(rows) != total:
        # Um filtro alterado por gravação concorrente deve ser consultado novamente.
        return {"registros": [], "total": max(total, len(rows)), "incompleto": True}
    return {"registros": _eventos(rows), "total": total}


def _eventos(rows):
    eventos = []
    for row in rows:
        item = dict(row)
        try:
            item["detalhes"] = limitar_detalhes(json.loads(item.get("detalhes_json") or "{}"))
            if not isinstance(item["detalhes"], dict):
                item["detalhes"] = {"dados": item["detalhes"]}
        except (TypeError, json.JSONDecodeError):
            item["detalhes"] = {}
        item["rastro"] = item["detalhes"].get("_rastro", {})
        eventos.append(item)
    return eventos
