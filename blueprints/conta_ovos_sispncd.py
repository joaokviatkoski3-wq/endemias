from datetime import date

from flask import Blueprint, jsonify, render_template, request

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import sispncd


bp = Blueprint("conta_ovos_sispncd", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


def _json_error(exc, status=400):
    return jsonify({"erro": str(exc)}), status


@bp.route("/conta-ovos-sispncd")
@login_required
def page():
    today = date.today()
    default_ano, default_semana = sispncd.epidemiological_week_for_date(today)
    default_conta_ovos = sispncd.get_default_conta_ovos(bh.db_path())
    localidades = bh.q("SELECT id_localidade, nome FROM localidades ORDER BY nome")
    return render_template(
        "conta_ovos_sispncd.html",
        localidades=localidades,
        default_conta_ovos=default_conta_ovos,
        default_semana=default_semana,
        default_ano=default_ano,
    )


@bp.route("/api/conta-ovos")
@login_required
def api_conta_ovos():
    try:
        result = sispncd.conta_ovos(
            bh.db_path(),
            request.args.get("data"),
            request.args.get("quarteirao"),
            id_localidade=request.args.get("localidade"),
        )
    except sispncd.ValidationError as exc:
        return _json_error(exc)
    return jsonify(result)


@bp.route("/api/sispncd/pesquisar")
@login_required
def api_sispncd_pesquisar():
    try:
        result = sispncd.sispncd(
            bh.db_path(),
            request.args.get("ano"),
            request.args.get("semana") or request.args.get("semana_epidemiologica"),
            request.args.getlist("tipo") or request.args.getlist("tipos_trabalho"),
            id_localidade=request.args.get("localidade"),
        )
    except sispncd.ValidationError as exc:
        return _json_error(exc)
    return jsonify(result)


@bp.route("/api/conta-ovos-sispncd/pendencias")
@login_required
def api_pendencias_envio():
    return jsonify(sispncd.pendencias_envio(bh.db_path()))


@bp.route("/api/sispncd/salvar", methods=["POST"])
@login_required
@nivel_min("operador")
def api_sispncd_salvar():
    data = request.json or {}
    try:
        result = sispncd.salvar_sispncd(
            bh.db_path(),
            data.get("ano"),
            data.get("semana") or data.get("semana_epidemiologica"),
            data.get("tipo") or data.get("tipos_trabalho"),
            data.get("codigo") or data.get("sispncd"),
            id_localidade=data.get("localidade"),
        )
    except sispncd.ValidationError as exc:
        return _json_error(exc)
    audit.registrar_evento(
        bh.get_db,
        "sispncd_salvo",
        entidade="visitas",
        detalhes={
            "ano": data.get("ano"),
            "semana": data.get("semana") or data.get("semana_epidemiologica"),
            "tipo": data.get("tipo") or data.get("tipos_trabalho"),
            "codigo": result.get("codigo"),
            "localidade": data.get("localidade"),
            "atualizados": result.get("atualizados"),
        },
    )
    return jsonify(result)


@bp.route("/api/conta-ovos/salvar-status", methods=["POST"])
@login_required
@nivel_min("admin")
def api_conta_ovos_salvar_status():
    data = request.json or {}
    try:
        result = sispncd.salvar_status_conta_ovos(
            bh.db_path(),
            data.get("data"),
            data.get("quarteirao"),
            id_localidade=data.get("localidade"),
        )
    except sispncd.ValidationError as exc:
        return _json_error(exc)
    audit.registrar_evento(
        bh.get_db,
        "conta_ovos_status_salvo",
        entidade="visitas",
        detalhes={
            "data": result.get("data"),
            "quarteirao": result.get("quarteirao"),
            "localidade": data.get("localidade"),
            "atualizados": result.get("atualizados"),
        },
    )
    return jsonify(result)
