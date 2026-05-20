from datetime import date

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import sispncd


bp = Blueprint("conta_ovos_sispncd", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


def q(sql, params=()):
    return db_core.query(_db_path(), sql, params)


def q1(sql, params=()):
    return db_core.query_one(_db_path(), sql, params)


def usuario_atual():
    return auth_core.usuario_atual(q1)


def nivel_min(nivel):
    return auth_core.nivel_min(nivel, usuario_atual)


def _json_error(exc, status=400):
    return jsonify({"erro": str(exc)}), status


@bp.route("/conta-ovos-sispncd")
@login_required
def page():
    today = date.today()
    default_conta_ovos = sispncd.get_default_conta_ovos(_db_path())
    localidades = q("SELECT id_localidade, nome FROM localidades ORDER BY nome")
    return render_template(
        "conta_ovos_sispncd.html",
        localidades=localidades,
        default_conta_ovos=default_conta_ovos,
        default_semana=today.isocalendar()[1],
        default_ano=today.year,
    )


@bp.route("/api/conta-ovos")
@login_required
def api_conta_ovos():
    try:
        result = sispncd.conta_ovos(
            _db_path(),
            request.args.get("data"),
            request.args.get("quarteirao"),
            id_localidade=request.args.get("localidade"),
        )
    except sispncd.ValidationError as exc:
        return _json_error(exc)
    return jsonify(result)


@bp.route("/api/sispncd/pesquisar")
@login_required
def api_sispncd_pesquisar():
    try:
        result = sispncd.sispncd(
            _db_path(),
            request.args.get("ano"),
            request.args.get("semana") or request.args.get("semana_epidemiologica"),
            request.args.getlist("tipo") or request.args.getlist("tipos_trabalho"),
            id_localidade=request.args.get("localidade"),
        )
    except sispncd.ValidationError as exc:
        return _json_error(exc)
    return jsonify(result)


@bp.route("/api/conta-ovos-sispncd/pendencias")
@login_required
def api_pendencias_envio():
    return jsonify(sispncd.pendencias_envio(_db_path()))


@bp.route("/api/sispncd/salvar", methods=["POST"])
@login_required
@nivel_min("admin")
def api_sispncd_salvar():
    data = request.json or {}
    try:
        result = sispncd.salvar_sispncd(
            _db_path(),
            data.get("ano"),
            data.get("semana") or data.get("semana_epidemiologica"),
            data.get("tipo") or data.get("tipos_trabalho"),
            data.get("codigo") or data.get("sispncd"),
            id_localidade=data.get("localidade"),
        )
    except sispncd.ValidationError as exc:
        return _json_error(exc)
    return jsonify(result)


@bp.route("/api/conta-ovos/salvar-status", methods=["POST"])
@login_required
@nivel_min("admin")
def api_conta_ovos_salvar_status():
    data = request.json or {}
    try:
        result = sispncd.salvar_status_conta_ovos(
            _db_path(),
            data.get("data"),
            data.get("quarteirao"),
            id_localidade=data.get("localidade"),
        )
    except sispncd.ValidationError as exc:
        return _json_error(exc)
    return jsonify(result)
