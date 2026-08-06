from collections import defaultdict

from app_core import db as db_core
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
        "nome": "Ações e Atendimentos",
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
            "vistorias": "COUNT(DISTINCT CASE WHEN ac.tipo='vistoria' THEN ac.id_acao END)",
            "reunioes": "COUNT(DISTINCT CASE WHEN ac.tipo='reuniao' THEN ac.id_acao END)",
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
    {
        "codigo": "REGISTRO_GEOGRAFICO",
        "nome": "Registro Geográfico",
        "tabela": "registro_geografico_imoveis",
        "alias": "rg",
        "id_col": "id_imovel",
        "data_col": "data_atualizacao",
        "localidade_expr": "rg.localidade",
        "joins": "",
        "agente_table": "registro_geografico_imovel_agentes",
        "agente_fk": "id_imovel",
        "extras": {},
    },
    {
        # O laboratorista e uma coluna da propria leitura, sem tabela de
        # ligacao, e a data util pode estar na leitura ou na coleta.
        "codigo": "LABORATORIO",
        "nome": "Leituras de laboratório",
        "tabela": "resultados_laboratorio",
        "alias": "rl",
        "id_col": "id_resultado",
        "data_col": "data_leitura",
        "data_expr": "COALESCE(rl.data_leitura, rl.data_coleta)",
        "localidade_expr": "CAST(NULL AS TEXT)",
        "joins": "",
        # O id fica vazio na maioria das leituras; o nome do laboratorista e
        # o que sempre vem preenchido.
        "agente_col": "id_laboratorista",
        "agente_nome_col": "laboratorista",
        "extras": {},
    },
    {
        # Uma palheta lida e uma ovitrampa lida: um lote com 30 ovitrampas
        # vale 30 leituras. Por isso a unidade aqui e a palheta, nao o lote.
        #
        # O mesmo trabalho vive em duas tabelas de epocas diferentes, e as
        # duas ja guardam uma linha por ovitrampa. Elas viram uma fonte so,
        # para o relatorio nao mostrar duas linhas que dizem a mesma coisa:
        #
        #   ovitrampas_laboratorio_itens
        #       fluxo atual; data e laboratorista vem do lote. O
        #       id_laboratorista do lote e do USUARIO logado, nao do agente,
        #       entao o vinculo usa o nome gravado.
        #   ovitrampas_leituras
        #       historico importado; ali o id aponta mesmo para agentes e e
        #       resolvido para nome, deixando as duas partes com o mesmo
        #       formato.
        "codigo": "OVITRAMPAS_PALHETA",
        "nome": "Leituras de palhetas",
        "tabela": """(
            SELECT li.id_item AS id_palheta,
                   lt.data_movimento AS data_leitura,
                   lt.laboratorista_nome AS laboratorista_nome,
                   li.ovos AS ovos
              FROM ovitrampas_laboratorio_itens li
              JOIN ovitrampas_laboratorio_lotes lt ON lt.id_lote=li.id_lote
            UNION ALL
            SELECT ol.id_leitura AS id_palheta,
                   COALESCE(ol.data_leitura, ol.data_coleta) AS data_leitura,
                   (SELECT ag2.nome FROM agentes ag2
                     WHERE ag2.id_agente=ol.id_laboratorista) AS laboratorista_nome,
                   ol.ovos AS ovos
              FROM ovitrampas_leituras ol
        )""",
        "tabelas_requeridas": (
            "ovitrampas_laboratorio_itens",
            "ovitrampas_laboratorio_lotes",
            "ovitrampas_leituras",
        ),
        "alias": "pal",
        "id_col": "id_palheta",
        "data_col": "data_leitura",
        "localidade_expr": "CAST(NULL AS TEXT)",
        "joins": "",
        "agente_nome_col": "laboratorista_nome",
        "extras": {
            "ovos": "COALESCE(SUM(pal.ovos),0)",
        },
    },
)


def _data_expr(fonte):
    """Data util da fonte, permitindo COALESCE entre colunas."""
    return fonte.get("data_expr") or f"{fonte['alias']}.{fonte['data_col']}"


def _chave_nome_sql(expressao):
    """Compara nomes ignorando caixa e espacos das pontas."""
    return f"LOWER(TRIM(COALESCE({expressao}, '')))"


def _vinculo_agente_sql(fonte, alias):
    """Condicao que liga a linha da fonte ao agente ``ag``.

    Ha duas formas diretas no banco, e a diferenca importa:

    ``agente_col``
        Id que aponta mesmo para ``agentes``.
    ``agente_nome_col``
        Nome gravado na propria linha. Usado quando o id esta vazio na maior
        parte das linhas (``resultados_laboratorio``) ou quando ele aponta
        para ``usuarios``, nao para ``agentes`` - o caso dos lotes de
        laboratorio, em que juntar pelo id credita a pessoa errada.

    Quando a fonte declara as duas, basta uma casar.
    """
    partes = []
    if fonte.get("agente_col"):
        partes.append(f"ag.id_agente={alias}.{fonte['agente_col']}")
    if fonte.get("agente_nome_col"):
        coluna = f"{alias}.{fonte['agente_nome_col']}"
        partes.append(
            f"({_chave_nome_sql(coluna)} <> '' "
            f"AND {_chave_nome_sql(coluna)}={_chave_nome_sql('ag.nome')})"
        )
    return "(" + " OR ".join(partes) + ")" if partes else None


def _fonte_disponivel(conn, fonte):
    # Fontes montadas por subconsulta declaram as tabelas que usam, ja que
    # nao ha um nome unico para checar.
    requeridas = fonte.get("tabelas_requeridas") or (fonte["tabela"],)
    if not all(_table_exists(conn, tabela) for tabela in requeridas):
        return False
    if fonte.get("agente_col") or fonte.get("agente_nome_col"):
        return True
    return _table_exists(conn, fonte["agente_table"])


def resumo(target, filtros=None):
    filtros = filtros or {}
    conn = db_core.connect(target)
    try:
        fontes = [
            _resumo_fonte(conn, fonte, filtros)
            if _fonte_disponivel(conn, fonte)
            else _fonte_vazia(fonte)
            for fonte in FONTES
        ]
    finally:
        conn.close()

    por_dia = _somar_series(fontes, "por_dia", "dia")
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
        "por_dia": por_dia,
        "por_mes": por_mes,
        "por_localidade": por_localidade[:15],
        "por_agente": por_agente,
    }


def _table_exists(conn, table_name):
    return db_core.table_exists(conn, table_name)


def _fonte_vazia(fonte):
    return {
        "codigo": fonte["codigo"],
        "nome": fonte["nome"],
        "registros": 0,
        "extras": {nome: 0 for nome in fonte.get("extras", {})},
        "dias_trabalhados": [],
        "localidades_trabalhadas": [],
        "agentes_trabalharam": [],
        "por_dia": [],
        "por_mes": [],
        "por_localidade": [],
        "por_agente": [],
    }


def _resumo_fonte(conn, fonte, filtros):
    where, params = _where_fonte(fonte, filtros)
    alias = fonte["alias"]
    id_expr = f"{alias}.{fonte['id_col']}"
    data_expr = _data_expr(fonte)
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
        "por_dia": _por_dia(conn, fonte, filtros),
        "por_mes": _por_mes(conn, fonte, filtros),
        "por_localidade": _por_localidade(conn, fonte, filtros),
        "por_agente": _por_agente(conn, fonte, filtros),
    }


def _where_fonte(fonte, filtros):
    alias = fonte["alias"]
    data_col = _data_expr(fonte)
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
        vinculo_direto = _vinculo_agente_sql(fonte, alias)
        if vinculo_direto:
            clauses.append(
                f"""EXISTS (
                        SELECT 1
                          FROM agentes ag
                         WHERE {vinculo_direto}
                           AND ag.nome IN ({_placeholders(agentes)})
                    )"""
            )
        else:
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
    data_expr = _data_expr(fonte)
    mes_expr = db_core.month_expression(data_expr)
    rows = conn.execute(
        f"""
        SELECT {mes_expr} AS mes,
               COUNT(DISTINCT {id_expr}) AS registros
          FROM {fonte['tabela']} {alias}
          {fonte.get('joins') or ''}
         WHERE {where}
         GROUP BY {mes_expr}
         ORDER BY mes
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _por_dia(conn, fonte, filtros):
    """Producao diaria da fonte, para somar os dias de todas as atividades."""
    where, params = _where_fonte(fonte, filtros)
    alias = fonte["alias"]
    id_expr = f"{alias}.{fonte['id_col']}"
    # O texto mantem o mesmo formato nos dois bancos e permite somar os dias
    # de fontes diferentes sem misturar date com string.
    dia_expr = f"CAST({_data_expr(fonte)} AS TEXT)"
    rows = conn.execute(
        f"""
        SELECT {dia_expr} AS dia,
               COUNT(DISTINCT {id_expr}) AS registros
          FROM {fonte['tabela']} {alias}
          {fonte.get('joins') or ''}
         WHERE {where}
         GROUP BY {dia_expr}
         ORDER BY dia
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
        HAVING COALESCE({localidade_expr}, '-') <> '-'
         ORDER BY registros DESC, localidade
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _por_agente(conn, fonte, filtros):
    where, params = _where_fonte(fonte, filtros)
    alias = fonte["alias"]
    id_expr = f"{alias}.{fonte['id_col']}"
    vinculo_direto = _vinculo_agente_sql(fonte, alias)
    if vinculo_direto:
        join_agente = f"JOIN agentes ag ON {vinculo_direto}"
    else:
        join_agente = (
            f"JOIN {fonte['agente_table']} pa ON pa.{fonte['agente_fk']}={id_expr} "
            f"JOIN agentes ag ON ag.id_agente=pa.id_agente"
        )
    rows = conn.execute(
        f"""
        SELECT COALESCE(NULLIF(ag.nome_completo,''), ag.nome) AS agente,
               COUNT(DISTINCT {id_expr}) AS registros
          FROM {fonte['tabela']} {alias}
          {join_agente}
          {fonte.get('joins') or ''}
         WHERE {where}
         GROUP BY ag.id_agente, ag.nome, ag.nome_completo
         ORDER BY registros DESC, agente
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
        if nome_coluna in ("mes", "dia")
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
