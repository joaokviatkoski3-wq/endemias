from flask import Blueprint, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import recolhimentos as recolhimentos_core
from app_core import utils as utils_core


bp = Blueprint("recolhimentos", __name__)
login_required = auth_core.login_required


@bp.route("/recolhimentos")
@login_required
def page():
    return render_template(
        "recolhimentos.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(365)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        localidades=recolhimentos_core.localidades(bh.db_target()),
        agentes=bh.catalogo_agentes(recolhimentos_core.agentes(bh.db_target())),
    )


@bp.route("/api/recolhimentos")
@login_required
def api_resumo():
    filtros = _filtros()
    return jsonify(recolhimentos_core.resumo(bh.db_target(), filtros))


@bp.route("/api/recolhimentos/listar")
@login_required
def api_listar():
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    return jsonify(recolhimentos_core.listar(bh.db_target(), filtros))


@bp.route("/api/recolhimentos/exportar")
@login_required
def exportar():
    from app_core.listagem_operacional import exportar_csv
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    dados = recolhimentos_core.listar(bh.db_target(), filtros, completo=True)
    campos = [["data","Data"],["hora","Hora"],["localidade","Localidade"],["agentes","Agentes"],["pneu","Pneus"],["louca_sanitaria","Louça sanitária"],["tv","TV"],["parachoque","Parachoque"],["outros","Outros"],["total_materiais","Total de materiais"],["origem_estrutura","Origem"]]
    return exportar_csv(dados["registros"], campos, "recolhimentos", bh.db_target(), bh.usuario_atual() or {})


def _filtros():
    return {
        "pagina": request.args.get("pagina", ""),
        "por_pagina": request.args.get("por_pagina", ""),
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "agente": request.args.get("agente", ""),
        "origem": request.args.get("origem", ""),
    }
