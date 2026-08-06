import logging
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import esporotricose as esporotricose_core
from app_core import ovitrampas as ovitrampas_core
from app_core import producao_operacional
from app_core import registro_geografico as registro_geografico_core
from app_core import utils as utils_core
from app_core import work_types


bp = Blueprint("relatorio_agente", __name__)
login_required = auth_core.login_required


def _db_target():
    return db_core.configured_target(current_app.config)


def _get_db():
    return db_core.connect(_db_target())


def _has_column(conn, table, column):
    try:
        return db_core.column_exists(conn, table, column)
    except Exception:
        return False


def _row_dict(row):
    return db_core.serialize_row(row) if row else {}


def _rows_dict(rows):
    return [db_core.serialize_row(row) for row in rows]


def _is_postgresql(conn):
    return getattr(conn, "backend", "sqlite") == "postgresql"


def _duration_expression(conn, alias):
    if _is_postgresql(conn):
        return (
            f"EXTRACT(EPOCH FROM ({alias}.hora_fim - {alias}.hora_inicio)) "
            "/ 60.0"
        )
    return (
        f"(julianday({alias}.data||' '||{alias}.hora_fim)-"
        f"julianday({alias}.data||' '||{alias}.hora_inicio))*24*60"
    )


def _week_start_expression(conn, expression):
    if _is_postgresql(conn):
        return (
            "to_char(date_trunc('week', "
            f"CAST({expression} AS timestamp)), 'YYYY-MM-DD')"
        )
    return f"strftime('%Y-%m-%d',{expression},'weekday 0','-6 days')"


def _distinct_aggregate(conn, expression):
    if _is_postgresql(conn):
        return f"string_agg(DISTINCT CAST({expression} AS TEXT), ',')"
    return f"GROUP_CONCAT(DISTINCT {expression})"


def _numeric_text_order(conn, expression):
    if _is_postgresql(conn):
        return (
            f"CAST(NULLIF(substring(CAST({expression} AS TEXT) "
            "FROM '^[0-9]+'), '') AS BIGINT)"
        )
    return f"CAST({expression} AS INTEGER)"


def _ovitrampa_date_expression(alias):
    return (
        f"COALESCE(CAST({alias}.data_leitura AS TEXT), "
        f"CAST({alias}.data_coleta AS TEXT), "
        f"CAST({alias}.data_envio_contagem AS TEXT))"
    )


def _servidores_relatorio(d_ini=None, d_fim=None):
    """Lista os agentes que podem ter relatorio no periodo consultado.

    Alem dos ativos, inclui os inativos que registraram producao no intervalo:
    sem isso o historico de quem saiu da equipe fica inacessivel pela tela,
    mesmo continuando integro no banco.
    """
    conn = _get_db()
    try:
        ativos = _rows_dict(conn.execute(
            """SELECT nome,
                      COALESCE(NULLIF(nome_completo,''), nome) AS nome_exibicao,
                      1 AS ativo
                 FROM agentes
                WHERE COALESCE(ativo,1)=1"""
        ).fetchall())
        inativos = []
        if d_ini and d_fim:
            partes = []
            for fonte in producao_operacional.FONTES:
                if not db_core.table_exists(conn, fonte["tabela"]):
                    continue
                alias = fonte["alias"]
                data_expr = producao_operacional._data_expr(fonte)
                vinculo_direto = producao_operacional._vinculo_agente_sql(fonte, alias)
                if vinculo_direto:
                    vinculo_sql = vinculo_direto
                    origem = f"{fonte['tabela']} {alias}"
                elif db_core.table_exists(conn, fonte["agente_table"]):
                    vinculo_sql = "pa.id_agente=ag.id_agente"
                    origem = (
                        f"{fonte['tabela']} {alias} "
                        f"JOIN {fonte['agente_table']} pa "
                        f"ON pa.{fonte['agente_fk']}={alias}.{fonte['id_col']}"
                    )
                else:
                    continue
                partes.append(
                    f"""EXISTS (SELECT 1
                                  FROM {origem}
                                 WHERE {vinculo_sql}
                                   AND {data_expr} BETWEEN ? AND ?)"""
                )
            existe = " OR ".join(partes)
            if existe:
                params = []
                for _ in range(existe.count("BETWEEN")):
                    params.extend([d_ini, d_fim])
                inativos = _rows_dict(conn.execute(
                    f"""SELECT ag.nome,
                               COALESCE(NULLIF(ag.nome_completo,''), ag.nome) AS nome_exibicao,
                               0 AS ativo
                          FROM agentes ag
                         WHERE COALESCE(ag.ativo,1)=0
                           AND ({existe})""",
                    params,
                ).fetchall())
        for item in inativos:
            item["nome_exibicao"] = f"{item['nome_exibicao']} (inativo)"
        servidores = ativos + inativos
        servidores.sort(key=lambda item: (item["nome_exibicao"], item["nome"]))
        return servidores
    finally:
        conn.close()


def _total_tratamentos_depositos_setor(conn, d_ini, d_fim):
    if not _has_column(conn, "tratamentos", "qtd_depositos_tratados"):
        return 0
    row = conn.execute(
        """
        SELECT COALESCE(SUM(COALESCE(t.qtd_depositos_tratados,0)),0) AS total
          FROM tratamentos t
          JOIN visitas v ON v.id_visita=t.id_visita
         WHERE v.data BETWEEN ? AND ?
        """,
        (d_ini, d_fim),
    ).fetchone()
    return utils_core.safe_int(row["total"] if row else 0)


def _total_tratamentos_depositos_agente(conn, nome, d_ini, d_fim):
    if not _has_column(conn, "tratamentos", "qtd_depositos_tratados"):
        return 0
    row = conn.execute(
        """
        SELECT COALESCE(SUM(qtd),0) AS total
          FROM (
                SELECT DISTINCT t.id, COALESCE(t.qtd_depositos_tratados,0) AS qtd
                  FROM tratamentos t
                  JOIN visitas v ON v.id_visita=t.id_visita
                  JOIN visita_agentes va ON va.id_visita=v.id_visita
                  JOIN agentes a ON a.id_agente=va.id_agente
                 WHERE a.nome=? AND v.data BETWEEN ? AND ?
               ) base
        """,
        (nome, d_ini, d_fim),
    ).fetchone()
    return utils_core.safe_int(row["total"] if row else 0)


def _resumo_esporotricose_agente(nome, d_ini, d_fim):
    filtros = {"agente": nome, "d_ini": d_ini, "d_fim": d_fim}
    resumo = esporotricose_core.resumo(_db_target(), filtros)
    dashboard = esporotricose_core.dashboard(_db_target(), filtros)
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
        _db_target(),
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
        item = _row_dict(row)
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


def _resumo_registro_geografico_agente(nome, d_ini, d_fim):
    conn = _get_db()
    try:
        registro_geografico_core.ensure_schema(conn, current_app.config.get("BASE_DIR"))
        if not (
            producao_operacional._table_exists(conn, "registro_geografico_imoveis")
            and producao_operacional._table_exists(conn, "registro_geografico_imovel_agentes")
        ):
            return _registro_geografico_vazio()
        base_params = (nome, d_ini, d_fim)
        totais = conn.execute(
            """
            SELECT COUNT(DISTINCT CASE WHEN COALESCE(i.tipo,'') NOT IN ('REF') THEN i.id_imovel END) AS imoveis,
                   COUNT(DISTINCT i.data_atualizacao) AS dias,
                   COUNT(DISTINCT i.id_localidade) AS localidades,
                   COUNT(DISTINCT i.quarteirao) AS quarteiroes,
                   SUM(CASE WHEN i.tipo='R' THEN 1 ELSE 0 END) AS residencias,
                   SUM(CASE WHEN i.tipo='C' THEN 1 ELSE 0 END) AS comercios,
                   SUM(CASE WHEN i.tipo='TB' THEN 1 ELSE 0 END) AS terrenos_baldios,
                   SUM(CASE WHEN i.tipo='PE' THEN 1 ELSE 0 END) AS pontos_estrategicos
              FROM registro_geografico_imoveis i
              JOIN registro_geografico_imovel_agentes ia ON ia.id_imovel=i.id_imovel
              JOIN agentes ag ON ag.id_agente=ia.id_agente
             WHERE ag.nome=? AND i.data_atualizacao BETWEEN ? AND ?
            """,
            base_params,
        ).fetchone()
        por_tipo = conn.execute(
            """
            SELECT COALESCE(NULLIF(i.tipo,''), '-') AS tipo,
                   COUNT(DISTINCT i.id_imovel) AS total
              FROM registro_geografico_imoveis i
              JOIN registro_geografico_imovel_agentes ia ON ia.id_imovel=i.id_imovel
              JOIN agentes ag ON ag.id_agente=ia.id_agente
             WHERE ag.nome=? AND i.data_atualizacao BETWEEN ? AND ?
               AND COALESCE(i.tipo,'') NOT IN ('REF')
             GROUP BY COALESCE(NULLIF(i.tipo,''), '-')
             ORDER BY total DESC, tipo
            """,
            base_params,
        ).fetchall()
        quarteirao_order = _numeric_text_order(conn, "i.quarteirao")
        por_quarteirao = conn.execute(
            f"""
            SELECT i.localidade,
                   i.quarteirao,
                   COUNT(DISTINCT i.id_imovel) AS imoveis,
                   COUNT(DISTINCT NULLIF(TRIM(i.logradouro),'')) AS logradouros,
                   MAX(i.data_atualizacao) AS ultima_atualizacao
              FROM registro_geografico_imoveis i
              JOIN registro_geografico_imovel_agentes ia ON ia.id_imovel=i.id_imovel
              JOIN agentes ag ON ag.id_agente=ia.id_agente
             WHERE ag.nome=? AND i.data_atualizacao BETWEEN ? AND ?
             GROUP BY i.localidade, i.quarteirao
             ORDER BY ultima_atualizacao DESC, i.localidade,
                      {quarteirao_order}, LOWER(CAST(i.quarteirao AS TEXT))
             LIMIT 40
            """,
            base_params,
        ).fetchall()
    finally:
        conn.close()

    data = _row_dict(totais)
    return {
        "totais": {key: utils_core.safe_int(data.get(key)) for key in (
            "imoveis", "dias", "localidades", "quarteiroes",
            "residencias", "comercios", "terrenos_baldios", "pontos_estrategicos",
        )},
        "por_tipo": _rows_dict(por_tipo),
        "por_quarteirao": [
            {
                **_row_dict(row),
                "quarteirao": _quarteirao_display(row["quarteirao"]),
            }
            for row in por_quarteirao
        ],
    }


def _registro_geografico_vazio():
    return {
        "totais": {
            "imoveis": 0,
            "dias": 0,
            "localidades": 0,
            "quarteiroes": 0,
            "residencias": 0,
            "comercios": 0,
            "terrenos_baldios": 0,
            "pontos_estrategicos": 0,
        },
        "por_tipo": [],
        "por_quarteirao": [],
    }


def _quarteirao_display(value):
    text = str(value or "").strip()
    if text.replace(".0", "").isdigit():
        return str(int(float(text)))
    return text


def _resumo_laboratorio_agente(nome, d_ini, d_fim):
    conn = _get_db()
    try:
        ovitrampas_core.ensure_schema(conn)
        larvas = _laboratorio_larvas(conn, nome, d_ini, d_fim)
        ovitrampas = _laboratorio_ovitrampas(conn, nome, d_ini, d_fim)
    finally:
        conn.close()
    total_leituras = larvas["leituras"] + ovitrampas["leituras"]
    dias = len(set(larvas["dias"]) | set(ovitrampas["dias"]))
    return {
        "totais": {
            "leituras": total_leituras,
            "dias": dias,
            "larvas": larvas["leituras"],
            "tubos": larvas["tubos"],
            "larvas_positivas": larvas["positivas"],
            "ovitrampas": ovitrampas["leituras"],
            "ovitrampas_positivas": ovitrampas["positivas"],
            "ovos": ovitrampas["ovos"],
        },
        "larvas": larvas,
        "ovitrampas": ovitrampas,
    }


def _laboratorio_larvas(conn, nome, d_ini, d_fim):
    vazio = {"leituras": 0, "tubos": 0, "positivas": 0, "dias": [], "por_mes": []}
    if not producao_operacional._table_exists(conn, "resultados_laboratorio"):
        return vazio
    params = (nome, d_ini, d_fim)
    mes_expr = db_core.month_expression(
        "COALESCE(rl.data_leitura, rl.data_coleta)"
    )
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT rl.id_resultado) AS leituras,
               COUNT(DISTINCT rl.num_tubo) AS tubos,
               COUNT(DISTINCT COALESCE(rl.data_leitura, rl.data_coleta)) AS dias,
               SUM(CASE WHEN COALESCE(rl.aegypt_larvas,0) + COALESCE(rl.aegypt_pupas,0)
                           + COALESCE(rl.aegypt_exuvias,0) + COALESCE(rl.aegypt_adulto,0)
                           + COALESCE(rl.albopictus_larvas,0) + COALESCE(rl.albopictus_pupas,0)
                           + COALESCE(rl.albopictus_exuvias,0) + COALESCE(rl.albopictus_adulto,0)
                           + COALESCE(rl.outra_larvas,0) + COALESCE(rl.outra_pupas,0)
                           + COALESCE(rl.outra_exuvias,0) + COALESCE(rl.outra_adulto,0) > 0
                        THEN 1 ELSE 0 END) AS positivas
          FROM resultados_laboratorio rl
         WHERE lower(trim(rl.laboratorista))=lower(trim(?))
           AND COALESCE(rl.data_leitura, rl.data_coleta) BETWEEN ? AND ?
        """,
        params,
    ).fetchone()
    por_mes = conn.execute(
        f"""
        SELECT {mes_expr} AS mes,
               COUNT(DISTINCT rl.id_resultado) AS leituras
          FROM resultados_laboratorio rl
         WHERE lower(trim(rl.laboratorista))=lower(trim(?))
           AND COALESCE(rl.data_leitura, rl.data_coleta) BETWEEN ? AND ?
         GROUP BY {mes_expr}
         ORDER BY mes
        """,
        params,
    ).fetchall()
    dias = conn.execute(
        """
        SELECT DISTINCT COALESCE(rl.data_leitura, rl.data_coleta) AS dia
          FROM resultados_laboratorio rl
         WHERE lower(trim(rl.laboratorista))=lower(trim(?))
           AND COALESCE(rl.data_leitura, rl.data_coleta) BETWEEN ? AND ?
         ORDER BY dia
        """,
        params,
    ).fetchall()
    data = _row_dict(row)
    dias_data = _rows_dict(dias)
    return {
        "leituras": utils_core.safe_int(data.get("leituras")),
        "tubos": utils_core.safe_int(data.get("tubos")),
        "positivas": utils_core.safe_int(data.get("positivas")),
        "dias": [r["dia"] for r in dias_data if r["dia"]],
        "por_mes": _rows_dict(por_mes),
    }


def _laboratorio_ovitrampas(conn, nome, d_ini, d_fim):
    vazio = {"leituras": 0, "positivas": 0, "ovos": 0, "dias": [], "por_mes": []}
    if not (
        producao_operacional._table_exists(conn, "ovitrampas_leituras")
        and producao_operacional._table_exists(conn, "agentes")
    ):
        return vazio
    params = (nome, d_ini, d_fim)
    data_expr = _ovitrampa_date_expression("l")
    mes_expr = db_core.month_expression(data_expr)
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT l.id_leitura) AS leituras,
               SUM(CASE WHEN COALESCE(l.ovos,0)>0 THEN 1 ELSE 0 END) AS positivas,
               SUM(COALESCE(l.ovos,0)) AS ovos
          FROM ovitrampas_leituras l
          JOIN agentes ag ON ag.id_agente=l.id_laboratorista
         WHERE ag.nome=?
           AND {data_expr} BETWEEN ? AND ?
        """,
        params,
    ).fetchone()
    por_mes = conn.execute(
        f"""
        SELECT {mes_expr} AS mes,
               COUNT(DISTINCT l.id_leitura) AS leituras,
               SUM(COALESCE(l.ovos,0)) AS ovos
          FROM ovitrampas_leituras l
          JOIN agentes ag ON ag.id_agente=l.id_laboratorista
         WHERE ag.nome=?
           AND {data_expr} BETWEEN ? AND ?
         GROUP BY {mes_expr}
         ORDER BY mes
        """,
        params,
    ).fetchall()
    dias = conn.execute(
        f"""
        SELECT DISTINCT {data_expr} AS dia
          FROM ovitrampas_leituras l
          JOIN agentes ag ON ag.id_agente=l.id_laboratorista
         WHERE ag.nome=?
           AND {data_expr} BETWEEN ? AND ?
         ORDER BY dia
        """,
        params,
    ).fetchall()
    data = _row_dict(row)
    dias_data = _rows_dict(dias)
    return {
        "leituras": utils_core.safe_int(data.get("leituras")),
        "positivas": utils_core.safe_int(data.get("positivas")),
        "ovos": utils_core.safe_int(data.get("ovos")),
        "dias": [r["dia"] for r in dias_data if r["dia"]],
        "por_mes": _rows_dict(por_mes),
    }


def _resumo_laboratorio_setor(d_ini, d_fim):
    conn = _get_db()
    try:
        ovitrampas_core.ensure_schema(conn)
        larvas = _laboratorio_larvas_setor(conn, d_ini, d_fim)
        ovitrampas = _laboratorio_ovitrampas_setor(conn, d_ini, d_fim)
    finally:
        conn.close()
    total_leituras = larvas["leituras"] + ovitrampas["leituras"]
    dias = len(set(larvas["dias"]) | set(ovitrampas["dias"]))
    return {
        "totais": {
            "leituras": total_leituras,
            "dias": dias,
            "larvas": larvas["leituras"],
            "tubos": larvas["tubos"],
            "larvas_positivas": larvas["positivas"],
            "ovitrampas": ovitrampas["leituras"],
            "ovitrampas_positivas": ovitrampas["positivas"],
            "ovos": ovitrampas["ovos"],
        },
        "larvas": larvas,
        "ovitrampas": ovitrampas,
    }


def _laboratorio_larvas_setor(conn, d_ini, d_fim):
    vazio = {"leituras": 0, "tubos": 0, "positivas": 0, "dias": [], "por_mes": []}
    if not producao_operacional._table_exists(conn, "resultados_laboratorio"):
        return vazio
    params = (d_ini, d_fim)
    mes_expr = db_core.month_expression(
        "COALESCE(rl.data_leitura, rl.data_coleta)"
    )
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT rl.id_resultado) AS leituras,
               COUNT(DISTINCT rl.num_tubo) AS tubos,
               COUNT(DISTINCT COALESCE(rl.data_leitura, rl.data_coleta)) AS dias,
               SUM(CASE WHEN COALESCE(rl.aegypt_larvas,0) + COALESCE(rl.aegypt_pupas,0)
                           + COALESCE(rl.aegypt_exuvias,0) + COALESCE(rl.aegypt_adulto,0)
                           + COALESCE(rl.albopictus_larvas,0) + COALESCE(rl.albopictus_pupas,0)
                           + COALESCE(rl.albopictus_exuvias,0) + COALESCE(rl.albopictus_adulto,0)
                           + COALESCE(rl.outra_larvas,0) + COALESCE(rl.outra_pupas,0)
                           + COALESCE(rl.outra_exuvias,0) + COALESCE(rl.outra_adulto,0) > 0
                        THEN 1 ELSE 0 END) AS positivas
          FROM resultados_laboratorio rl
         WHERE COALESCE(rl.data_leitura, rl.data_coleta) BETWEEN ? AND ?
        """,
        params,
    ).fetchone()
    por_mes = conn.execute(
        f"""
        SELECT {mes_expr} AS mes,
               COUNT(DISTINCT rl.id_resultado) AS leituras
          FROM resultados_laboratorio rl
         WHERE COALESCE(rl.data_leitura, rl.data_coleta) BETWEEN ? AND ?
         GROUP BY {mes_expr}
         ORDER BY mes
        """,
        params,
    ).fetchall()
    dias = conn.execute(
        """
        SELECT DISTINCT COALESCE(rl.data_leitura, rl.data_coleta) AS dia
          FROM resultados_laboratorio rl
         WHERE COALESCE(rl.data_leitura, rl.data_coleta) BETWEEN ? AND ?
         ORDER BY dia
        """,
        params,
    ).fetchall()
    data = _row_dict(row)
    dias_data = _rows_dict(dias)
    return {
        "leituras": utils_core.safe_int(data.get("leituras")),
        "tubos": utils_core.safe_int(data.get("tubos")),
        "positivas": utils_core.safe_int(data.get("positivas")),
        "dias": [r["dia"] for r in dias_data if r["dia"]],
        "por_mes": _rows_dict(por_mes),
    }


def _laboratorio_ovitrampas_setor(conn, d_ini, d_fim):
    vazio = {"leituras": 0, "positivas": 0, "ovos": 0, "dias": [], "por_mes": []}
    if not producao_operacional._table_exists(conn, "ovitrampas_leituras"):
        return vazio
    params = (d_ini, d_fim)
    data_expr = _ovitrampa_date_expression("l")
    mes_expr = db_core.month_expression(data_expr)
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT l.id_leitura) AS leituras,
               SUM(CASE WHEN COALESCE(l.ovos,0)>0 THEN 1 ELSE 0 END) AS positivas,
               SUM(COALESCE(l.ovos,0)) AS ovos
          FROM ovitrampas_leituras l
         WHERE {data_expr} BETWEEN ? AND ?
        """,
        params,
    ).fetchone()
    por_mes = conn.execute(
        f"""
        SELECT {mes_expr} AS mes,
               COUNT(DISTINCT l.id_leitura) AS leituras,
               SUM(COALESCE(l.ovos,0)) AS ovos
          FROM ovitrampas_leituras l
         WHERE {data_expr} BETWEEN ? AND ?
         GROUP BY {mes_expr}
         ORDER BY mes
        """,
        params,
    ).fetchall()
    dias = conn.execute(
        f"""
        SELECT DISTINCT {data_expr} AS dia
          FROM ovitrampas_leituras l
         WHERE {data_expr} BETWEEN ? AND ?
         ORDER BY dia
        """,
        params,
    ).fetchall()
    data = _row_dict(row)
    dias_data = _rows_dict(dias)
    return {
        "leituras": utils_core.safe_int(data.get("leituras")),
        "positivas": utils_core.safe_int(data.get("positivas")),
        "ovos": utils_core.safe_int(data.get("ovos")),
        "dias": [r["dia"] for r in dias_data if r["dia"]],
        "por_mes": _rows_dict(por_mes),
    }


def _resumo_ovitrampas_setor(d_ini, d_fim):
    conn = _get_db()
    try:
        ovitrampas_core.ensure_schema(conn)
        agentes_agg = _distinct_aggregate(
            conn,
            "COALESCE(NULLIF(ag.nome_completo,''), ag.nome)",
        )
        rows = conn.execute(
            f"""
            SELECT e.data,
                   e.movimento,
                   e.ciclo,
                   e.observacoes,
                   g.nome AS grupo,
                   g.localidades AS localidades,
                   {agentes_agg} AS agentes
              FROM {ovitrampas_core.CAL_EVENTOS_TABLE} e
              LEFT JOIN {ovitrampas_core.CAL_GRUPOS_TABLE} g ON g.id_grupo=e.id_grupo
              LEFT JOIN {ovitrampas_core.CAL_AGENTES_TABLE} ea ON ea.id_evento=e.id_evento
              LEFT JOIN agentes ag ON ag.id_agente=ea.id_agente
             WHERE e.data BETWEEN ? AND ?
               AND e.movimento <> 'feriado'
             GROUP BY e.id_evento, e.data, e.movimento, e.ciclo,
                      e.observacoes, g.nome, g.localidades
             ORDER BY e.data, e.id_evento
            """,
            (d_ini, d_fim),
        ).fetchall()
    finally:
        conn.close()

    eventos = []
    por_movimento = {}
    por_grupo = {}
    por_agente = {}
    dias = set()
    grupos = set()
    ciclos = set()
    agentes = set()
    movimentos = getattr(ovitrampas_core, "MOVIMENTOS", {})
    for row in rows:
        item = _row_dict(row)
        movimento = item.get("movimento") or ""
        item["movimento_label"] = movimentos.get(movimento, movimento)
        eventos.append(item)
        dias.add(item.get("data"))
        if item.get("grupo"):
            grupos.add(item["grupo"])
            por_grupo[item["grupo"]] = por_grupo.get(item["grupo"], 0) + 1
        if item.get("ciclo"):
            ciclos.add(item["ciclo"])
        por_movimento[item["movimento_label"]] = por_movimento.get(item["movimento_label"], 0) + 1
        for agente in [a.strip() for a in (item.get("agentes") or "").split(",") if a.strip()]:
            agentes.add(agente)
            por_agente[agente] = por_agente.get(agente, 0) + 1

    return {
        "totais": {
            "eventos": len(eventos),
            "dias": len(dias),
            "grupos": len(grupos),
            "ciclos": len(ciclos),
            "agentes": len(agentes),
        },
        "por_movimento": [
            {"movimento": nome_mov, "total": total}
            for nome_mov, total in sorted(por_movimento.items())
        ],
        "por_grupo": [
            {"grupo": grupo, "total": total}
            for grupo, total in sorted(por_grupo.items(), key=lambda item: (-item[1], item[0]))
        ],
        "por_agente": [
            {"agente": agente, "total": total}
            for agente, total in sorted(por_agente.items(), key=lambda item: (-item[1], item[0]))
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
    if codigo == "ACOES_SETOR":
        return (
            f"{utils_core.safe_int(extras.get('educativas'))} educativas, "
            f"{utils_core.safe_int(extras.get('limpezas'))} limpezas"
        )
    if codigo == "OVITRAMPAS":
        return f"{utils_core.safe_int(atividade.get('registros'))} eventos"
    return ""


def _obter_dados_setor(d_ini, d_fim):
    resumo = producao_operacional.resumo(
        _db_target(),
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
        "ovitrampas": _resumo_ovitrampas_setor(d_ini, d_fim),
        "laboratorio": _resumo_laboratorio_setor(d_ini, d_fim),
        "agentes": _producao_agentes_setor(d_ini, d_fim),
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def _join_agente_fonte(fonte, id_expr):
    """JOIN com agentes, seja por tabela de vinculo ou direto na linha."""
    vinculo_direto = producao_operacional._vinculo_agente_sql(fonte, fonte["alias"])
    if vinculo_direto:
        return f"JOIN agentes ag ON {vinculo_direto}"
    return (
        f"JOIN {fonte['agente_table']} pa ON pa.{fonte['agente_fk']}={id_expr} "
        f"JOIN agentes ag ON ag.id_agente=pa.id_agente"
    )


def _producao_agentes_setor(d_ini, d_fim):
    conn = _get_db()
    try:
        agentes = {}
        fontes = [
            fonte for fonte in producao_operacional.FONTES
            if producao_operacional._fonte_disponivel(conn, fonte)
        ]
        for fonte in fontes:
            alias = fonte["alias"]
            id_expr = f"{alias}.{fonte['id_col']}"
            data_expr = producao_operacional._data_expr(fonte)
            localidade_expr = fonte["localidade_expr"]
            joins = fonte.get("joins") or ""
            dias_agg = _distinct_aggregate(conn, data_expr)
            localidades_agg = _distinct_aggregate(
                conn,
                f"COALESCE({localidade_expr}, '')",
            )
            rows = conn.execute(
                f"""
                SELECT COALESCE(NULLIF(ag.nome_completo,''), ag.nome) AS agente,
                       COUNT(DISTINCT {id_expr}) AS registros,
                       {dias_agg} AS dias,
                       {localidades_agg} AS localidades
                  FROM {fonte['tabela']} {alias}
                  {_join_agente_fonte(fonte, id_expr)}
                  {joins}
                 WHERE {data_expr} BETWEEN ? AND ?
                 GROUP BY ag.id_agente, ag.nome, ag.nome_completo
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
        duracao_v = _duration_expression(conn, "v")
        duracao_e = _duration_expression(conn, "e")
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
            SELECT periodo,
                   COUNT(DISTINCT fonte || ':' || CAST(id_visita AS TEXT)) AS total,
                   COUNT(DISTINCT data) AS dias
              FROM (
                    SELECT 'vetor' AS fonte,
                           v.id_visita,
                           v.data,
                           CASE WHEN v.hora_inicio < '12:00' THEN 'Manha' ELSE 'Tarde' END AS periodo
                      FROM visitas v
                     WHERE v.data BETWEEN ? AND ?
                       AND v.hora_inicio IS NOT NULL
                       AND TRIM(CAST(v.hora_inicio AS TEXT))<>''
                    UNION ALL
                    SELECT 'esporo' AS fonte,
                           e.id_visita,
                           e.data,
                           CASE WHEN e.hora_inicio < '12:00' THEN 'Manha' ELSE 'Tarde' END AS periodo
                      FROM esporotricose_visitas e
                     WHERE e.data BETWEEN ? AND ?
                       AND e.hora_inicio IS NOT NULL
                       AND TRIM(CAST(e.hora_inicio AS TEXT))<>''
                   ) base
             GROUP BY periodo
             ORDER BY periodo
            """,
            (d_ini, d_fim, d_ini, d_fim),
        ).fetchall()

        duracao_por_tipo = conn.execute(
            f"""
            SELECT tipo, COUNT(*) AS n,
                   ROUND(AVG(dur),1) AS media,
                   ROUND(MIN(dur),1) AS minimo,
                   ROUND(MAX(dur),1) AS maximo
              FROM (
                    SELECT v.tipo AS tipo,
                           {duracao_v} AS dur
                      FROM visitas v
                     WHERE v.data BETWEEN ? AND ?
                       AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
                    UNION ALL
                    SELECT 'Esporotricose' AS tipo,
                           {duracao_e} AS dur
                      FROM esporotricose_visitas e
                     WHERE e.data BETWEEN ? AND ?
                       AND e.hora_inicio IS NOT NULL AND e.hora_fim IS NOT NULL
                   ) base
             WHERE dur BETWEEN 1 AND 240
             GROUP BY tipo
             ORDER BY media DESC, tipo
            """,
            (d_ini, d_fim, d_ini, d_fim),
        ).fetchall()

        duracao_por_acesso = conn.execute(
            f"""
            SELECT grupo, COUNT(*) AS n,
                   ROUND(AVG(dur),1) AS media,
                   ROUND(MIN(dur),1) AS minimo,
                   ROUND(MAX(dur),1) AS maximo
              FROM (
                    SELECT CASE WHEN LOWER(COALESCE(v.visita,'')) IN ('normal','recuperado')
                                THEN 'Acessados' ELSE 'Nao acessados' END AS grupo,
                           {duracao_v} AS dur
                      FROM visitas v
                     WHERE v.data BETWEEN ? AND ?
                       AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
                    UNION ALL
                    SELECT CASE WHEN LOWER(COALESCE(e.visita,'')) IN ('normal','recuperado')
                                THEN 'Acessados' ELSE 'Nao acessados' END AS grupo,
                           {duracao_e} AS dur
                      FROM esporotricose_visitas e
                     WHERE e.data BETWEEN ? AND ?
                       AND e.hora_inicio IS NOT NULL AND e.hora_fim IS NOT NULL
                   ) base
             WHERE dur BETWEEN 1 AND 240
             GROUP BY grupo
             ORDER BY grupo
            """,
            (d_ini, d_fim, d_ini, d_fim),
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
        tratamentos_depositos_setor = _total_tratamentos_depositos_setor(conn, d_ini, d_fim)

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

    totais_d = _row_dict(totais)
    total = utils_core.safe_int(totais_d.get("total"))
    dias = utils_core.safe_int(totais_d.get("dias"))
    dep_d = _row_dict(dep)
    dep_d["tratados"] = (
        utils_core.safe_int(dep_d.get("tratados"))
        + tratamentos_depositos_setor
    )
    coletas_d = _row_dict(coletas)
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
        "por_tipo": _rows_dict(por_tipo),
        "por_status": _rows_dict(por_status),
        "por_periodo": [
            {
                **_row_dict(row),
                "media_dia": round((row["total"] or 0) / (row["dias"] or 1), 1),
            }
            for row in por_periodo
        ],
        "duracao_por_tipo": _rows_dict(duracao_por_tipo),
        "duracao_por_acesso": _rows_dict(duracao_por_acesso),
        "depositos": dep_d,
        "coletas": {
            **coletas_d,
            "indice": round(pos_aeg / total_coletas * 100, 1) if total_coletas else 0,
        },
    }


def _obter_dados(nome, d_ini, d_fim):
    conn = _get_db()
    duracao_v = _duration_expression(conn, "v")
    duracao_e = _duration_expression(conn, "e")
    semana_expr = _week_start_expression(conn, "v.data")
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
            f"SELECT {semana_expr} as semana, "
            f"COUNT(DISTINCT v.id_visita) as total {base_w} GROUP BY semana ORDER BY semana", p
        ).fetchall()

        dep = conn.execute("""
            SELECT SUM(d.inspecionado) as insp, SUM(d.eliminado) as elim, SUM(d.tratado) as trat
            FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
            JOIN agentes a ON a.id_agente=va.id_agente
            LEFT JOIN depositos_inspecionados d ON d.id_visita=v.id_visita
            WHERE a.nome=? AND v.data BETWEEN ? AND ?""", p).fetchone()
        tratamentos_depositos_agente = _total_tratamentos_depositos_agente(conn, nome, d_ini, d_fim)

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

        tbo_raw = conn.execute(f"""
            SELECT
                CASE WHEN LOWER(sub.visita) IN ('normal','recuperado') THEN 'acessados'
                     ELSE 'nao_acessados' END as grupo,
                COUNT(*) as n, ROUND(AVG(dur),1) as media,
                ROUND(MIN(dur),1) as minimo, ROUND(MAX(dur),1) as maximo
            FROM (SELECT v.visita,
                  {duracao_v} AS dur
                  FROM visitas v JOIN visita_agentes va ON va.id_visita=v.id_visita
                  JOIN agentes a ON a.id_agente=va.id_agente
                  WHERE a.nome=? AND v.data BETWEEN ? AND ? AND v.tipo=?
                  AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL) sub
            WHERE dur BETWEEN 1 AND 240 GROUP BY grupo""",
            p + [work_types.primary_duration_work_type_code()],
        ).fetchall()
        esporotricose_core.ensure_schema(conn)
        duracao_tbo_raw = conn.execute(f"""
            SELECT COUNT(*) AS n,
                   ROUND(AVG(dur),1) AS media,
                   ROUND(MIN(dur),1) AS minimo,
                   ROUND(MAX(dur),1) AS maximo
              FROM (
                    SELECT {duracao_v} AS dur
                      FROM visitas v
                      JOIN visita_agentes va ON va.id_visita=v.id_visita
                      JOIN agentes a ON a.id_agente=va.id_agente
                     WHERE a.nome=? AND v.data BETWEEN ? AND ? AND v.tipo=?
                       AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
                   ) sub
             WHERE dur BETWEEN 1 AND 240""",
            p + [work_types.primary_duration_work_type_code()],
        ).fetchone()
        duracao_esporo_raw = conn.execute(f"""
            SELECT COUNT(*) AS n,
                   ROUND(AVG(dur),1) AS media,
                   ROUND(MIN(dur),1) AS minimo,
                   ROUND(MAX(dur),1) AS maximo
              FROM (
                    SELECT {duracao_e} AS dur
                      FROM esporotricose_visitas e
                      JOIN esporotricose_visita_agentes va ON va.id_visita=e.id_visita
                      JOIN agentes a ON a.id_agente=va.id_agente
                     WHERE a.nome=? AND e.data BETWEEN ? AND ?
                       AND e.hora_inicio IS NOT NULL AND e.hora_fim IS NOT NULL
                   ) sub
             WHERE dur BETWEEN 1 AND 240""",
            p,
        ).fetchone()
        duracao_total_raw = conn.execute(f"""
            SELECT COUNT(*) AS n,
                   ROUND(AVG(dur),1) AS media,
                   ROUND(MIN(dur),1) AS minimo,
                   ROUND(MAX(dur),1) AS maximo
              FROM (
                    SELECT {duracao_v} AS dur
                      FROM visitas v
                      JOIN visita_agentes va ON va.id_visita=v.id_visita
                      JOIN agentes a ON a.id_agente=va.id_agente
                     WHERE a.nome=? AND v.data BETWEEN ? AND ? AND v.tipo=?
                       AND v.hora_inicio IS NOT NULL AND v.hora_fim IS NOT NULL
                    UNION ALL
                    SELECT {duracao_e} AS dur
                      FROM esporotricose_visitas e
                      JOIN esporotricose_visita_agentes ea ON ea.id_visita=e.id_visita
                      JOIN agentes ag ON ag.id_agente=ea.id_agente
                     WHERE ag.nome=? AND e.data BETWEEN ? AND ?
                       AND e.hora_inicio IS NOT NULL AND e.hora_fim IS NOT NULL
                   ) sub
             WHERE dur BETWEEN 1 AND 240""",
            p + [work_types.primary_duration_work_type_code()] + p,
        ).fetchone()

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
        agente_row = conn.execute(
            "SELECT COALESCE(NULLIF(nome_completo,''), nome) AS nome_exibicao FROM agentes WHERE nome=?",
            (nome,),
        ).fetchone()
        agente_exibicao = agente_row["nome_exibicao"] if agente_row else nome
    finally:
        conn.close()

    totais_d = _row_dict(totais)
    dep_d = _row_dict(dep)
    dep_d["trat"] = (
        utils_core.safe_int(dep_d.get("trat"))
        + tratamentos_depositos_agente
    )
    col_d = _row_dict(col)
    tbo_rows = _rows_dict(tbo_raw)
    tv = utils_core.safe_int(totais_d.get("total", 0))
    dias = utils_core.safe_int(totais_d.get("dias", 0))
    tc = utils_core.safe_int(col_d.get("total", 0))
    ta = utils_core.safe_int(col_d.get("pos_aeg", 0))
    duracao_tbo = _duracao_dict(duracao_tbo_raw)
    duracao_esporo = _duracao_dict(duracao_esporo_raw)
    duracao_total = _duracao_dict(duracao_total_raw)

    por_periodo = {}
    for r in por_periodo_raw:
        rd = _row_dict(r)
        dias_p = utils_core.safe_int(rd.get("dias_periodo")) or 1
        por_periodo[rd["periodo"]] = {
            "total": utils_core.safe_int(rd.get("total", 0)),
            "media": round(utils_core.safe_int(rd.get("total", 0)) / dias_p, 1),
        }

    comparacao = {}
    if media_geral_raw:
        mg = _row_dict(media_geral_raw)
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
    registro_geografico = _resumo_registro_geografico_agente(nome, d_ini, d_fim)
    laboratorio = _resumo_laboratorio_agente(nome, d_ini, d_fim)
    comparacao_esporotricose = {}
    if comparacao_esporo_raw:
        ce = _row_dict(comparacao_esporo_raw)
        comparacao_esporotricose = {
            "media_visitas": round(ce.get("media_visitas") or 0, 1),
            "media_dia": round(ce.get("media_dia") or 0, 1),
            "media_animais": round(ce.get("media_animais") or 0, 1),
            "media_feridas": round(ce.get("media_feridas") or 0, 1),
            "media_fechadas": round(ce.get("media_fechadas") or 0, 1),
            "media_recusas": round(ce.get("media_recusas") or 0, 1),
            "num_agentes": utils_core.safe_int(ce.get("num_agentes")),
        }

    # A producao diaria precisa somar as sete atividades. A consulta acima olha
    # so a tabela visitas, entao dias de esporotricose, recolhimento, amostra,
    # BRI, acao ou ovitrampa nao apareciam. Mantemos a serie de visitas como
    # reserva para o caso de a producao vir vazia.
    por_dia_visitas = _rows_dict(por_dia)
    por_dia_producao = [
        {"data": item.get("dia"), "total": item.get("registros", 0)}
        for item in (producao.get("por_dia") or [])
    ]

    return {
        "agente": agente_exibicao, "d_ini": d_ini, "d_fim": d_fim,
        "totais": totais_d,
        "por_tipo": _rows_dict(por_tipo),
        "por_loc": _rows_dict(por_loc),
        "por_dia": por_dia_producao or por_dia_visitas,
        "por_dia_visitas": por_dia_visitas,
        "evolucao": _rows_dict(evolucao),
        "dep": dep_d,
        "col": col_d,
        "tbo_por_grupo": {r["grupo"]: r for r in tbo_rows},
        "duracao_visitas": {
            "tbo": duracao_tbo,
            "esporotricose": duracao_esporo,
            "total": duracao_total,
            "por_grupo": {r["grupo"]: r for r in tbo_rows},
        },
        "taxa_normal": round(utils_core.safe_int(totais_d.get("normais", 0)) / tv * 100, 1) if tv else 0,
        "media_dia": round(tv / dias, 1) if dias else 0,
        "por_periodo": por_periodo,
        "comparacao": comparacao,
        "producao_operacional": producao,
        "ovitrampas": ovitrampas,
        "registro_geografico": registro_geografico,
        "laboratorio": laboratorio,
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


def _duracao_dict(row):
    data = _row_dict(row)
    return {
        "n": utils_core.safe_int(data.get("n")),
        "media": data.get("media") if data.get("media") is not None else None,
        "minimo": data.get("minimo") if data.get("minimo") is not None else None,
        "maximo": data.get("maximo") if data.get("maximo") is not None else None,
    }


@bp.route("/relatorio-agente")
@login_required
def page():
    d_ini = request.args.get("d_ini", utils_core.data_n_dias(30))
    d_fim = request.args.get("d_fim", utils_core.hoje())
    servidores = _servidores_relatorio(d_ini, d_fim)
    agente_sel = request.args.get("agente", "")
    selecionado = next((item for item in servidores if item["nome"] == agente_sel), None)
    return render_template(
        "relatorio_agente.html",
        agente_sel=agente_sel,
        agente_sel_nome=(selecionado or {}).get("nome_exibicao", agente_sel),
        servidores=servidores,
        d_ini=d_ini,
        d_fim=d_fim,
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
                **dados["duracao_visitas"]["tbo"],
                "por_grupo": dados["duracao_visitas"]["por_grupo"],
                "esporotricose": dados["duracao_visitas"]["esporotricose"],
                "total": dados["duracao_visitas"]["total"],
            },
            "por_tipo": dados["por_tipo"],
            "por_loc": dados["por_loc"],
            "por_dia": dados["por_dia"],
            "evolucao": dados["evolucao"],
            "comparacao": dados["comparacao"],
            "producao_operacional": dados["producao_operacional"],
            "ovitrampas": dados["ovitrampas"],
            "registro_geografico": dados["registro_geografico"],
            "laboratorio": dados["laboratorio"],
            "esporotricose": dados["esporotricose"],
            "comparacao_esporotricose": dados["comparacao_esporotricose"],
        })
    except Exception:
        logging.exception("Erro em relatorio_agente.api")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500
