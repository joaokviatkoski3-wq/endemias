import logging

from flask import Blueprint, redirect, render_template, request, session, url_for

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh


bp = Blueprint("auth", __name__)
login_required = auth_core.login_required


def _url_segura(target):
    return auth_core.url_segura(target)


def _chave_login(usuario):
    return auth_core.chave_login(usuario)


def _login_bloqueado(chave, agora=None):
    return auth_core.login_bloqueado_db(bh.get_db, chave, agora)


def _registrar_login_falha(chave, agora=None):
    return auth_core.registrar_login_falha_db(bh.get_db, chave, agora)


def _limpar_login_falhas(chave):
    return auth_core.limpar_login_falhas_db(bh.get_db, chave)


def _hash(senha):
    return auth_core.hash_senha(senha)


def _verificar_senha(senha_digitada, hash_armazenado):
    return auth_core.verificar_senha(senha_digitada, hash_armazenado)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("uid"):
        return redirect(url_for("home.page"))
    erro = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        chave = _chave_login(usuario)
        if _login_bloqueado(chave):
            logging.warning(
                "Login bloqueado por excesso de tentativas | usuario=%s | IP=%s",
                usuario,
                request.remote_addr,
            )
            return render_template(
                "login.html",
                erro="Muitas tentativas incorretas. Aguarde alguns minutos e tente novamente.",
            ), 429
        u = bh.q1("SELECT * FROM usuarios WHERE usuario=? AND ativo=1", (usuario,))
        if u:
            ok, novo_hash = _verificar_senha(senha, u["senha_hash"])
            if ok:
                _limpar_login_falhas(chave)
                session.permanent = True
                session["uid"] = u["id_usuario"]
                session["nivel"] = u["nivel"]
                session["nome"] = u["nome"]
                if novo_hash:
                    try:
                        conn = bh.get_db()
                        conn.execute(
                            "UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                            (novo_hash, u["id_usuario"]),
                        )
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
                dest = request.args.get("next", "")
                if not dest or not _url_segura(dest):
                    dest = url_for("home.page")
                return redirect(dest)
        erro = "Usuario ou senha incorretos."
        _registrar_login_falha(chave)
    return render_template("login.html", erro=erro)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/minha-senha", methods=["GET", "POST"])
@login_required
def minha_senha():
    erro = ok = None
    if request.method == "POST":
        atual = request.form.get("atual", "")
        nova = request.form.get("nova", "")
        conf = request.form.get("confirmar", "")
        u = bh.q1("SELECT * FROM usuarios WHERE id_usuario=?", (session["uid"],))
        senha_ok, _ = _verificar_senha(atual, u["senha_hash"])
        if not senha_ok:
            erro = "Senha atual incorreta."
        elif len(nova) < 6:
            erro = "A nova senha deve ter ao menos 6 caracteres."
        elif nova != conf:
            erro = "As senhas nao coincidem."
        else:
            conn = bh.get_db()
            conn.execute(
                "UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                (_hash(nova), session["uid"]),
            )
            conn.commit()
            conn.close()
            ok = "Senha alterada com sucesso."
    return render_template("minha_senha.html", erro=erro, ok=ok)
