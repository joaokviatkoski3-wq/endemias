from app_core import db as db_core
from app_core import esporotricose as esporotricose_core
from app_core import ovitrampas as ovitrampas_core
from app_core import pontos_estrategicos as pe_core
from app_core import producao_operacional
from app_core import utils as utils_core
from app_core import work_types


DURATION_WORK_TYPE_CODE = work_types.primary_duration_work_type_code()


def integrado(target, args):
    vetores = vetorial(target, args)
    esporo_filtros = _esporotricose_filtros(args)
    esporo_resumo = esporotricose_core.resumo(target, esporo_filtros)
    esporo_dashboard = esporotricose_core.dashboard(
        target,
        esporo_filtros,
    )
    pe_resumo = pe_core.resumo_operacional(
        target,
        {
            "d_ini": args.get("d_ini", ""),
            "d_fim": args.get("d_fim", ""),
            "localidade": _values(args, "localidade"),
        },
    )
    producao = producao_operacional.resumo(target, args)
    dados_ovitrampas = ovitrampas(target, args)

    vetores_mes = {
        row["mes"]: row["visitas"]
        for row in vetores["evolucao_mensal"]
    }
    esporo_mes = {
        row["mes"]: row.get("visitas", 0)
        for row in esporo_dashboard.get("evolucao", [])
    }
    ovitrampas_mes = {
        row["mes"]: row.get("movimentos", 0)
        for row in dados_ovitrampas.get("calendario", {}).get(
            "por_mes", []
        )
    }
    meses = sorted(
        set(vetores_mes) | set(esporo_mes) | set(ovitrampas_mes)
    )
    vetores.update(
        {
            "comparativo_mensal": [
                {
                    "mes": mes,
                    "vetores": vetores_mes.get(mes, 0),
                    "esporotricose": esporo_mes.get(mes, 0),
                    "ovitrampas": ovitrampas_mes.get(mes, 0),
                }
                for mes in meses
            ],
            "esporotricose": {
                "resumo": esporo_resumo,
                "dashboard": esporo_dashboard,
            },
            "pontos_estrategicos": pe_resumo,
            "producao_operacional": producao,
            "ovitrampas": dados_ovitrampas,
        }
    )
    return vetores


def vetorial(target, args):
    where, params = utils_core.build_visit_where(
        args,
        localidade_fallback=True,
    )
    base = f"""
        FROM visitas v
        LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
        {where}
    """
    conn, close = _open_connection(target)
    try:
        kpi = conn.execute(
            f"""
            SELECT COUNT(DISTINCT v.id_visita) AS total,
                   COUNT(DISTINCT v.data) AS dias,
                   COUNT(DISTINCT v.quarteirao) AS quarteiroes,
                   COUNT(DISTINCT CASE
                       WHEN LOWER(v.visita)='normal'
                       THEN v.id_visita END) AS normais,
                   COUNT(DISTINCT CASE
                       WHEN LOWER(v.visita)='fechado'
                       THEN v.id_visita END) AS fechados,
                   COUNT(DISTINCT CASE
                       WHEN LOWER(v.visita)='recuperado'
                       THEN v.id_visita END) AS recuperados,
                   COUNT(DISTINCT CASE
                       WHEN LOWER(v.visita)='recusa'
                       THEN v.id_visita END) AS recusados
              {base}
            """,
            params,
        ).fetchone()
        por_tipo = conn.execute(
            f"""SELECT v.tipo, COUNT(DISTINCT v.id_visita) AS total
                  {base}
                 GROUP BY v.tipo""",
            params,
        ).fetchall()
        por_localidade = conn.execute(
            f"""SELECT COALESCE(l.nome, v.localidade) AS loc,
                       COUNT(DISTINCT v.id_visita) AS total
                  {base}
                 GROUP BY COALESCE(l.nome, v.localidade)
                 ORDER BY total DESC
                 LIMIT 15""",
            params,
        ).fetchall()
        por_status = conn.execute(
            f"""SELECT COALESCE(LOWER(v.visita), 'sem info') AS visita,
                       COUNT(DISTINCT v.id_visita) AS total
                  {base}
                 GROUP BY COALESCE(LOWER(v.visita), 'sem info')""",
            params,
        ).fetchall()

        semana_expr = _week_expression(conn, "v.data")
        evolucao = conn.execute(
            f"""SELECT {semana_expr} AS sem,
                       COUNT(DISTINCT v.id_visita) AS total
                  {base}
                 GROUP BY {semana_expr}
                 ORDER BY sem""",
            params,
        ).fetchall()
        mes_expr = db_core.month_expression("v.data")
        evolucao_mensal = conn.execute(
            f"""SELECT {mes_expr} AS mes,
                       COUNT(DISTINCT v.id_visita) AS visitas
                  {base}
                 GROUP BY {mes_expr}
                 ORDER BY mes""",
            params,
        ).fetchall()
        por_agente = conn.execute(
            f"""
            SELECT a.nome, COUNT(DISTINCT v.id_visita) AS total
              FROM visitas v
              LEFT JOIN localidades l
                ON l.id_localidade=v.id_localidade
              JOIN visita_agentes va ON va.id_visita=v.id_visita
              JOIN agentes a ON a.id_agente=va.id_agente
              {where}
             GROUP BY a.nome
             ORDER BY total DESC
            """,
            params,
        ).fetchall()
        por_imovel = conn.execute(
            f"""SELECT v.tipo_imovel,
                       COUNT(DISTINCT v.id_visita) AS total
                  {base}
                   AND v.tipo_imovel IS NOT NULL
                 GROUP BY v.tipo_imovel
                 ORDER BY total DESC""",
            params,
        ).fetchall()

        depositos = conn.execute(
            f"""
            SELECT COALESCE(SUM(d.inspecionado), 0) AS insp,
                   COALESCE(SUM(d.eliminado), 0) AS elim,
                   COALESCE(SUM(d.tratado), 0) AS trat
              FROM depositos_inspecionados d
              JOIN visitas v ON v.id_visita=d.id_visita
              LEFT JOIN localidades l
                ON l.id_localidade=v.id_localidade
              {where}
            """,
            params,
        ).fetchone()
        tratamentos_depositos = _total_tratamentos_depositos(
            conn,
            where,
            params,
        )
        depositos_por_tipo = conn.execute(
            f"""
            SELECT d.tipo_deposito,
                   COALESCE(SUM(d.inspecionado), 0) AS insp
              FROM depositos_inspecionados d
              JOIN visitas v ON v.id_visita=d.id_visita
              LEFT JOIN localidades l
                ON l.id_localidade=v.id_localidade
              {where}
             GROUP BY d.tipo_deposito
             ORDER BY insp DESC
            """,
            params,
        ).fetchall()

        duracao_expr = _duration_expression(conn)
        duracao = conn.execute(
            f"""
            SELECT COUNT(*) AS n,
                   ROUND(AVG(dur), 1) AS media,
                   ROUND(MIN(dur), 1) AS minimo,
                   ROUND(MAX(dur), 1) AS maximo
              FROM (
                    SELECT {duracao_expr} AS dur
                      FROM visitas v
                      LEFT JOIN localidades l
                        ON l.id_localidade=v.id_localidade
                      {where}
                       AND v.tipo=?
                       AND v.hora_inicio IS NOT NULL
                       AND v.hora_fim IS NOT NULL
                   ) sub
             WHERE dur BETWEEN 1 AND 240
            """,
            params + [DURATION_WORK_TYPE_CODE],
        ).fetchone()
        duracao_por_tipo = conn.execute(
            f"""
            SELECT CASE
                     WHEN LOWER(sub.visita)
                          IN ('normal', 'recuperado')
                     THEN 'acessados'
                     ELSE 'nao_acessados'
                   END AS grupo,
                   COUNT(*) AS n,
                   ROUND(AVG(dur), 1) AS media,
                   ROUND(MIN(dur), 1) AS minimo,
                   ROUND(MAX(dur), 1) AS maximo
              FROM (
                    SELECT v.visita, {duracao_expr} AS dur
                      FROM visitas v
                      LEFT JOIN localidades l
                        ON l.id_localidade=v.id_localidade
                      {where}
                       AND v.tipo=?
                       AND v.hora_inicio IS NOT NULL
                       AND v.hora_fim IS NOT NULL
                   ) sub
             WHERE dur BETWEEN 1 AND 240
             GROUP BY CASE
                        WHEN LOWER(sub.visita)
                             IN ('normal', 'recuperado')
                        THEN 'acessados'
                        ELSE 'nao_acessados'
                      END
            """,
            params + [DURATION_WORK_TYPE_CODE],
        ).fetchall()
    finally:
        if close:
            conn.close()

    duracao_dict = db_core.serialize_row(duracao) if duracao else {}
    return {
        "kpi": db_core.serialize_row(kpi) if kpi else {},
        "depositos": {
            "inspecionados": utils_core.safe_int(depositos["insp"]),
            "eliminados": utils_core.safe_int(depositos["elim"]),
            "tratados": (
                utils_core.safe_int(depositos["trat"])
                + tratamentos_depositos
            ),
        },
        "dep_por_tipo": [
            db_core.serialize_row(row) for row in depositos_por_tipo
        ],
        "tbo_duracao": {
            "n": duracao_dict.get("n", 0),
            "media": duracao_dict.get("media"),
            "minimo": duracao_dict.get("minimo"),
            "maximo": duracao_dict.get("maximo"),
            "por_grupo": {
                row["grupo"]: {
                    "n": row["n"],
                    "media": row["media"],
                    "minimo": row["minimo"],
                    "maximo": row["maximo"],
                }
                for row in duracao_por_tipo
            },
        },
        "por_tipo": [db_core.serialize_row(row) for row in por_tipo],
        "por_loc": [
            db_core.serialize_row(row) for row in por_localidade
        ],
        "por_status": [
            db_core.serialize_row(row) for row in por_status
        ],
        "evolucao": [db_core.serialize_row(row) for row in evolucao],
        "evolucao_mensal": [
            db_core.serialize_row(row) for row in evolucao_mensal
        ],
        "por_agente": [
            db_core.serialize_row(row) for row in por_agente
        ],
        "por_imovel": [
            db_core.serialize_row(row) for row in por_imovel
        ],
    }


def ovitrampas(target, args):
    d_ini = args.get("d_ini") or utils_core.data_n_dias(90)
    d_fim = args.get("d_fim") or utils_core.hoje()
    localidades = _values(args, "localidade")
    agentes = _values(args, "agente")
    conn, close = _open_connection(target)
    try:
        ovitrampas_core.ensure_schema(conn)
        leitura_where = [
            """substr(
                   COALESCE(
                       CAST(l.data_leitura AS TEXT),
                       CAST(l.data_coleta AS TEXT),
                       l.data_envio_contagem
                   ),
                   1,
                   10
               ) BETWEEN ? AND ?"""
        ]
        leitura_params = [d_ini, d_fim]
        if localidades:
            leitura_where.append(
                "COALESCE(a.localidade, l.distrito, '-') "
                f"IN ({_placeholders(localidades)})"
            )
            leitura_params.extend(localidades)
        if agentes:
            leitura_where.append(
                f"lab.nome IN ({_placeholders(agentes)})"
            )
            leitura_params.extend(agentes)
        leitura_where_sql = "WHERE " + " AND ".join(leitura_where)
        leitura_join = f"""
            FROM {ovitrampas_core.TABLE} l
            LEFT JOIN {ovitrampas_core.ARMADILHAS_TABLE} a
              ON a.ovitrampa_id=l.ovitrampa_id
            LEFT JOIN agentes lab
              ON lab.id_agente=l.id_laboratorista
        """
        ano_semana = (
            "CAST(l.ano AS TEXT) || '-' || CAST(l.semana AS TEXT)"
        )
        leituras_totais = db_core.serialize_row(
            conn.execute(
                f"""
                SELECT COUNT(*) AS leituras,
                       COUNT(DISTINCT l.ovitrampa_id) AS ovitrampas,
                       COALESCE(SUM(l.ovos), 0) AS ovos,
                       SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END)
                           AS positivas,
                       COUNT(DISTINCT {ano_semana}) AS semanas,
                       COUNT(DISTINCT lab.id_agente) AS laboratoristas
                  {leitura_join}
                  {leitura_where_sql}
                """,
                leitura_params,
            ).fetchone()
        )
        por_semana = _rows(
            conn,
            f"""
            SELECT l.ano, l.semana,
                   COUNT(*) AS leituras,
                   COALESCE(SUM(l.ovos), 0) AS ovos,
                   SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END)
                       AS positivas
              {leitura_join}
              {leitura_where_sql}
             GROUP BY l.ano, l.semana
             ORDER BY l.ano, l.semana
            """,
            leitura_params,
        )
        por_localidade = _rows(
            conn,
            f"""
            SELECT COALESCE(a.localidade, l.distrito, '-') AS localidade,
                   COUNT(*) AS leituras,
                   COUNT(DISTINCT l.ovitrampa_id) AS ovitrampas,
                   COALESCE(SUM(l.ovos), 0) AS ovos,
                   SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END)
                       AS positivas
              {leitura_join}
              {leitura_where_sql}
             GROUP BY COALESCE(a.localidade, l.distrito, '-')
             ORDER BY ovos DESC, positivas DESC, leituras DESC
             LIMIT 15
            """,
            leitura_params,
        )
        por_laboratorista = _rows(
            conn,
            f"""
            SELECT COALESCE(lab.nome, 'Sem laboratorista') AS agente,
                   COUNT(*) AS leituras,
                   COALESCE(SUM(l.ovos), 0) AS ovos,
                   SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END)
                       AS positivas
              {leitura_join}
              {leitura_where_sql}
             GROUP BY COALESCE(lab.nome, 'Sem laboratorista')
             ORDER BY leituras DESC, agente
             LIMIT 15
            """,
            leitura_params,
        )

        calendario_where = [
            "e.data BETWEEN ? AND ?",
            "e.movimento <> 'feriado'",
        ]
        calendario_params = [d_ini, d_fim]
        if localidades:
            loc_clause = " OR ".join(
                "g.nome=? OR g.localidades LIKE ?" for _ in localidades
            )
            calendario_where.append(f"({loc_clause})")
            for localidade in localidades:
                calendario_params.extend(
                    [localidade, f"%{localidade}%"]
                )
        if agentes:
            calendario_where.append(
                f"""EXISTS (
                        SELECT 1
                          FROM {ovitrampas_core.CAL_AGENTES_TABLE} ea2
                          JOIN agentes ag2
                            ON ag2.id_agente=ea2.id_agente
                         WHERE ea2.id_evento=e.id_evento
                           AND ag2.nome IN (
                               {_placeholders(agentes)}
                           )
                    )"""
            )
            calendario_params.extend(agentes)
        calendario_where_sql = (
            "WHERE " + " AND ".join(calendario_where)
        )
        calendario_join = f"""
            FROM {ovitrampas_core.CAL_EVENTOS_TABLE} e
            LEFT JOIN {ovitrampas_core.CAL_GRUPOS_TABLE} g
              ON g.id_grupo=e.id_grupo
            LEFT JOIN {ovitrampas_core.CAL_AGENTES_TABLE} ea
              ON ea.id_evento=e.id_evento
            LEFT JOIN agentes ag ON ag.id_agente=ea.id_agente
        """
        calendario_totais = db_core.serialize_row(
            conn.execute(
                f"""
                SELECT COUNT(DISTINCT e.id_evento) AS movimentos,
                       COUNT(DISTINCT e.data) AS dias,
                       COUNT(DISTINCT e.id_grupo) AS grupos,
                       COUNT(DISTINCT ag.id_agente) AS agentes
                  {calendario_join}
                  {calendario_where_sql}
                """,
                calendario_params,
            ).fetchone()
        )
        por_movimento = _rows(
            conn,
            f"""
            SELECT e.movimento,
                   COUNT(DISTINCT e.id_evento) AS total
              {calendario_join}
              {calendario_where_sql}
             GROUP BY e.movimento
             ORDER BY total DESC, e.movimento
            """,
            calendario_params,
        )
        por_grupo = _rows(
            conn,
            f"""
            SELECT COALESCE(g.nome, '-') AS grupo,
                   COUNT(DISTINCT e.id_evento) AS total
              {calendario_join}
              {calendario_where_sql}
             GROUP BY COALESCE(g.nome, '-')
             ORDER BY total DESC, grupo
             LIMIT 12
            """,
            calendario_params,
        )
        por_agente = _rows(
            conn,
            f"""
            SELECT ag.nome AS agente,
                   COUNT(DISTINCT e.id_evento) AS total
              {calendario_join}
              {calendario_where_sql}
               AND ag.nome IS NOT NULL
             GROUP BY ag.nome
             ORDER BY total DESC, agente
             LIMIT 15
            """,
            calendario_params,
        )
        mes_expr = db_core.month_expression("e.data")
        por_mes = _rows(
            conn,
            f"""
            SELECT {mes_expr} AS mes,
                   COUNT(DISTINCT e.id_evento) AS movimentos
              {calendario_join}
              {calendario_where_sql}
             GROUP BY {mes_expr}
             ORDER BY mes
            """,
            calendario_params,
        )
    finally:
        if close:
            conn.close()

    movimentos = getattr(ovitrampas_core, "MOVIMENTOS", {})
    for row in por_movimento:
        row["nome"] = movimentos.get(
            row.get("movimento"),
            row.get("movimento") or "-",
        )
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


def _total_tratamentos_depositos(conn, where, params):
    if not db_core.column_exists(
        conn,
        "tratamentos",
        "qtd_depositos_tratados",
    ):
        return 0
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(qtd), 0) AS total
          FROM (
                SELECT DISTINCT t.id,
                       COALESCE(t.qtd_depositos_tratados, 0) AS qtd
                  FROM tratamentos t
                  JOIN visitas v ON v.id_visita=t.id_visita
                  LEFT JOIN localidades l
                    ON l.id_localidade=v.id_localidade
                  {where}
               ) base
        """,
        params,
    ).fetchone()
    return utils_core.safe_int(row["total"] if row else 0)


def _duration_expression(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return (
            "EXTRACT(EPOCH FROM (v.hora_fim - v.hora_inicio)) / 60.0"
        )
    return (
        "(julianday(v.data || ' ' || v.hora_fim) - "
        "julianday(v.data || ' ' || v.hora_inicio)) * 24 * 60"
    )


def _week_expression(conn, expression):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return f"to_char({expression}, 'IYYY-IW')"
    return f"strftime('%Y-%W', {expression})"


def _esporotricose_filtros(args):
    filtros = {
        "d_ini": args.get("d_ini", ""),
        "d_fim": args.get("d_fim", ""),
    }
    localidades = _values(args, "localidade")
    agentes = _values(args, "agente")
    if localidades:
        filtros["localidade"] = localidades
    if agentes:
        filtros["agente"] = agentes
    return filtros


def _values(args, key):
    if hasattr(args, "getlist"):
        values = args.getlist(key)
    else:
        raw = args.get(key, [])
        values = raw if isinstance(raw, (list, tuple)) else [raw]
    return [
        str(value).strip()
        for value in values
        if str(value or "").strip()
    ]


def _placeholders(items):
    return ",".join("?" for _ in items)


def _rows(conn, sql, params):
    return [
        db_core.serialize_row(row)
        for row in conn.execute(sql, params).fetchall()
    ]


def _open_connection(target):
    if hasattr(target, "execute"):
        return target, False
    return db_core.connect(target), True
