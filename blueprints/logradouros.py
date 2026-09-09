"""Tela administrativa do cadastro oficial de logradouros."""

import logging

from flask import Blueprint, jsonify, render_template, request

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import db as db_core
from app_core import logradouros as logradouros_core


bp = Blueprint("logradouros", __name__)
login_required = auth_core.login_required


def _target():
    return bh.db_target()


def _get_db():
    return db_core.connect(_target())


def _usuario_atual():
    return auth_core.usuario_atual(
        lambda sql, params=(): db_core.query_one(_target(), sql, params)
    )


def nivel_min(nivel):
    return auth_core.nivel_min(nivel, _usuario_atual)


@bp.route("/logradouros")
@login_required
def page():
    return render_template("logradouros.html")


@bp.route("/api/logradouros/resumo")
@login_required
def api_resumo():
    try:
        return jsonify(logradouros_core.resumo(_target()))
    except Exception:
        logging.exception("Erro ao carregar resumo de logradouros")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.route("/api/logradouros")
@login_required
def api_listar():
    try:
        return jsonify(
            logradouros_core.listar(
                _target(), request.args.get("busca", ""), request.args.get("limite", 300)
            )
        )
    except Exception:
        logging.exception("Erro ao listar logradouros")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.route("/api/logradouros/importar", methods=["POST"])
@login_required
@nivel_min("admin")
def api_importar():
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify({"erro": "Selecione o CSV oficial de logradouros."}), 400
    if not arquivo.filename.lower().endswith(".csv"):
        return jsonify({"erro": "Envie um arquivo CSV."}), 400
    try:
        result = logradouros_core.importar_csv(_target(), arquivo.read())
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        logging.exception("Erro ao importar logradouros")
        return jsonify({"erro": "Nao foi possivel importar o CSV."}), 500
    usuario = _usuario_atual() or {}
    audit.registrar_evento(
        _get_db,
        "logradouros_importados",
        entidade="logradouros_oficiais",
        detalhes={"arquivo": arquivo.filename, "usuario": usuario.get("nome"), **result},
    )
    return jsonify({"ok": True, **result})
