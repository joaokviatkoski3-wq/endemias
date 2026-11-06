import logging

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import formularios as formularios_core
from app_core import rg_formulario
from app_core import audit, campo_protocolo


bp = Blueprint("formularios", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


@bp.route("/sw.js")
def sw_js():
    response = send_from_directory(
        current_app.static_folder, "sw.js", mimetype="application/javascript"
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


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
        is_admin=usuario.get("nivel") in {"admin", "superadmin"},
    )


@bp.route("/api/formularios", methods=["POST"])
@login_required
def api_salvar():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"erro": "Envio inválido."}), 400
    usuario = bh.usuario_atual() or {}
    if payload.get("captura") is not None:
        if payload.get("usuario_offline") != usuario.get("id_usuario") or isinstance(payload.get("usuario_offline"), bool):
            return jsonify({"erro": "A conta mudou. Volte à página online antes de sincronizar.", "codigo": "conta_alterada"}), 403
        dados = payload.get("payload") or {}
        if not isinstance(dados, dict):
            return jsonify({"erro": "Conteúdo de campo inválido."}), 400
        try:
            campo_protocolo.validar_rg(dados, payload.get("status") or "enviado")
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 400
        ids = dados.get("agentes_ids", [])
        permitidos = {a["id_agente"] for a in rg_formulario.contexto(bh.db_target(), usuario)["agentes"]}
        if not isinstance(ids, list) or any(not isinstance(i, int) or isinstance(i, bool) or i not in permitidos for i in ids):
            return jsonify({"erro": "Confira os agentes liberados para sua conta antes de enviar."}), 400
    def auditar(conn, ident, metadata):
        audit.registrar_evento(bh.get_db, "formulario_campo_salvo", entidade="formularios", entidade_id=ident,
            detalhes={"tipo": payload.get("tipo"), "status": payload.get("status") or "enviado",
                      "revisao": metadata["revisao"] if metadata else None}, conn=conn)
    try:
        novo_id = formularios_core.salvar(
            bh.db_target(),
            payload.get("tipo"),
            payload.get("payload") or {},
            usuario,
            uuid_cliente=payload.get("uuid_cliente"),
            status=payload.get("status") or formularios_core.STATUS_ENVIADO,
            captura=payload.get("captura"),
            auditar=auditar if payload.get("captura") is not None else None,
        )
    except campo_protocolo.ConflitoCampo as exc:
        return jsonify({"erro": str(exc), "codigo": exc.codigo}), 409
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    status_atual = formularios_core.obter(bh.db_target(), novo_id)["status"] if payload.get("captura") else None
    return jsonify({"ok": True, "id_formulario": novo_id, "uuid_cliente": payload.get("uuid_cliente"),
                    "revisao_recebida": (payload.get("captura") or {}).get("revisao"), "status_atual": status_atual})


@bp.get("/api/formularios/campo-sessao")
def campo_sessao():
    from flask_wtf.csrf import generate_csrf
    usuario = bh.usuario_atual() or {}
    if not usuario.get("id_usuario"):
        return jsonify({"erro": "Entre novamente para sincronizar."}), 401
    return jsonify({"usuario_id": usuario["id_usuario"], "csrf": generate_csrf(), "protocolo": 1})


@bp.route("/api/formularios")
@login_required
def api_listar():
    usuario = bh.usuario_atual() or {}
    if request.args.get("proprios") == "1":
        usuario = {**usuario, "nivel": "usuario"}
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
    usuario = bh.usuario_atual() or {}
    if usuario.get("nivel") not in {"admin", "superadmin"} and item["usuario_id"] != usuario.get("id_usuario"):
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
    if not isinstance(payload, dict):
        return jsonify({"erro": "Seleção inválida."}), 400
    selecoes = payload.get("selecoes") or []
    if not isinstance(selecoes, list) or not 1 <= len(selecoes) <= 500 or any(not isinstance(s, dict) for s in selecoes):
        return jsonify({"erro": "Selecione entre 1 e 500 quarteirões por vez."}), 400
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
