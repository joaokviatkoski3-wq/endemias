import logging

from flask import Blueprint, jsonify, render_template, request

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import dashboard as dashboard_core
from app_core import laboratorio as laboratorio_core
from app_core import producao_operacional
from app_core import utils as utils_core
from app_core import visitas as visitas_core


bp = Blueprint("consultas", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(90)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        tipos_sel=request.args.getlist("tipo"),
        locs_sel=request.args.getlist("localidade"),
        ags_sel=request.args.getlist("agente"),
    )


@bp.route("/laboratorio")
@login_required
def laboratorio():
    return render_template(
        "laboratorio.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(90)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
    )


@bp.route("/visitas")
@login_required
def visitas():
    return render_template(
        "visitas.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(7)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        opcoes=visitas_core.filter_options(bh.db_target()),
    )


@bp.route("/api/dashboard")
@login_required
def api_dashboard():
    try:
        return jsonify(
            dashboard_core.integrado(bh.db_target(), request.args)
        )
    except Exception:
        logging.exception("Erro em api_dashboard")
        return jsonify(
            {"erro": "Erro interno. Verifique endemias.log"}
        ), 500


@bp.route("/api/producao-operacional")
@login_required
def api_producao_operacional():
    try:
        return jsonify(
            producao_operacional.resumo(
                bh.db_target(),
                request.args,
            )
        )
    except Exception:
        logging.exception("Erro em api_producao_operacional")
        return jsonify(
            {"erro": "Erro interno. Verifique endemias.log"}
        ), 500


@bp.route("/api/laboratorio")
@login_required
def api_laboratorio():
    try:
        pagina = bh.request_int_arg("pagina", 1, minimo=1)
        por_pagina = bh.request_int_arg(
            "por_pagina",
            50,
            minimo=1,
            maximo=500,
        )
        return jsonify(
            laboratorio_core.listar(
                bh.db_target(),
                request.args,
                pagina=pagina,
                por_pagina=por_pagina,
            )
        )
    except Exception:
        logging.exception("Erro em api_laboratorio")
        return jsonify(
            {"erro": "Erro interno. Verifique endemias.log"}
        ), 500


@bp.route("/api/visitas")
@login_required
def api_visitas():
    try:
        pagina = bh.request_int_arg("pagina", 1, minimo=1)
        por_pagina = bh.request_int_arg(
            "por_pagina",
            30,
            minimo=1,
            maximo=200,
        )
        return jsonify(
            visitas_core.listar(
                bh.db_target(),
                request.args,
                pagina=pagina,
                por_pagina=por_pagina,
            )
        )
    except Exception:
        logging.exception("Erro em api_visitas")
        return jsonify(
            {"erro": "Erro interno. Verifique endemias.log"}
        ), 500


@bp.route("/api/visitas/<id_visita>")
@login_required
def api_visita_detalhe(id_visita):
    try:
        return jsonify(
            visitas_core.detalhar(bh.db_target(), id_visita)
        )
    except visitas_core.VisitaNaoEncontrada as exc:
        return jsonify({"erro": str(exc)}), 404
    except Exception:
        logging.exception("Erro em api_visita_detalhe")
        return jsonify(
            {"erro": "Erro interno. Verifique endemias.log"}
        ), 500


@bp.route("/api/visitas/<id_visita>/editar", methods=["POST"])
@login_required
@nivel_min("operador")
def api_visita_editar(id_visita):
    dados = request.get_json(silent=True) or {}
    try:
        resultado = visitas_core.editar(
            bh.db_target(),
            id_visita,
            dados,
        )
        audit.registrar_evento(
            bh.get_db,
            "visita_editada",
            entidade="visitas",
            entidade_id=id_visita,
            detalhes=resultado,
        )
        return jsonify({"ok": True})
    except visitas_core.VisitaNaoEncontrada as exc:
        return jsonify({"erro": str(exc)}), 404
    except (
        visitas_core.VisitaInvalida,
        visitas_core.ColetaComResultado,
    ) as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        logging.exception("Erro em api_visita_editar")
        return jsonify(
            {"erro": "Erro interno. Verifique endemias.log"}
        ), 500
