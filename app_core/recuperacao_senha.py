"""Links assistidos de uso unico; nenhum token em texto aberto no banco."""

import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app_core import auth, db, permissoes


VALIDADE_SEGUNDOS = 15 * 60
ERRO_LINK = "Link inválido, expirado ou já utilizado. Solicite outro ao responsável pelo sistema."


def url_publica(token, base="https://endemias.vsatt.com.br"):
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Endereço de recuperação deve ser uma origem HTTPS configurada.")
    # Fragmento nao e enviado ao servidor, proxy, logs HTTP ou Referer.
    return base.rstrip("/") + "/recuperar-senha#" + token


def ensure_schema(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.execute("""CREATE TABLE IF NOT EXISTS usuarios_recuperacao_senha (
        usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id_usuario),
        token_hash TEXT NOT NULL UNIQUE,
        senha_vinculo TEXT NOT NULL,
        criado_por INTEGER NOT NULL REFERENCES usuarios(id_usuario),
        criado_em TEXT NOT NULL,
        expira_em BIGINT NOT NULL,
        usado_em TEXT
    )""")
    conn.commit()


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _lock_user(conn, uid):
    suffix = " FOR UPDATE" if getattr(conn, "backend", "sqlite") == "postgresql" else ""
    if not suffix:
        conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT * FROM usuarios WHERE id_usuario=?" + suffix, (uid,)).fetchone()
    return dict(row) if row else None


def _timestamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def gerar(target, uid, administrador_id, *, agora=None, auditar=None):
    now = int(time.time() if agora is None else agora)
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        usuario = _lock_user(conn, uid)
        admin = conn.execute("SELECT id_usuario,nivel,ativo FROM usuarios WHERE id_usuario=? AND ativo=1 AND nivel IN ('admin','superadmin')",
                             (administrador_id,)).fetchone()
        if not admin:
            raise ValueError("Somente um administrador ativo pode gerar o link.")
        if not usuario or not usuario["ativo"]:
            raise ValueError("Selecione uma conta ativa para gerar o link.")
        if not permissoes.pode_gerenciar_conta(dict(admin), usuario):
            raise ValueError("Esta conta é protegida contra recuperação de senha pelo seu perfil.")
        token = secrets.token_urlsafe(32)
        conn.execute("""INSERT INTO usuarios_recuperacao_senha
            (usuario_id, token_hash, senha_vinculo, criado_por, criado_em, expira_em, usado_em)
            VALUES (?,?,?,?,?,?,NULL)
            ON CONFLICT(usuario_id) DO UPDATE SET token_hash=excluded.token_hash,
            senha_vinculo=excluded.senha_vinculo, criado_por=excluded.criado_por,
            criado_em=excluded.criado_em, expira_em=excluded.expira_em, usado_em=NULL""",
            (uid, _digest(token), _digest(usuario["senha_hash"]), administrador_id,
             _timestamp(now), now + VALIDADE_SEGUNDOS))
        if auditar:
            auditar(conn, usuario)
        conn.commit()
        return token
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def consumir(target, token, nova_senha, *, agora=None, auditar=None):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise ValueError(ERRO_LINK)
    if not auth.senha_valida(nova_senha) or len(nova_senha) > 1024:
        raise ValueError(auth.mensagem_senha_invalida() if len(nova_senha) <= 1024 else "Senha muito longa.")
    now = int(time.time() if agora is None else agora)
    token_hash = _digest(token)
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        reference = conn.execute("SELECT usuario_id FROM usuarios_recuperacao_senha WHERE token_hash=?",
                                 (token_hash,)).fetchone()
        if not reference:
            raise ValueError(ERRO_LINK)
        usuario = _lock_user(conn, reference["usuario_id"])
        link = conn.execute("""SELECT r.*,a.nivel AS nivel_emissor FROM usuarios_recuperacao_senha r
            JOIN usuarios a ON a.id_usuario=r.criado_por AND a.ativo=1 AND a.nivel IN ('admin','superadmin')
            WHERE r.token_hash=? AND r.usado_em IS NULL AND r.expira_em>?""", (token_hash, now)).fetchone()
        if (not usuario or not usuario["ativo"] or not link
                or not permissoes.pode_gerenciar_conta({"nivel": link["nivel_emissor"], "ativo": 1}, usuario)
                or not hmac.compare_digest(link["senha_vinculo"], _digest(usuario["senha_hash"]))):
            raise ValueError(ERRO_LINK)
        result = conn.execute("""UPDATE usuarios_recuperacao_senha SET usado_em=?
            WHERE token_hash=? AND usado_em IS NULL AND expira_em>?""", (_timestamp(now), token_hash, now))
        if result.rowcount != 1:
            raise ValueError(ERRO_LINK)
        conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=?", (auth.hash_senha(nova_senha), usuario["id_usuario"]))
        if auditar:
            auditar(conn, usuario, link["criado_por"])
        conn.commit()
        return usuario["id_usuario"]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
