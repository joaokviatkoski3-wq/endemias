import logging
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import esporotricose as esporotricose_core
from app_core import producao_operacional
from app_core import utils as utils_core
from app_core import work_types


bp = Blueprint("relatorio_agente", __name__)
login_required = auth_core.login_required


def _get_db():
    return db_core.connect(current_app.config["DB_PATH"])


def _resumo_esporotricose_agente(nome, d_ini, d_fim):
    filtros = {"agente": nome, "d_ini": d_ini, "d_fim": d_fim}
    resumo = esporotricose_core.resumo(current_app.config["DB_PATH"], filtros)
    dashboard = esporotricose_core.dashboard(current_app.config["DB_PATH"], filtros)
    totais = resumo.get("totais", {})
    animais = resumo.get("animais", {})
    visitas = utils_core.safe_int(totais.get("visitas", 0))
    dias = utils_core.safe_int(totais.get("dias", 0))
    total_animais = utils_core.safe_int(animais.get("total", 0))
    com_feridas = utils_core.safe_int(animais.get("com_feridas", 0))

    return {
        "totais": {
            "visitas": visitas,
            "dias": dias,
            "media_dia": round(visitas / dias, 1) if dias else 0,
            "localidades": utils_core.safe_int(totais.get("localidades", 0)),
            "normais": utils_core.safe_int(totais.get("normais", 0)),
            "fechadas": utils_core.safe_int(totais.get("fechadas", 0)),
            "recusas": utils_core.safe_int(totais.get("recusas", 0)),
            "recuperadas": utils_core.safe_int(totais.get("recuperadas", 0)),
        },
        "animais": {
            "total": total_animais,
            "caes": utils_core.safe_int(animais.get("caes", 0)),
            "gatos": utils_core.safe_int(animais.get("gatos", 0)),
            "com_feridas": com_feridas,
            "taxa_feridas": round(com_feridas / total_animais * 100, 1) if total_animais else 0,
        },
        "dashboard": dashboard,
    }


def _resumo_producao_agente(nome, d_ini, d_fim):
    resumo = producao_operacional.resumo(
        current_app.config["DB_PATH"],
        {"agente": [nome], "d_ini": d_ini, "d_fim": d_fim},
    )
    atividades = resumo.get("por_atividade", [])
    total = utils_core.safe_int(resumo.get("totais", {}).get("registros_total", 0))
    for atividade in atividades:
        registros = utils_core.safe_int(atividade.get("registros", 0))
        atividade["percentual"] = round(registros / total * 100, 1) if total else 0
        atividade.get("extras", {}).pop("pendentes_sispncd", None)
    resumo["por_agente"] = [{"agente": nome, "registros": total}]
    resumo.setdefault("totais", {})["agentes"] = 1 if total else 0
    return resumo


def _obter_dados(nome, d_ini, d_fim):
    conn = _get_db()
    p = [nome, d_ini, d_fim]
    base_w = (
        "FROM visitas v "
        "JOIN visita_agentes va ON va.id_visita=v.id_visita "
        "JOIN agentes a ON a.id_agente=va.id_agente "
        "LEFT JOIN localidades l ON l.id_localidade=v.id_localidade "
        "WHERE a.nome=? AND v.data BETWEEN ? AND ?"
    )

    try:
        totais = conn.execute(f"""SELECT
            COUNT(DISTINCT v.id_visita) as total, COUNT(DISTINCT v.data) as dias,
            COUNT(DISTINCT v.quarteirao) as quarteiroes,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados
            {base_w}""", p).fetchone()

        por_tipo = conn.execute(f"""SELECT v.tipo,
            COUNT(DISTINCT v.id_visita) as total,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados
            {base_w} GROUP BY v.tipo ORDER BY total DESC""", p).fetchall()

        por_loc = conn.execute(
            f"SELECT l.nome as localidade, COUNT(DISTINCT v.id_visita) as total "
            f"{base_w} GROUP BY l.nome ORDER BY total DESC", p
        ).fetchall()

        por_dia = conn.execute(
            f"SELECT v.data, COUNT(DISTINCT v.id_visita) as total "
            f"{base_w} GROUP BY v.data ORDER BY v.data", p
        ).fetchall()

        evolucao = conn.execute(
            f"SELECT strftime('%Y-%m-%d',v.data,'weekday 0','-6 days') as semana, "
            f"COUNT(DISTINCT v.id_visita) as total {base_w} GROUP BY semana ORDER BY semana", p
        ).fetchall()

        dep = conn.execute("""
            SELECT SUM(d.inspecionado) as insp, SUM(d.eliminado) as elim, SUM(d.tratado) as trat
            FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
            JOIN agentes a ON a.id_agente=va.id_agente
            LEFT JOIN depositos_inspecionados d ON d.id_visita=v.id_visita
            WHERE a.nome=? AND v.data BETWEEN ? AND ?""", p).fetchone()

        col = conn.execute("""
            SELECT COUNT(DISTINCT c.id_coleta) as total,
                COUNT(DISTINCT CASE WHEN rl.aegypt_larvas>0 OR rl.aegypt_pupas>0
                    OR rl.aegypt_exuvias>0 OR rl.aegypt_adulto>0 THEN c.id_coleta END) as pos_aeg,
                COUNT(DISTINCT CASE WHEN rl.albopictus_larvas>0 OR rl.albopictus_pupas>0
                    THEN c.id_coleta END) as pos_alb
            FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
            JOIN agentes a ON a.id_agente=va.id_agente
            LEFT JOIN coletas c ON c.id_visita=v.id_visita
            LEFT JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
            WHERE a.nome=? AND v.data BETWEEN ? AND ?""", p).fetchone()

        tbo_raw = conn.execute("""
            SELECT
                CASE WHEN LOWER(sub.visita) IN ('normal','recuperado') THEN 'acessados'
                     ELSE 'nao_acessados' END as grupo,
                COUNT(*) as n, ROUND(AVG(dur),1) as media,
                ROUND(MIN(dur),1) as minimo, ROUND(MAX(dur),1) as maximo
            FROM (SELECT v.visita,
                  (julianday(v.data||' '||v.hora_fim)-julianday(v.data||' '||v.hora_inicio))*24*60 AS dur
                  FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
                  JOIN agentes a ON a.id_agente=va.id_agente
                  WHERE a.nome=? AND v.data BETWEEN ? AND ? AND v.tipo=?
                  AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL) sub
            WHERE dur BETWEEN 1 AND 240 GROUP BY grupo""",
            p + [work_types.primary_duration_work_type_code()],
        ).fetchall()

        por_periodo_raw = conn.execute(f"""SELECT
            CASE WHEN v.hora_inicio < '12:00' THEN 'manha' ELSE 'tarde' END as periodo,
            COUNT(DISTINCT v.id_visita) as total,
            COUNT(DISTINCT v.data) as dias_periodo
            {base_w} AND v.hora_inicio IS NOT NULL GROUP BY periodo""", p).fetchall()

        media_geral_raw = conn.execute("""
            SELECT
                AVG(total) as media_total,
                AVG(CASE WHEN dias > 0 THEN total * 1.0 / dias ELSE 0 END) as media_dia,
                AVG(normais) as media_normais,
                AVG(fechados) as media_fechados,
                AVG(recuperados) as media_recuperados,
                AVG(recusados) as media_recusados,
                COUNT(*) as num_agentes
            FROM (
                SELECT a.id_agente,
                    COUNT(DISTINCT v.id_visita) as total,
                    COUNT(DISTINCT v.data) as dias,
                    COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
                    COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
                    COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
                    COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados
                FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
                JOIN agentes a ON a.id_agente=va.id_agente
                WHERE v.data BETWEEN ? AND ? AND a.nome <> ?
                GROUP BY a.id_agente
            ) medias""", [d_ini, d_fim, nome]).fetchone()

        esporotricose_core.ensure_schema(conn)
        comparacao_esporo_raw = conn.execute("""
            SELECT
                AVG(visitas) as media_visitas,
                AVG(CASE WHEN dias > 0 THEN visitas * 1.0 / dias ELSE 0 END) as media_dia,
                AVG(animais) as media_animais,
                AVG(com_feridas) as media_feridas,
                AVG(fechadas) as media_fechadas,
                AVG(recusas) as media_recusas,
                COUNT(*) as num_agentes
            FROM (
                SELECT ag.id_agente,
                    COUNT(DISTINCT v.id_visita) AS visitas,
                    COUNT(DISTINCT v.data) AS dias,
                    COUNT(DISTINCT an.id_animal) AS animais,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(an.feridas,''))='sim' THEN an.id_animal END) AS com_feridas,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='fechado' THEN v.id_visita END) AS fechadas,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='recusa' THEN v.id_visita END) AS recusas
                FROM esporotricose_visitas v
                JOIN esporotricose_visita_agentes va ON va.id_visita=v.id_visita
                JOIN agentes ag ON ag.id_agente=va.id_agente
                LEFT JOIN esporotricose_animais an ON an.id_visita=v.id_visita
                WHERE v.data BETWEEN ? AND ? AND ag.nome <> ?
                GROUP BY ag.id_agente
            ) medias""", [d_ini, d_fim, nome]).fetchone()
    finally:
        conn.close()

    totais_d = dict(totais) if totais else {}
    dep_d = dict(dep) if dep else {}
    col_d = dict(col) if col else {}
    tv = utils_core.safe_int(totais_d.get("total", 0))
    dias = utils_core.safe_int(totais_d.get("dias", 0))
    tc = utils_core.safe_int(col_d.get("total", 0))
    ta = utils_core.safe_int(col_d.get("pos_aeg", 0))

    por_periodo = {}
    for r in por_periodo_raw:
        rd = dict(r)
        dias_p = utils_core.safe_int(rd.get("dias_periodo")) or 1
        por_periodo[rd["periodo"]] = {
            "total": utils_core.safe_int(rd.get("total", 0)),
            "media": round(utils_core.safe_int(rd.get("total", 0)) / dias_p, 1),
        }

    comparacao = {}
    if media_geral_raw:
        mg = dict(media_geral_raw)
        n_ag = utils_core.safe_int(mg.get("num_agentes"))
        comparacao = {
            "media_total": round(mg.get("media_total") or 0, 1),
            "media_dia": round(mg.get("media_dia") or 0, 1),
            "media_normais": round(mg.get("media_normais") or 0, 1),
            "media_fechados": round(mg.get("media_fechados") or 0, 1),
            "media_recuperados": round(mg.get("media_recuperados") or 0, 1),
            "media_recusados": round(mg.get("media_recusados") or 0, 1),
            "num_agentes": n_ag,
        }

    esporotricose = _resumo_esporotricose_agente(nome, d_ini, d_fim)
    producao = _resumo_producao_agente(nome, d_ini, d_fim)
    comparacao_esporotricose = {}
    if comparacao_esporo_raw:
        ce = dict(comparacao_esporo_raw)
        comparacao_esporotricose = {
            "media_visitas": round(ce.get("media_visitas") or 0, 1),
            "media_dia": round(ce.get("media_dia") or 0, 1),
            "media_animais": round(ce.get("media_animais") or 0, 1),
            "media_feridas": round(ce.get("media_feridas") or 0, 1),
            "media_fechadas": round(ce.get("media_fechadas") or 0, 1),
            "media_recusas": round(ce.get("media_recusas") or 0, 1),
            "num_agentes": utils_core.safe_int(ce.get("num_agentes")),
        }

    return {
        "agente": nome, "d_ini": d_ini, "d_fim": d_fim,
        "totais": totais_d,
        "por_tipo": [dict(r) for r in por_tipo],
        "por_loc": [dict(r) for r in por_loc],
        "por_dia": [dict(r) for r in por_dia],
        "evolucao": [dict(r) for r in evolucao],
        "dep": dep_d,
        "col": col_d,
        "tbo_por_grupo": {r["grupo"]: dict(r) for r in tbo_raw},
        "taxa_normal": round(utils_core.safe_int(totais_d.get("normais", 0)) / tv * 100, 1) if tv else 0,
        "media_dia": round(tv / dias, 1) if dias else 0,
        "por_periodo": por_periodo,
        "comparacao": comparacao,
        "producao_operacional": producao,
        "esporotricose": esporotricose,
        "comparacao_esporotricose": comparacao_esporotricose,
        "totais_api": {
            "total": tv, "dias": dias,
            "media_dia": round(tv / dias, 1) if dias else 0,
            "quarteiroes": utils_core.safe_int(totais_d.get("quarteiroes", 0)),
            "normais": utils_core.safe_int(totais_d.get("normais", 0)),
            "fechados": utils_core.safe_int(totais_d.get("fechados", 0)),
            "recuperados": utils_core.safe_int(totais_d.get("recuperados", 0)),
            "recusados": utils_core.safe_int(totais_d.get("recusados", 0)),
            "inspecionados": utils_core.safe_int(dep_d.get("insp", 0)),
            "eliminados": utils_core.safe_int(dep_d.get("elim", 0)),
            "tratados": utils_core.safe_int(dep_d.get("trat", 0)),
        },
        "coletas_api": {
            "total": tc, "pos_aeg": ta,
            "pos_alb": utils_core.safe_int(col_d.get("pos_alb", 0)),
            "indice": round(ta / tc * 100, 1) if tc else 0,
        },
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


@bp.route("/relatorio-agente")
@login_required
def page():
    return render_template(
        "relatorio_agente.html",
        agente_sel=request.args.get("agente", ""),
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(30)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
    )


@bp.route("/relatorio-agente/pdf")
@login_required
def pdf():
    nome = request.args.get("agente", "")
    d_ini = request.args.get("d_ini", utils_core.data_n_dias(30))
    d_fim = request.args.get("d_fim", utils_core.hoje())
    if not nome:
        return "Agente nao informado.", 400
    try:
        dados = _obter_dados(nome, d_ini, d_fim)
    except Exception as exc:
        logging.exception("Erro em relatorio_agente.pdf")
        return f"Erro ao gerar relatorio: {exc}", 500
    return render_template("relatorio_agente_pdf.html", **dados)


@bp.route("/api/relatorio-agente")
@login_required
def api():
    try:
        nome = request.args.get("agente", "")
        d_ini = request.args.get("d_ini", utils_core.data_n_dias(30))
        d_fim = request.args.get("d_fim", utils_core.hoje())
        if not nome:
            return jsonify({"erro": "Agente nao informado"}), 400
        dados = _obter_dados(nome, d_ini, d_fim)
        return jsonify({
            "agente": dados["agente"],
            "d_ini": dados["d_ini"],
            "d_fim": dados["d_fim"],
            "totais": dados["totais_api"],
            "coletas": dados["coletas_api"],
            "tbo_duracao": {
                "por_grupo": dados["tbo_por_grupo"],
            },
            "por_tipo": dados["por_tipo"],
            "por_loc": dados["por_loc"],
            "por_dia": dados["por_dia"],
            "evolucao": dados["evolucao"],
            "comparacao": dados["comparacao"],
            "producao_operacional": dados["producao_operacional"],
            "esporotricose": dados["esporotricose"],
            "comparacao_esporotricose": dados["comparacao_esporotricose"],
        })
    except Exception:
        logging.exception("Erro em relatorio_agente.api")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500
