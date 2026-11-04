"""Presenca aproximada por sessao; dados exibidos apenas a administradores."""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from flask import current_app, request, session
from flask.sessions import SecureCookieSessionInterface

from app_core import db


ONLINE_SEGUNDOS = 120
GRAVACAO_INTERVALO = 20
SESSOES_RETENCAO = 24 * 3600


class SessionInterface(SecureCookieSessionInterface):
    def should_set_cookie(self, app, sess):
        if request.endpoint in {"auth.presenca", "admin.presencas"}:
            # Polling nao renova o prazo de cookies permanentes a cada 30s.
            return sess.modified
        return super().should_set_cookie(app, sess)


def nova_sessao():
    session["presenca_id"] = secrets.token_urlsafe(32)


def sessao_hash():
    nonce = session.get("presenca_id")
    if not nonce:
        # Sessoes anteriores a esta versao ja possuem CSRF aleatorio. Derivar
        # dele evita dois IDs diferentes nas primeiras chamadas de duas abas.
        csrf = session.get("csrf_token")
        if csrf:
            nonce = "legado:" + str(csrf) + ":" + str(session.get("uid"))
        else:
            nova_sessao()
            nonce = session["presenca_id"]
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode("utf-8")
    return hmac.new(key, ("presenca:" + nonce).encode("utf-8"), hashlib.sha256).hexdigest()


def ensure_schema(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.execute("""CREATE TABLE IF NOT EXISTS usuarios_presenca (
        usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id_usuario),
        ultima_presenca BIGINT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS usuarios_presenca_sessoes (
        sessao_hash TEXT PRIMARY KEY,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id_usuario),
        senha_vinculo TEXT NOT NULL,
        ultima_presenca BIGINT NOT NULL,
        encerrada_em BIGINT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_presenca_sessoes_ultima ON usuarios_presenca_sessoes(ultima_presenca)")
    conn.commit()


def _senha_vinculo(senha_hash):
    return hashlib.sha256(senha_hash.encode("utf-8")).hexdigest()


def _ultima(conn, uid, now):
    conn.execute("""INSERT INTO usuarios_presenca (usuario_id,ultima_presenca) VALUES (?,?)
        ON CONFLICT(usuario_id) DO UPDATE SET ultima_presenca=CASE
        WHEN usuarios_presenca.ultima_presenca<excluded.ultima_presenca
        THEN excluded.ultima_presenca ELSE usuarios_presenca.ultima_presenca END""", (uid, now))


def confirmar(target, usuario, identidade, *, agora=None):
    now = int(time.time() if agora is None else agora)
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        result = conn.execute("""INSERT INTO usuarios_presenca_sessoes
            (sessao_hash,usuario_id,senha_vinculo,ultima_presenca,encerrada_em)
            VALUES (?,?,?,?,NULL)
            ON CONFLICT(sessao_hash) DO UPDATE SET ultima_presenca=excluded.ultima_presenca
            WHERE usuarios_presenca_sessoes.encerrada_em IS NULL
              AND usuarios_presenca_sessoes.usuario_id=excluded.usuario_id
              AND usuarios_presenca_sessoes.senha_vinculo=excluded.senha_vinculo
              AND usuarios_presenca_sessoes.ultima_presenca<=?""",
            (identidade, usuario["id_usuario"], _senha_vinculo(usuario["senha_hash"]), now, now - GRAVACAO_INTERVALO))
        if result.rowcount:
            _ultima(conn, usuario["id_usuario"], now)
            conn.execute("DELETE FROM usuarios_presenca_sessoes WHERE ultima_presenca<? AND (encerrada_em IS NULL OR encerrada_em<?)",
                         (now - SESSOES_RETENCAO, now - SESSOES_RETENCAO))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def encerrar(target, usuario, identidade, *, agora=None):
    now = int(time.time() if agora is None else agora)
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        # Tombstone tambem quando o logout chega antes do primeiro heartbeat.
        conn.execute("""INSERT INTO usuarios_presenca_sessoes
            (sessao_hash,usuario_id,senha_vinculo,ultima_presenca,encerrada_em)
            VALUES (?,?,?,?,?) ON CONFLICT(sessao_hash) DO UPDATE SET encerrada_em=excluded.encerrada_em
            WHERE usuarios_presenca_sessoes.usuario_id=excluded.usuario_id""",
            (identidade, usuario["id_usuario"], _senha_vinculo(usuario["senha_hash"]), now, now))
        _ultima(conn, usuario["id_usuario"], now)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def resumo(target, *, agora=None):
    now = int(time.time() if agora is None else agora)
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        users = conn.execute("""SELECT u.id_usuario,u.ativo,u.senha_hash,p.ultima_presenca
            FROM usuarios u LEFT JOIN usuarios_presenca p ON p.usuario_id=u.id_usuario
            ORDER BY u.id_usuario""").fetchall()
        sessions = conn.execute("""SELECT usuario_id,senha_vinculo FROM usuarios_presenca_sessoes
            WHERE encerrada_em IS NULL AND ultima_presenca>=?""", (now - ONLINE_SEGUNDOS,)).fetchall()
        active = {(row["usuario_id"], row["senha_vinculo"]) for row in sessions}
        result = []
        for row in users:
            online = bool(row["ativo"] and (row["id_usuario"], _senha_vinculo(row["senha_hash"])) in active)
            seen = row["ultima_presenca"]
            result.append({"id_usuario": row["id_usuario"], "online": online,
                "ultima_presenca": datetime.fromtimestamp(seen, timezone.utc).isoformat() if seen is not None else None})
        return {"usuarios": result, "online_total": sum(item["online"] for item in result),
                "verificado_em": datetime.fromtimestamp(now, timezone.utc).isoformat()}
    finally:
        conn.close()
