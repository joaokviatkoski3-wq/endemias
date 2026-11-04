"""Registro revogavel de sessoes; o cookie guarda somente um identificador aleatorio."""

import hashlib
import secrets
import time

from flask import current_app, session

from app_core import db


def ensure_schema(conn):
    if getattr(conn, 'backend', 'sqlite') == 'postgresql':
        return
    conn.execute('''CREATE TABLE IF NOT EXISTS usuarios_sessoes (
        sessao_hash TEXT PRIMARY KEY,
        usuario_id BIGINT NOT NULL REFERENCES usuarios(id_usuario),
        senha_vinculo TEXT NOT NULL,
        criada_em BIGINT NOT NULL,
        expira_em BIGINT NOT NULL,
        revogada_em BIGINT
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_usuarios_sessoes_expira ON usuarios_sessoes(expira_em)')
    conn.commit()


def digest(value):
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def criar(target, usuario):
    now = int(time.time())
    sid = secrets.token_urlsafe(32)
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        conn.execute('''INSERT INTO usuarios_sessoes
            (sessao_hash,usuario_id,senha_vinculo,criada_em,expira_em)
            VALUES (?,?,?,?,?)''', (digest(sid), usuario['id_usuario'], digest(usuario['senha_hash']),
                now, now + int(current_app.permanent_session_lifetime.total_seconds())))
        # Limpeza nao permite revalidar cookies antigos: sessao ausente e invalida.
        conn.execute('DELETE FROM usuarios_sessoes WHERE expira_em<?', (now,))
        conn.commit()
    finally:
        conn.close()
    return sid


def valida(query_one, usuario):
    sid = session.get('sessao_id')
    if not isinstance(sid, str) or len(sid) != 43:
        return False
    row = query_one('''SELECT usuario_id FROM usuarios_sessoes WHERE sessao_hash=?
        AND usuario_id=? AND senha_vinculo=? AND revogada_em IS NULL AND expira_em>?''',
        (digest(sid), usuario['id_usuario'], digest(usuario['senha_hash']), int(time.time())))
    return bool(row)


def revogar(target):
    sid = session.get('sessao_id')
    if not sid:
        return
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        conn.execute('UPDATE usuarios_sessoes SET revogada_em=? WHERE sessao_hash=? AND usuario_id=?',
                     (int(time.time()), digest(sid), session.get('uid')))
        conn.commit()
    finally:
        conn.close()
