import hashlib
import hmac
import re
import time
from datetime import datetime
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import current_app, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app_core import db as db_core
from app_core import permissoes


LOGIN_MAX_TENTATIVAS = 5
LOGIN_JANELA_SEG = 15 * 60
LOGIN_MAX_POR_IP = 50
PASSWORD_MIN_LENGTH = 10
login_tentativas = {}
_DUMMY_HASH = generate_password_hash("comparacao-sem-conta", method="pbkdf2:sha256", salt_length=16)


def garantir_tabela_login_tentativas(get_db, conn=None):
    fechar = conn is None
    conn = conn or get_db()
    if getattr(conn, "backend", "sqlite") == "postgresql":
        if fechar:
            conn.close()
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_tentativas (
            chave       TEXT PRIMARY KEY,
            tentativas  INTEGER NOT NULL DEFAULT 0,
            primeira_em REAL    NOT NULL,
            atualizado_em TEXT  NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_login_tentativas_primeira ON login_tentativas(primeira_em)")
    conn.commit()
    if fechar:
        conn.close()


def hash_legado(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def hash_senha(senha):
    return generate_password_hash(senha, method="pbkdf2:sha256", salt_length=16)


def senha_valida(senha):
    return bool(senha) and len(senha) >= PASSWORD_MIN_LENGTH


def mensagem_senha_invalida():
    return f"A senha deve ter ao menos {PASSWORD_MIN_LENGTH} caracteres."


def verificar_senha(senha_digitada, hash_armazenado):
    if hash_armazenado and hash_armazenado.startswith("pbkdf2:"):
        return check_password_hash(hash_armazenado, senha_digitada), None
    if hash_armazenado == hash_legado(senha_digitada):
        return True, hash_senha(senha_digitada)
    return False, None


def usuario_atual(query_one):
    uid = session.get("uid")
    if not uid:
        return None
    if getattr(g, "_auth_uid", None) == uid:
        return g._auth_usuario
    usuario = query_one("SELECT * FROM usuarios WHERE id_usuario=? AND ativo=1", (uid,))
    token = session.get("auth_token")
    if usuario and (token or current_app.config.get("REQUIRE_SESSION_TOKEN")):
        if not token or not hmac.compare_digest(str(token), token_sessao(usuario["senha_hash"])):
            usuario = None
    if not usuario:
        session.clear()
    g._auth_uid, g._auth_usuario = uid, usuario
    return usuario


def token_sessao(senha_hash):
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode("utf-8")
    return hmac.new(key, str(senha_hash).encode("utf-8"), hashlib.sha256).hexdigest()


def login_required(view):
    @wraps(view)
    def dec(*args, **kwargs):
        uid = session.get("uid")
        if not uid:
            return redirect(url_for("auth.login", next=request.path))
        usuario = usuario_atual(lambda sql, params=(): db_core.query_one(
            db_core.configured_target(current_app.config), sql, params
        ))
        if not usuario:
            session.clear()
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return dec


def nivel_min(nivel, usuario_atual_func):

    def dec(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            usuario = usuario_atual_func()
            if not usuario:
                return redirect(url_for("auth.login"))
            if not permissoes.tem_nivel(usuario, nivel):
                if request.path.startswith("/api/"):
                    return jsonify({"erro": "Você não tem permissão para realizar esta ação."}), 403
                return render_template("403.html"), 403
            return view(*args, **kwargs)
        return wrapper
    return dec


def url_segura(target):
    if not isinstance(target, str) or "\\" in target or target.startswith("//") or re.search(r"[\x00-\x20]", target):
        return False
    ref = urlparse(request.host_url)
    tst = urlparse(urljoin(request.host_url, target))
    return tst.scheme == ref.scheme and ref.netloc == tst.netloc


def chave_login(usuario):
    ip = client_ip()
    return f"{ip}:{(usuario or '').strip().lower()}"


def client_ip():
    ip = request.remote_addr or ""
    if current_app.config.get("TRUST_PROXY_HEADERS", False):
        forwarded = request.headers.get("X-Forwarded-For", "")
        ip = forwarded or ip
    ip = ip.split(",", 1)[0].strip()
    return ip


def login_bloqueado(chave, agora=None):
    agora = agora if agora is not None else time.monotonic()
    info = login_tentativas.get(chave)
    if not info:
        return False
    tentativas, primeira = info
    if agora - primeira > LOGIN_JANELA_SEG:
        login_tentativas.pop(chave, None)
        return False
    return tentativas >= LOGIN_MAX_TENTATIVAS


def login_bloqueado_db(get_db, chave, agora=None, limite=LOGIN_MAX_TENTATIVAS):
    agora = agora if agora is not None else time.time()
    conn = get_db()
    try:
        garantir_tabela_login_tentativas(get_db, conn)
        row = conn.execute(
            "SELECT tentativas, primeira_em FROM login_tentativas WHERE chave=?",
            (chave,),
        ).fetchone()
        if not row:
            return False
        if agora - row["primeira_em"] > LOGIN_JANELA_SEG:
            conn.execute("DELETE FROM login_tentativas WHERE chave=?", (chave,))
            conn.commit()
            return False
        return row["tentativas"] >= limite
    finally:
        conn.close()


def registrar_login_falha(chave, agora=None):
    agora = agora if agora is not None else time.monotonic()
    tentativas, primeira = login_tentativas.get(chave, (0, agora))
    if agora - primeira > LOGIN_JANELA_SEG:
        tentativas, primeira = 0, agora
    login_tentativas[chave] = (tentativas + 1, primeira)


def registrar_login_falha_db(get_db, chave, agora=None):
    agora = agora if agora is not None else time.time()
    atualizado = datetime.now().isoformat()
    conn = get_db()
    try:
        garantir_tabela_login_tentativas(get_db, conn)
        conn.execute(
            """
            INSERT INTO login_tentativas (chave, tentativas, primeira_em, atualizado_em)
            VALUES (?,?,?,?)
            ON CONFLICT(chave) DO UPDATE SET
                tentativas=CASE WHEN login_tentativas.primeira_em < ?
                    THEN 1 ELSE login_tentativas.tentativas + 1 END,
                primeira_em=CASE WHEN login_tentativas.primeira_em < ?
                    THEN excluded.primeira_em ELSE login_tentativas.primeira_em END,
                atualizado_em=excluded.atualizado_em
            """,
            (chave, 1, agora, atualizado, agora - LOGIN_JANELA_SEG, agora - LOGIN_JANELA_SEG),
        )
        # Limita o crescimento causado por nomes inventados na tela publica.
        conn.execute("DELETE FROM login_tentativas WHERE primeira_em < ?", (agora - LOGIN_JANELA_SEG,))
        conn.commit()
    finally:
        conn.close()


def limpar_login_falhas(chave):
    login_tentativas.pop(chave, None)


def limpar_login_falhas_db(get_db, chave):
    conn = get_db()
    try:
        garantir_tabela_login_tentativas(get_db, conn)
        conn.execute("DELETE FROM login_tentativas WHERE chave=?", (chave,))
        conn.commit()
    finally:
        conn.close()
