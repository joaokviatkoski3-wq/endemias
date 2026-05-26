from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import audit
from app_core import auth as auth_core
from app_core import db as db_core
from app_core import pontos_estrategicos as pe_core


bp = Blueprint("pontos_estrategicos", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


def get_db():
    return db_core.connect(_db_path())


def q1(sql, params=()):
    return db_core.query_one(_db_path(), sql, params)


def usuario_atual():
    return auth_core.usuario_atual(q1)


def nivel_min(nivel):
    return auth_core.nivel_min(nivel, usuario_atual)


@bp.route("/pontos-estrategicos")
@login_required
def page():
    return render_template("pontos_estrategicos.html", opcoes=pe_core.opcoes(_db_path()))


@bp.route("/api/pontos-estrategicos")
@login_required
def api_listar():
    return jsonify(pe_core.listar(_db_path(), _filtros()))


@bp.route("/api/pontos-estrategicos/opcoes")
@login_required
def api_opcoes():
    return jsonify(pe_core.opcoes(_db_path()))


@bp.route("/api/pontos-estrategicos/<int:id_pe>")
@login_required
def api_obter(id_pe):
    registro = pe_core.obter(_db_path(), id_pe)
    if not registro:
        return jsonify({"erro": "Ponto estrategico nao encontrado."}), 404
    return jsonify(registro)


@bp.route("/api/pontos-estrategicos", methods=["POST"])
@login_required
@nivel_min("operador")
def api_criar():
    payload = request.get_json(silent=True) or {}
    if not _payload_valido(payload):
        return jsonify({"erro": "Informe ao menos o nome/local do PE."}), 400
    criado = pe_core.salvar(_db_path(), payload)
    audit.registrar_evento(
        get_db,
        "pe_criado",
        entidade="pontos_estrategicos",
        detalhes={"nome": payload.get("nome"), "localidade": payload.get("localidade")},
    )
    return jsonify({"ok": bool(criado)})


@bp.route("/api/pontos-estrategicos/<int:id_pe>", methods=["POST"])
@login_required
@nivel_min("operador")
def api_atualizar(id_pe):
    payload = request.get_json(silent=True) or {}
    if not _payload_valido(payload):
        return jsonify({"erro": "Informe ao menos o nome/local do PE."}), 400
    atualizado = pe_core.salvar(_db_path(), payload, id_pe=id_pe)
    if not atualizado:
        return jsonify({"erro": "Ponto estrategico nao encontrado."}), 404
    audit.registrar_evento(
        get_db,
        "pe_atualizado",
        entidade="pontos_estrategicos",
        entidade_id=id_pe,
        detalhes={"nome": payload.get("nome"), "localidade": payload.get("localidade")},
    )
    return jsonify({"ok": True})


@bp.route("/api/pontos-estrategicos/<int:id_pe>/situacao", methods=["POST"])
@login_required
@nivel_min("operador")
def api_situacao(id_pe):
    payload = request.get_json(silent=True) or {}
    situacao = int(payload.get("situacao", 1))
    if situacao not in (0, 1):
        return jsonify({"erro": "Situacao invalida."}), 400
    atualizado = pe_core.definir_situacao(_db_path(), id_pe, situacao)
    if not atualizado:
        return jsonify({"erro": "Ponto estrategico nao encontrado."}), 404
    audit.registrar_evento(
        get_db,
        "pe_situacao",
        entidade="pontos_estrategicos",
        entidade_id=id_pe,
        detalhes={"situacao": situacao},
    )
    return jsonify({"ok": True})


def _filtros():
    return {
        "situacao": request.args.get("situacao", ""),
        "localidade": request.args.get("localidade", ""),
        "tipo": request.args.get("tipo", ""),
        "busca": request.args.get("busca", "").strip(),
    }


def _payload_valido(payload):
    return bool(str(payload.get("nome") or "").strip())
