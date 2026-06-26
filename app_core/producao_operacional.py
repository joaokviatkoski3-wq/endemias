import sqlite3
from collections import defaultdict

from app_core import utils


FONTES = (
    {
        "codigo": "VETORES",
        "nome": "Vetores",
        "tabela": "visitas",
        "alias": "v",
        "id_col": "id_visita",
        "data_col": "data",
        "localidade_expr": "COALESCE(l.nome, v.localidade)",
        "joins": "LEFT JOIN localidades l ON l.id_localidade=v.id_localidade",
        "agente_table": "visita_agentes",
        "agente_fk": "id_visita",
        "tipo_col": "tipo",
        "extras": {
            "normais": "COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='normal' THEN v.id_visita END)",
            "fechados": "COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='fechado' THEN v.id_visita END)",
        },
    },
    {
        "codigo": "ESPOROTRICOSE",
        "nome": "Esporotricose",
        "tabela": "esporotricose_visitas",
        "alias": "e",
        "id_col": "id_visita",
        "data_col": "data",
        "localidade_expr": "COALESCE(l.nome, e.localidade)",
        "joins": "LEFT JOIN localidades l ON l.id_localidade=e.id_localidade",
        "agente_table": "esporotricose_visita_agentes",
        "agente_fk": "id_visita",
        "extras": {
            "animais": "COUNT(DISTINCT an.id_animal)",
            "animais_com_feridas": "COUNT(DISTINCT CASE WHEN LOWER(COALESCE(an.feridas,''))='sim' THEN an.id_animal END)",
        },
        "extra_joins": "LEFT JOIN esporotricose_animais an ON an.id_visita=e.id_visita",
    },
    {
        "codigo": "RECOLHIMENTO",
        "nome": "Recolhimentos",
        "tabela": "recolhimentos",
        "alias": "r",
        "id_col": "id_recolhimento",
        "data_col": "data",
        "localidade_expr": "r.localidade",
        "joins": "",
        "agente_table": "recolhimento_agentes",
        "agente_fk": "id_recolhimento",
        "extras": {
            "materiais": "COALESCE(SUM(r.total_materiais),0)",
            "pneus": "COALESCE(SUM(r.pneu),0)",
        },
    },
    {
        "codigo": "AMOSTRA_ANIMAIS",
        "nome": "Amostras animais",
        "tabela": "amostras_animais",
        "alias": "am",
        "id_col": "id_amostra",
        "data_col": "data",
        "localidade_expr": "am.localidade",
        "joins": "",
        "agente_table": "amostra_animais_agentes",
        "agente_fk": "id_amostra",
        "extras": {
            "animais": "COALESCE(SUM(am.quantidade),0)",
            "acidentes": "SUM(CASE WHEN LOWER(COALESCE(am.houve_acidente,''))='sim' THEN 1 ELSE 0 END)",
            "capturas": "SUM(CASE WHEN LOWER(COALESCE(am.houve_captura,''))='sim' THEN 1 ELSE 0 END)",
        },
    },
    {
        "codigo": "BRI",
        "nome": "BRI",
        "tabela": "bri_registros",
        "alias": "b",
        "id_col": "id_bri",
        "data_col": "data",
        "localidade_expr": "b.localidade",
        "joins": "",
        "agente_table": "bri_agentes",
        "agente_fk": "id_bri",
        "extras": {
            "carga": "COALESCE(SUM(b.quantidade_carga + b.quantidade_carga_extra),0)",
            "pendentes_sispncd": "SUM(CASE WHEN b.sispncd IS NULL OR TRIM(b.sispncd)='' THEN 1 ELSE 0 END)",
        },
    },
    {
        "codigo": "ACOES_SETOR",
        "nome": "Ações do Setor",
        "tabela": "acoes_setor",
        "alias": "ac",
        "id_col": "id_acao",
        "data_col": "data",
        "localidade_expr": "ac.localidade",
        "joins": "",
        "agente_table": "acoes_setor_agentes",
        "agente_fk": "id_acao",
        "tipo_col": "tipo",
        "extras": {
            "educativas": "COUNT(DISTINCT CASE WHEN ac.tipo='educativa' THEN ac.id_acao END)",
            "limpezas": "COUNT(DISTINCT CASE WHEN ac.tipo='limpeza' THEN ac.id_acao END)",
            "publico": "COALESCE(SUM(ac.publico_aproximado),0)",
        },
    },
    {
        "codigo": "OVITRAMPAS",
        "nome": "Ovitrampas",
        "tabela": "ovitrampas_calendario_eventos",
        "alias": "e",
        "id_col": "id_evento",
        "data_col": "data",
        "localidade_expr": "CAST(NULL AS TEXT)",
        "joins": "",
        "agente_table": "ovitrampas_calendario_agentes",
        "agente_fk": "id_evento",
        "where_extra": "e.movimento <> 'feriado'",
        "extras": {},
    },
)


def resumo(db_path, filtros=None):
    filtros = filtros or {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        fontes = [
            _resumo_fonte(conn, fonte, filtros)
            if _table_exists(conn, fonte["tabela"]) and _table_exists(conn, fonte["agente_table"])
            else _fonte_vazia(fonte)
            for fonte in FONTES
        ]
    finally:
        conn.close()

    por_mes = _somar_series(fontes, "por_mes", "mes")
    por_localidade = _somar_series(fontes, "por_localidade", "localidade")
    por_agente = _somar_series(fontes, "por_agente", "agente")
    totais = {
        "registros_total": sum(item["registros"] for item in fontes),
        "dias": len({dia for item in fontes for dia in item["dias_trabalhados"]}),
        "localidades": len({loc for item in fontes for loc in item["localidades_trabalhadas"] if loc}),
        "agentes": len({ag for item in fontes for ag in item["agentes_trabalharam"] if ag}),
    }
    return {
        "totais": totais,
        "por_atividade": [
            {
                "codigo": item["codigo"],
                "nome": item["nome"],
                "registros": item["registros"],
                "extras": item["extras"],
            }
            for item in fontes
        ],
        "por_mes": por_mes,
        "por_localidade": por_localidade[:15],
        "por_agente": por_agente,
    }


def _table_exists(conn, table_name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone())


def _fonte_vazia(fonte):
    return {
        "codigo": fonte["codigo"],
        "nome": fonte["nome"],
        "registros": 0,
        "extras": {nome: 0 for nome in fonte.get("extras", {})},
        "dias_trabalhados": [],
        "localidades_trabalhadas": [],
        "agentes_trabalharam": [],
        "por_mes": [],
        "por_localidade": [],
        "por_agente": [],
    }


def _resumo_fonte(conn, fonte, filtros):
    where, params = _where_fonte(fonte, filtros)
    alias = fonte["alias"]
    id_expr = f"{alias}.{fonte['id_col']}"
    data_expr = f"{alias}.{fonte['data_col']}"
    localidade_expr = fonte["localidade_expr"]
    joins = " ".join(part for part in (fonte.get("joins"), fonte.get("extra_joins")) if part)
    extras_sql = "".join(f", {expr} AS {nome}" for nome, expr in fonte.get("extras", {}).items())

    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT {id_expr}) AS registros,
               COUNT(DISTINCT {data_expr}) AS dias,
               COUNT(DISTINCT {localidade_expr}) AS localidades
               {extras_sql}
          FROM {fonte['tabela']} {alias}
          {joins}
         WHERE {where}
        """,
        params,
    ).fetchone()
    registros = row["registros"] or 0

    return {
        "codigo": fonte["codigo"],
        "nome": fonte["nome"],
        "registros": registros,
        "extras": {
            nome: row[nome] or 0
            for nome in fonte.get("extras", {})
        },
        "dias_trabalhados": _distinct(conn, fonte, filtros, data_expr, "dia"),
        "localidades_trabalhadas": _distinct(conn, fonte, filtros, localidade_expr, "localidade"),
        "agentes_trabalharam": [r["agente"] for r in _por_agente(conn, fonte, filtros)],
        "por_mes": _por_mes(conn, fonte, filtros),
        "por_localidade": _por_localidade(conn, fonte, filtros),
        "por_agente": _por_agente(conn, fonte, filtros),
    }


def _where_fonte(fonte, filtros):
    alias = fonte["alias"]
    data_col = f"{alias}.{fonte['data_col']}"
    localidade_expr = fonte["localidade_expr"]
    d_ini = filtros.get("d_ini") or utils.data_n_dias(365)
    d_fim = filtros.get("d_fim") or utils.hoje()
    clauses = [f"{data_col} BETWEEN ? AND ?"]
    params = [d_ini, d_fim]

    tipos = _getlist(filtros, "tipo")
    if fonte.get("tipo_col") and tipos:
        clauses.append(f"{alias}.{fonte['tipo_col']} IN ({_placeholders(tipos)})")
        params.extend(tipos)

    localidades = _getlist(filtros, "localidade")
    if localidades:
        clauses.append(f"{localidade_expr} IN ({_placeholders(localidades)})")
        params.extend(localidades)

    where_extra = fonte.get("where_extra")
    if where_extra:
        clauses.append(where_extra)

    agentes = _getlist(filtros, "agente")
    if agentes:
        clauses.append(
            f"""EXISTS (
                    SELECT 1
                      FROM {fonte['agente_table']} pa
                      JOIN agentes ag ON ag.id_agente=pa.id_agente
                     WHERE pa.{fonte['agente_fk']}={alias}.{fonte['id_col']}
                       AND ag.nome IN ({_placeholders(agentes)})
                )"""
        )
        params.extend(agentes)

    return " AND ".join(clauses), params


def _distinct(conn, fonte, filtros, expr, alias_nome):
    where, params = _where_fonte(fonte, filtros)
    rows = conn.execute(
        f"""
        SELECT DISTINCT {expr} AS {alias_nome}
          FROM {fonte['tabela']} {fonte['alias']}
          {fonte.get('joins') or ''}
         WHERE {where}
           AND {expr} IS NOT NULL
           AND TRIM(CAST({expr} AS TEXT))<>''
        """,
        params,
    ).fetchall()
    return [row[alias_nome] for row in rows]


def _por_mes(conn, fonte, filtros):
    where, params = _where_fonte(fonte, filtros)
    alias = fonte["alias"]
    id_expr = f"{alias}.{fonte['id_col']}"
    data_expr = f"{alias}.{fonte['data_col']}"
    rows = conn.execute(
        f"""
        SELECT substr({data_expr},1,7) AS mes,
               COUNT(DISTINCT {id_expr}) AS registros
          FROM {fonte['tabela']} {alias}
          {fonte.get('joins') or ''}
         WHERE {where}
         GROUP BY substr({data_expr},1,7)
         ORDER BY mes
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _por_localidade(conn, fonte, filtros):
    where, params = _where_fonte(fonte, filtros)
    alias = fonte["alias"]
    id_expr = f"{alias}.{fonte['id_col']}"
    localidade_expr = fonte["localidade_expr"]
    rows = conn.execute(
        f"""
        SELECT COALESCE({localidade_expr}, '-') AS localidade,
               COUNT(DISTINCT {id_expr}) AS registros
          FROM {fonte['tabela']} {alias}
          {fonte.get('joins') or ''}
         WHERE {where}
         GROUP BY COALESCE({localidade_expr}, '-')
         ORDER BY registros DESC, localidade
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _por_agente(conn, fonte, filtros):
    where, params = _where_fonte(fonte, filtros)
    alias = fonte["alias"]
    id_expr = f"{alias}.{fonte['id_col']}"
    rows = conn.execute(
        f"""
        SELECT ag.nome AS agente,
               COUNT(DISTINCT {id_expr}) AS registros
          FROM {fonte['tabela']} {alias}
          JOIN {fonte['agente_table']} pa ON pa.{fonte['agente_fk']}={id_expr}
          JOIN agentes ag ON ag.id_agente=pa.id_agente
          {fonte.get('joins') or ''}
         WHERE {where}
         GROUP BY ag.nome
         ORDER BY registros DESC, ag.nome
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _somar_series(fontes, key, nome_coluna):
    acumulado = defaultdict(int)
    for fonte in fontes:
        for row in fonte[key]:
            nome = row[nome_coluna] or "-"
            acumulado[nome] += row["registros"] or 0
    sort_key = (
        (lambda item: item[0])
        if nome_coluna == "mes"
        else (lambda item: (-item[1], item[0]))
    )
    return [
        {nome_coluna: nome, "registros": total}
        for nome, total in sorted(acumulado.items(), key=sort_key)
    ]


def _getlist(filtros, key):
    if hasattr(filtros, "getlist"):
        return [value for value in filtros.getlist(key) if value]
    value = filtros.get(key, [])
    if isinstance(value, (list, tuple)):
        return [item for item in value if item]
    return [value] if value else []


def _placeholders(items):
    return ",".join("?" for _ in items)
