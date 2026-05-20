from datetime import date

from app_core import db as db_core
from app_core import work_types


DEPOSIT_TYPES = ("A1", "A2", "B", "C", "D1", "D2", "E")
WORK_TYPES_ALLOWED = set(work_types.WORK_TYPE_CODES)


class ValidationError(ValueError):
    pass


def parse_iso_date(value, field_name="data"):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} invalida.")


def parse_int(value, field_name, minimo=None, maximo=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} invalido.")
    if minimo is not None and result < minimo:
        raise ValidationError(f"{field_name} abaixo do minimo.")
    if maximo is not None and result > maximo:
        raise ValidationError(f"{field_name} acima do maximo.")
    return result


def epidemiological_week_range(year, week):
    year = parse_int(year, "ano", 2020, 2099)
    week = parse_int(week, "semana", 1, 53)
    try:
        start = date.fromisocalendar(year, week, 1)
        end = date.fromisocalendar(year, week, 7)
    except ValueError:
        raise ValidationError("Semana epidemiologica invalida para o ano informado.")
    return start.isoformat(), end.isoformat()


def normalize_work_types(values):
    selected = []
    for value in values or []:
        if not value:
            continue
        code = str(value).strip().upper()
        if code in ("TB/TBO", "TB_TBO"):
            candidates = ("TB", "TBO")
        else:
            candidates = (code,)
        for candidate in candidates:
            if candidate not in WORK_TYPES_ALLOWED:
                raise ValidationError(f"Tipo de trabalho invalido: {candidate}.")
            if candidate not in selected:
                selected.append(candidate)
    if not selected:
        raise ValidationError("Selecione ao menos um tipo de trabalho.")
    return selected


def optional_localidade(value):
    if value in (None, "", "null"):
        return None
    return parse_int(value, "localidade", 1)


def _placeholders(items):
    return ",".join("?" for _ in items)


def _base_where(data_inicio, data_fim, tipos, id_localidade=None, alias="v"):
    clauses = [
        f"{alias}.data BETWEEN ? AND ?",
        f"{alias}.tipo IN ({_placeholders(tipos)})",
    ]
    params = [data_inicio, data_fim] + list(tipos)
    if id_localidade:
        clauses.append(f"{alias}.id_localidade = ?")
        params.append(id_localidade)
    return " AND ".join(clauses), params


def _empty_kind_dict():
    return {
        "residencia": 0,
        "comercio": 0,
        "tb": 0,
        "pe": 0,
        "outros": 0,
    }


def _kind_sql(alias="v"):
    raw = f"LOWER(COALESCE({alias}.tipo_imovel, ''))"
    return (
        f"CASE "
        f"WHEN {raw} LIKE 'resid%' THEN 'residencia' "
        f"WHEN {raw} LIKE 'com%rcio' OR {raw} LIKE 'comercio' THEN 'comercio' "
        f"WHEN {raw} LIKE '%terreno%' OR {alias}.tipo = 'TB' THEN 'tb' "
        f"WHEN {alias}.tipo = 'PE' THEN 'pe' "
        f"ELSE 'outros' END"
    )


def get_default_conta_ovos(db_path):
    row = db_core.query_one(
        db_path,
        """
        SELECT data, quarteirao
          FROM visitas
         WHERE tipo='TBO'
           AND CONTAOVOS_STATUS = 0
           AND quarteirao IS NOT NULL
         GROUP BY data, quarteirao
         ORDER BY data DESC, COUNT(*) DESC
         LIMIT 1
        """,
    )
    return row or {"data": date.today().isoformat(), "quarteirao": ""}


def pendencias_envio(db_path, limite_grupos=None):
    conn = db_core.connect(db_path)
    try:
        conta_total = conn.execute(
            "SELECT COUNT(*) FROM visitas WHERE tipo='TBO' AND CONTAOVOS_STATUS = 0"
        ).fetchone()[0] or 0
        conta_sql = """
                SELECT data,
                       quarteirao,
                       COALESCE(localidade, '-') AS localidade,
                       COUNT(*) AS total
                  FROM visitas
                 WHERE tipo='TBO'
                   AND CONTAOVOS_STATUS = 0
                 GROUP BY data, quarteirao, COALESCE(localidade, '-')
                 ORDER BY data DESC, total DESC
                """
        conta_params = ()
        if limite_grupos:
            conta_sql += " LIMIT ?"
            conta_params = (limite_grupos,)
        conta_grupos = [
            dict(row)
            for row in conn.execute(conta_sql, conta_params)
        ]

        sispncd_total = conn.execute(
            "SELECT COUNT(*) FROM visitas WHERE SISPNCD IS NULL"
        ).fetchone()[0] or 0
        sispncd_sql = """
                SELECT tipo,
                       COALESCE(localidade, '-') AS localidade,
                       MIN(data) AS data_inicio,
                       MAX(data) AS data_fim,
                       COUNT(*) AS total
                  FROM visitas
                 WHERE SISPNCD IS NULL
                 GROUP BY tipo, COALESCE(localidade, '-')
                 ORDER BY total DESC, tipo, localidade
                """
        sispncd_params = ()
        if limite_grupos:
            sispncd_sql += " LIMIT ?"
            sispncd_params = (limite_grupos,)
        sispncd_grupos = [
            dict(row)
            for row in conn.execute(sispncd_sql, sispncd_params)
        ]
    finally:
        conn.close()

    return {
        "conta_ovos": {"total": conta_total, "total_grupos": len(conta_grupos), "grupos": conta_grupos},
        "sispncd": {"total": sispncd_total, "total_grupos": len(sispncd_grupos), "grupos": sispncd_grupos},
    }


def salvar_status_conta_ovos(db_path, data, quarteirao, id_localidade=None):
    data = parse_iso_date(data)
    quarteirao = parse_int(quarteirao, "quarteirao", 0)
    id_localidade = optional_localidade(id_localidade)

    where = (
        "tipo = 'TBO' "
        "AND CONTAOVOS_STATUS = 0 "
        "AND data = ? "
        "AND quarteirao = ?"
    )
    params = [data, quarteirao]
    if id_localidade:
        where += " AND id_localidade = ?"
        params.append(id_localidade)

    conn = db_core.connect(db_path)
    try:
        cur = conn.execute(
            f"UPDATE visitas SET CONTAOVOS_STATUS = 1 WHERE {where}",
            params,
        )
        conn.commit()
        atualizados = cur.rowcount if cur.rowcount is not None else 0
    finally:
        conn.close()

    return {"ok": True, "atualizados": atualizados, "data": data, "quarteirao": quarteirao}


def conta_ovos(db_path, data, quarteirao, id_localidade=None):
    data = parse_iso_date(data)
    quarteirao = parse_int(quarteirao, "quarteirao", 0)
    id_localidade = optional_localidade(id_localidade)

    where = (
        "v.tipo = 'TBO' "
        "AND v.CONTAOVOS_STATUS = 0 "
        "AND v.data = ? "
        "AND v.quarteirao = ?"
    )
    params = [data, quarteirao]
    if id_localidade:
        where += " AND v.id_localidade = ?"
        params.append(id_localidade)

    conn = db_core.connect(db_path)
    try:
        imoveis_rows = conn.execute(
            f"""
            WITH base AS (
                SELECT v.id_visita, v.tipo_imovel, v.tipo, v.visita
                  FROM visitas v
                 WHERE {where}
            ),
            com_coleta AS (
                SELECT DISTINCT id_visita FROM coletas
            ),
            tratados AS (
                SELECT DISTINCT id_visita
                  FROM depositos_inspecionados
                 WHERE COALESCE(tratado, 0) > 0
            )
            SELECT {_kind_sql('b')} AS categoria,
                   COUNT(CASE WHEN LOWER(COALESCE(b.visita,'')) IN ('normal','recuperado') THEN 1 END) AS visitas,
                   COUNT(CASE WHEN LOWER(COALESCE(b.visita,'')) IN ('fechado','recusa') THEN 1 END) AS pendencias,
                   COUNT(CASE WHEN cc.id_visita IS NOT NULL THEN 1 END) AS positivas,
                   COUNT(CASE WHEN tr.id_visita IS NOT NULL THEN 1 END) AS tratadas
              FROM base b
              LEFT JOIN com_coleta cc ON cc.id_visita = b.id_visita
              LEFT JOIN tratados tr ON tr.id_visita = b.id_visita
             GROUP BY categoria
            """,
            params,
        ).fetchall()

        deposito_rows = conn.execute(
            f"""
            SELECT di.tipo_deposito,
                   COALESCE(SUM(di.inspecionado), 0) AS quantidade,
                   COALESCE(SUM(di.eliminado), 0) AS eliminado,
                   COALESCE(SUM(di.tratado), 0) AS tratado,
                   COALESCE(ROUND(SUM(di.qtd_carga), 2), 0) AS larvicida_mg
              FROM depositos_inspecionados di
              JOIN visitas v ON v.id_visita = di.id_visita
             WHERE {where}
               AND di.tipo_deposito IN ({_placeholders(DEPOSIT_TYPES)})
             GROUP BY di.tipo_deposito
            """,
            params + list(DEPOSIT_TYPES),
        ).fetchall()
    finally:
        conn.close()

    imoveis = {
        key: {"visitas": 0, "pendencias": 0, "positivas": 0, "tratadas": 0}
        for key in ("residencia", "comercio", "tb", "pe", "outros")
    }
    for row in imoveis_rows:
        imoveis[row["categoria"]] = {
            "visitas": row["visitas"] or 0,
            "pendencias": row["pendencias"] or 0,
            "positivas": row["positivas"] or 0,
            "tratadas": row["tratadas"] or 0,
        }

    depositos = {
        code.lower(): {
            "quantidade": 0,
            "eliminado": 0,
            "tratado": 0,
            "larvicida_mg": 0,
        }
        for code in DEPOSIT_TYPES
    }
    for row in deposito_rows:
        depositos[str(row["tipo_deposito"]).lower()] = {
            "quantidade": row["quantidade"] or 0,
            "eliminado": row["eliminado"] or 0,
            "tratado": row["tratado"] or 0,
            "larvicida_mg": row["larvicida_mg"] or 0,
        }

    return {
        "data": data,
        "quarteirao": quarteirao,
        "imoveis": imoveis,
        "depositos": depositos,
        "total_visitas": sum(v["visitas"] + v["pendencias"] for v in imoveis.values()),
    }


def sispncd(db_path, year, week, tipos, id_localidade=None):
    data_inicio, data_fim = epidemiological_week_range(year, week)
    tipos = normalize_work_types(tipos)
    id_localidade = optional_localidade(id_localidade)
    where, params = _base_where(data_inicio, data_fim, tipos, id_localidade)
    kind_expr = _kind_sql("v")

    dados = {
        "total_quarteiroes": 0,
        "imoveis": _empty_kind_dict(),
        "imoveis_tratados": 0,
        "imoveis_inspecionados": 0,
        "total_coletas": 0,
        "pendencias": {"recusa": 0, "fechado": 0, "recuperado": 0},
        "depositos": {code.lower(): 0 for code in DEPOSIT_TYPES},
        "total_eliminados": 0,
        "total_tratados": 0,
        "tratamentos": [],
        "total_agentes": 0,
        "total_dias": 0,
    }
    lab = {
        "depositos_aegypti": [],
        "depositos_albopictus": [],
        "imoveis_aegypti": _empty_kind_dict(),
        "imoveis_albopictus": _empty_kind_dict(),
        "imoveis_outras": _empty_kind_dict(),
        "exemplares_aegypti": {"larvas": 0, "pupas": 0, "exuvias": 0, "adultos": 0},
        "exemplares_albopictus": {"larvas": 0, "pupas": 0, "exuvias": 0, "adultos": 0},
        "exemplares_outras": {"larvas": 0, "pupas": 0, "exuvias": 0, "adultos": 0},
        "quarteiroes_aegypti": 0,
        "quarteiroes_albopictus": 0,
        "quarteiroes_ambas": 0,
    }

    conn = db_core.connect(db_path)
    try:
        tb_types = [t for t in tipos if t in ("TB", "TBO")]
        if tb_types:
            tb_where, tb_params = _base_where(data_inicio, data_fim, tb_types, id_localidade)
            dados["total_quarteiroes"] = conn.execute(
                f"SELECT COUNT(DISTINCT quarteirao) FROM visitas v WHERE {tb_where}",
                tb_params,
            ).fetchone()[0] or 0

        for row in conn.execute(
            f"SELECT {kind_expr} AS categoria, COUNT(DISTINCT v.id_visita) AS total FROM visitas v WHERE {where} GROUP BY categoria",
            params,
        ):
            dados["imoveis"][row["categoria"]] = row["total"] or 0

        dados["imoveis_tratados"] = conn.execute(
            f"""
            SELECT COUNT(DISTINCT t.id_visita)
              FROM tratamentos t
              JOIN visitas v ON v.id_visita = t.id_visita
             WHERE {where}
            """,
            params,
        ).fetchone()[0] or 0

        dados["imoveis_inspecionados"] = conn.execute(
            f"""
            SELECT COUNT(DISTINCT v.id_visita)
              FROM visitas v
             WHERE {where}
               AND LOWER(COALESCE(v.visita,'')) IN ('normal','recuperado')
            """,
            params,
        ).fetchone()[0] or 0

        dados["total_coletas"] = conn.execute(
            f"""
            SELECT COUNT(DISTINCT c.id_coleta)
              FROM coletas c
              JOIN visitas v ON v.id_visita = c.id_visita
             WHERE {where}
            """,
            params,
        ).fetchone()[0] or 0

        for row in conn.execute(
            f"""
            SELECT LOWER(v.visita) AS tipo_pendencia, COUNT(DISTINCT v.id_visita) AS total
              FROM visitas v
             WHERE {where}
               AND LOWER(COALESCE(v.visita,'')) IN ('recusa','fechado','recuperado')
             GROUP BY LOWER(v.visita)
            """,
            params,
        ):
            dados["pendencias"][row["tipo_pendencia"]] = row["total"] or 0

        dep_types = [t for t in tipos if t != "TBO"]
        if dep_types:
            dep_where, dep_params = _base_where(data_inicio, data_fim, dep_types, id_localidade)
            for row in conn.execute(
                f"""
                SELECT di.tipo_deposito, COALESCE(SUM(di.inspecionado), 0) AS total
                  FROM depositos_inspecionados di
                  JOIN visitas v ON v.id_visita = di.id_visita
                 WHERE {dep_where}
                   AND di.tipo_deposito IN ({_placeholders(DEPOSIT_TYPES)})
                 GROUP BY di.tipo_deposito
                """,
                dep_params + list(DEPOSIT_TYPES),
            ):
                dados["depositos"][str(row["tipo_deposito"]).lower()] = row["total"] or 0

        dados["total_eliminados"] = conn.execute(
            f"""
            SELECT COALESCE(SUM(di.eliminado), 0)
              FROM depositos_inspecionados di
              JOIN visitas v ON v.id_visita = di.id_visita
             WHERE {where}
               AND di.tipo_deposito IN ({_placeholders(DEPOSIT_TYPES)})
            """,
            params + list(DEPOSIT_TYPES),
        ).fetchone()[0] or 0

        dados["tratamentos"] = [
            {
                "tipo": row["tipo_tratamento"] or "Sem tipo",
                "quantidade": row["quantidade_tratamentos"] or 0,
                "carga_kg": row["total_carga_kg"] or 0,
            }
            for row in conn.execute(
                f"""
                SELECT COALESCE(t.tipo, 'Sem tipo') AS tipo_tratamento,
                       COUNT(t.id) AS quantidade_tratamentos,
                       COALESCE(SUM(t.quantidade_carga), 0) AS total_carga_kg
                  FROM tratamentos t
                  JOIN visitas v ON v.id_visita = t.id_visita
                 WHERE {where}
                 GROUP BY COALESCE(t.tipo, 'Sem tipo')
                 ORDER BY tipo_tratamento
                """,
                params,
            )
        ]
        dados["total_tratados"] = sum(row["quantidade"] for row in dados["tratamentos"])

        dados["total_agentes"] = conn.execute(
            f"""
            SELECT COUNT(DISTINCT va.id_agente)
              FROM visita_agentes va
              JOIN visitas v ON v.id_visita = va.id_visita
             WHERE {where}
            """,
            params,
        ).fetchone()[0] or 0

        dados["total_dias"] = conn.execute(
            f"SELECT COUNT(DISTINCT v.data) FROM visitas v WHERE {where}",
            params,
        ).fetchone()[0] or 0

        _fill_laboratorio(conn, lab, where, params, kind_expr)
    finally:
        conn.close()

    return {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "tipos": tipos,
        "dados_gerais": dados,
        "laboratorio": lab,
    }


def salvar_sispncd(db_path, year, week, tipos, codigo, id_localidade=None):
    data_inicio, data_fim = epidemiological_week_range(year, week)
    if isinstance(tipos, str):
        tipos = [tipos]
    tipos = normalize_work_types(tipos)
    id_localidade = optional_localidade(id_localidade)
    codigo = (codigo or "").strip()
    if not codigo:
        raise ValidationError("Informe o codigo SisPNCD.")
    if len(codigo) > 20:
        raise ValidationError("Codigo SisPNCD muito longo.")

    clauses = [
        "data BETWEEN ? AND ?",
        f"tipo IN ({_placeholders(tipos)})",
    ]
    params = [data_inicio, data_fim] + list(tipos)
    if id_localidade:
        clauses.append("id_localidade = ?")
        params.append(id_localidade)
    where = " AND ".join(clauses)
    conn = db_core.connect(db_path)
    try:
        cur = conn.execute(
            f"UPDATE visitas SET SISPNCD = ? WHERE {where} AND SISPNCD IS NULL",
            [codigo] + params,
        )
        conn.commit()
        atualizados = cur.rowcount if cur.rowcount is not None else 0
    finally:
        conn.close()

    return {
        "ok": True,
        "atualizados": atualizados,
        "codigo": codigo,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "tipos": tipos,
    }


def _species_condition(prefix):
    return (
        f"COALESCE(rl.{prefix}_larvas,0) > 0 OR "
        f"COALESCE(rl.{prefix}_pupas,0) > 0 OR "
        f"COALESCE(rl.{prefix}_exuvias,0) > 0 OR "
        f"COALESCE(rl.{prefix}_adulto,0) > 0"
    )


def _fill_laboratorio(conn, lab, where, params, kind_expr):
    species = {
        "aegypti": "aegypt",
        "albopictus": "albopictus",
    }
    for public_name, column_prefix in species.items():
        condition = _species_condition(column_prefix)
        lab[f"depositos_{public_name}"] = [
            {"tipo_deposito": row["tipo_deposito"] or "Sem tipo", "quantidade": row["total"] or 0}
            for row in conn.execute(
                f"""
                SELECT c.tipo_deposito, COUNT(DISTINCT c.id_coleta) AS total
                  FROM coletas c
                  JOIN resultados_laboratorio rl ON rl.id_coleta = c.id_coleta
                  JOIN visitas v ON v.id_visita = c.id_visita
                 WHERE {where}
                   AND ({condition})
                 GROUP BY c.tipo_deposito
                 ORDER BY c.tipo_deposito
                """,
                params,
            )
        ]
        for row in conn.execute(
            f"""
            SELECT {kind_expr} AS categoria, COUNT(DISTINCT v.id_visita) AS total
              FROM visitas v
              JOIN coletas c ON c.id_visita = v.id_visita
              JOIN resultados_laboratorio rl ON rl.id_coleta = c.id_coleta
             WHERE {where}
               AND ({condition})
             GROUP BY categoria
            """,
            params,
        ):
            lab[f"imoveis_{public_name}"][row["categoria"]] = row["total"] or 0

        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(rl.{column_prefix}_larvas), 0) AS larvas,
                   COALESCE(SUM(rl.{column_prefix}_pupas), 0) AS pupas,
                   COALESCE(SUM(rl.{column_prefix}_exuvias), 0) AS exuvias,
                   COALESCE(SUM(rl.{column_prefix}_adulto), 0) AS adultos
              FROM resultados_laboratorio rl
              JOIN coletas c ON c.id_coleta = rl.id_coleta
              JOIN visitas v ON v.id_visita = c.id_visita
             WHERE {where}
            """,
            params,
        ).fetchone()
        lab[f"exemplares_{public_name}"] = dict(row)

        lab[f"quarteiroes_{public_name}"] = conn.execute(
            f"""
            SELECT COUNT(DISTINCT v.quarteirao)
              FROM visitas v
              JOIN coletas c ON c.id_visita = v.id_visita
              JOIN resultados_laboratorio rl ON rl.id_coleta = c.id_coleta
             WHERE {where}
               AND ({condition})
            """,
            params,
        ).fetchone()[0] or 0

    outras_condition = _species_condition("outra")
    for row in conn.execute(
        f"""
        SELECT {kind_expr} AS categoria, COUNT(DISTINCT v.id_visita) AS total
          FROM visitas v
          JOIN coletas c ON c.id_visita = v.id_visita
          JOIN resultados_laboratorio rl ON rl.id_coleta = c.id_coleta
         WHERE {where}
           AND ({outras_condition})
         GROUP BY categoria
        """,
        params,
    ):
        lab["imoveis_outras"][row["categoria"]] = row["total"] or 0

    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(rl.outra_larvas), 0) AS larvas,
               COALESCE(SUM(rl.outra_pupas), 0) AS pupas,
               COALESCE(SUM(rl.outra_exuvias), 0) AS exuvias,
               COALESCE(SUM(rl.outra_adulto), 0) AS adultos
          FROM resultados_laboratorio rl
          JOIN coletas c ON c.id_coleta = rl.id_coleta
          JOIN visitas v ON v.id_visita = c.id_visita
         WHERE {where}
        """,
        params,
    ).fetchone()
    lab["exemplares_outras"] = dict(row)

    aegypti = _species_condition("aegypt")
    albopictus = _species_condition("albopictus")
    lab["quarteiroes_ambas"] = conn.execute(
        f"""
        SELECT COUNT(DISTINCT v.quarteirao)
          FROM visitas v
          JOIN coletas c ON c.id_visita = v.id_visita
          JOIN resultados_laboratorio rl ON rl.id_coleta = c.id_coleta
         WHERE {where}
           AND ({aegypti})
           AND ({albopictus})
        """,
        params,
    ).fetchone()[0] or 0
