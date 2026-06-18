from collections import defaultdict
from datetime import date, timedelta

from app_core import bri as bri_core
from app_core import db as db_core
from app_core import work_types


DEPOSIT_TYPES = ("A1", "A2", "B", "C", "D1", "D2", "E")
BRI_TYPE = "BRI"
WORK_TYPES_ALLOWED = set(work_types.WORK_TYPE_CODES) | {BRI_TYPE}


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
    year_start = _epidemiological_year_start(year)
    next_year_start = _epidemiological_year_start(year + 1)
    start = year_start + timedelta(days=(week - 1) * 7)
    end = start + timedelta(days=6)
    if start >= next_year_start:
        raise ValidationError("Semana epidemiologica invalida para o ano informado.")
    return start.isoformat(), end.isoformat()


def epidemiological_week_for_date(value):
    if not isinstance(value, date):
        value = date.fromisoformat(str(value))
    year = value.year
    year_start = _epidemiological_year_start(year)
    if value < year_start:
        year -= 1
        year_start = _epidemiological_year_start(year)
    elif value >= _epidemiological_year_start(year + 1):
        year += 1
        year_start = _epidemiological_year_start(year)
    week = ((value - year_start).days // 7) + 1
    return year, week


def _epidemiological_year_start(year):
    jan4 = date(year, 1, 4)
    days_since_sunday = (jan4.weekday() + 1) % 7
    return jan4 - timedelta(days=days_since_sunday)


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


def split_sispncd_work_types(tipos):
    return [tipo for tipo in tipos if tipo != BRI_TYPE], BRI_TYPE in tipos


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


def _tratamento_real_sql(alias="t", tem_qtd_depositos=True):
    checks = [
        f"TRIM(COALESCE({alias}.tipo, '')) <> ''",
        f"COALESCE({alias}.quantidade_carga, 0) > 0",
    ]
    if tem_qtd_depositos:
        checks.append(f"COALESCE({alias}.qtd_depositos_tratados, 0) > 0")
    return "(" + " OR ".join(checks) + ")"


def _tratamento_deposito_real_sql(alias="di", tem_tipo_tratamento=True, tem_qtd_carga=True):
    checks = [f"COALESCE({alias}.tratado, 0) > 0"]
    if tem_qtd_carga:
        checks.append(f"COALESCE({alias}.qtd_carga, 0) > 0")
    if tem_tipo_tratamento:
        checks.append(f"TRIM(COALESCE({alias}.tipo_tratamento, '')) <> ''")
    return "(" + " OR ".join(checks) + ")"


def _deposit_code_sql(tipo_col, codigo_col=None):
    raw_values = []
    if codigo_col:
        raw_values.append(f"UPPER(TRIM(COALESCE({codigo_col}, '')))")
    raw_values.append(f"UPPER(TRIM(COALESCE({tipo_col}, '')))")
    text = f"LOWER(TRIM(COALESCE({tipo_col}, '')))"
    valid_codes = ", ".join(f"'{code}'" for code in DEPOSIT_TYPES)
    exact_checks = " ".join(
        f"WHEN {raw} IN ({valid_codes}) THEN {raw}"
        for raw in raw_values
    )
    code_hints = " ".join(
        f"WHEN {raw} LIKE '%{code}%' THEN '{code}'"
        for raw in raw_values
        for code in ("A1", "A2", "D1", "D2")
    )
    return (
        "CASE "
        f"{exact_checks} "
        f"{code_hints} "
        f"WHEN ({text} LIKE '%solo%' OR {text} LIKE '%nivel%') "
        f" AND ({text} LIKE '%agua%' OR {text} LIKE '%água%' OR {text} LIKE '%tambor%' OR {text} LIKE '%tonel%') THEN 'A2' "
        f"WHEN ({text} LIKE '%caixa%' OR {text} LIKE '%elevad%') "
        f" AND ({text} LIKE '%agua%' OR {text} LIKE '%água%') THEN 'A1' "
        f"WHEN {text} LIKE '%tambor%' OR {text} LIKE '%tonel%' OR {text} LIKE '%barril%' "
        f" OR {text} LIKE '%cisterna%' OR {text} LIKE '%poco%' OR {text} LIKE '%poço%' THEN 'A2' "
        f"WHEN {text} LIKE '%pneu%' THEN 'D1' "
        f"WHEN {text} LIKE '%lixo%' OR {text} LIKE '%sucata%' OR {text} LIKE '%garrafa%' "
        f" OR {text} LIKE '%lata%' OR {text} LIKE '%plast%' OR {text} LIKE '%entulho%' "
        f" OR {text} LIKE '%recipiente%' THEN 'D2' "
        f"WHEN {text} LIKE '%natural%' OR {text} LIKE '%brom%' OR {text} LIKE '%arvore%' "
        f" OR {text} LIKE '%árvore%' OR {text} LIKE '%rocha%' THEN 'E' "
        f"WHEN {text} LIKE '%movel%' OR {text} LIKE '%móvel%' OR {text} LIKE '%vaso%' "
        f" OR {text} LIKE '%prato%' OR {text} LIKE '%bebedouro%' OR {text} LIKE '%flor%' THEN 'B' "
        f"WHEN {text} LIKE '%fixo%' OR {text} LIKE '%calha%' OR {text} LIKE '%laje%' "
        f" OR {text} LIKE '%piscina%' OR {text} LIKE '%ralo%' OR {text} LIKE '%sanitario%' "
        f" OR {text} LIKE '%sanitário%' THEN 'C' "
        "ELSE NULL END"
    )


def _has_column(conn, table_name, column_name):
    return any(
        row["name"] == column_name
        for row in conn.execute(f"PRAGMA table_info({table_name})")
    )


def get_default_conta_ovos(db_path):
    row = db_core.query_one(
        db_path,
        """
        SELECT data, quarteirao
          FROM visitas
         WHERE tipo='TBO'
           AND COALESCE(CONTAOVOS_STATUS, 0) = 0
           AND quarteirao IS NOT NULL
         GROUP BY data, quarteirao
         ORDER BY data DESC, COUNT(*) DESC
         LIMIT 1
        """,
    )
    if not row:
        row = db_core.query_one(
            db_path,
            """
            SELECT data, quarteirao
              FROM visitas
             WHERE tipo='TBO'
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
                       id_localidade,
                       COALESCE(localidade, '-') AS localidade,
                       COUNT(*) AS total
                  FROM visitas
                 WHERE tipo='TBO'
                   AND CONTAOVOS_STATUS = 0
                 GROUP BY data, quarteirao, id_localidade, COALESCE(localidade, '-')
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

        sispncd_rows = conn.execute(
            """
            SELECT v.tipo,
                   v.data,
                   v.id_localidade,
                   COALESCE(v.localidade, l.nome, '-') AS localidade
              FROM visitas v
              LEFT JOIN localidades l ON l.id_localidade = v.id_localidade
             WHERE v.SISPNCD IS NULL OR TRIM(v.SISPNCD)=''
            """
        ).fetchall()
        bri_core.ensure_schema(conn)
        sispncd_rows += conn.execute(
            """
            SELECT 'BRI' AS tipo,
                   b.data,
                   b.id_localidade,
                   COALESCE(b.localidade, '-') AS localidade
              FROM bri_registros b
             WHERE b.sispncd IS NULL OR TRIM(b.sispncd)=''
            """
        ).fetchall()
        sispncd_total = len(sispncd_rows)
        sispncd_grupos = _agrupar_pendencias_sispncd(sispncd_rows, limite_grupos)
    finally:
        conn.close()

    return {
        "conta_ovos": {"total": conta_total, "total_grupos": len(conta_grupos), "grupos": conta_grupos},
        "sispncd": {"total": sispncd_total, "total_grupos": len(sispncd_grupos), "grupos": sispncd_grupos},
    }


def salvar_status_conta_ovos(db_path, data, quarteirao, id_localidade=None):
    data = parse_iso_date(data)
    if quarteirao in (None, ""):
        return {"ok": True, "atualizados": 0, "data": data, "quarteirao": None}
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
    if quarteirao in (None, ""):
        return _conta_ovos_vazio(data, None)
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
    deposito_codigo = _deposit_code_sql("di.tipo_deposito")

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
            WITH normalizados AS (
                SELECT {deposito_codigo} AS codigo,
                       di.inspecionado,
                       di.eliminado,
                       di.tratado,
                       di.qtd_carga
                  FROM depositos_inspecionados di
                  JOIN visitas v ON v.id_visita = di.id_visita
                 WHERE {where}
                   AND {deposito_codigo} IS NOT NULL
            )
            SELECT codigo AS tipo_deposito,
                   COALESCE(SUM(inspecionado), 0) AS quantidade,
                   COALESCE(SUM(eliminado), 0) AS eliminado,
                   COALESCE(SUM(tratado), 0) AS tratado,
                   COALESCE(ROUND(SUM(qtd_carga), 2), 0) AS larvicida_mg
              FROM normalizados
             GROUP BY codigo
             ORDER BY codigo
            """,
            params,
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


def _conta_ovos_vazio(data, quarteirao):
    return {
        "data": data,
        "quarteirao": quarteirao,
        "imoveis": {
            key: {"visitas": 0, "pendencias": 0, "positivas": 0, "tratadas": 0}
            for key in ("residencia", "comercio", "tb", "pe", "outros")
        },
        "depositos": {
            code.lower(): {"quantidade": 0, "eliminado": 0, "tratado": 0, "larvicida_mg": 0}
            for code in DEPOSIT_TYPES
        },
        "total_visitas": 0,
    }


def sispncd(db_path, year, week, tipos, id_localidade=None):
    data_inicio, data_fim = epidemiological_week_range(year, week)
    tipos = normalize_work_types(tipos)
    visita_tipos, inclui_bri = split_sispncd_work_types(tipos)
    id_localidade = optional_localidade(id_localidade)
    where, params = (
        _base_where(data_inicio, data_fim, visita_tipos, id_localidade)
        if visita_tipos else ("1=0", [])
    )
    kind_expr = _kind_sql("v")
    deposito_inspecionado_codigo = _deposit_code_sql("di.tipo_deposito")

    dados = {
        "total_quarteiroes": 0,
        "imoveis": _empty_kind_dict(),
        "imoveis_tratados": 0,
        "imoveis_inspecionados": 0,
        "total_coletas": 0,
        "pendencias": {"recusa": 0, "fechado": 0, "recuperado": 0},
        "depositos": {code.lower(): 0 for code in DEPOSIT_TYPES},
        "total_depositos_inspecionados": 0,
        "total_eliminados": 0,
        "total_tratados": 0,
        "tratamentos": [],
        "total_agentes": 0,
        "total_dias": 0,
        "bri": _bri_empty(),
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
        "quarteiroes_aegypti_lista": [],
        "quarteiroes_albopictus_lista": [],
        "quarteiroes_ambas_lista": [],
    }

    conn = db_core.connect(db_path)
    try:
        bri_core.ensure_schema(conn)
        tem_qtd_depositos_tratados = _has_column(conn, "tratamentos", "qtd_depositos_tratados")
        tratamento_real = _tratamento_real_sql("t", tem_qtd_depositos_tratados)
        tem_deposito_tipo_tratamento = _has_column(conn, "depositos_inspecionados", "tipo_tratamento")
        tem_deposito_qtd_carga = _has_column(conn, "depositos_inspecionados", "qtd_carga")
        tratamento_deposito_real = _tratamento_deposito_real_sql(
            "di",
            tem_tipo_tratamento=tem_deposito_tipo_tratamento,
            tem_qtd_carga=tem_deposito_qtd_carga,
        )
        deposito_tipo_tratamento_sql = (
            "COALESCE(NULLIF(TRIM(di.tipo_tratamento), ''), 'Sem tipo')"
            if tem_deposito_tipo_tratamento
            else "'Sem tipo'"
        )
        deposito_qtd_carga_sql = "di.qtd_carga" if tem_deposito_qtd_carga else "0"
        quantidade_tratamentos_sql = (
            "COALESCE(SUM(t.qtd_depositos_tratados), 0)"
            if tem_qtd_depositos_tratados
            else "COUNT(t.id)"
        )
        tb_types = [t for t in visita_tipos if t in ("TB", "TBO")]
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
               AND {tratamento_real}
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

        if visita_tipos:
            for row in conn.execute(
                f"""
                WITH normalizados AS (
                    SELECT {deposito_inspecionado_codigo} AS codigo,
                           di.inspecionado
                      FROM depositos_inspecionados di
                      JOIN visitas v ON v.id_visita = di.id_visita
                     WHERE {where}
                       AND {deposito_inspecionado_codigo} IS NOT NULL
                )
                SELECT codigo AS tipo_deposito,
                       COALESCE(SUM(inspecionado), 0) AS total
                  FROM normalizados
                 GROUP BY codigo
                 ORDER BY codigo
                """,
                params,
            ):
                dados["depositos"][str(row["tipo_deposito"]).lower()] = row["total"] or 0
        dados["total_depositos_inspecionados"] = sum(dados["depositos"].values())

        dados["total_eliminados"] = conn.execute(
            f"""
            SELECT COALESCE(SUM(di.eliminado), 0)
              FROM depositos_inspecionados di
              JOIN visitas v ON v.id_visita = di.id_visita
             WHERE {where}
            """,
            params,
        ).fetchone()[0] or 0

        tratamento_rows_params = params + params
        dados["tratamentos"] = [
            {
                "tipo": row["tipo_tratamento"] or "Sem tipo",
                "quantidade": row["depositos_tratados"] or 0,
                "carga_kg": row["total_carga_kg"] or 0,
            }
            for row in conn.execute(
                f"""
                WITH tratamentos_unificados AS (
                    SELECT COALESCE(NULLIF(TRIM(t.tipo), ''), 'Sem tipo') AS tipo_tratamento,
                           {quantidade_tratamentos_sql} AS depositos_tratados,
                           COALESCE(SUM(t.quantidade_carga), 0) AS total_carga_kg
                      FROM tratamentos t
                      JOIN visitas v ON v.id_visita = t.id_visita
                     WHERE {where}
                       AND {tratamento_real}
                     GROUP BY COALESCE(NULLIF(TRIM(t.tipo), ''), 'Sem tipo')
                    UNION ALL
                    SELECT {deposito_tipo_tratamento_sql} AS tipo_tratamento,
                           COALESCE(SUM(di.tratado), 0) AS depositos_tratados,
                           COALESCE(SUM({deposito_qtd_carga_sql}), 0) AS total_carga_kg
                      FROM depositos_inspecionados di
                      JOIN visitas v ON v.id_visita = di.id_visita
                     WHERE {where}
                       AND {tratamento_deposito_real}
                     GROUP BY {deposito_tipo_tratamento_sql}
                )
                SELECT tipo_tratamento,
                       COALESCE(SUM(depositos_tratados), 0) AS depositos_tratados,
                       COALESCE(ROUND(SUM(total_carga_kg), 2), 0) AS total_carga_kg
                  FROM tratamentos_unificados
                 GROUP BY tipo_tratamento
                 ORDER BY tipo_tratamento
                """,
                tratamento_rows_params,
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
        if inclui_bri:
            dados["bri"] = _bri_sispncd_stats(conn, data_inicio, data_fim, id_localidade)
            if not visita_tipos:
                dados["total_dias"] = dados["bri"]["dias"]
                dados["total_agentes"] = dados["bri"]["agentes"]
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
    visita_tipos, inclui_bri = split_sispncd_work_types(tipos)
    id_localidade = optional_localidade(id_localidade)
    codigo = (codigo or "").strip()
    if not codigo:
        raise ValidationError("Informe o codigo SisPNCD.")
    if len(codigo) > 20:
        raise ValidationError("Codigo SisPNCD muito longo.")

    atualizados_visitas = 0
    atualizados_bri = 0
    conn = db_core.connect(db_path)
    try:
        if visita_tipos:
            clauses = [
                "data BETWEEN ? AND ?",
                f"tipo IN ({_placeholders(visita_tipos)})",
            ]
            params = [data_inicio, data_fim] + list(visita_tipos)
            if id_localidade:
                clauses.append("id_localidade = ?")
                params.append(id_localidade)
            where = " AND ".join(clauses)
            cur = conn.execute(
                f"UPDATE visitas SET SISPNCD = ? WHERE {where} AND (SISPNCD IS NULL OR TRIM(SISPNCD)='')",
                [codigo] + params,
            )
            atualizados_visitas = cur.rowcount if cur.rowcount is not None else 0
        if inclui_bri:
            bri_core.ensure_schema(conn)
            bri_where, bri_params = _bri_where(data_inicio, data_fim, id_localidade, alias=None)
            cur = conn.execute(
                f"UPDATE bri_registros SET sispncd = ? WHERE {bri_where} AND (sispncd IS NULL OR TRIM(sispncd)='')",
                [codigo] + bri_params,
            )
            atualizados_bri = cur.rowcount if cur.rowcount is not None else 0
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "atualizados": atualizados_visitas + atualizados_bri,
        "visitas_atualizadas": atualizados_visitas,
        "bri_atualizados": atualizados_bri,
        "codigo": codigo,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "tipos": tipos,
    }


def _agrupar_pendencias_sispncd(rows, limite_grupos=None):
    grupos = defaultdict(lambda: {
        "tipo": "",
        "ano": 0,
        "semana": 0,
        "id_localidade": None,
        "localidade": "-",
        "data_inicio": None,
        "data_fim": None,
        "total": 0,
    })
    for row in rows:
        try:
            data = date.fromisoformat(row["data"])
        except (TypeError, ValueError):
            continue
        ano, semana = epidemiological_week_for_date(data)
        chave = (row["tipo"], ano, semana, row["id_localidade"], row["localidade"] or "-")
        grupo = grupos[chave]
        grupo.update({
            "tipo": row["tipo"],
            "ano": ano,
            "semana": semana,
            "id_localidade": row["id_localidade"],
            "localidade": row["localidade"] or "-",
        })
        grupo["data_inicio"] = min(grupo["data_inicio"] or row["data"], row["data"])
        grupo["data_fim"] = max(grupo["data_fim"] or row["data"], row["data"])
        grupo["total"] += 1

    result = sorted(
        grupos.values(),
        key=lambda g: (-g["ano"], -g["semana"], -g["total"], g["tipo"] or "", g["localidade"] or ""),
    )
    if limite_grupos:
        result = result[:limite_grupos]
    return result


def _bri_empty():
    return {
        "registros": 0,
        "pendentes_sispncd": 0,
        "carga": 0,
        "ovitrampas": 0,
        "pontos_estrategicos": 0,
        "outros": 0,
        "extras": 0,
        "dias": 0,
        "agentes": 0,
    }


def _bri_where(data_inicio, data_fim, id_localidade=None, alias="b"):
    prefix = f"{alias}." if alias else ""
    clauses = [f"{prefix}data BETWEEN ? AND ?"]
    params = [data_inicio, data_fim]
    if id_localidade:
        clauses.append(f"{prefix}id_localidade = ?")
        params.append(id_localidade)
    return " AND ".join(clauses), params


def _bri_sispncd_stats(conn, data_inicio, data_fim, id_localidade=None):
    where, params = _bri_where(data_inicio, data_fim, id_localidade)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS registros,
               SUM(CASE WHEN b.sispncd IS NULL OR TRIM(b.sispncd)='' THEN 1 ELSE 0 END) AS pendentes_sispncd,
               COALESCE(SUM(b.quantidade_carga + b.quantidade_carga_extra), 0) AS carga,
               SUM(CASE WHEN b.destino_tratamento='Ovitrampa' THEN 1 ELSE 0 END) AS ovitrampas,
               SUM(CASE WHEN b.destino_tratamento='Ponto Estratégico' THEN 1 ELSE 0 END) AS pontos_estrategicos,
               SUM(CASE WHEN b.destino_tratamento='Outro' THEN 1 ELSE 0 END) AS outros,
               SUM(CASE WHEN b.tratou_imovel_extra='Sim' THEN 1 ELSE 0 END) AS extras,
               COUNT(DISTINCT b.data) AS dias
          FROM bri_registros b
         WHERE {where}
        """,
        params,
    ).fetchone()
    agentes = conn.execute(
        f"""
        SELECT COUNT(DISTINCT ba.id_agente)
          FROM bri_agentes ba
          JOIN bri_registros b ON b.id_bri=ba.id_bri
         WHERE {where}
        """,
        params,
    ).fetchone()[0] or 0
    result = _bri_empty()
    result.update({key: (row[key] or 0) for key in result if key != "agentes"})
    result["agentes"] = agentes
    return result


def _species_condition(prefix):
    return (
        f"COALESCE(rl.{prefix}_larvas,0) > 0 OR "
        f"COALESCE(rl.{prefix}_pupas,0) > 0 OR "
        f"COALESCE(rl.{prefix}_exuvias,0) > 0 OR "
        f"COALESCE(rl.{prefix}_adulto,0) > 0"
    )


def _sort_quarteiroes(values):
    def key(value):
        text = str(value)
        try:
            return (0, int(text), text)
        except ValueError:
            return (1, 0, text)

    return sorted([value for value in values if value not in (None, "")], key=key)


def _quarteiroes_positivos(conn, where, params, condition):
    rows = conn.execute(
        f"""
        SELECT DISTINCT v.quarteirao
          FROM visitas v
          JOIN coletas c ON c.id_visita = v.id_visita
          JOIN resultados_laboratorio rl ON rl.id_coleta = c.id_coleta
         WHERE {where}
           AND ({condition})
           AND v.quarteirao IS NOT NULL
           AND TRIM(CAST(v.quarteirao AS TEXT)) <> ''
        """,
        params,
    ).fetchall()
    return _sort_quarteiroes(row["quarteirao"] for row in rows)


def _fill_laboratorio(conn, lab, where, params, kind_expr):
    species = {
        "aegypti": "aegypt",
        "albopictus": "albopictus",
    }
    deposito_codigo_col = "c.codigo_deposito" if _has_column(conn, "coletas", "codigo_deposito") else None
    deposito_codigo = _deposit_code_sql("c.tipo_deposito", deposito_codigo_col)
    for public_name, column_prefix in species.items():
        condition = _species_condition(column_prefix)
        lab[f"depositos_{public_name}"] = [
            {"tipo_deposito": row["tipo_deposito"], "quantidade": row["total"] or 0}
            for row in conn.execute(
                f"""
                WITH normalizados AS (
                    SELECT {deposito_codigo} AS codigo,
                           c.id_coleta
                      FROM coletas c
                      JOIN resultados_laboratorio rl ON rl.id_coleta = c.id_coleta
                      JOIN visitas v ON v.id_visita = c.id_visita
                     WHERE {where}
                       AND ({condition})
                       AND {deposito_codigo} IS NOT NULL
                )
                SELECT codigo AS tipo_deposito,
                       COUNT(DISTINCT id_coleta) AS total
                  FROM normalizados
                 GROUP BY codigo
                 ORDER BY codigo
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

        quarteiroes = _quarteiroes_positivos(conn, where, params, condition)
        lab[f"quarteiroes_{public_name}_lista"] = quarteiroes
        lab[f"quarteiroes_{public_name}"] = len(quarteiroes)

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

    ambas = _sort_quarteiroes(
        set(lab["quarteiroes_aegypti_lista"]) & set(lab["quarteiroes_albopictus_lista"])
    )
    lab["quarteiroes_ambas_lista"] = ambas
    lab["quarteiroes_ambas"] = len(ambas)
