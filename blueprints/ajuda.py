from flask import Blueprint, jsonify, request, current_app
import hashlib
import hmac
import json
from urllib.parse import urlsplit, parse_qs
from werkzeug.exceptions import HTTPException

from app_core import ajuda as ajuda_core
from app_core import blueprint_helpers as bh
from app_core import setores
from app_core import modules, permissoes
from app_core.auth import login_required


bp = Blueprint("ajuda", __name__)


@bp.route("/api/ajuda")
@login_required
def api_ajuda():
    usuario = bh.usuario_atual() or {}
    adapter = current_app.url_map.bind("")
    def permitida(link):
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
            return False
        try:
            endpoint, _ = adapter.match(parsed.path, method="GET")
        except HTTPException:
            return False
        if not setores.permite_endpoint(endpoint):
            return False
        if permissoes.exige_tecnica(endpoint, parsed.path) and not permissoes.permite(usuario, "tecnica"):
            return False
        if parsed.path == "/admin/auditoria" and "tecnico" in parse_qs(parsed.query).get("origem", ()) and not permissoes.permite(usuario, "tecnica"):
            return False
        if endpoint in {"auth.minha_senha", "auth.termos"}:
            return True
        candidates = [m for m in modules.MODULES if endpoint in m.endpoints
            or parsed.path == urlsplit(m.href).path
            or m.href != "/" and parsed.path.startswith(urlsplit(m.href).path + "/")]
        return bool(candidates) and any(modules.can_access(m, usuario) for m in candidates)
    result = ajuda_core.consultar(
        consulta=request.args.get("q", ""),
        rota=request.args.get("rota", "/"),
        limite=request.args.get("limite", 12),
        contexto=request.args.get("contexto", ""),
        nivel=usuario.get("nivel", "visualizador"),
        somente_laboratorio=bool(usuario.get("somente_laboratorio")),
        rota_permitida=permitida,
        setor=setores.atual(),
        usuario=usuario,
    )
    identity = {k: usuario.get(k) for k in ("id_usuario", "nivel", "acesso_laboratorio", "somente_laboratorio")}
    identity["setor"] = result["setor"]
    secret = current_app.secret_key
    if not isinstance(secret, bytes):
        secret = str(secret).encode("utf-8")
    result["escopo"] = hmac.new(secret, json.dumps(identity, sort_keys=True).encode("utf-8"), hashlib.sha256).hexdigest()
    response = jsonify(result)
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.vary.add("Cookie")
    return response
