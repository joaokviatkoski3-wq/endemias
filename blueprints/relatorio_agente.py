import logging
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import esporotricose as esporotricose_core
from app_core import ovitrampas as ovitrampas_core
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
    _preparar_resumo_producao_relatorio(resumo)
    total = utils_core.safe_int(resumo.get("totais", {}).get("registros_total", 0))
    resumo["por_agente"] = [{"agente": nome, "registros": total}]
    resumo.setdefault("totais", {})["agentes"] = 1 if total else 0
    return resumo


def _resumo_ovitrampas_agente(nome, d_ini, d_fim):
    conn = _get_db()
    try:
        ovitrampas_core.ensure_schema(conn)
        rows = conn.execute(
            f"""
            SELECT e.data,
                   e.movimento,
                   e.ciclo,
                   e.observacoes,
                   g.nome AS grupo,
                   g.localidades AS localidades
              FROM {ovitrampas_core.CAL_EVENTOS_TABLE} e
              JOIN {ovitrampas_core.CAL_AGENTES_TABLE} ea ON ea.id_evento=e.id_evento
              JOIN agentes ag ON ag.id_agente=ea.id_agente
              LEFT JOIN {ovitrampas_core.CAL_GRUPOS_TABLE} g ON g.id_grupo=e.id_grupo
             WHERE ag.nome=?
               AND e.data BETWEEN ? AND ?
               AND e.movimento <> 'feriado'
             ORDER BY e.data, e.id_evento
            """,
            (nome, d_ini, d_fim),
        ).fetchall()
    finally:
        conn.close()

    eventos = []
    por_movimento = {}
    grupos = set()
    ciclos = set()
    dias = set()
    movimentos = getattr(ovitrampas_core, "MOVIMENTOS", {})
    for row in rows:
        item = dict(row)
        movimento = item.get("movimento") or ""
        item["movimento_label"] = movimentos.get(movimento, movimento)
        eventos.append(item)
        dias.add(item.get("data"))
        if item.get("grupo"):
            grupos.add(item["grupo"])
        if item.get("ciclo"):
            ciclos.add(item["ciclo"])
        por_movimento[item["movimento_label"]] = por_movimento.get(item["movimento_label"], 0) + 1

    return {
        "totais": {
            "eventos": len(eventos),
            "dias": len(dias),
            "grupos": len(grupos),
            "ciclos": len(ciclos),
        },
        "por_movimento": [
            {"movimento": nome_mov, "total": total}
            for nome_mov, total in sorted(por_movimento.items())
        ],
        "eventos": eventos,
    }


def _preparar_resumo_producao_relatorio(resumo):
    atividades = resumo.get("por_atividade", [])
    total = utils_core.safe_int(resumo.get("totais", {}).get("registros_total", 0))
    for atividade in atividades:
        registros = utils_core.safe_int(atividade.get("registros", 0))
        atividade["percentual"] = round(registros / total * 100, 1) if total else 0
        atividade.get("extras", {}).pop("pendentes_sispncd", None)
    return resumo


def _detalhe_atividade(atividade):
    extras = atividade.get("extras") or {}
    codigo = atividade.get("codigo")
    if codigo == "VETORES":
        return f"{utils_core.safe_int(extras.get('normais'))} normais, {utils_core.safe_int(extras.get('fechados'))} fechados"
    if codigo == "ESPOROTRICOSE":
        return f"{utils_core.safe_int(extras.get('animais'))} animais, {utils_core.safe_int(extras.get('animais_com_feridas'))} com feridas"
    if codigo == "RECOLHIMENTO":
        return f"{utils_core.safe_int(extras.get('materiais'))} materiais, {utils_core.safe_int(extras.get('pneus'))} pneus"
    if codigo == "AMOSTRA_ANIMAIS":
        return f"{utils_core.safe_int(extras.get('animais'))} animais, {utils_core.safe_int(extras.get('acidentes'))} acidentes"
    if codigo == "BRI":
        return f"{utils_core.safe_int(extras.get('carga'))} carga"
    return ""


def _obter_dados_setor(d_ini, d_fim):
    resumo = producao_operacional.resumo(
        current_app.config["DB_PATH"],
        {"d_ini": d_ini, "d_fim": d_fim},
    )
    _preparar_resumo_producao_relatorio(resumo)
    for atividade in resumo.get("por_atividade", []):
        atividade["detalhe"] = _detalhe_atividade(atividade)
    return {
        "d_ini": d_ini,
        "d_fim": d_fim,
        "producao_operacional": resumo,
        "visitas_setor": _metricas_visitas_setor(d_ini, d_fim),
        "agentes": _producao_agentes_setor(d_ini, d_fim),
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def _producao_agentes_setor(d_ini, d_fim):
    conn = _get_db()
    try:
        agentes = {}
        fontes = [
            fonte for fonte in producao_operacional.FONTES
            if producao_operacional._table_exists(conn, fonte["tabela"])
            and producao_operacional._table_exists(conn, fonte["agente_table"])
        ]
        for fonte in fontes:
            alias = fonte["alias"]
            id_expr = f"{alias}.{fonte['id_col']}"
            data_expr = f"{alias}.{fonte['data_col']}"
            localidade_expr = fonte["localidade_expr"]
            joins = fonte.get("joins") or ""
            rows = conn.execute(
                f"""
                SELECT ag.nome AS agente,
                       COUNT(DISTINCT {id_expr}) AS registros,
                       GROUP_CONCAT(DISTINCT {data_expr}) AS dias,
                       GROUP_CONCAT(DISTINCT COALESCE({localidade_expr}, '')) AS localidades
                  FROM {fonte['tabela']} {alias}
                  JOIN {fonte['agente_table']} pa ON pa.{fonte['agente_fk']}={id_expr}
                  JOIN agentes ag ON ag.id_agente=pa.id_agente
                  {joins}
                 WHERE {data_expr} BETWEEN ? AND ?
                 GROUP BY ag.nome
                """,
                (d_ini, d_fim),
            ).fetchall()
            for row in rows:
                nome = row["agente"]
                item = agentes.setdefault(nome, {
                    "nome": nome,
                    "total": 0,
                    "dias_set": set(),
                    "localidades_set": set(),
                    "atividades": {
                        f["codigo"]: {"codigo": f["codigo"], "nome": f["nome"], "registros": 0}
                        for f in producao_operacional.FONTES
                    },
                })
                registros = utils_core.safe_int(row["registros"])
                item["total"] += registros
                item["atividades"][fonte["codigo"]]["registros"] = registros
                item["dias_set"].update(part for part in (row["dias"] or "").split(",") if part)
                item["localidades_set"].update(part for part in (row["localidades"] or "").split(",") if part)
    finally:
        conn.close()

    resultado = []
    for item in agentes.values():
        resultado.append({
            "nome": item["nome"],
            "total": item["total"],
            "dias": len(item["dias_set"]),
            "localidades": len(item["localidades_set"]),
            "atividades": list(item["atividades"].values()),
        })
    return sorted(resultado, key=lambda item: (-item["total"], item["nome"]))


def _metricas_visitas_setor(d_ini, d_fim):
    conn = _get_db()
    try:
        totais = conn.execute(
            """
            SELECT COUNT(DISTINCT v.id_visita) AS total,
                   COUNT(DISTINCT v.data) AS dias,
                   COUNT(DISTINCT v.quarteirao) AS quarteiroes,
                   COUNT(DISTINCT COALESCE(l.nome, v.localidade)) AS localidades,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='normal' THEN v.id_visita END) AS normais,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='fechado' THEN v.id_visita END) AS fechados,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='recuperado' THEN v.id_visita END) AS recuperados,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='recusa' THEN v.id_visita END) AS recusados
              FROM visitas v
              LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
             WHERE v.data BETWEEN ? AND ?
            """,
            (d_ini, d_fim),
        ).fetchone()

        por_tipo = conn.execute(
            """
            SELECT v.tipo,
                   COUNT(DISTINCT v.id_visita) AS total,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='normal' THEN v.id_visita END) AS normais,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='fechado' THEN v.id_visita END) AS fechados,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='recuperado' THEN v.id_visita END) AS recuperados,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='recusa' THEN v.id_visita END) AS recusados
              FROM visitas v
             WHERE v.data BETWEEN ? AND ?
             GROUP BY v.tipo
             ORDER BY total DESC, v.tipo
            """,
            (d_ini, d_fim),
        ).fetchall()

        por_status = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(v.visita),''), '-') AS status,
                   COUNT(DISTINCT v.id_visita) AS total
              FROM visitas v
             WHERE v.data BETWEEN ? AND ?
             GROUP BY COALESCE(NULLIF(TRIM(v.visita),''), '-')
             ORDER BY total DESC, status
            """,
            (d_ini, d_fim),
        ).fetchall()

        por_periodo = conn.execute(
            """
            SELECT CASE WHEN v.hora_inicio < '12:00' THEN 'Manha' ELSE 'Tarde' END AS periodo,
                   COUNT(DISTINCT v.id_visita) AS total,
                   COUNT(DISTINCT v.data) AS dias
              FROM visitas v
             WHERE v.data BETWEEN ? AND ?
               AND v.hora_inicio IS NOT NULL
               AND TRIM(v.hora_inicio)<>''
             GROUP BY periodo
             ORDER BY periodo
            """,
            (d_ini, d_fim),
        ).fetchall()

        duracao_por_tipo = conn.execute(
            """
            SELECT tipo, COUNT(*) AS n,
                   ROUND(AVG(dur),1) AS media,
                   ROUND(MIN(dur),1) AS minimo,
                   ROUND(MAX(dur),1) AS maximo
              FROM (
                    SELECT v.tipo,
                           (julianday(v.data||' '||v.hora_fim)-julianday(v.data||' '||v.hora_inicio))*24*60 AS dur
                      FROM visitas v
                     WHERE v.data BETWEEN ? AND ?
                       AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
                   ) base
             WHERE dur BETWEEN 1 AND 240
             GROUP BY tipo
             ORDER BY media DESC, tipo
            """,
            (d_ini, d_fim),
        ).fetchall()

        duracao_por_acesso = conn.execute(
            """
            SELECT grupo, COUNT(*) AS n,
                   ROUND(AVG(dur),1) AS media,
                   ROUND(MIN(dur),1) AS minimo,
                   ROUND(MAX(dur),1) AS maximo
              FROM (
                    SELECT CASE WHEN LOWER(COALESCE(v.visita,'')) IN ('normal','recuperado')
                                THEN 'Acessados' ELSE 'Nao acessados' END AS grupo,
                           (julianday(v.data||' '||v.hora_fim)-julianday(v.data||' '||v.hora_inicio))*24*60 AS dur
                      FROM visitas v
                     WHERE v.data BETWEEN ? AND ?
                       AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
                   ) base
             WHERE dur BETWEEN 1 AND 240
             GROUP BY grupo
             ORDER BY grupo
            """,
            (d_ini, d_fim),
        ).fetchall()

        dep = conn.execute(
            """
            SELECT COALESCE(SUM(inspecionado),0) AS inspecionados,
                   COALESCE(SUM(eliminado),0) AS eliminados,
                   COALESCE(SUM(tratado),0) AS tratados
              FROM depositos_inspecionados d
              JOIN visitas v ON v.id_visita=d.id_visita
             WHERE v.data BETWEEN ? AND ?
            """,
            (d_ini, d_fim),
        ).fetchone()

        coletas = conn.execute(
            """
            SELECT COUNT(DISTINCT c.id_coleta) AS total,
                   COUNT(DISTINCT CASE WHEN rl.aegypt_larvas>0 OR rl.aegypt_pupas>0
                         OR rl.aegypt_exuvias>0 OR rl.aegypt_adulto>0 THEN c.id_coleta END) AS pos_aeg,
                   COUNT(DISTINCT CASE WHEN rl.albopictus_larvas>0 OR rl.albopictus_pupas>0
                         OR rl.albopictus_exuvias>0 OR rl.albopictus_adulto>0 THEN c.id_coleta END) AS pos_alb
              FROM coletas c
              JOIN visitas v ON v.id_visita=c.id_visita
              LEFT JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
             WHERE v.data BETWEEN ? AND ?
            """,
            (d_ini, d_fim),
        ).fetchone()
    finally:
        conn.close()

    totais_d = dict(totais) if totais else {}
    total = utils_core.safe_int(totais_d.get("total"))
    dias = utils_core.safe_int(totais_d.get("dias"))
    coletas_d = dict(coletas) if coletas else {}
    total_coletas = utils_core.safe_int(coletas_d.get("total"))
    pos_aeg = utils_core.safe_int(coletas_d.get("pos_aeg"))
    return {
        "totais": {
            **totais_d,
            "media_dia": round(total / dias, 1) if dias else 0,
            "taxa_acesso": round(
                (utils_core.safe_int(totais_d.get("normais")) + utils_core.safe_int(totais_d.get("recuperados"))) / total * 100,
                1,
            ) if total else 0,
        },
        "por_tipo": [dict(row) for row in por_tipo],
        "por_status": [dict(row) for row in por_status],
        "por_periodo": [
            {**dict(row), "media_dia": round((row["total"] or 0) / (row["dias"] or 1), 1)}
            for row in por_periodo
        ],
        "duracao_por_tipo": [dict(row) for row in duracao_por_tipo],
        "duracao_por_acesso": [dict(row) for row in duracao_por_acesso],
        "depositos": dict(dep) if dep else {},
        "coletas": {
            **coletas_d,
            "indice": round(pos_aeg / total_coletas * 100, 1) if total_coletas else 0,
        },
    }


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
    ovitrampas = _resumo_ovitrampas_agente(nome, d_ini, d_fim)
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
        "ovitrampas": ovitrampas,
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


@bp.route("/relatorio-agente/setor/pdf")
@login_required
def pdf_setor():
    d_ini = request.args.get("d_ini", utils_core.data_n_dias(30))
    d_fim = request.args.get("d_fim", utils_core.hoje())
    try:
        dados = _obter_dados_setor(d_ini, d_fim)
    except Exception as exc:
        logging.exception("Erro em relatorio_agente.pdf_setor")
        return f"Erro ao gerar relatorio do setor: {exc}", 500
    return render_template("relatorio_setor_pdf.html", **dados)


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
            "ovitrampas": dados["ovitrampas"],
            "esporotricose": dados["esporotricose"],
            "comparacao_esporotricose": dados["comparacao_esporotricose"],
        })
    except Exception:
        logging.exception("Erro em relatorio_agente.api")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500
