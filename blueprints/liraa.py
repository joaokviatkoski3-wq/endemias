"""Planejamento de ciclos, estratos e sorteios do LIRAa."""

import logging

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import db as db_core
from app_core import liraa as liraa_core


bp = Blueprint("liraa", __name__)
login_required = auth_core.login_required


def _target():
    return bh.db_target()


def _base_dir():
    return current_app.config.get("BASE_DIR")


def _get_db():
    return db_core.connect(_target())


def _q1(sql, params=()):
    return db_core.query_one(_target(), sql, params)


def _usuario():
    return auth_core.usuario_atual(_q1)


nivel_admin = auth_core.nivel_min("admin", _usuario)


@bp.route("/liraa")
@login_required
def page():
    dados, erro = None, None
    try:
        dados = liraa_core.painel(_target(), _base_dir())
    except Exception:
        logging.exception("Falha ao carregar planejamento LIRAa")
        erro = "Planejamento indisponível. Confirme as migrações 0023/0024 e a camada de quarteirões ativa."
    editando = None
    try:
        id_edicao = int(request.args.get("editar", "0"))
    except ValueError:
        id_edicao = 0
    if dados and id_edicao:
        editando = next((e for c in dados["ciclos"] for e in c["estratos"]
                         if e["id_estrato"] == id_edicao and not e["sorteio"]), None)
    return render_template("liraa.html", dados=dados, erro=erro,
                           editando=editando, is_admin=(_usuario() or {}).get("nivel") == "admin")


def _resposta(acao, func, entidade, detalhes, auditoria_embutida=False):
    try:
        identificador = func()
        if not auditoria_embutida:
            audit.registrar_evento(_get_db, acao, entidade=entidade,
                                   entidade_id=identificador, detalhes=detalhes)
        flash("Alteração salva com sucesso.", "success")
    except liraa_core.LiraaError as exc:
        flash(str(exc), "error")
    except Exception:
        logging.exception("Falha na operação LIRAa: %s", acao)
        flash("Não foi possível concluir a operação. Confirme a migração e tente novamente.", "error")
    return redirect(url_for("liraa.page"))


@bp.route("/liraa/ciclos", methods=["POST"])
@login_required
@nivel_admin
def criar_ciclo():
    payload = request.form.to_dict()
    return _resposta("liraa_ciclo_criado", lambda: liraa_core.criar_ciclo(_target(), payload),
                     "liraa_ciclo", {k: payload.get(k) for k in ("ano", "nome", "inicio", "fim")})


@bp.route("/liraa/ciclos/<int:id_ciclo>/editar", methods=["POST"])
@login_required
@nivel_admin
def atualizar_ciclo(id_ciclo):
    payload = request.form.to_dict()
    return _resposta("liraa_ciclo_atualizado", lambda: liraa_core.atualizar_ciclo(
        _target(), id_ciclo, payload), "liraa_ciclo",
        {k: payload.get(k) for k in ("ano", "nome", "inicio", "fim")})


@bp.route("/liraa/ciclos/<int:id_ciclo>/excluir", methods=["POST"])
@login_required
@nivel_admin
def excluir_ciclo(id_ciclo):
    if request.form.get("confirmar_exclusao") != "sim":
        flash("Confirme a exclusão do ciclo antes de continuar.", "error")
        return redirect(url_for("liraa.page"))
    def excluir():
        liraa_core.excluir_ciclo(_target(), id_ciclo, auditar=lambda conn, detalhes:
            audit.registrar_evento(_get_db, "liraa_ciclo_excluido", entidade="liraa_ciclo",
                                   entidade_id=id_ciclo, detalhes=detalhes, conn=conn))
        return id_ciclo
    return _resposta("liraa_ciclo_excluido", excluir, "liraa_ciclo", {}, auditoria_embutida=True)


@bp.route("/liraa/ciclos/<int:id_ciclo>/estratos", methods=["POST"])
@login_required
@nivel_admin
def salvar_estrato(id_ciclo):
    payload = request.form.to_dict()
    payload["localidades"] = request.form.getlist("localidades")
    if "quarteiroes" in request.form:
        payload["quarteiroes"] = request.form.getlist("quarteiroes")
    id_estrato = request.form.get("id_estrato") or None
    return _resposta("liraa_estrato_salvo", lambda: liraa_core.salvar_estrato(
        _target(), id_ciclo, payload, id_estrato, _base_dir()), "liraa_estrato",
        {k: payload.get(k) for k in ("numero", "tipo", "imoveis_confirmados", "localidades", "quarteiroes")})


@bp.route("/liraa/estratos/<int:id_estrato>/sortear", methods=["POST"])
@login_required
@nivel_admin
def sortear(id_estrato):
    return _resposta("liraa_estrato_sorteado", lambda: liraa_core.sortear(
        _target(), id_estrato, _base_dir())["id_sorteio"], "liraa_sorteio",
        {"id_estrato": id_estrato})


@bp.route("/liraa/estratos/<int:id_estrato>/excluir", methods=["POST"])
@login_required
@nivel_admin
def excluir_estrato(id_estrato):
    if request.form.get("confirmar_exclusao") != "sim":
        flash("Confirme a exclusão do estrato antes de continuar.", "error")
        return redirect(url_for("liraa.page"))
    def excluir():
        liraa_core.excluir_estrato(_target(), id_estrato, auditar=lambda conn, detalhes:
            audit.registrar_evento(_get_db, "liraa_estrato_excluido", entidade="liraa_estrato",
                                   entidade_id=id_estrato, detalhes=detalhes, conn=conn))
        return id_estrato
    return _resposta("liraa_estrato_excluido", excluir, "liraa_estrato", {}, auditoria_embutida=True)
