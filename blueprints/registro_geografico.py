import logging

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import db as db_core
from app_core import registro_geografico as rg_core


bp = Blueprint("registro_geografico", __name__)
login_required = auth_core.login_required


def _db_path():
    return bh.db_target()


def _base_dir():
    return current_app.config.get("BASE_DIR")


def get_db():
    return db_core.connect(_db_path())


def q1(sql, params=()):
    return db_core.query_one(_db_path(), sql, params)


def usuario_atual():
    return auth_core.usuario_atual(q1)


def nivel_min(nivel):
    return auth_core.nivel_min(nivel, usuario_atual)


def _autor_atualizacao():
    usuario = usuario_atual()
    if not usuario:
        return None, None
    return usuario["id_usuario"], usuario["nome"] or usuario["usuario"]


@bp.route("/registro-geografico")
@login_required
def page():
    try:
        opcoes = rg_core.opcoes(_db_path(), _base_dir())
    except ValueError as exc:
        opcoes = {"localidades": [], "agentes": [], "tipos": [], "erro_importacao": str(exc)}
    return render_template("registro_geografico.html", opcoes=opcoes)


@bp.route("/api/registro-geografico")
@login_required
def api_listar():
    try:
        return jsonify(rg_core.listar(_db_path(), _filtros(), limite=request.args.get("limite") or 500, base_dir=_base_dir()))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        logging.exception("Erro ao listar Registro Geografico")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.route("/api/registro-geografico/acompanhamento")
@login_required
def api_acompanhamento():
    try:
        filtros = {
            "localidade": request.args.getlist("localidade") or request.args.get("localidade", ""),
            "situacao": request.args.get("situacao", ""),
            "agente": request.args.get("agente", ""),
            "d_ini": request.args.get("d_ini", ""),
            "d_fim": request.args.get("d_fim", ""),
            "busca": request.args.get("busca", ""),
        }
        return jsonify(rg_core.acompanhamento_atualizacoes(_db_path(), filtros, _base_dir()))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        logging.exception("Erro ao carregar acompanhamento do Registro Geografico")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.route("/api/registro-geografico", methods=["POST"])
@login_required
@nivel_min("operador")
def api_criar():
    try:
        usuario_id, usuario_nome = _autor_atualizacao()
        registro = rg_core.criar(
            _db_path(), request.get_json(silent=True) or {}, _base_dir(), usuario_id, usuario_nome
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        get_db,
        "registro_geografico_criado",
        entidade="registro_geografico",
        entidade_id=registro.get("id_imovel"),
        detalhes={"localidade": registro.get("localidade"), "quarteirao": registro.get("quarteirao")},
    )
    return jsonify({"ok": True, "registro": registro}), 201


@bp.route("/api/registro-geografico/opcoes")
@login_required
def api_opcoes():
    try:
        return jsonify(rg_core.opcoes(_db_path(), _base_dir()))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/api/registro-geografico/quarteiroes")
@login_required
def api_quarteiroes():
    try:
        return jsonify({
            "registros": rg_core.quarteiroes_por_localidade(
                _db_path(),
                request.args.get("localidade") or request.args.get("id_localidade"),
                _base_dir(),
            )
        })
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/api/registro-geografico/quarteirao")
@login_required
def api_quarteirao():
    try:
        return jsonify(
            rg_core.quarteirao(
                _db_path(),
                request.args.get("localidade") or request.args.get("id_localidade"),
                request.args.get("quarteirao"),
                _base_dir(),
            )
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/api/registro-geografico/quarteirao", methods=["POST"])
@login_required
@nivel_min("operador")
def api_salvar_quarteirao():
    try:
        usuario_id, usuario_nome = _autor_atualizacao()
        dados = rg_core.salvar_quarteirao(
            _db_path(), request.get_json(silent=True) or {}, _base_dir(), usuario_id, usuario_nome
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        get_db,
        "registro_geografico_quarteirao_atualizado",
        entidade="registro_geografico",
        detalhes={"localidade": dados.get("localidade", {}).get("nome"), "quarteirao": dados.get("quarteirao")},
    )
    return jsonify({"ok": True, "quarteirao": dados})


@bp.route("/api/registro-geografico/quarteirao/limpar", methods=["POST"])
@login_required
@nivel_min("operador")
def api_limpar_quarteirao():
    payload = request.get_json(silent=True) or {}
    try:
        usuario_id, usuario_nome = _autor_atualizacao()
        dados = rg_core.limpar_quarteirao(_db_path(), payload, _base_dir(), usuario_id, usuario_nome)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        get_db,
        "registro_geografico_quarteirao_limpo",
        entidade="registro_geografico",
        detalhes={
            "localidade": dados.get("localidade", {}).get("nome"),
            "quarteirao": dados.get("quarteirao"),
            "removidos": dados.get("removidos"),
        },
    )
    return jsonify({"ok": True, "quarteirao": dados})


@bp.route("/api/registro-geografico/quarteirao/excluir", methods=["POST"])
@login_required
@nivel_min("operador")
def api_excluir_quarteirao():
    payload = request.get_json(silent=True) or {}
    try:
        dados = rg_core.excluir_quarteirao(_db_path(), payload, _base_dir())
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        get_db,
        "registro_geografico_quarteirao_excluido",
        entidade="registro_geografico",
        detalhes={
            "localidade": dados.get("localidade", {}).get("nome"),
            "quarteirao": dados.get("quarteirao"),
            "removidos": dados.get("removidos"),
        },
    )
    return jsonify({"ok": True, "quarteirao": dados})


@bp.route("/api/registro-geografico/mapa-resumo")
@login_required
def api_mapa_resumo():
    try:
        return jsonify(rg_core.resumo_mapa(_db_path(), _base_dir()))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/api/registro-geografico/logradouros-sugestoes")
@login_required
def api_logradouros_sugestoes():
    try:
        return jsonify(
            rg_core.sugestoes_logradouros(
                _db_path(),
                busca=request.args.get("q") or request.args.get("busca") or "",
                id_localidade=request.args.get("localidade") or request.args.get("id_localidade"),
                limite=request.args.get("limite") or 12,
                base_dir=_base_dir(),
            )
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/api/registro-geografico/logradouros-similares")
@login_required
def api_logradouros_similares():
    try:
        filtros = {
            "localidade": request.args.getlist("localidade") or request.args.get("localidade", ""),
            "quarteirao": request.args.getlist("quarteirao") or request.args.get("quarteirao", ""),
        }
        return jsonify(
            rg_core.logradouros_similares(
                _db_path(),
                filtros=filtros,
                score_min=request.args.get("score_min") or request.args.get("score") or 78,
                limite=request.args.get("limite") or 80,
                base_dir=_base_dir(),
            )
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/api/registro-geografico/lote/preview", methods=["POST"])
@login_required
@nivel_min("operador")
def api_preview_lote():
    try:
        return jsonify(rg_core.preview_substituicao_lote(_db_path(), request.get_json(silent=True) or {}, _base_dir()))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/api/registro-geografico/lote/aplicar", methods=["POST"])
@login_required
@nivel_min("operador")
def api_aplicar_lote():
    payload = request.get_json(silent=True) or {}
    try:
        usuario_id, usuario_nome = _autor_atualizacao()
        dados = rg_core.aplicar_substituicao_lote(_db_path(), payload, _base_dir(), usuario_id, usuario_nome)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        get_db,
        "registro_geografico_lote_atualizado",
        entidade="registro_geografico",
        detalhes={
            "campo": dados.get("campo"),
            "atualizados": dados.get("atualizados"),
            "modo": payload.get("modo"),
        },
    )
    return jsonify(dados)


@bp.route("/registro-geografico/imprimir")
@login_required
def imprimir_quarteirao():
    try:
        localidade = request.args.get("localidade") or request.args.get("id_localidade")
        quarteiroes = request.args.getlist("quarteirao")
        incluir_mapa = request.args.get("mini_mapa") in {"1", "true", "sim", "on"}
        duplex_recto = request.args.get("duplex_recto") in {"1", "true", "sim", "on"}
        if not quarteiroes and request.args.get("quarteirao"):
            quarteiroes = [request.args.get("quarteirao")]
        dados_lista = [
            rg_core.quarteirao(_db_path(), localidade, quarteirao, _base_dir())
            for quarteirao in quarteiroes
            if str(quarteirao or "").strip()
        ]
        if not dados_lista:
            raise ValueError("Selecione ao menos um quarteirao.")
    except ValueError as exc:
        return render_template("500.html", erro=str(exc)), 400
    return render_template(
        "registro_geografico_impressao.html",
        dados_lista=dados_lista,
        dados=dados_lista[0],
        auto_print=True,
        incluir_mapa=incluir_mapa,
        duplex_recto=duplex_recto,
    )


@bp.route("/api/registro-geografico/<int:id_imovel>")
@login_required
def api_obter(id_imovel):
    registro = rg_core.obter(_db_path(), id_imovel, _base_dir())
    if not registro:
        return jsonify({"erro": "Imovel nao encontrado."}), 404
    return jsonify(registro)


@bp.route("/api/registro-geografico/<int:id_imovel>", methods=["POST"])
@login_required
@nivel_min("operador")
def api_salvar(id_imovel):
    try:
        usuario_id, usuario_nome = _autor_atualizacao()
        registro = rg_core.salvar(
            _db_path(), id_imovel, request.get_json(silent=True) or {}, _base_dir(), usuario_id, usuario_nome
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        get_db,
        "registro_geografico_atualizado",
        entidade="registro_geografico",
        entidade_id=id_imovel,
        detalhes={"localidade": registro.get("localidade"), "quarteirao": registro.get("quarteirao")},
    )
    return jsonify({"ok": True, "registro": registro})


@bp.route("/api/registro-geografico/<int:id_imovel>", methods=["DELETE"])
@login_required
@nivel_min("operador")
def api_excluir(id_imovel):
    try:
        rg_core.excluir(_db_path(), id_imovel, _base_dir())
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        get_db,
        "registro_geografico_excluido",
        entidade="registro_geografico",
        entidade_id=id_imovel,
    )
    return jsonify({"ok": True})


def _filtros():
    return {
        "busca": request.args.get("busca", ""),
        "localidade": request.args.getlist("localidade") or request.args.get("localidade", ""),
    "quarteirao": request.args.getlist("quarteirao") or request.args.get("quarteirao", ""),
        "tipo": request.args.get("tipo", ""),
        "atualizacao": request.args.get("atualizacao", ""),
        "agente": request.args.get("agente", ""),
    }
