from flask import Blueprint, render_template

from app_core import auth as auth_core


bp = Blueprint("esporotricose", __name__)
login_required = auth_core.login_required


@bp.route("/esporotricose")
@login_required
def page():
    return render_template("esporotricose.html")
