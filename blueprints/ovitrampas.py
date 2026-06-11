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
    return render_template("ovitrampas.html", distritos=ovitrampas_core.distritos(_db_path()))


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


def _filtros():
    return {
        "ano": request.args.get("ano", ""),
        "semana": request.args.get("semana", ""),
        "distrito": request.args.get("distrito", ""),
        "positivas": request.args.get("positivas", ""),
    }
