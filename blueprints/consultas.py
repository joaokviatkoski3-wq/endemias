import logging

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import agentes as agentes_core
from app_core import audit
from app_core import blueprint_helpers as bh
from app_core import esporotricose as esporotricose_core
from app_core import auth as auth_core
from app_core import db as db_core
from app_core import normalizadores
from app_core import ovitrampas as ovitrampas_core
from app_core import pontos_estrategicos as pe_core
from app_core import producao_operacional
from app_core import utils as utils_core
from app_core import work_types


bp = Blueprint("consultas", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min
DURATION_WORK_TYPE_CODE = work_types.primary_duration_work_type_code()


def _db_path():
    return current_app.config["DB_PATH"]


def get_db():
    return db_core.connect(_db_path())


def _has_column(conn, table, column):
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return False
    return any(row["name"] == column for row in rows)


def _total_tratamentos_depositos_dashboard(conn, where, params):
    if not _has_column(conn, "tratamentos", "qtd_depositos_tratados"):
        return 0
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(qtd),0) AS total
          FROM (
                SELECT DISTINCT t.id, COALESCE(t.qtd_depositos_tratados,0) AS qtd
                  FROM tratamentos t
                  JOIN visitas v ON v.id_visita=t.id_visita
                  LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                  LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                  LEFT JOIN agentes a ON a.id_agente=va.id_agente
                  {where}
               ) base
        """,
        params,
    ).fetchone()
    return utils_core.safe_int(row["total"] if row else 0)


def request_int_arg(nome, default, minimo=None, maximo=None):
    return utils_core.bounded_int(request.args.get(nome), default, minimo, maximo)


def _dashboard_esporotricose_filtros(args):
    filtros = {
        "d_ini": args.get("d_ini", ""),
        "d_fim": args.get("d_fim", ""),
    }
    localidades = [v for v in args.getlist("localidade") if v]
    agentes = [v for v in args.getlist("agente") if v]
    if localidades:
        filtros["localidade"] = localidades
    if agentes:
        filtros["agente"] = agentes
    return filtros


def _dashboard_ovitrampas(args):
    d_ini = args.get("d_ini") or utils_core.data_n_dias(90)
    d_fim = args.get("d_fim") or utils_core.hoje()
    localidades = [v for v in args.getlist("localidade") if v]
    agentes = [v for v in args.getlist("agente") if v]
    conn = get_db()
    try:
        ovitrampas_core.ensure_schema(conn)
        leitura_where = ["COALESCE(l.data_leitura, l.data_coleta, l.data_envio_contagem) BETWEEN ? AND ?"]
        leitura_params = [d_ini, d_fim]
        if localidades:
            leitura_where.append(f"COALESCE(a.localidade, l.distrito, '-') IN ({','.join('?' * len(localidades))})")
            leitura_params.extend(localidades)
        if agentes:
            leitura_where.append(f"lab.nome IN ({','.join('?' * len(agentes))})")
            leitura_params.extend(agentes)
        leitura_where_sql = "WHERE " + " AND ".join(leitura_where)
        leitura_join = f"""
            FROM {ovitrampas_core.TABLE} l
            LEFT JOIN {ovitrampas_core.ARMADILHAS_TABLE} a ON a.ovitrampa_id=l.ovitrampa_id
            LEFT JOIN agentes lab ON lab.id_agente=l.id_laboratorista
        """

        leituras_totais = dict(conn.execute(
            f"""SELECT COUNT(*) AS leituras,
                       COUNT(DISTINCT l.ovitrampa_id) AS ovitrampas,
                       COALESCE(SUM(l.ovos),0) AS ovos,
                       SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END) AS positivas,
                       COUNT(DISTINCT l.ano || '-' || l.semana) AS semanas,
                       COUNT(DISTINCT lab.id_agente) AS laboratoristas
                  {leitura_join} {leitura_where_sql}""",
            leitura_params,
        ).fetchone())
        por_semana = [dict(row) for row in conn.execute(
            f"""SELECT l.ano, l.semana,
                       COUNT(*) AS leituras,
                       COALESCE(SUM(l.ovos),0) AS ovos,
                       SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END) AS positivas
                  {leitura_join} {leitura_where_sql}
                 GROUP BY l.ano, l.semana
                 ORDER BY l.ano, l.semana""",
            leitura_params,
        ).fetchall()]
        por_localidade = [dict(row) for row in conn.execute(
            f"""SELECT COALESCE(a.localidade, l.distrito, '-') AS localidade,
                       COUNT(*) AS leituras,
                       COUNT(DISTINCT l.ovitrampa_id) AS ovitrampas,
                       COALESCE(SUM(l.ovos),0) AS ovos,
                       SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END) AS positivas
                  {leitura_join} {leitura_where_sql}
                 GROUP BY COALESCE(a.localidade, l.distrito, '-')
                 ORDER BY ovos DESC, positivas DESC, leituras DESC
                 LIMIT 15""",
            leitura_params,
        ).fetchall()]
        por_laboratorista = [dict(row) for row in conn.execute(
            f"""SELECT COALESCE(lab.nome, 'Sem laboratorista') AS agente,
                       COUNT(*) AS leituras,
                       COALESCE(SUM(l.ovos),0) AS ovos,
                       SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END) AS positivas
                  {leitura_join} {leitura_where_sql}
                 GROUP BY COALESCE(lab.nome, 'Sem laboratorista')
                 ORDER BY leituras DESC, agente
                 LIMIT 15""",
            leitura_params,
        ).fetchall()]

        cal_where = ["e.data BETWEEN ? AND ?", "e.movimento <> 'feriado'"]
        cal_params = [d_ini, d_fim]
        if localidades:
            loc_clause = " OR ".join(["g.nome=? OR g.localidades LIKE ?" for _ in localidades])
            cal_where.append(f"({loc_clause})")
            for loc in localidades:
                cal_params.extend([loc, f"%{loc}%"])
        if agentes:
            cal_where.append(
                f"""EXISTS (
                    SELECT 1 FROM {ovitrampas_core.CAL_AGENTES_TABLE} ea2
                    JOIN agentes ag2 ON ag2.id_agente=ea2.id_agente
                    WHERE ea2.id_evento=e.id_evento
                      AND ag2.nome IN ({','.join('?' * len(agentes))})
                )"""
            )
            cal_params.extend(agentes)
        cal_where_sql = "WHERE " + " AND ".join(cal_where)
        cal_join = f"""
            FROM {ovitrampas_core.CAL_EVENTOS_TABLE} e
            LEFT JOIN {ovitrampas_core.CAL_GRUPOS_TABLE} g ON g.id_grupo=e.id_grupo
            LEFT JOIN {ovitrampas_core.CAL_AGENTES_TABLE} ea ON ea.id_evento=e.id_evento
            LEFT JOIN agentes ag ON ag.id_agente=ea.id_agente
        """
        calendario_totais = dict(conn.execute(
            f"""SELECT COUNT(DISTINCT e.id_evento) AS movimentos,
                       COUNT(DISTINCT e.data) AS dias,
                       COUNT(DISTINCT e.id_grupo) AS grupos,
                       COUNT(DISTINCT ag.id_agente) AS agentes
                  {cal_join} {cal_where_sql}""",
            cal_params,
        ).fetchone())
        por_movimento = [dict(row) for row in conn.execute(
            f"""SELECT e.movimento, COUNT(DISTINCT e.id_evento) AS total
                  {cal_join} {cal_where_sql}
                 GROUP BY e.movimento
                 ORDER BY total DESC, e.movimento""",
            cal_params,
        ).fetchall()]
        por_grupo = [dict(row) for row in conn.execute(
            f"""SELECT COALESCE(g.nome, '-') AS grupo, COUNT(DISTINCT e.id_evento) AS total
                  {cal_join} {cal_where_sql}
                 GROUP BY COALESCE(g.nome, '-')
                 ORDER BY total DESC, grupo
                 LIMIT 12""",
            cal_params,
        ).fetchall()]
        por_agente = [dict(row) for row in conn.execute(
            f"""SELECT ag.nome AS agente, COUNT(DISTINCT e.id_evento) AS total
                  {cal_join} {cal_where_sql} AND ag.nome IS NOT NULL
                 GROUP BY ag.nome
                 ORDER BY total DESC, agente
                 LIMIT 15""",
            cal_params,
        ).fetchall()]
        por_mes = [dict(row) for row in conn.execute(
            f"""SELECT substr(e.data,1,7) AS mes, COUNT(DISTINCT e.id_evento) AS movimentos
                  {cal_join} {cal_where_sql}
                 GROUP BY substr(e.data,1,7)
                 ORDER BY mes""",
            cal_params,
        ).fetchall()]
    finally:
        conn.close()

    movimentos = getattr(ovitrampas_core, "MOVIMENTOS", {})
    for row in por_movimento:
        row["nome"] = movimentos.get(row.get("movimento"), row.get("movimento") or "-")

    return {
        "leituras": {
            "totais": leituras_totais,
            "por_semana": por_semana,
            "por_localidade": por_localidade,
            "por_laboratorista": por_laboratorista,
        },
        "calendario": {
            "totais": calendario_totais,
            "por_movimento": por_movimento,
            "por_grupo": por_grupo,
            "por_agente": por_agente,
            "por_mes": por_mes,
        },
    }


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


@bp.route("/api/dashboard")
@login_required
def api_dashboard():
    try:
        where, params = utils_core.build_visit_where(request.args)
        base = f"""FROM visitas v
                   LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                   LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                   LEFT JOIN agentes a ON a.id_agente=va.id_agente
                   {where}"""
        conn = get_db()
        try:
            kpi = conn.execute(f"""
                SELECT COUNT(DISTINCT v.id_visita) as total,
                       COUNT(DISTINCT v.data) as dias,
                       COUNT(DISTINCT v.quarteirao) as quarteiroes,
                       COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
                       COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
                       COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
                       COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados
                {base}""", params).fetchone()

            por_tipo = conn.execute(
                f"SELECT v.tipo, COUNT(DISTINCT v.id_visita) as total {base} GROUP BY v.tipo",
                params,
            ).fetchall()
            por_loc = conn.execute(
                f"SELECT l.nome as loc, COUNT(DISTINCT v.id_visita) as total {base} GROUP BY l.nome ORDER BY total DESC LIMIT 15",
                params,
            ).fetchall()
            por_status = conn.execute(
                f"SELECT COALESCE(LOWER(v.visita),'sem info') as visita, COUNT(*) as total {base} GROUP BY LOWER(v.visita)",
                params,
            ).fetchall()
            evolucao = conn.execute(
                f"SELECT strftime('%Y-%W',v.data) as sem, COUNT(DISTINCT v.id_visita) as total {base} GROUP BY sem ORDER BY sem",
                params,
            ).fetchall()
            evolucao_mes = conn.execute(
                f"SELECT substr(v.data,1,7) as mes, COUNT(DISTINCT v.id_visita) as visitas {base} GROUP BY mes ORDER BY mes",
                params,
            ).fetchall()
            por_agente = conn.execute(
                f"SELECT a.nome, COUNT(DISTINCT v.id_visita) as total {base} AND a.nome IS NOT NULL GROUP BY a.nome ORDER BY total DESC",
                params,
            ).fetchall()
            por_imovel = conn.execute(
                f"SELECT v.tipo_imovel, COUNT(*) as total {base} AND v.tipo_imovel IS NOT NULL GROUP BY v.tipo_imovel ORDER BY total DESC",
                params,
            ).fetchall()
            dep = conn.execute(
                f"SELECT SUM(d.inspecionado) as insp, SUM(d.eliminado) as elim, SUM(d.tratado) as trat FROM depositos_inspecionados d JOIN visitas v ON v.id_visita=d.id_visita LEFT JOIN localidades l ON l.id_localidade=v.id_localidade LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita LEFT JOIN agentes a ON a.id_agente=va.id_agente {where}",
                params,
            ).fetchone()
            dep_tratamentos = _total_tratamentos_depositos_dashboard(conn, where, params)
            dep_tipo = conn.execute(
                f"SELECT d.tipo_deposito, SUM(d.inspecionado) as insp FROM depositos_inspecionados d JOIN visitas v ON v.id_visita=d.id_visita LEFT JOIN localidades l ON l.id_localidade=v.id_localidade LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita LEFT JOIN agentes a ON a.id_agente=va.id_agente {where} GROUP BY d.tipo_deposito ORDER BY insp DESC",
                params,
            ).fetchall()
            tbo_dur = conn.execute(f"""
                SELECT COUNT(*) as n,
                       ROUND(AVG(dur),1) as media,
                       ROUND(MIN(dur),1) as minimo,
                       ROUND(MAX(dur),1) as maximo
                FROM (
                    SELECT (julianday(v.data||' '||v.hora_fim)-julianday(v.data||' '||v.hora_inicio))*24*60 AS dur
                    FROM visitas v
                    LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                    LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                    LEFT JOIN agentes a ON a.id_agente=va.id_agente
                    {where} AND v.tipo=? AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
                ) sub WHERE dur BETWEEN 1 AND 240
            """, params + [DURATION_WORK_TYPE_CODE]).fetchone()

            tbo_dur_tipo = conn.execute(f"""
                SELECT
                    CASE WHEN LOWER(sub.visita) IN ('normal','recuperado') THEN 'acessados'
                         ELSE 'nao_acessados' END as grupo,
                    COUNT(*) as n,
                    ROUND(AVG(dur),1) as media,
                    ROUND(MIN(dur),1) as minimo,
                    ROUND(MAX(dur),1) as maximo
                FROM (
                    SELECT v.visita,
                        (julianday(v.data||' '||v.hora_fim)-julianday(v.data||' '||v.hora_inicio))*24*60 AS dur
                    FROM visitas v
                    LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                    LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                    LEFT JOIN agentes a ON a.id_agente=va.id_agente
                    {where} AND v.tipo=? AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
                ) sub WHERE dur BETWEEN 1 AND 240
                GROUP BY grupo
            """, params + [DURATION_WORK_TYPE_CODE]).fetchall()
        finally:
            conn.close()

        esporo_filtros = _dashboard_esporotricose_filtros(request.args)
        esporo_resumo = esporotricose_core.resumo(_db_path(), esporo_filtros)
        esporo_dash = esporotricose_core.dashboard(_db_path(), esporo_filtros)
        pe_resumo = pe_core.resumo_operacional(_db_path(), {
            "d_ini": request.args.get("d_ini", ""),
            "d_fim": request.args.get("d_fim", ""),
            "localidade": request.args.getlist("localidade"),
        })
        producao = producao_operacional.resumo(_db_path(), request.args)
        ovitrampas = _dashboard_ovitrampas(request.args)
        vetores_mes = {dict(r)["mes"]: dict(r)["visitas"] for r in evolucao_mes}
        esporo_mes = {r["mes"]: r.get("visitas", 0) for r in esporo_dash.get("evolucao", [])}
        ovi_mes = {r["mes"]: r.get("movimentos", 0) for r in ovitrampas.get("calendario", {}).get("por_mes", [])}
        meses = sorted(set(vetores_mes) | set(esporo_mes) | set(ovi_mes))
        comparativo_mensal = [
            {
                "mes": mes,
                "vetores": vetores_mes.get(mes, 0),
                "esporotricose": esporo_mes.get(mes, 0),
                "ovitrampas": ovi_mes.get(mes, 0),
            }
            for mes in meses
        ]

        return jsonify({
            "kpi": dict(kpi) if kpi else {},
            "depositos": {
                "inspecionados": utils_core.safe_int(dep["insp"]) if dep else 0,
                "eliminados": utils_core.safe_int(dep["elim"]) if dep else 0,
                "tratados": (utils_core.safe_int(dep["trat"]) if dep else 0) + dep_tratamentos,
            },
            "dep_por_tipo": [dict(r) for r in dep_tipo],
            "tbo_duracao": {
                "n": dict(tbo_dur)["n"] if tbo_dur else 0,
                "media": dict(tbo_dur)["media"] if tbo_dur else None,
                "minimo": dict(tbo_dur)["minimo"] if tbo_dur else None,
                "maximo": dict(tbo_dur)["maximo"] if tbo_dur else None,
                "por_grupo": {
                    dict(r)["grupo"]: {
                        "n": dict(r)["n"],
                        "media": dict(r)["media"],
                        "minimo": dict(r)["minimo"],
                        "maximo": dict(r)["maximo"],
                    }
                    for r in tbo_dur_tipo
                },
            },
            "por_tipo": [dict(r) for r in por_tipo],
            "por_loc": [dict(r) for r in por_loc],
            "por_status": [dict(r) for r in por_status],
            "evolucao": [dict(r) for r in evolucao],
            "evolucao_mensal": [dict(r) for r in evolucao_mes],
            "comparativo_mensal": comparativo_mensal,
            "por_agente": [dict(r) for r in por_agente],
            "por_imovel": [dict(r) for r in por_imovel],
            "esporotricose": {
                "resumo": esporo_resumo,
                "dashboard": esporo_dash,
            },
            "pontos_estrategicos": pe_resumo,
            "producao_operacional": producao,
            "ovitrampas": ovitrampas,
        })
    except Exception:
        logging.exception("Erro em api_dashboard")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@bp.route("/api/producao-operacional")
@login_required
def api_producao_operacional():
    try:
        return jsonify(producao_operacional.resumo(_db_path(), request.args))
    except Exception:
        logging.exception("Erro em api_producao_operacional")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@bp.route("/api/laboratorio")
@login_required
def api_laboratorio():
    try:
        d_ini = request.args.get("d_ini", utils_core.data_n_dias(365))
        d_fim = request.args.get("d_fim", utils_core.hoje())
        tipos = request.args.getlist("tipo")
        locs = request.args.getlist("localidade")
        ags = request.args.getlist("agente")
        tubo = request.args.get("tubo", "").strip()
        especie = request.args.get("especie", "")
        apenas_pos = request.args.get("apenas_pos", "")
        pagina = request_int_arg("pagina", 1, minimo=1)
        pp = request_int_arg("por_pagina", 50, minimo=1, maximo=500)

        where = "WHERE v.data BETWEEN ? AND ?"
        params = [d_ini, d_fim]
        if tipos:
            where += f" AND v.tipo IN ({','.join('?' * len(tipos))})"
            params += tipos
        if locs:
            where += f" AND l.nome IN ({','.join('?' * len(locs))})"
            params += locs
        if ags:
            cond = " OR ".join(["a.nome=?" for _ in ags])
            where += f" AND ({cond})"
            params += ags
        if tubo:
            where += " AND c.num_tubo LIKE ?"
            params.append(f"%{tubo}%")

        aeg = "(rl.aegypt_larvas>0 OR rl.aegypt_pupas>0 OR rl.aegypt_exuvias>0 OR rl.aegypt_adulto>0)"
        alb = "(rl.albopictus_larvas>0 OR rl.albopictus_pupas>0 OR rl.albopictus_exuvias>0 OR rl.albopictus_adulto>0)"
        out = "(rl.outra_larvas>0 OR rl.outra_pupas>0 OR rl.outra_exuvias>0 OR rl.outra_adulto>0)"

        if apenas_pos == "1" or especie == "aegypti":
            where += f" AND {aeg}"
        elif especie == "albopictus":
            where += f" AND {alb}"
        elif especie == "outra":
            where += f" AND {out}"

        base = f"""FROM resultados_laboratorio rl
                   JOIN coletas c ON c.id_coleta=rl.id_coleta
                   JOIN visitas v ON v.id_visita=c.id_visita
                   LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                   LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                   LEFT JOIN agentes a ON a.id_agente=va.id_agente
                   {where}"""

        conn = get_db()
        try:
            total = conn.execute(f"SELECT COUNT(DISTINCT rl.id_resultado) {base}", params).fetchone()[0]
            total_pag = max(1, (total + pp - 1) // pp)
            pagina = min(pagina, total_pag)
            offset = (pagina - 1) * pp

            rows = conn.execute(f"""
                SELECT DISTINCT rl.id_resultado, v.data, v.tipo, l.nome as localidade,
                       v.quarteirao, v.logradouro, v.numero, c.num_tubo, c.tipo_deposito,
                       rl.data_leitura, rl.laboratorista,
                       rl.aegypt_larvas, rl.aegypt_pupas, rl.aegypt_exuvias, rl.aegypt_adulto,
                       rl.albopictus_larvas, rl.albopictus_pupas, rl.albopictus_exuvias, rl.albopictus_adulto,
                       rl.outra_larvas, rl.outra_pupas, rl.outra_exuvias, rl.outra_adulto,
                       GROUP_CONCAT(DISTINCT a.nome) as agentes,
                       ({aeg}) as pos_aeg, ({alb}) as pos_alb, ({out}) as pos_out
                {base} GROUP BY rl.id_resultado ORDER BY v.data DESC, rl.id_resultado DESC
                LIMIT ? OFFSET ?
            """, params + [pp, offset]).fetchall()

            totais = conn.execute(f"""SELECT
                SUM(sub.ta) as total_aeg, SUM(sub.tb) as total_alb, SUM(sub.tc) as total_out,
                COUNT(*) as total_col, SUM(sub.pa) as pos_aeg, SUM(sub.pb) as pos_alb
                FROM (
                  SELECT DISTINCT rl.id_resultado,
                    rl.aegypt_larvas+rl.aegypt_pupas+rl.aegypt_exuvias+rl.aegypt_adulto as ta,
                    rl.albopictus_larvas+rl.albopictus_pupas+rl.albopictus_exuvias+rl.albopictus_adulto as tb,
                    rl.outra_larvas+rl.outra_pupas+rl.outra_exuvias+rl.outra_adulto as tc,
                    CASE WHEN {aeg} THEN 1 ELSE 0 END as pa,
                    CASE WHEN {alb} THEN 1 ELSE 0 END as pb
                  {base}
                ) sub""", params).fetchone()

            evolucao = conn.execute(f"""
                SELECT strftime('%Y-%m', v.data) as mes,
                       COUNT(DISTINCT rl.id_resultado) as total,
                       COUNT(DISTINCT CASE WHEN {aeg} THEN rl.id_resultado END) as positivos
                {base} GROUP BY mes ORDER BY mes
            """, params).fetchall()

            por_loc = conn.execute(f"""
                SELECT l.nome as loc, COUNT(DISTINCT rl.id_resultado) as total,
                       COUNT(DISTINCT CASE WHEN {aeg} THEN rl.id_resultado END) as positivos
                {base} GROUP BY l.nome ORDER BY total DESC
            """, params).fetchall()
        finally:
            conn.close()

        tc = utils_core.safe_int(totais["total_col"])
        ta = utils_core.safe_int(totais["pos_aeg"])
        return jsonify({
            "total": total,
            "total_paginas": total_pag,
            "pagina": pagina,
            "totais": {
                "total_coletas": tc,
                "aegypti": utils_core.safe_int(totais["total_aeg"]),
                "albopictus": utils_core.safe_int(totais["total_alb"]),
                "outra": utils_core.safe_int(totais["total_out"]),
                "positivos_aeg": ta,
                "positivos_alb": utils_core.safe_int(totais["pos_alb"]),
                "indice_pos": round(ta / tc * 100, 1) if tc else 0,
            },
            "evolucao": [dict(r) for r in evolucao],
            "por_loc": [dict(r) for r in por_loc],
            "registros": [dict(r) for r in rows],
        })
    except Exception:
        logging.exception("Erro em api_laboratorio")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@bp.route("/api/visitas")
@login_required
def api_visitas():
    try:
        where, params = utils_core.build_visit_where(request.args)
        busca = request.args.get("busca", "").strip()
        if busca:
            where += " AND (v.logradouro LIKE ? OR CAST(v.quarteirao AS TEXT) LIKE ?)"
            b = f"%{busca}%"
            params += [b, b]

        pagina = request_int_arg("pagina", 1, minimo=1)
        pp = request_int_arg("por_pagina", 100, minimo=1, maximo=500)
        base = f"""FROM visitas v
                   LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                   LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
                   LEFT JOIN agentes a ON a.id_agente=va.id_agente
                   {where}"""

        conn = get_db()
        try:
            total = conn.execute(f"SELECT COUNT(DISTINCT v.id_visita) {base}", params).fetchone()[0]
            total_pag = max(1, (total + pp - 1) // pp)
            pagina = min(pagina, total_pag)
            rows = conn.execute(f"""
                SELECT DISTINCT v.id_visita, v.data, v.tipo, l.nome as localidade,
                       v.quarteirao, v.logradouro, v.numero, v.visita,
                       v.tipo_imovel, v.ciclo, v.sequencia, v.morador,
                       v.hora_inicio, v.hora_fim, v.observacoes,
                       GROUP_CONCAT(DISTINCT a.nome) as agentes,
                       CASE WHEN EXISTS(
                           SELECT 1 FROM focos_positivos f
                           WHERE f.id_visita=v.id_visita AND f.gera_notificacao=1
                       ) THEN 1 ELSE 0 END as positiva
                {base} GROUP BY v.id_visita ORDER BY v.data DESC, v.hora_inicio
                LIMIT ? OFFSET ?
            """, params + [pp, (pagina - 1) * pp]).fetchall()
        finally:
            conn.close()

        return jsonify({
            "total": total,
            "total_paginas": total_pag,
            "pagina": pagina,
            "registros": [dict(r) for r in rows],
        })
    except Exception:
        logging.exception("Erro em api_visitas")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@bp.route("/api/visitas/<id_visita>/editar", methods=["POST"])
@login_required
@nivel_min("operador")
def api_visita_editar(id_visita):
    dados = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        atual = conn.execute("SELECT * FROM visitas WHERE id_visita=?", (id_visita,)).fetchone()
        if not atual:
            return jsonify({"erro": "Visita não encontrada."}), 404

        localidade = normalizadores.normalizar_localidade(dados.get("localidade"))
        id_localidade = None
        if localidade:
            row_loc = conn.execute("SELECT id_localidade FROM localidades WHERE nome=?", (localidade,)).fetchone()
            if row_loc:
                id_localidade = row_loc["id_localidade"]
            else:
                cur_loc = conn.execute("INSERT INTO localidades(nome, cod_localidade) VALUES (?,NULL)", (localidade,))
                id_localidade = cur_loc.lastrowid

        payload = {
            "data": _limpar_texto(dados.get("data")),
            "hora_inicio": _limpar_texto(dados.get("hora_inicio")),
            "hora_fim": _limpar_texto(dados.get("hora_fim")),
            "localidade": localidade,
            "id_localidade": id_localidade,
            "logradouro": _limpar_texto(dados.get("logradouro")),
            "numero": _limpar_texto(dados.get("numero")),
            "quarteirao": _limpar_int(dados.get("quarteirao")),
            "sequencia": _limpar_texto(dados.get("sequencia")),
            "morador": _limpar_texto(dados.get("morador")),
            "tipo_imovel": _limpar_texto(dados.get("tipo_imovel")),
            "visita": _limpar_texto(dados.get("visita")),
            "observacoes": _limpar_texto(dados.get("observacoes")),
        }
        if not payload["data"]:
            return jsonify({"erro": "Informe a data da visita."}), 400

        conn.execute(
            """UPDATE visitas SET
                   data=?, hora_inicio=?, hora_fim=?, localidade=?, id_localidade=?,
                   logradouro=?, numero=?, quarteirao=?, sequencia=?, morador=?,
                   tipo_imovel=?, visita=?, observacoes=?
                 WHERE id_visita=?""",
            (
                payload["data"], payload["hora_inicio"], payload["hora_fim"],
                payload["localidade"], payload["id_localidade"], payload["logradouro"],
                payload["numero"], payload["quarteirao"], payload["sequencia"],
                payload["morador"], payload["tipo_imovel"], payload["visita"],
                payload["observacoes"], id_visita,
            ),
        )

        nomes_agentes = _split_agentes_edicao(dados.get("agentes"))
        conn.execute("DELETE FROM visita_agentes WHERE id_visita=?", (id_visita,))
        for nome in nomes_agentes:
            id_agente = agentes_core.obter_ou_criar(conn, nome)
            if id_agente:
                conn.execute(
                    "INSERT OR IGNORE INTO visita_agentes(id_visita, id_agente) VALUES (?,?)",
                    (id_visita, id_agente),
                )
        conn.commit()
        audit.registrar_evento(
            get_db,
            "visita_editada",
            entidade="visitas",
            entidade_id=id_visita,
            detalhes={"antes": dict(atual), "depois": payload, "agentes": nomes_agentes},
        )
        return jsonify({"ok": True})
    except Exception:
        conn.rollback()
        logging.exception("Erro em api_visita_editar")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500
    finally:
        conn.close()


def _limpar_texto(valor):
    texto = str(valor or "").strip()
    return texto or None


def _limpar_int(valor):
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return int(float(texto.replace(",", ".")))
    except ValueError:
        return None


def _split_agentes_edicao(valor):
    texto = str(valor or "").replace("\n", ",").replace(";", ",")
    nomes = []
    for parte in texto.split(","):
        nome = agentes_core.normalizar_nome(parte)
        if nome and nome not in nomes:
            nomes.append(nome)
    return nomes
