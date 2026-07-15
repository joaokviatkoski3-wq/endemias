from flask import Blueprint, jsonify, request

from app_core import ajuda as ajuda_core
from app_core import blueprint_helpers as bh
from app_core.auth import login_required


bp = Blueprint("ajuda", __name__)


@bp.route("/api/ajuda")
@login_required
def api_ajuda():
    usuario = bh.usuario_atual() or {}
    return jsonify(ajuda_core.consultar(
        consulta=request.args.get("q", ""),
        rota=request.args.get("rota", "/"),
        limite=request.args.get("limite", 12),
        contexto=request.args.get("contexto", ""),
        nivel=usuario.get("nivel", "visualizador"),
        somente_laboratorio=bool(usuario.get("somente_laboratorio")),
    ))
