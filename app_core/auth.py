import hashlib
import time
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


LOGIN_MAX_TENTATIVAS = 5
LOGIN_JANELA_SEG = 15 * 60
login_tentativas = {}


def hash_legado(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def hash_senha(senha):
    return generate_password_hash(senha, method="pbkdf2:sha256", salt_length=16)


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
    return query_one("SELECT * FROM usuarios WHERE id_usuario=? AND ativo=1", (uid,))


def login_required(view):
    @wraps(view)
    def dec(*args, **kwargs):
        if not session.get("uid"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return dec


def nivel_min(nivel, usuario_atual_func):
    ordem = {"admin": 3, "operador": 2, "visualizador": 1}

    def dec(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            usuario = usuario_atual_func()
            if not usuario:
                return redirect(url_for("auth.login"))
            if ordem.get(usuario["nivel"], 0) < ordem.get(nivel, 999):
                return render_template("403.html"), 403
            return view(*args, **kwargs)
        return wrapper
    return dec


def url_segura(target):
    ref = urlparse(request.host_url)
    tst = urlparse(urljoin(request.host_url, target))
    return tst.scheme in ("http", "https") and ref.netloc == tst.netloc


def chave_login(usuario):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    ip = ip.split(",", 1)[0].strip()
    return f"{ip}:{(usuario or '').strip().lower()}"


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


def registrar_login_falha(chave, agora=None):
    agora = agora if agora is not None else time.monotonic()
    tentativas, primeira = login_tentativas.get(chave, (0, agora))
    if agora - primeira > LOGIN_JANELA_SEG:
        tentativas, primeira = 0, agora
    login_tentativas[chave] = (tentativas + 1, primeira)


def limpar_login_falhas(chave):
    login_tentativas.pop(chave, None)
