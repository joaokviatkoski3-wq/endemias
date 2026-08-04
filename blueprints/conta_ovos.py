"""Central de consulta da integracao Conta Ovos.

As rotas deste blueprint sao deliberadamente somente leitura. Sincronizacao e
qualquer escrita remota continuam sendo fluxos supervisionados fora da web.
"""

from flask import Blueprint, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import contaovos_consultas


bp = Blueprint("conta_ovos", __name__)
login_required = auth_core.login_required


@bp.route("/conta-ovos")
@login_required
def page():
    return render_template("conta_ovos.html")


@bp.route("/api/conta-ovos/central/resumo")
@login_required
def api_resumo():
    try:
        return jsonify(contaovos_consultas.resumo(bh.db_target()))
    except contaovos_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503


@bp.route("/api/conta-ovos/central/contagens")
@login_required
def api_contagens():
    try:
        return jsonify(contaovos_consultas.listar_contagens(
            bh.db_target(), request.args, request.args.get("limite")
        ))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except contaovos_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503


@bp.route("/api/conta-ovos/central/ovitrampas")
@login_required
def api_ovitrampas():
    try:
        return jsonify(contaovos_consultas.listar_ovitrampas(
            bh.db_target(), request.args, request.args.get("limite")
        ))
    except contaovos_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503


@bp.route("/api/conta-ovos/central/ovitrampas/<path:ovitrampa_id>")
@login_required
def api_ovitrampa(ovitrampa_id):
    try:
        data = contaovos_consultas.detalhes_ovitrampa(bh.db_target(), ovitrampa_id)
    except contaovos_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503
    if not data["armadilha"] and not data["contagens"]:
        return jsonify({"erro": "Ovitrampa nao encontrada no espelho local."}), 404
    return jsonify(data)
