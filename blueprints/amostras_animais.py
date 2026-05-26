from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import amostras_animais as amostras_core
from app_core import auth as auth_core
from app_core import utils as utils_core


bp = Blueprint("amostras_animais", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


@bp.route("/amostras-animais")
@login_required
def page():
    return render_template(
        "amostras_animais.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(365)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        localidades=amostras_core.localidades(_db_path()),
        agentes=amostras_core.agentes(_db_path()),
        motivos=amostras_core.opcoes(_db_path(), "motivo_visita"),
        tipos=amostras_core.opcoes(_db_path(), "tipo_animal"),
    )


@bp.route("/api/amostras-animais")
@login_required
def api_resumo():
    return jsonify(amostras_core.resumo(_db_path(), _filtros()))


@bp.route("/api/amostras-animais/listar")
@login_required
def api_listar():
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    return jsonify(amostras_core.listar(_db_path(), filtros))


def _filtros():
    return {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "agente": request.args.get("agente", ""),
        "motivo": request.args.get("motivo", ""),
        "tipo_animal": request.args.get("tipo_animal", ""),
        "acidente": request.args.get("acidente", ""),
        "captura": request.args.get("captura", ""),
        "origem": request.args.get("origem", ""),
    }
