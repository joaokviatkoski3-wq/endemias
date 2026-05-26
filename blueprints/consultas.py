import logging

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import esporotricose as esporotricose_core
from app_core import auth as auth_core
from app_core import db as db_core
from app_core import pontos_estrategicos as pe_core
from app_core import utils as utils_core
from app_core import work_types


bp = Blueprint("consultas", __name__)
login_required = auth_core.login_required
DURATION_WORK_TYPE_CODE = work_types.primary_duration_work_type_code()


def _db_path():
    return current_app.config["DB_PATH"]


def get_db():
    return db_core.connect(_db_path())


def request_int_arg(nome, default, minimo=None, maximo=None):
    return utils_core.bounded_int(request.args.get(nome), default, minimo, maximo)


def build_where(params_dict, alias_v="v", alias_l="l", alias_a="a"):
    return utils_core.build_visit_where(params_dict, alias_v, alias_l)


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
        where, params = build_where(request.args)
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
        vetores_mes = {dict(r)["mes"]: dict(r)["visitas"] for r in evolucao_mes}
        esporo_mes = {r["mes"]: r.get("visitas", 0) for r in esporo_dash.get("evolucao", [])}
        meses = sorted(set(vetores_mes) | set(esporo_mes))
        comparativo_mensal = [
            {
                "mes": mes,
                "vetores": vetores_mes.get(mes, 0),
                "esporotricose": esporo_mes.get(mes, 0),
            }
            for mes in meses
        ]

        return jsonify({
            "kpi": dict(kpi) if kpi else {},
            "depositos": {
                "inspecionados": utils_core.safe_int(dep["insp"]) if dep else 0,
                "eliminados": utils_core.safe_int(dep["elim"]) if dep else 0,
                "tratados": utils_core.safe_int(dep["trat"]) if dep else 0,
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
        })
    except Exception:
        logging.exception("Erro em api_dashboard")
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
        where, params = build_where(request.args)
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
