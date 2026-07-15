from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import audit
from app_core import blueprint_helpers as bh
from app_core import meteorologia as meteorologia_core
from app_core.auth import login_required


bp = Blueprint("meteorologia", __name__)
nivel_min = bh.nivel_min


@bp.route("/meteorologia")
@login_required
def page():
    painel = meteorologia_core.obter_painel(current_app.config["DB_PATH"], limite=30)
    return render_template("meteorologia.html", painel=painel)


@bp.route("/api/meteorologia/sincronizar", methods=["POST"])
@login_required
@nivel_min("admin")
def sincronizar():
    dados = request.get_json(silent=True) or {}
    try:
        dias = max(1, min(int(dados.get("dias") or 7), 90))
    except (TypeError, ValueError):
        return jsonify({"erro": "Quantidade de dias invalida."}), 400

    try:
        resultado = meteorologia_core.sincronizar(current_app.config["DB_PATH"], dias=dias)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 502

    audit.registrar_evento(
        bh.get_db,
        "meteorologia.sincronizar",
        entidade="meteorologia",
        entidade_id=resultado["sincronizacao_id"],
        detalhes=resultado,
    )
    return jsonify(resultado)
