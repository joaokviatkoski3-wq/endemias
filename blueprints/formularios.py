import logging

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import formularios as formularios_core
from app_core import rg_formulario


bp = Blueprint("formularios", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


@bp.route("/sw.js")
def sw_js():
    return send_from_directory(
        current_app.static_folder, "sw.js", mimetype="application/javascript"
    )


@bp.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(
        current_app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json"
    )


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


@bp.route("/api/formularios/<int:id_formulario>", methods=["DELETE"])
@login_required
@nivel_min("admin")
def api_excluir(id_formulario):
    try:
        formularios_core.excluir(bh.db_target(), id_formulario)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True})


# ── Formulário específico: atualização de RG ──────────────────────────────────

@bp.route("/formularios/rg-campo")
@login_required
def rg_campo_page():
    usuario = bh.usuario_atual() or {}
    contexto = rg_formulario.contexto(bh.db_target(), usuario)
    return render_template(
        "rg_campo.html",
        agente_proprio=contexto["agente_proprio"],
        agentes=contexto["agentes"],
    )


@bp.route("/formularios/rg-revisao")
@login_required
@nivel_min("admin")
def rg_revisao_page():
    return render_template("rg_revisao.html")


@bp.route("/api/formularios/rg/snapshot", methods=["POST"])
@login_required
def api_rg_snapshot():
    payload = request.get_json(silent=True) or {}
    selecoes = payload.get("selecoes") or []
    try:
        return jsonify(rg_formulario.snapshot(bh.db_target(), selecoes))
    except Exception:
        logging.exception("Erro em api_rg_snapshot")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@bp.route("/api/formularios/<int:id_formulario>/oficializar", methods=["POST"])
@login_required
@nivel_min("admin")
def api_oficializar(id_formulario):
    usuario = bh.usuario_atual() or {}
    try:
        rg_formulario.oficializar(bh.db_target(), id_formulario, usuario)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True})
