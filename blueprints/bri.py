from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import bri as bri_core
from app_core import utils as utils_core


bp = Blueprint("bri", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


@bp.route("/bri")
@login_required
def page():
    return render_template(
        "bri.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(365)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        localidades=bri_core.localidades(_db_path()),
        agentes=bri_core.agentes(_db_path()),
    )


@bp.route("/api/bri")
@login_required
def api_resumo():
    return jsonify(bri_core.resumo(_db_path(), _filtros()))


@bp.route("/api/bri/listar")
@login_required
def api_listar():
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    return jsonify(bri_core.listar(_db_path(), filtros))


def _filtros():
    return {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "agente": request.args.get("agente", ""),
        "destino": request.args.get("destino", ""),
        "extra": request.args.get("extra", ""),
        "origem": request.args.get("origem", ""),
    }
