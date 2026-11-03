import logging

from flask import Blueprint, redirect, render_template, request, session, url_for

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import termos_uso


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
        if len(usuario) > 150 or len(senha) > 1024:
            return render_template("login.html", erro="Usuario ou senha incorretos."), 400
        chave = _chave_login(usuario)
        chave_ip = "ip:" + auth_core.client_ip()
        if _login_bloqueado(chave) or auth_core.login_bloqueado_db(bh.get_db, chave_ip, limite=auth_core.LOGIN_MAX_POR_IP):
            logging.warning(
                "Login bloqueado por excesso de tentativas | usuario=%s | IP=%s",
                usuario,
                request.remote_addr,
            )
            audit.registrar_evento(
                bh.get_db,
                "login_bloqueado",
                entidade="usuarios",
                detalhes={"usuario": usuario},
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
                session.clear()
                session.permanent = True
                session["uid"] = u["id_usuario"]
                session["nivel"] = u["nivel"]
                session["nome"] = u["nome"]
                session["auth_token"] = auth_core.token_sessao(u["senha_hash"])
                audit.registrar_evento(
                    bh.get_db,
                    "login_sucesso",
                    entidade="usuarios",
                    entidade_id=u["id_usuario"],
                    detalhes={"usuario": usuario, "nivel": u["nivel"]},
                )
                if novo_hash:
                    try:
                        conn = bh.get_db()
                        conn.execute(
                            "UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                            (novo_hash, u["id_usuario"]),
                        )
                        conn.commit()
                        conn.close()
                        session["auth_token"] = auth_core.token_sessao(novo_hash)
                    except Exception:
                        pass
                dest = request.args.get("next", "")
                if u.get("somente_laboratorio") and u.get("nivel") != "admin":
                    dest = url_for("laboratorio_lancamentos.page")
                elif not dest or not _url_segura(dest):
                    dest = url_for("home.page")
                return redirect(dest)
        if not u:
            # Mantem custo semelhante ao de uma senha errada em conta existente.
            auth_core.verificar_senha(senha, auth_core._DUMMY_HASH)
        erro = "Usuario ou senha incorretos."
        _registrar_login_falha(chave)
        _registrar_login_falha(chave_ip)
        audit.registrar_evento(
            bh.get_db,
            "login_falha",
            entidade="usuarios",
            detalhes={"usuario": usuario},
        )
    return render_template("login.html", erro=erro)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit.registrar_evento(bh.get_db, "logout", entidade="usuarios", entidade_id=session.get("uid"))
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
        elif not auth_core.senha_valida(nova):
            erro = auth_core.mensagem_senha_invalida()
        elif nova != conf:
            erro = "As senhas nao coincidem."
        else:
            conn = bh.get_db()
            novo_hash = _hash(nova)
            conn.execute(
                "UPDATE usuarios SET senha_hash=? WHERE id_usuario=?",
                (novo_hash, session["uid"]),
            )
            conn.commit()
            conn.close()
            session["auth_token"] = auth_core.token_sessao(novo_hash)
            audit.registrar_evento(
                bh.get_db,
                "usuario_alterou_senha",
                entidade="usuarios",
                entidade_id=session["uid"],
            )
            ok = "Senha alterada com sucesso."
    return render_template("minha_senha.html", erro=erro, ok=ok)


@bp.route("/termos")
@login_required
def termos():
    return render_template("termos_uso.html", termo=termos_uso)


@bp.route("/termos/aceitar", methods=["POST"])
@login_required
def aceitar_termos():
    if (request.form.get("concordo") != "sim" or request.form.get("versao") != termos_uso.VERSAO
            or request.form.get("termo_hash") != termos_uso.HASH):
        return render_template("termos_uso.html", termo=termos_uso,
                               erro="Leia o termo atual e marque a confirmação para continuar."), 400
    termos_uso.registrar(bh.db_target(), session["uid"])
    session["termo_aceito"] = termos_uso.VERSAO + ":" + termos_uso.HASH
    return redirect(url_for("home.page"))
