"""Consulta unificada de focos positivos de *Aedes aegypti*.

Os focos anteriores ao sistema nao possuem, em geral, uma coleta/tubo ou as
quantidades por forma do vetor. Eles foram preservados em ``focos_positivos``
com ``origem='historico'``. Ja as leituras atuais sao apuradas diretamente em
``resultados_laboratorio``. Esta camada apresenta as duas fontes lado a lado,
sem atribuir detalhes laboratoriais inexistentes aos registros legados.
"""

from app_core import db as db_core
from app_core import normalizadores
from app_core import utils as utils_core


AEGYPT_TOTAL_SQL = " + ".join(
    f"COALESCE(rl.aegypt_{forma},0)"
    for forma in ("larvas", "pupas", "exuvias", "adulto")
)


def listar(target, args, pagina=1, por_pagina=50):
    """Lista positivos de Aedes aegypti, atuais e pre-sistema."""
    consultas = _consultas(args)
    backend = getattr(target, "backend", None) or (
        "sqlite" if db_core.is_sqlite(target) else "postgresql"
    )
    conn, close = _open_connection(target)
    try:
        _preparar_filtro_localidades(conn, consultas)
        union_sql, params = _union_sql(consultas, backend)
        total = conn.execute(
            f"SELECT COUNT(*) FROM ({union_sql}) positivos",
            params,
        ).fetchone()[0]
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        pagina = min(max(1, pagina), total_paginas)
        offset = (pagina - 1) * por_pagina
        registros = conn.execute(
            f"""SELECT * FROM ({union_sql}) positivos
                 ORDER BY data DESC, origem ASC, id_registro DESC
                 LIMIT ? OFFSET ?""",
            params + [por_pagina, offset],
        ).fetchall()
        totais = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN origem='historico' THEN 1 ELSE 0 END),0) AS historico,
                       COALESCE(SUM(CASE WHEN origem='laboratorio' THEN 1 ELSE 0 END),0) AS laboratorio,
                       COALESCE(SUM(aegypti_total),0) AS aegypti_quantificado
                  FROM ({union_sql}) positivos""",
            params,
        ).fetchone()
        por_localidade = conn.execute(
            f"""SELECT localidade, COUNT(*) AS total,
                       COALESCE(SUM(CASE WHEN origem='historico' THEN 1 ELSE 0 END),0) AS historico,
                       COALESCE(SUM(CASE WHEN origem='laboratorio' THEN 1 ELSE 0 END),0) AS laboratorio
                  FROM ({union_sql}) positivos
                 GROUP BY localidade
                 ORDER BY total DESC, localidade""",
            params,
        ).fetchall()
    finally:
        if close:
            conn.close()

    return {
        "total": total,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "totais": db_core.serialize_row(totais),
        "por_localidade": _agrupar_por_localidade(por_localidade),
        "registros": [_normalizar_registro(row) for row in registros],
    }


def opcoes(target):
    """Opcoes que incluem os tipos/localidades preservados apenas no legado."""
    conn, close = _open_connection(target)
    try:
        tipos = conn.execute(
            """SELECT DISTINCT tipo FROM (
                   SELECT tipo FROM visitas WHERE tipo IS NOT NULL AND TRIM(CAST(tipo AS TEXT))<>''
                   UNION
                   SELECT tipo_trabalho AS tipo FROM focos_positivos
                    WHERE origem='historico' AND tipo_trabalho IS NOT NULL
                      AND TRIM(CAST(tipo_trabalho AS TEXT))<>''
               ) opcoes ORDER BY tipo"""
        ).fetchall()
        localidades = conn.execute(
            """SELECT DISTINCT localidade FROM (
                   SELECT nome AS localidade FROM localidades WHERE nome IS NOT NULL AND TRIM(CAST(nome AS TEXT))<>''
                   UNION
                   SELECT localidade FROM visitas WHERE localidade IS NOT NULL AND TRIM(CAST(localidade AS TEXT))<>''
                   UNION
                   SELECT localidade FROM focos_positivos
                    WHERE origem='historico' AND localidade IS NOT NULL
                      AND TRIM(CAST(localidade AS TEXT))<>''
               ) opcoes ORDER BY localidade"""
        ).fetchall()
    finally:
        if close:
            conn.close()
    return {
        "tipos": [row[0] for row in tipos],
        "localidades": _localidades_normalizadas(row[0] for row in localidades),
    }


def _consultas(args):
    fonte = str(args.get("fonte") or "todos").strip().lower()
    if fonte not in {"todos", "historico", "laboratorio"}:
        fonte = "todos"
    return {
        "d_ini": args.get("d_ini") or utils_core.data_n_dias(365),
        "d_fim": args.get("d_fim") or utils_core.hoje(),
        "tipos": _values(args, "tipo"),
        "localidades": _values(args, "localidade"),
        "agentes": _values(args, "agente"),
        "busca": str(args.get("busca") or "").strip(),
        "fonte": fonte,
    }


def _union_sql(consultas, backend):
    partes, params = [], []
    if consultas["fonte"] in {"todos", "laboratorio"}:
        sql, valores = _laboratorio_sql(consultas, backend)
        partes.append(sql)
        params.extend(valores)
    if consultas["fonte"] in {"todos", "historico"}:
        sql, valores = _historico_sql(consultas)
        partes.append(sql)
        params.extend(valores)
    return " UNION ALL ".join(partes), params


def _laboratorio_sql(consultas, backend):
    clauses = ["v.data BETWEEN ? AND ?", f"({AEGYPT_TOTAL_SQL}) > 0"]
    params = [consultas["d_ini"], consultas["d_fim"]]
    if consultas["tipos"]:
        clauses.append(f"v.tipo IN ({_placeholders(consultas['tipos'])})")
        params.extend(consultas["tipos"])
    if consultas["localidades"]:
        clauses.append(
            "COALESCE(l.nome, v.localidade) "
            f"IN ({_placeholders(_localidades_para_sql(consultas))})"
        )
        params.extend(_localidades_para_sql(consultas))
    if consultas["agentes"]:
        clauses.append(
            f"""EXISTS (
                    SELECT 1 FROM visita_agentes va_filtro
                    JOIN agentes a_filtro ON a_filtro.id_agente=va_filtro.id_agente
                    WHERE va_filtro.id_visita=v.id_visita
                      AND a_filtro.nome IN ({_placeholders(consultas['agentes'])})
                )"""
        )
        params.extend(consultas["agentes"])
    if consultas["busca"]:
        clauses.append(_busca_sql("v", "c", "v.morador"))
        params.extend(_busca_params(consultas["busca"]))
    agentes = _agentes_sql("v.id_visita", backend)
    return f"""
        SELECT 'laboratorio' AS origem,
               'Leitura laboratorial' AS origem_rotulo,
               CAST(rl.id_resultado AS TEXT) AS id_registro,
               v.id_visita, c.id_coleta, rl.id_resultado,
               CAST(v.data AS TEXT) AS data, COALESCE(l.nome, v.localidade) AS localidade,
               v.quarteirao, v.logradouro, v.numero, NULL AS complemento,
               v.morador AS morador, v.tipo AS tipo, v.tipo_imovel,
               c.num_tubo, c.tipo_deposito AS depositos,
               ({agentes}) AS agentes,
               {AEGYPT_TOTAL_SQL} AS aegypti_total,
               rl.aegypt_larvas, rl.aegypt_pupas, rl.aegypt_exuvias, rl.aegypt_adulto,
               0 AS legado_sem_detalhe
          FROM resultados_laboratorio rl
          JOIN coletas c ON c.id_coleta=rl.id_coleta
          JOIN visitas v ON v.id_visita=c.id_visita
          LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
         WHERE {' AND '.join(clauses)}
    """, params


def _historico_sql(consultas):
    clauses = [
        "f.origem='historico'",
        "f.data BETWEEN ? AND ?",
    ]
    params = [consultas["d_ini"], consultas["d_fim"]]
    if consultas["tipos"]:
        clauses.append(f"f.tipo_trabalho IN ({_placeholders(consultas['tipos'])})")
        params.extend(consultas["tipos"])
    if consultas["localidades"]:
        clauses.append(
            "COALESCE(l.nome, f.localidade) "
            f"IN ({_placeholders(_localidades_para_sql(consultas))})"
        )
        params.extend(_localidades_para_sql(consultas))
    if consultas["agentes"]:
        partes = ["LOWER(COALESCE(CAST(f.agentes AS TEXT),'')) LIKE LOWER(?)" for _ in consultas["agentes"]]
        clauses.append("(" + " OR ".join(partes) + ")")
        params.extend(f"%{agente}%" for agente in consultas["agentes"])
    if consultas["busca"]:
        clauses.append(_busca_sql("f", "f", "f.nome_morador"))
        params.extend(_busca_params(consultas["busca"]))
    return f"""
        SELECT 'historico' AS origem,
               'Histórico pré-sistema' AS origem_rotulo,
               f.id_foco AS id_registro,
               f.id_visita, f.id_coleta, f.id_resultado,
               CAST(f.data AS TEXT) AS data, COALESCE(l.nome, f.localidade) AS localidade,
               f.quarteirao, f.logradouro, f.numero, f.complemento,
               f.nome_morador AS morador, f.tipo_trabalho AS tipo, f.tipo_imovel,
               f.num_tubo, f.depositos, f.agentes,
               0 AS aegypti_total,
               NULL AS aegypt_larvas, NULL AS aegypt_pupas,
               NULL AS aegypt_exuvias, NULL AS aegypt_adulto,
               1 AS legado_sem_detalhe
          FROM focos_positivos f
          LEFT JOIN localidades l ON l.id_localidade=f.id_localidade
         WHERE {' AND '.join(clauses)}
    """, params


def _busca_sql(visita_alias, coleta_alias, morador_expr):
    return f"""(
        LOWER(COALESCE(CAST({visita_alias}.logradouro AS TEXT),'')) LIKE LOWER(?) OR
        LOWER(COALESCE(CAST({visita_alias}.numero AS TEXT),'')) LIKE LOWER(?) OR
        LOWER(COALESCE(CAST({morador_expr} AS TEXT),'')) LIKE LOWER(?) OR
        LOWER(COALESCE(CAST({visita_alias}.quarteirao AS TEXT),'')) LIKE LOWER(?) OR
        LOWER(COALESCE(CAST({coleta_alias}.num_tubo AS TEXT),'')) LIKE LOWER(?)
    )"""


def _busca_params(busca):
    return [f"%{busca}%"] * 5


def _agentes_sql(id_visita_expr, backend):
    agregador = (
        "string_agg(nomes.nome, ', ' ORDER BY nomes.nome)"
        if backend == "postgresql"
        else "GROUP_CONCAT(nomes.nome, ', ')"
    )
    return f"""SELECT {agregador}
                  FROM (
                        SELECT DISTINCT a.nome
                          FROM visita_agentes va
                          JOIN agentes a ON a.id_agente=va.id_agente
                         WHERE va.id_visita={id_visita_expr}
                  ) nomes"""


def _values(args, key):
    if hasattr(args, "getlist"):
        values = args.getlist(key)
    else:
        raw = args.get(key, [])
        values = raw if isinstance(raw, (list, tuple)) else [raw]
    return [str(value).strip() for value in values if str(value or "").strip()]


def _placeholders(values):
    return ",".join("?" for _ in values)


def _preparar_filtro_localidades(conn, consultas):
    if not consultas["localidades"]:
        return
    rows = conn.execute(
        """SELECT localidade FROM (
               SELECT nome AS localidade FROM localidades
               UNION SELECT localidade FROM visitas
               UNION SELECT localidade FROM focos_positivos WHERE origem='historico'
           ) opcoes WHERE localidade IS NOT NULL
             AND TRIM(CAST(localidade AS TEXT))<>''"""
    ).fetchall()
    selecionadas = set(consultas["localidades"])
    variantes = [
        row[0] for row in rows
        if normalizadores.normalizar_localidade(row[0]) in selecionadas
    ]
    consultas["localidades_bd"] = variantes or consultas["localidades"]


def _localidades_para_sql(consultas):
    return consultas.get("localidades_bd", consultas["localidades"])


def _localidades_normalizadas(values):
    normalizadas = {
        normalizadores.normalizar_localidade(value)
        for value in values
        if normalizadores.normalizar_localidade(value)
    }
    return sorted(normalizadas, key=lambda value: value.casefold())


def _normalizar_registro(row):
    registro = db_core.serialize_row(row)
    registro["localidade"] = normalizadores.normalizar_localidade(registro.get("localidade"))
    return registro


def _agrupar_por_localidade(rows):
    grupos = {}
    for row in rows:
        item = db_core.serialize_row(row)
        localidade = normalizadores.normalizar_localidade(item.get("localidade")) or "Não informada"
        grupo = grupos.setdefault(localidade, {
            "localidade": localidade, "total": 0, "historico": 0, "laboratorio": 0,
        })
        for campo in ("total", "historico", "laboratorio"):
            grupo[campo] += item.get(campo) or 0
    return sorted(grupos.values(), key=lambda item: (-item["total"], item["localidade"].casefold()))


def _open_connection(target):
    if hasattr(target, "execute"):
        return target, False
    return db_core.connect(target), True
