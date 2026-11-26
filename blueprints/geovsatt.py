import logging

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import blueprint_helpers as bh
from app_core import geovsatt as geo_core
from app_core.auth import login_required


bp = Blueprint("geovsatt", __name__)


def _base_dir():
    return current_app.config.get("BASE_DIR")


def _json(payload):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.get("/geovsatt")
@login_required
def page():
    return render_template("geovsatt.html", catalogo=geo_core.catalogo(bh.usuario_atual()))


@bp.get("/api/geovsatt/catalogo")
@login_required
def api_catalogo():
    return _json(geo_core.catalogo(bh.usuario_atual()))


@bp.get("/api/geovsatt/camadas/quarteiroes")
@login_required
def api_quarteiroes():
    try:
        return _json(geo_core.quarteiroes(bh.db_target(), _base_dir()))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        logging.exception("Erro ao carregar quarteirões no GeoVSATT")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.get("/api/geovsatt/camadas/localidades")
@login_required
def api_localidades():
    try:
        return _json(geo_core.localidades(bh.db_target(), _base_dir()))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.get("/api/geovsatt/camadas/logradouros")
@login_required
def api_logradouros():
    try:
        return _json(geo_core.logradouros(_base_dir()))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.get("/api/geovsatt/busca")
@login_required
def api_busca():
    try:
        return _json({"resultados": geo_core.buscar(bh.db_target(), _base_dir(), request.args.get("q"))})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.get("/api/geovsatt/quarteiroes/<int:id_localidade>/<numero>")
@login_required
def api_detalhe_quarteirao(id_localidade, numero):
    try:
        return _json(geo_core.detalhe_quarteirao(bh.db_target(), _base_dir(), id_localidade, numero))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 404
