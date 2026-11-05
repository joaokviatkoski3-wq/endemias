from flask import Blueprint, jsonify, request, current_app
from urllib.parse import urlsplit
from werkzeug.exceptions import HTTPException

from app_core import ajuda as ajuda_core
from app_core import blueprint_helpers as bh
from app_core import setores
from app_core.auth import login_required


bp = Blueprint("ajuda", __name__)


@bp.route("/api/ajuda")
@login_required
def api_ajuda():
    usuario = bh.usuario_atual() or {}
    adapter = current_app.url_map.bind("")
    def permitida(link):
        if not setores.atual():
            return True
        try:
            endpoint, _ = adapter.match(urlsplit(link).path)
        except HTTPException:
            return False
        return setores.permite_endpoint(endpoint)
    return jsonify(ajuda_core.consultar(
        consulta=request.args.get("q", ""),
        rota=request.args.get("rota", "/"),
        limite=request.args.get("limite", 12),
        contexto=request.args.get("contexto", ""),
        nivel=usuario.get("nivel", "visualizador"),
        somente_laboratorio=bool(usuario.get("somente_laboratorio")),
        rota_permitida=permitida,
        setor=setores.atual(),
    ))
