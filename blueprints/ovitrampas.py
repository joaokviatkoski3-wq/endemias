import os
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import audit
from app_core import auth as auth_core
from app_core import ovitrampas as ovitrampas_core


bp = Blueprint("ovitrampas", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


def get_db():
    return ovitrampas_core.db_core.connect(_db_path())


def _q1(sql, params=()):
    conn = get_db()
    try:
        row = conn.execute(sql, params).fetchone()
        return row
    finally:
        conn.close()


def _usuario_atual():
    return auth_core.usuario_atual(_q1)


def nivel_min(nivel):
    return auth_core.nivel_min(nivel, _usuario_atual)


@bp.route("/ovitrampas")
@login_required
def page():
    return render_template(
        "ovitrampas.html",
        distritos=ovitrampas_core.distritos(_db_path()),
        agentes=ovitrampas_core.agentes(_db_path()),
    )


@bp.route("/ovitrampas/calendario/imprimir")
@login_required
def imprimir_calendario():
    dados = ovitrampas_core.calendario_impressao(_db_path(), request.args.get("ano"))
    return render_template("ovitrampas_calendario_impressao.html", **dados)


@bp.route("/api/ovitrampas")
@login_required
def api_resumo():
    return jsonify(ovitrampas_core.resumo(_db_path(), _filtros()))


@bp.route("/api/ovitrampas/listar")
@login_required
def api_listar():
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    return jsonify(ovitrampas_core.listar(_db_path(), filtros, limite=request.args.get("limite") or 500))


@bp.route("/api/ovitrampas/armadilhas")
@login_required
def api_armadilhas():
    filtros = {"distrito": request.args.get("distrito", ""), "busca": request.args.get("busca", "")}
    return jsonify(ovitrampas_core.listar_armadilhas(_db_path(), filtros, limite=request.args.get("limite") or 500))


@bp.route("/api/ovitrampas/monitoramento")
@login_required
def api_monitoramento():
    filtros = {
        "ano": request.args.get("ano", ""),
        "semana_ini": request.args.get("semana_ini", ""),
        "semana_fim": request.args.get("semana_fim", ""),
        "ultimas": request.args.get("ultimas", ""),
        "distrito": request.args.get("distrito", ""),
    }
    return jsonify(ovitrampas_core.monitoramento(_db_path(), filtros))


@bp.route("/api/ovitrampas/armadilhas/<path:ovitrampa_id>")
@login_required
def api_historico_armadilha(ovitrampa_id):
    data = ovitrampas_core.historico_armadilha(_db_path(), ovitrampa_id)
    if not data["armadilha"] and not data["leituras"]:
        return jsonify({"erro": "Ovitrampa nao encontrada."}), 404
    return jsonify(data)


@bp.route("/api/ovitrampas/calendario")
@login_required
def api_calendario():
    return jsonify(ovitrampas_core.calendario_dados(_db_path(), request.args.get("ano")))


@bp.route("/api/ovitrampas/calendario/grupos", methods=["POST"])
@login_required
@nivel_min("operador")
def api_calendario_grupo_criar():
    try:
        grupo = ovitrampas_core.salvar_grupo(_db_path(), request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "grupo": grupo}), 201


@bp.route("/api/ovitrampas/calendario/grupos/<int:id_grupo>", methods=["PUT", "DELETE"])
@login_required
@nivel_min("operador")
def api_calendario_grupo(id_grupo):
    try:
        if request.method == "DELETE":
            ovitrampas_core.excluir_grupo(_db_path(), id_grupo)
            return jsonify({"ok": True})
        grupo = ovitrampas_core.salvar_grupo(_db_path(), request.get_json(silent=True) or {}, id_grupo=id_grupo)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "grupo": grupo})


@bp.route("/api/ovitrampas/calendario/eventos", methods=["POST"])
@login_required
@nivel_min("operador")
def api_calendario_evento_criar():
    usuario = _usuario_atual() or {}
    usuario_nome = usuario["nome"] if usuario and "nome" in usuario.keys() else "sistema"
    try:
        evento = ovitrampas_core.salvar_evento_calendario(
            _db_path(),
            request.get_json(silent=True) or {},
            usuario_nome=usuario_nome,
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(get_db, "ovitrampas_calendario_criou", entidade="ovitrampas", entidade_id=evento["id_evento"], detalhes=evento)
    return jsonify({"ok": True, "evento": evento}), 201


@bp.route("/api/ovitrampas/calendario/eventos/<int:id_evento>", methods=["PUT", "DELETE"])
@login_required
@nivel_min("operador")
def api_calendario_evento(id_evento):
    try:
        if request.method == "DELETE":
            ovitrampas_core.excluir_evento_calendario(_db_path(), id_evento)
            audit.registrar_evento(get_db, "ovitrampas_calendario_excluiu", entidade="ovitrampas", entidade_id=id_evento)
            return jsonify({"ok": True})
        usuario = _usuario_atual() or {}
        usuario_nome = usuario["nome"] if usuario and "nome" in usuario.keys() else "sistema"
        evento = ovitrampas_core.salvar_evento_calendario(
            _db_path(),
            request.get_json(silent=True) or {},
            usuario_nome=usuario_nome,
            id_evento=id_evento,
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(get_db, "ovitrampas_calendario_atualizou", entidade="ovitrampas", entidade_id=id_evento, detalhes=evento)
    return jsonify({"ok": True, "evento": evento})


@bp.route("/api/ovitrampas/leituras/<id_leitura>", methods=["PUT"])
@login_required
@nivel_min("operador")
def api_atualizar_leitura(id_leitura):
    try:
        row = ovitrampas_core.atualizar_leitura(_db_path(), id_leitura, request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400

    audit.registrar_evento(
        get_db,
        "ovitrampas_leitura_atualizada",
        entidade="ovitrampas",
        entidade_id=id_leitura,
        detalhes={"id_laboratorista": row.get("id_laboratorista"), "data_leitura": row.get("data_leitura")},
    )
    return jsonify({"ok": True, "registro": row})


@bp.route("/api/ovitrampas/importar", methods=["POST"])
@login_required
@nivel_min("admin")
def api_importar():
    arquivos = request.files.getlist("arquivos")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo CSV enviado."}), 400

    total = {"arquivos": 0, "linhas": 0, "inseridos": 0, "duplicados": 0, "erros": []}
    with tempfile.TemporaryDirectory() as tmpdir:
        for arquivo in arquivos:
            nome = os.path.basename(arquivo.filename or "")
            if not nome.lower().endswith(".csv"):
                total["erros"].append(f"{nome or 'arquivo'}: formato inválido")
                continue
            destino = Path(tmpdir) / nome
            arquivo.save(destino)
            result = ovitrampas_core.importar_csv(_db_path(), destino)
            total["arquivos"] += 1
            total["linhas"] += result["linhas"]
            total["inseridos"] += result["inseridos"]
            total["duplicados"] += result["duplicados"]
            total["erros"].extend(f"{nome}: {erro}" for erro in result["erros"])

    audit.registrar_evento(
        get_db,
        "ovitrampas_importacao",
        entidade="ovitrampas",
        detalhes=total,
    )
    return jsonify({"ok": not total["erros"], **total})


@bp.route("/api/ovitrampas/armadilhas/importar", methods=["POST"])
@login_required
@nivel_min("admin")
def api_importar_armadilhas():
    arquivo = request.files.get("arquivo")
    if not arquivo:
        return jsonify({"erro": "Nenhum CSV enviado."}), 400
    nome = os.path.basename(arquivo.filename or "")
    if not nome.lower().endswith(".csv"):
        return jsonify({"erro": "Envie um arquivo CSV do cadastro de ovitrampas."}), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        destino = Path(tmpdir) / nome
        arquivo.save(destino)
        result = ovitrampas_core.importar_armadilhas_csv(_db_path(), destino)

    audit.registrar_evento(
        get_db,
        "ovitrampas_armadilhas_importacao",
        entidade="ovitrampas",
        detalhes=result,
    )
    return jsonify({"ok": not result["erros"], **result})


def _filtros():
    return {
        "ano": request.args.get("ano", ""),
        "semana": request.args.get("semana", ""),
        "distrito": request.args.get("distrito", ""),
        "positivas": request.args.get("positivas", ""),
    }
