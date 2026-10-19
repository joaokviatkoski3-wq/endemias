import logging

from flask import Blueprint, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import formularios as formularios_core


bp = Blueprint("formularios", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


@bp.route("/formularios")
@login_required
def page():
    usuario = bh.usuario_atual() or {}
    return render_template(
        "formularios.html",
        formularios=formularios_core.FORMULARIOS,
        is_admin=usuario.get("nivel") == "admin",
    )


@bp.route("/api/formularios", methods=["POST"])
@login_required
def api_salvar():
    payload = request.get_json(silent=True) or {}
    usuario = bh.usuario_atual() or {}
    try:
        novo_id = formularios_core.salvar(
            bh.db_target(),
            payload.get("tipo"),
            payload.get("payload") or {},
            usuario,
            uuid_cliente=payload.get("uuid_cliente"),
            status=payload.get("status") or formularios_core.STATUS_ENVIADO,
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "id_formulario": novo_id})


@bp.route("/api/formularios")
@login_required
def api_listar():
    usuario = bh.usuario_atual() or {}
    try:
        itens = formularios_core.listar(
            bh.db_target(),
            tipo=request.args.get("tipo"),
            status=request.args.get("status"),
            usuario=usuario,
        )
    except Exception:
        logging.exception("Erro em api_listar formularios")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500
    return jsonify({"formularios": itens})


@bp.route("/api/formularios/<int:id_formulario>")
@login_required
def api_obter(id_formulario):
    item = formularios_core.obter(bh.db_target(), id_formulario)
    if not item:
        return jsonify({"erro": "Formulário não encontrado."}), 404
    return jsonify(item)


@bp.route("/api/formularios/<int:id_formulario>/revisar", methods=["POST"])
@login_required
@nivel_min("admin")
def api_revisar(id_formulario):
    payload = request.get_json(silent=True) or {}
    usuario = bh.usuario_atual() or {}
    try:
        formularios_core.revisar(
            bh.db_target(),
            id_formulario,
            payload.get("payload") or {},
            payload.get("decisao"),
            usuario,
            motivo=payload.get("motivo"),
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True})
