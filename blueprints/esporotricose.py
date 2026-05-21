from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import esporotricose as esporotricose_core
from app_core import utils as utils_core


bp = Blueprint("esporotricose", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


def _localidades():
    conn = db_core.connect(_db_path())
    esporotricose_core.ensure_schema(conn)
    try:
        return [
            dict(r) for r in conn.execute(
                """SELECT DISTINCT localidade AS nome
                   FROM esporotricose_visitas
                   WHERE localidade IS NOT NULL AND TRIM(localidade) <> ''
                   ORDER BY localidade"""
            )
        ]
    finally:
        conn.close()


def _agentes():
    conn = db_core.connect(_db_path())
    esporotricose_core.ensure_schema(conn)
    try:
        return [
            dict(r) for r in conn.execute(
                """SELECT DISTINCT ag.nome
                   FROM esporotricose_visita_agentes va
                   JOIN agentes ag ON ag.id_agente = va.id_agente
                   ORDER BY ag.nome"""
            )
        ]
    finally:
        conn.close()


@bp.route("/esporotricose")
@login_required
def page():
    return render_template(
        "esporotricose.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(365)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        localidades=_localidades(),
        agentes=_agentes(),
    )


@bp.route("/api/esporotricose")
@login_required
def api_resumo():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
    }
    return jsonify(esporotricose_core.resumo(_db_path(), filtros))


@bp.route("/api/esporotricose/visitas")
@login_required
def api_visitas():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
        "busca": request.args.get("busca", ""),
    }
    return jsonify(esporotricose_core.listar_visitas(_db_path(), filtros))


@bp.route("/api/esporotricose/animais")
@login_required
def api_animais():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
        "busca": request.args.get("busca", ""),
        "especie": request.args.get("especie", ""),
        "feridas": request.args.get("feridas", ""),
        "vacinado": request.args.get("vacinado", ""),
        "castrado": request.args.get("castrado", ""),
        "ambiente": request.args.get("ambiente", ""),
        "prioritarios": request.args.get("prioritarios", ""),
    }
    return jsonify(esporotricose_core.listar_animais(_db_path(), filtros))


@bp.route("/api/esporotricose/localidades")
@login_required
def api_localidades():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
    }
    return jsonify(esporotricose_core.resumo_localidades(_db_path(), filtros))


@bp.route("/api/esporotricose/dashboard")
@login_required
def api_dashboard():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
    }
    return jsonify(esporotricose_core.dashboard(_db_path(), filtros))
