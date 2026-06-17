import logging

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from app_core import agentes as agentes_core
from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import utils as utils_core


bp = Blueprint("controle_pessoal", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


def _invalidate_globals():
    fn = current_app.extensions.get("invalidar_cache_globals")
    if fn:
        fn()


@bp.route("/admin/agentes")
@login_required
@nivel_min("admin")
def page():
    filtros = {
        "status": request.args.get("status", "ativos"),
        "busca": request.args.get("busca", ""),
    }
    agentes = agentes_core.listar(current_app.config["DB_PATH"], filtros)
    return render_template(
        "admin_agentes.html",
        agentes=agentes,
        filtros=filtros,
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(30)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
    )


@bp.route("/admin/agentes/criar", methods=["POST"])
@login_required
@nivel_min("admin")
def criar():
    dados = request.form.to_dict()
    try:
        novo_id = agentes_core.criar(current_app.config["DB_PATH"], dados)
        _invalidate_globals()
        audit.registrar_evento(
            bh.get_db,
            "agente_criado",
            entidade="agentes",
            entidade_id=novo_id,
            detalhes={"nome": dados.get("nome") or dados.get("nome_completo"), "matricula": dados.get("matricula")},
        )
    except Exception as exc:
        logging.exception("Erro ao criar agente")
        filtros = {"status": "todos", "busca": ""}
        return render_template(
            "admin_agentes.html",
            agentes=agentes_core.listar(current_app.config["DB_PATH"], filtros),
            filtros=filtros,
            d_ini=utils_core.data_n_dias(30),
            d_fim=utils_core.hoje(),
            erro=str(exc),
        ), 400
    return redirect(url_for("controle_pessoal.page", status="todos"))


@bp.route("/admin/agentes/<int:id_agente>/editar", methods=["POST"])
@login_required
@nivel_min("admin")
def editar(id_agente):
    campo = request.form.get("campo", "")
    valor = request.form.get("valor", "")
    try:
        anterior, novo = agentes_core.atualizar_campo(current_app.config["DB_PATH"], id_agente, campo, valor)
        _invalidate_globals()
        audit.registrar_evento(
            bh.get_db,
            "agente_editado",
            entidade="agentes",
            entidade_id=id_agente,
            detalhes={
                "nome": anterior.get("nome"),
                "campo": campo,
                "valor_antigo": anterior.get(campo),
                "valor_novo": novo,
            },
        )
        return jsonify({"ok": True})
    except Exception as exc:
        logging.exception("Erro ao editar agente")
        return jsonify({"erro": str(exc)}), 400
