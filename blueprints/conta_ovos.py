"""Central de consulta da integracao Conta Ovos.

As rotas deste blueprint sao deliberadamente somente leitura (GET). Nenhuma
delas chama a API remota durante a requisicao: todas leem exclusivamente o
espelho local ja sincronizado por processos supervisionados fora da web.
Sincronizacao e qualquer escrita remota continuam fora deste modulo.
"""

from flask import Blueprint, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import contaovos_consultas
from app_core import contaovos_ovitrampas_consultas as ovi_consultas


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


# ─────────────────────── Sub-area Ovitrampas (remoto) ───────────────────────

@bp.route("/api/conta-ovos/ovitrampas/resumo")
@login_required
def api_ovi_resumo():
    try:
        return jsonify(ovi_consultas.resumo_ovitrampas(bh.db_target()))
    except ovi_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503


@bp.route("/api/conta-ovos/ovitrampas/contagens")
@login_required
def api_ovi_contagens():
    try:
        return jsonify(ovi_consultas.listar_contagens_api(
            bh.db_target(), request.args, request.args.get("limite")
        ))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except ovi_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503


@bp.route("/api/conta-ovos/ovitrampas/monitoramento")
@login_required
def api_ovi_monitoramento():
    try:
        return jsonify(ovi_consultas.monitoramento_api(bh.db_target(), request.args))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except ovi_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503


@bp.route("/api/conta-ovos/ovitrampas/cadastro-remoto")
@login_required
def api_ovi_cadastro_remoto():
    try:
        return jsonify(ovi_consultas.listar_cadastro_remoto(
            bh.db_target(), request.args, request.args.get("limite")
        ))
    except ovi_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503


@bp.route("/api/conta-ovos/ovitrampas/cadastro-remoto/<path:ovitrampa_id_remoto>")
@login_required
def api_ovi_cadastro_remoto_detalhe(ovitrampa_id_remoto):
    try:
        data = ovi_consultas.detalhes_cadastro_remoto(bh.db_target(), ovitrampa_id_remoto)
    except ovi_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503
    if not data:
        return jsonify({"erro": "Ovitrampa nao encontrada no espelho remoto."}), 404
    return jsonify(data)


@bp.route("/api/conta-ovos/ovitrampas/mapa")
@login_required
def api_ovi_mapa():
    try:
        return jsonify(ovi_consultas.mapa_pontos(bh.db_target()))
    except ovi_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503


@bp.route("/api/conta-ovos/ovitrampas/sincronizacao")
@login_required
def api_ovi_sincronizacao():
    status = ovi_consultas.sincronizacao_status(bh.db_target())
    try:
        status["divergencias"] = ovi_consultas.divergencias(bh.db_target())
    except ovi_consultas.EspelhoContaOvosIndisponivel as exc:
        return jsonify({"erro": str(exc)}), 503
    return jsonify(status)
