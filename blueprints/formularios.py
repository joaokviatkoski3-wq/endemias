import logging
import os

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory, session

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import formularios as formularios_core
from app_core import campo_push, rg_formulario
from app_core import audit, avisos_campo, campo_protocolo, escopo_agente, formulario_piloto, formulario_revisao, permissoes, setores


bp = Blueprint("formularios", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


@bp.before_request
def preservar_fluxo_rg():
    ident=(request.view_args or {}).get('id_formulario')
    if ident:
        item=formularios_core.obter(bh.db_target(),ident)
        if item and item['tipo_formulario'].startswith('kobo_'):
            return jsonify({'erro':'Use a área de formulários internos do setor.'}),404


@bp.route("/sw.js")
def sw_js():
    response = send_from_directory(
        current_app.static_folder, "sw.js", mimetype="application/javascript"
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"
    return response


@bp.route("/manifest.webmanifest")
def manifest():
    response = send_from_directory(
        current_app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json"
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.get("/manifest-campo.webmanifest")
def manifest_campo():
    response = send_from_directory(current_app.static_folder, "manifest-campo.webmanifest",
                                   mimetype="application/manifest+json")
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.route("/formularios")
@login_required
def page():
    usuario = bh.usuario_atual() or {}
    from app_core import formulario_piloto,formularios_kobo,setores
    rg=list(formularios_core.FORMULARIOS) if setores.atual()!='ambiental' and not usuario.get('somente_laboratorio') else []
    is_admin=permissoes.gerencia(usuario)
    aba="revisao" if is_admin and request.args.get("aba")=="revisao" else "campo"
    itens,filtros,total,pagina=[],{},0,1
    erro=None
    if aba=="revisao":
        try:
            itens,filtros,total,pagina=formulario_revisao.listar(bh.db_target(),usuario,request.args)
        except ValueError:
            erro="Confira as datas usadas para filtrar a revisão."
    return render_template(
        "formularios.html",
        formularios=rg+formularios_kobo.catalogo(usuario),
        piloto_offline=formulario_piloto.habilitado(usuario),
        is_admin=is_admin,aba=aba,itens=itens,filtros=filtros,total=total,pagina=pagina,
        erro=erro,por_pagina=formulario_revisao.POR_PAGINA,
        situacoes=formulario_revisao.SITUACOES,tipos=formulario_revisao.tipos(usuario) if is_admin else {},
    )


@bp.route("/api/formularios", methods=["POST"])
@login_required
def api_salvar():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"erro": "Envio inválido."}), 400
    if payload.get('tipo')!='rg_atualizacao':return jsonify({'erro':'Tipo indisponível nesta entrada.'}),400
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


@bp.route("/api/formularios/campo-avisos", methods=["GET", "POST"])
@login_required
def campo_avisos():
    from flask_wtf.csrf import generate_csrf

    usuario = bh.usuario_atual() or {}
    if setores.atual() == "ambiental" or usuario.get("somente_laboratorio"):
        return jsonify({"erro": "Avisos disponíveis para agentes de Endemias."}), 403
    target = bh.db_target()
    agente = escopo_agente.agente_proprio(target, usuario)
    ident = usuario["id_usuario"]
    if request.method == "GET":
        avisos = (avisos_campo.listar(target, ident, agente["id_agente"]) if agente
                  else {"itens": [], "nao_lidos": 0})
        return jsonify({"usuario": ident, "vinculado": bool(agente), "csrf": generate_csrf(), **avisos})
    item = request.get_json(silent=True)
    if not isinstance(item, dict) or type(item.get("resultado")) is not int or not isinstance(item.get("versao"), str):
        return jsonify({"erro": "Aviso inválido."}), 400
    if not (-2**63 <= item["resultado"] < 2**63) or len(item["versao"]) > 100:
        return jsonify({"erro": "Aviso inválido."}), 400
    if not agente or item.get("usuario") != ident or not avisos_campo.ler(
        target, ident, agente["id_agente"], item["resultado"], item["versao"]
    ):
        return jsonify({"erro": "Aviso indisponível ou atualizado. Consulte novamente."}), 404
    return jsonify({"ok": True})


@bp.route("/api/formularios/campo-push", methods=["GET", "POST"])
@login_required
def campo_push_api():
    from flask_wtf.csrf import generate_csrf

    usuario = bh.usuario_atual() or {}
    path = os.environ.get(campo_push.CHAVE_ENV)
    if (not current_app.config.get("ACESSO_EXTERNO") or not request.is_secure
            or setores.atual() != "endemias" or not path or not campo_push.identificavel(usuario)):
        return jsonify({"erro": "Notificações do aparelho reservadas ao piloto."}), 403
    target = bh.db_target()
    agente = escopo_agente.agente_proprio(target, usuario)
    sid = session.get("sessao_id")
    if not agente or not sid:
        return jsonify({"erro": "Entre com a conta de campo vinculada ao agente do piloto."}), 403
    try:
        public = campo_push.chave_publica(campo_push.chave(path))
    except (OSError, ValueError, ImportError):
        return jsonify({"erro": "A configuração de notificações está indisponível."}), 503
    ident = usuario["id_usuario"]
    if request.method == "GET":
        return jsonify({"usuario": ident, "chave": public,
                        "aparelho": campo_push.status(target, ident), "csrf": generate_csrf()})
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or body.get("usuario") != ident:
        return jsonify({"erro": "Reabra o aplicativo na conta do piloto."}), 403
    try:
        acao, endpoint = body.get("acao"), body.get("endpoint")
        if acao == "ativar":
            campo_push.inscrever(target, usuario, sid, endpoint)
        elif acao == "desativar":
            campo_push.cancelar(target, ident, endpoint)
        elif acao == "testar":
            campo_push.testar(target, ident, endpoint)
        else:
            raise ValueError("Ação inválida.")
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
    return jsonify({"ok": True})


@bp.route("/api/formularios")
@login_required
def api_listar():
    usuario = bh.usuario_atual() or {}
    if request.args.get("proprios") == "1":
        usuario = {**usuario, "nivel": "usuario"}
    try:
        itens = formularios_core.listar(
            bh.db_target(),
            tipo='rg_atualizacao',
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
    return jsonify({**item,"etag":formulario_revisao.versao(item)})


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
            esperado=payload.get("etag"),
        )
    except campo_protocolo.ConflitoCampo as exc:
        return jsonify({"erro":str(exc)}),409
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
    piloto = formulario_piloto.habilitado(usuario)
    response = current_app.make_response(render_template(
        "rg_campo.html",
        agente_proprio=contexto["agente_proprio"],
        agentes=contexto["agentes"],
        piloto_campo=piloto,
        avisos_campo=setores.atual() != "ambiental",
    ))
    if piloto:
        response.headers["X-Endemias-Campo-Offline"] = "1"
    return response


@bp.route("/formularios/rg-revisao")
@login_required
@nivel_min("admin")
def rg_revisao_page():
    return render_template("rg_revisao.html",embutido=request.args.get("embutido")=="1")


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


@bp.get("/api/formularios/rg/referencias")
@login_required
def api_rg_referencias():
    if setores.atual() == "ambiental":
        return jsonify({"erro": "RG disponível em Endemias."}), 403
    referencias = formulario_piloto.catalogos(bh.db_target())
    return jsonify({"areas": referencias["areas"], "rg": referencias["rg"]})


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


@bp.post("/api/formularios/<int:id_formulario>/aceitar")
@login_required
@nivel_min("admin")
def api_aceitar(id_formulario):
    payload=request.get_json(silent=True)
    tag=payload.get("etag") if isinstance(payload,dict) else None
    if not isinstance(tag,str) or len(tag)!=64:
        return jsonify({"erro":"Abra a revisão antes de aceitar."}),400
    try:
        rg_formulario.oficializar(bh.db_target(),id_formulario,bh.usuario_atual() or {},aceitar_versao=tag)
    except campo_protocolo.ConflitoCampo as exc:
        return jsonify({"erro":str(exc)}),409
    except ValueError as exc:
        return jsonify({"erro":str(exc)}),400
    return jsonify({"ok":True})
