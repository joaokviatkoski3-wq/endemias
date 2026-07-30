from flask import Blueprint, current_app, render_template

from app_core import audit
from app_core import backup as backup_core
from app_core import blueprint_helpers as bh
from app_core import db as db_core
from app_core import import_history
from app_core import meteorologia as meteorologia_core
from app_core import utils as utils_core
from app_core.auth import login_required


bp = Blueprint("home", __name__)


@bp.route("/")
@login_required
def page():
    usuario = bh.usuario_atual()
    is_admin = (usuario or {}).get("nivel") == "admin"
    conn = bh.get_db()
    try:
        ano_ini = utils_core.data_ano()
        hoje = utils_core.hoje()
        limite_foco_atrasado = utils_core.data_n_dias(7)
        kpis = {
            "visitas_hoje": conn.execute(
                "SELECT COUNT(*) FROM visitas WHERE data=?",
                (hoje,),
            ).fetchone()[0],
            "visitas_ano": conn.execute(
                "SELECT COUNT(*) FROM visitas WHERE data>=?",
                (ano_ini,),
            ).fetchone()[0],
            "focos_pendentes": conn.execute(
                "SELECT COUNT(*) FROM focos_positivos "
                "WHERE status_notificacao='pendente' AND gera_notificacao=1"
            ).fetchone()[0],
            "focos_atrasados": conn.execute(
                """
                SELECT COUNT(*) FROM focos_positivos
                 WHERE status_notificacao='pendente'
                   AND gera_notificacao=1
                   AND substr(
                       CAST(COALESCE(processado_em, data) AS TEXT),1,10
                   ) <= ?
                """,
                (limite_foco_atrasado,),
            ).fetchone()[0],
            "conta_ovos_pendente": conn.execute(
                "SELECT COUNT(*) FROM visitas WHERE tipo='TBO' AND COALESCE(CONTAOVOS_STATUS,0)=0"
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
            """
            SELECT data, total
              FROM (
                    SELECT data, COUNT(*) as total
                      FROM visitas
                     WHERE data>=?
                     GROUP BY data
                     ORDER BY data DESC
                     LIMIT 14
                   )
             ORDER BY data
            """,
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
            WHERE f.gera_notificacao=1 ORDER BY f.processado_em DESC LIMIT 6
            """
        ).fetchall()
        agenda = conn.execute(
            """
            SELECT titulo, tipo, data_inicio, data_fim
              FROM agenda_eventos
             WHERE substr(CAST(data_inicio AS TEXT),1,10) >= ?
             ORDER BY data_inicio, id_evento
             LIMIT 5
            """,
            (hoje,),
        ).fetchall()
        meteorologia = conn.execute(
            """
            SELECT data, temperatura_min, temperatura_max, precipitacao, provisorio
              FROM meteorologia_resumos_diarios
             ORDER BY data DESC, id DESC
             LIMIT 1
            """
        ).fetchone()
        clima_atual = conn.execute(
            """
            SELECT observado_em, temperatura, sensacao_termica, umidade
              FROM meteorologia_condicoes_atuais
             ORDER BY observado_em DESC, id DESC
             LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()

    admin_info = None
    if is_admin:
        backups = backup_core.listar_backups(current_app.config["BACKUP_DIR"], limite=3)
        admin_info = {
            "backups": backups,
            "importacoes": import_history.listar_importacoes_recentes(bh.get_db, limite=4),
            "eventos": audit.listar_eventos(bh.get_db, limite=5),
        }

    clima_trabalho = meteorologia_core.resumo_trabalho(
        bh.db_target(), dias_uteis=2
    )
    clima_alerta = next(
        (day for day in clima_trabalho["dias"] if day["nivel"] in {"atencao", "critico"}),
        None,
    )

    atividade_lista = [db_core.serialize_row(r) for r in atividade]
    atividade_max = max((r["total"] for r in atividade_lista), default=0)
    return render_template(
        "home.html",
        kpis=kpis,
        atividade=atividade_lista,
        atividade_max=atividade_max,
        dist_tipo=[db_core.serialize_row(r) for r in dist_tipo],
        focos_recentes=[db_core.serialize_row(r) for r in focos_rec],
        agenda_proxima=[db_core.serialize_row(r) for r in agenda],
        meteorologia=(
            db_core.serialize_row(meteorologia) if meteorologia else None
        ),
        clima_atual=(
            db_core.serialize_row(clima_atual) if clima_atual else None
        ),
        clima_alerta=clima_alerta,
        admin_info=admin_info,
    )
