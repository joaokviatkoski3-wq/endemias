from flask import Blueprint, render_template, request

from app_core import auth as auth_core
from app_core import utils as utils_core


bp = Blueprint("consultas", __name__)
login_required = auth_core.login_required


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
        tipos_sel=request.args.getlist("tipo"),
        locs_sel=request.args.getlist("localidade"),
        ags_sel=request.args.getlist("agente"),
    )
