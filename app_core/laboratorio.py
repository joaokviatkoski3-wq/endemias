from app_core import db as db_core
from app_core import utils as utils_core


def listar(target, args, pagina=1, por_pagina=50):
    where, params = _where(args)
    base = f"""
        FROM resultados_laboratorio rl
        JOIN coletas c ON c.id_coleta=rl.id_coleta
        JOIN visitas v ON v.id_visita=c.id_visita
        LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
        {where}
    """
    conn, close = _open_connection(target)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) {base}",
            params,
        ).fetchone()[0]
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        pagina = min(max(1, pagina), total_paginas)
        offset = (pagina - 1) * por_pagina
        agentes_agg = _string_aggregate(conn, "nomes.nome")
        aeg = _presence_sql("aegypt", "rl")
        alb = _presence_sql("albopictus", "rl")
        outra = _presence_sql("outra", "rl")

        rows = conn.execute(
            f"""
            SELECT rl.id_resultado, v.data, v.tipo,
                   COALESCE(l.nome, v.localidade) AS localidade,
                   v.quarteirao, v.logradouro, v.numero,
                   c.num_tubo, c.tipo_deposito,
                   rl.data_leitura, rl.laboratorista,
                   rl.aegypt_larvas, rl.aegypt_pupas,
                   rl.aegypt_exuvias, rl.aegypt_adulto,
                   rl.albopictus_larvas, rl.albopictus_pupas,
                   rl.albopictus_exuvias, rl.albopictus_adulto,
                   rl.outra_larvas, rl.outra_pupas,
                   rl.outra_exuvias, rl.outra_adulto,
                   (
                       SELECT {agentes_agg}
                         FROM (
                               SELECT DISTINCT a.nome
                                 FROM visita_agentes va
                                 JOIN agentes a
                                   ON a.id_agente=va.id_agente
                                WHERE va.id_visita=v.id_visita
                         ) nomes
                   ) AS agentes,
                   CASE WHEN {aeg} THEN 1 ELSE 0 END AS pos_aeg,
                   CASE WHEN {alb} THEN 1 ELSE 0 END AS pos_alb,
                   CASE WHEN {outra} THEN 1 ELSE 0 END AS pos_out
              {base}
             ORDER BY v.data DESC, rl.id_resultado DESC
             LIMIT ? OFFSET ?
            """,
            params + [por_pagina, offset],
        ).fetchall()

        totais = conn.execute(
            f"""
            SELECT
                COALESCE(SUM({_total_sql("aegypt", "rl")}), 0)
                    AS total_aeg,
                COALESCE(SUM({_total_sql("albopictus", "rl")}), 0)
                    AS total_alb,
                COALESCE(SUM({_total_sql("outra", "rl")}), 0)
                    AS total_out,
                COUNT(*) AS total_col,
                COALESCE(SUM(CASE WHEN {aeg} THEN 1 ELSE 0 END), 0)
                    AS pos_aeg,
                COALESCE(SUM(CASE WHEN {alb} THEN 1 ELSE 0 END), 0)
                    AS pos_alb
              {base}
            """,
            params,
        ).fetchone()

        mes_expr = db_core.month_expression("v.data")
        evolucao = conn.execute(
            f"""
            SELECT {mes_expr} AS mes,
                   COUNT(*) AS total,
                   SUM(CASE WHEN {aeg} THEN 1 ELSE 0 END) AS positivos
              {base}
             GROUP BY {mes_expr}
             ORDER BY mes
            """,
            params,
        ).fetchall()
        por_localidade = conn.execute(
            f"""
            SELECT COALESCE(l.nome, v.localidade) AS loc,
                   COUNT(*) AS total,
                   SUM(CASE WHEN {aeg} THEN 1 ELSE 0 END) AS positivos
              {base}
             GROUP BY COALESCE(l.nome, v.localidade)
             ORDER BY total DESC
            """,
            params,
        ).fetchall()
    finally:
        if close:
            conn.close()

    total_coletas = utils_core.safe_int(totais["total_col"])
    positivos_aeg = utils_core.safe_int(totais["pos_aeg"])
    return {
        "total": total,
        "total_paginas": total_paginas,
        "pagina": pagina,
        "totais": {
            "total_coletas": total_coletas,
            "aegypti": utils_core.safe_int(totais["total_aeg"]),
            "albopictus": utils_core.safe_int(totais["total_alb"]),
            "outra": utils_core.safe_int(totais["total_out"]),
            "positivos_aeg": positivos_aeg,
            "positivos_alb": utils_core.safe_int(totais["pos_alb"]),
            "indice_pos": (
                round(positivos_aeg / total_coletas * 100, 1)
                if total_coletas
                else 0
            ),
        },
        "evolucao": [db_core.serialize_row(row) for row in evolucao],
        "por_loc": [
            db_core.serialize_row(row) for row in por_localidade
        ],
        "registros": [db_core.serialize_row(row) for row in rows],
    }


def _where(args):
    d_ini = args.get("d_ini") or utils_core.data_n_dias(365)
    d_fim = args.get("d_fim") or utils_core.hoje()
    tipos = _values(args, "tipo")
    localidades = _values(args, "localidade")
    agentes = _values(args, "agente")
    tubo = str(args.get("tubo") or "").strip()
    especie = str(args.get("especie") or "").strip()
    apenas_positivos = str(args.get("apenas_pos") or "").strip()
    clauses = ["v.data BETWEEN ? AND ?"]
    params = [d_ini, d_fim]

    if tipos:
        clauses.append(f"v.tipo IN ({_placeholders(tipos)})")
        params.extend(tipos)
    if localidades:
        clauses.append(
            "COALESCE(l.nome, v.localidade) "
            f"IN ({_placeholders(localidades)})"
        )
        params.extend(localidades)
    if agentes:
        clauses.append(
            f"""EXISTS (
                    SELECT 1
                      FROM visita_agentes va_filtro
                      JOIN agentes a_filtro
                        ON a_filtro.id_agente=va_filtro.id_agente
                     WHERE va_filtro.id_visita=v.id_visita
                       AND a_filtro.nome IN ({_placeholders(agentes)})
                )"""
        )
        params.extend(agentes)
    if tubo:
        clauses.append(
            "LOWER(COALESCE(c.num_tubo, '')) LIKE LOWER(?)"
        )
        params.append(f"%{tubo}%")

    if apenas_positivos == "1" or especie == "aegypti":
        clauses.append(_presence_sql("aegypt", "rl"))
    elif especie == "albopictus":
        clauses.append(_presence_sql("albopictus", "rl"))
    elif especie == "outra":
        clauses.append(_presence_sql("outra", "rl"))

    return "WHERE " + " AND ".join(clauses), params


def _presence_sql(prefix, alias):
    return f"({_total_sql(prefix, alias)}) > 0"


def _total_sql(prefix, alias):
    return " + ".join(
        f"COALESCE({alias}.{prefix}_{forma}, 0)"
        for forma in ("larvas", "pupas", "exuvias", "adulto")
    )


def _string_aggregate(conn, expression):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return f"string_agg({expression}, ', ' ORDER BY {expression})"
    return f"GROUP_CONCAT({expression}, ', ')"


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


def _open_connection(target):
    if hasattr(target, "execute"):
        return target, False
    return db_core.connect(target), True
