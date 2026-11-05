from flask import Blueprint, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import bri as bri_core
from app_core import utils as utils_core


bp = Blueprint("bri", __name__)
login_required = auth_core.login_required


@bp.route("/bri")
@login_required
def page():
    return render_template(
        "bri.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(365)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        localidades=bri_core.localidades(bh.db_target()),
        agentes=bh.catalogo_agentes(bri_core.agentes(bh.db_target())),
    )


@bp.route("/api/bri")
@login_required
def api_resumo():
    return jsonify(bri_core.resumo(bh.db_target(), _filtros()))


@bp.route("/api/bri/listar")
@login_required
def api_listar():
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    return jsonify(bri_core.listar(bh.db_target(), filtros))


@bp.route("/api/bri/exportar")
@login_required
def exportar():
    from app_core.listagem_operacional import exportar_csv
    filtros = _filtros()
    filtros["busca"] = request.args.get("busca", "")
    dados = bri_core.listar(bh.db_target(), filtros, completo=True)
    campos = [["data", "Data"], ["hora", "Hora"], ["sispncd", "SISPNCD"], ["agentes", "Agentes"],
              ["destino_tratamento", "Destino"], ["local_tratamento", "Local de tratamento"], ["codigo_pe", "PE"],
              ["localidade", "Localidade"], ["quarteirao", "Quarteirão"], ["logradouro", "Logradouro"], ["numero", "Número"],
              ["numero_ovitrampa", "Ovitrampa"], ["quantidade_carga", "Carga"], ["tratou_imovel_extra", "Tratou imóvel adicional"],
              ["qual_imovel_extra", "Imóvel adicional"], ["depositos_tratados_extra", "Depósitos adicionais"],
              ["quantidade_carga_extra", "Carga adicional"], ["origem_estrutura", "Origem"]]
    return exportar_csv(dados["registros"], campos, "bri", bh.db_target(), bh.usuario_atual() or {})


def _filtros():
    return {
        "pagina": request.args.get("pagina", ""),
        "por_pagina": request.args.get("por_pagina", ""),
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "agente": request.args.get("agente", ""),
        "destino": request.args.get("destino", ""),
        "extra": request.args.get("extra", ""),
        "origem": request.args.get("origem", ""),
    }
