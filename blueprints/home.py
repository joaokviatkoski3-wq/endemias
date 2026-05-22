from flask import Blueprint, render_template

from app_core import blueprint_helpers as bh
from app_core import utils as utils_core
from app_core.auth import login_required


bp = Blueprint("home", __name__)


@bp.route("/")
@login_required
def page():
    conn = bh.get_db()
    try:
        ano_ini = utils_core.data_ano()
        kpis = {
            "visitas_hoje": conn.execute(
                "SELECT COUNT(*) FROM visitas WHERE data=?",
                (utils_core.hoje(),),
            ).fetchone()[0],
            "visitas_ano": conn.execute(
                "SELECT COUNT(*) FROM visitas WHERE data>=?",
                (ano_ini,),
            ).fetchone()[0],
            "focos_pendentes": conn.execute(
                "SELECT COUNT(*) FROM focos_positivos "
                "WHERE status_notificacao='pendente' AND gera_notificacao=1"
            ).fetchone()[0],
            "agentes_ativos": conn.execute(
                "SELECT COUNT(DISTINCT id_agente) FROM visita_agentes va "
                "JOIN visitas v ON v.id_visita=va.id_visita WHERE v.data>=?",
                (utils_core.data_n_dias(30),),
            ).fetchone()[0],
            "coletas_total": conn.execute("SELECT COUNT(*) FROM coletas").fetchone()[0],
            "positivos_aeg": conn.execute(
                "SELECT COUNT(*) FROM resultados_laboratorio "
                "WHERE aegypt_larvas>0 OR aegypt_pupas>0 "
                "OR aegypt_exuvias>0 OR aegypt_adulto>0"
            ).fetchone()[0],
        }
        atividade = conn.execute(
            "SELECT data, COUNT(*) as total FROM visitas WHERE data>=? "
            "GROUP BY data ORDER BY data DESC LIMIT 14",
            (utils_core.data_n_dias(14),),
        ).fetchall()
        dist_tipo = conn.execute(
            "SELECT tipo, COUNT(*) as total FROM visitas WHERE data>=? "
            "GROUP BY tipo ORDER BY total DESC",
            (ano_ini,),
        ).fetchall()
        focos_rec = conn.execute(
            """
            SELECT f.*, l.nome as localidade_nome FROM focos_positivos f
            LEFT JOIN localidades l ON l.id_localidade=f.id_localidade
            WHERE f.gera_notificacao=1 ORDER BY f.processado_em DESC LIMIT 5
            """
        ).fetchall()
    finally:
        conn.close()
    return render_template(
        "home.html",
        kpis=kpis,
        atividade=[dict(r) for r in atividade],
        dist_tipo=[dict(r) for r in dist_tipo],
        focos_recentes=[dict(r) for r in focos_rec],
    )
