import json
import math
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app_core import db as db_core


API_BASE = "https://apitempo.inmet.gov.br"
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=-25.32&longitude=-49.31"
    "&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
    "precipitation,weather_code,wind_speed_10m"
    "&hourly=temperature_2m,apparent_temperature,relative_humidity_2m,"
    "precipitation_probability,precipitation,weather_code,wind_speed_10m,wind_gusts_10m"
    "&forecast_days=7"
    "&timezone=America%2FSao_Paulo"
)
MUNICIPIO_LATITUDE = -25.32
MUNICIPIO_LONGITUDE = -49.31
ESTACOES_REFERENCIA = {
    "B806": "principal",
    "A807": "apoio",
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meteorologia_estacoes (
    codigo          TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    uf              TEXT,
    situacao        TEXT,
    tipo            TEXT,
    entidade        TEXT,
    latitude        REAL,
    longitude       REAL,
    altitude        REAL,
    distancia_km    REAL,
    papel           TEXT NOT NULL DEFAULT 'referencia',
    inicio_operacao TEXT,
    fim_operacao    TEXT,
    fonte           TEXT NOT NULL DEFAULT 'INMET',
    atualizado_em   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meteorologia_resumos_diarios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    data                DATE NOT NULL,
    referencia          TEXT NOT NULL,
    fonte               TEXT NOT NULL,
    temperatura_min     REAL,
    temperatura_max     REAL,
    umidade_min         REAL,
    precipitacao        REAL,
    provisorio          INTEGER NOT NULL DEFAULT 0 CHECK(provisorio IN (0,1)),
    bruto_json          TEXT NOT NULL,
    importado_em        TEXT NOT NULL,
    UNIQUE(data, referencia, fonte)
);

CREATE TABLE IF NOT EXISTS meteorologia_condicoes_atuais (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    observado_em            TEXT NOT NULL,
    fonte                   TEXT NOT NULL,
    latitude                REAL,
    longitude               REAL,
    temperatura             REAL,
    sensacao_termica        REAL,
    umidade                 REAL,
    precipitacao            REAL,
    velocidade_vento        REAL,
    codigo_tempo            INTEGER,
    periodo_dia             INTEGER CHECK(periodo_dia IN (0,1)),
    bruto_json              TEXT NOT NULL,
    importado_em            TEXT NOT NULL,
    UNIQUE(observado_em, fonte)
);

CREATE TABLE IF NOT EXISTS meteorologia_previsoes_horarias (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    previsto_em             TEXT NOT NULL,
    fonte                   TEXT NOT NULL DEFAULT 'Open-Meteo',
    temperatura             REAL,
    sensacao_termica        REAL,
    umidade                 REAL,
    probabilidade_chuva     REAL,
    precipitacao            REAL,
    codigo_tempo            INTEGER,
    velocidade_vento        REAL,
    rajada_vento            REAL,
    importado_em            TEXT NOT NULL,
    UNIQUE(previsto_em, fonte)
);

CREATE TABLE IF NOT EXISTS meteorologia_alertas_config (
    id                          INTEGER PRIMARY KEY CHECK(id = 1),
    expediente_inicio           INTEGER NOT NULL DEFAULT 8,
    expediente_fim              INTEGER NOT NULL DEFAULT 17,
    chuva_atencao_pct            REAL NOT NULL DEFAULT 50,
    chuva_critica_mm_hora        REAL NOT NULL DEFAULT 5,
    rajada_atencao_kmh           REAL NOT NULL DEFAULT 40,
    rajada_critica_kmh           REAL NOT NULL DEFAULT 60,
    sensacao_frio_atencao_c      REAL NOT NULL DEFAULT 7,
    sensacao_frio_critica_c      REAL NOT NULL DEFAULT 3,
    sensacao_calor_atencao_c     REAL NOT NULL DEFAULT 32,
    sensacao_calor_critica_c     REAL NOT NULL DEFAULT 36,
    atualizado_em                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meteorologia_sincronizacoes (
    id_sincronizacao INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte            TEXT NOT NULL,
    status           TEXT NOT NULL,
    iniciado_em      TEXT NOT NULL,
    finalizado_em    TEXT,
    registros        INTEGER NOT NULL DEFAULT 0,
    detalhes_json    TEXT NOT NULL DEFAULT '{}',
    erro             TEXT
);

CREATE INDEX IF NOT EXISTS idx_meteo_resumos_data
    ON meteorologia_resumos_diarios(data DESC);
CREATE INDEX IF NOT EXISTS idx_meteo_atual_observado
    ON meteorologia_condicoes_atuais(observado_em DESC);
CREATE INDEX IF NOT EXISTS idx_meteo_previsao_hora
    ON meteorologia_previsoes_horarias(previsto_em);
CREATE INDEX IF NOT EXISTS idx_meteo_sync_inicio
    ON meteorologia_sincronizacoes(iniciado_em DESC);

INSERT OR IGNORE INTO meteorologia_alertas_config(id, atualizado_em)
VALUES (1, CURRENT_TIMESTAMP);
"""


def ensure_schema(db_path):
    conn = db_core.connect(db_path)
    try:
        if db_core.is_sqlite(db_path):
            conn.executescript(SCHEMA_SQL)
        else:
            conn.execute(
                """INSERT INTO meteorologia_alertas_config(id, atualizado_em)
                   VALUES (?,?)
                   ON CONFLICT(id) DO NOTHING""",
                (1, datetime.now().isoformat(timespec="seconds")),
            )
        conn.commit()
    finally:
        conn.close()


def _fetch_json(url, timeout=20):
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Endemias-Almirante-Tamandare/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8-sig")
    except HTTPError as exc:
        raise RuntimeError(f"INMET respondeu HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Nao foi possivel acessar o INMET: {exc.reason}.") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("O INMET retornou uma resposta invalida.") from exc


def _parse_number(value):
    if value is None or value == "":
        return None
    cleaned = str(value).strip().replace("*", "").replace(",", ".")
    if cleaned in {"", "-", "null", "None"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_provisional(item):
    return any("*" in str(item.get(field) or "") for field in ("TMIN18", "TMAX18", "UMIN18", "PMAX12"))


def _haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return round(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)


def _field(item, *names):
    for name in names:
        if item.get(name) not in (None, ""):
            return item[name]
    return None


def _station_record(item, imported_at):
    codigo = str(_field(item, "CD_ESTACAO", "CD_OSCAR", "codigo") or "").strip().upper()
    latitude = _parse_number(_field(item, "VL_LATITUDE", "latitude"))
    longitude = _parse_number(_field(item, "VL_LONGITUDE", "longitude"))
    return {
        "codigo": codigo,
        "nome": str(_field(item, "DC_NOME", "nome") or codigo).strip(),
        "uf": str(_field(item, "SG_ESTADO", "uf") or "").strip().upper(),
        "situacao": _field(item, "CD_SITUACAO", "situacao"),
        "tipo": _field(item, "TP_ESTACAO", "tipo"),
        "entidade": _field(item, "SG_ENTIDADE", "entidade"),
        "latitude": latitude,
        "longitude": longitude,
        "altitude": _parse_number(_field(item, "VL_ALTITUDE", "altitude")),
        "distancia_km": _haversine_km(MUNICIPIO_LATITUDE, MUNICIPIO_LONGITUDE, latitude, longitude),
        "papel": ESTACOES_REFERENCIA.get(codigo, "referencia"),
        "inicio_operacao": _field(item, "DT_INICIO_OPERACAO", "inicio_operacao"),
        "fim_operacao": _field(item, "DT_FIM_OPERACAO", "fim_operacao"),
        "atualizado_em": imported_at,
    }


def _capital_record(item, day, imported_at):
    return {
        "data": day.isoformat(),
        "referencia": "Curitiba",
        "fonte": "INMET - Condicao das capitais",
        "temperatura_min": _parse_number(item.get("TMIN18")),
        "temperatura_max": _parse_number(item.get("TMAX18")),
        "umidade_min": _parse_number(item.get("UMIN18")),
        "precipitacao": _parse_number(item.get("PMAX12")),
        "provisorio": int(_is_provisional(item)),
        "bruto_json": json.dumps(item, ensure_ascii=False, sort_keys=True),
        "importado_em": imported_at,
    }


def _current_record(payload, imported_at):
    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict) or not current.get("time"):
        raise RuntimeError("O Open-Meteo nao retornou as condicoes atuais esperadas.")
    return {
        "observado_em": str(current["time"]),
        "fonte": "Open-Meteo",
        "latitude": _parse_number(payload.get("latitude")),
        "longitude": _parse_number(payload.get("longitude")),
        "temperatura": _parse_number(current.get("temperature_2m")),
        "sensacao_termica": _parse_number(current.get("apparent_temperature")),
        "umidade": _parse_number(current.get("relative_humidity_2m")),
        "precipitacao": _parse_number(current.get("precipitation")),
        "velocidade_vento": _parse_number(current.get("wind_speed_10m")),
        "codigo_tempo": int(current["weather_code"]) if current.get("weather_code") is not None else None,
        "periodo_dia": int(current["is_day"]) if current.get("is_day") in (0, 1) else None,
        "bruto_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "importado_em": imported_at,
    }


def _forecast_records(payload, imported_at):
    hourly = payload.get("hourly") if isinstance(payload, dict) else None
    if not isinstance(hourly, dict):
        return []
    times = hourly.get("time") or []
    fields = {
        "temperatura": hourly.get("temperature_2m") or [],
        "sensacao_termica": hourly.get("apparent_temperature") or [],
        "umidade": hourly.get("relative_humidity_2m") or [],
        "probabilidade_chuva": hourly.get("precipitation_probability") or [],
        "precipitacao": hourly.get("precipitation") or [],
        "codigo_tempo": hourly.get("weather_code") or [],
        "velocidade_vento": hourly.get("wind_speed_10m") or [],
        "rajada_vento": hourly.get("wind_gusts_10m") or [],
    }
    records = []
    for index, previsto_em in enumerate(times):
        if not previsto_em:
            continue
        record = {
            "previsto_em": str(previsto_em),
            "fonte": "Open-Meteo",
            "importado_em": imported_at,
        }
        for name, values in fields.items():
            value = values[index] if index < len(values) else None
            record[name] = _parse_number(value)
        if record["codigo_tempo"] is not None:
            record["codigo_tempo"] = int(record["codigo_tempo"])
        records.append(record)
    return records


def _weather_description(code):
    if code is None:
        return "Condicao nao informada"
    descriptions = {
        0: "Ceu limpo",
        1: "Predominio de ceu limpo",
        2: "Parcialmente nublado",
        3: "Encoberto",
        45: "Nevoeiro",
        48: "Nevoeiro com geada",
        51: "Garoa leve",
        53: "Garoa moderada",
        55: "Garoa intensa",
        56: "Garoa congelante leve",
        57: "Garoa congelante intensa",
        61: "Chuva leve",
        63: "Chuva moderada",
        65: "Chuva forte",
        66: "Chuva congelante leve",
        67: "Chuva congelante forte",
        71: "Neve leve",
        73: "Neve moderada",
        75: "Neve forte",
        77: "Graos de neve",
        80: "Pancadas de chuva leves",
        81: "Pancadas de chuva moderadas",
        82: "Pancadas de chuva fortes",
        85: "Pancadas de neve leves",
        86: "Pancadas de neve fortes",
        95: "Tempestade",
        96: "Tempestade com granizo leve",
        99: "Tempestade com granizo forte",
    }
    return descriptions.get(int(code), "Condicao nao informada")


def _begin_sync(db_path, started_at):
    ensure_schema(db_path)
    conn = db_core.connect(db_path)
    try:
        sync_id = db_core.insert_and_get_id(
            conn,
            """INSERT INTO meteorologia_sincronizacoes(
                   fonte,status,iniciado_em
               ) VALUES (?,?,?)""",
            ("INMET + Open-Meteo", "executando", started_at),
            "id_sincronizacao",
        )
        conn.commit()
        return sync_id
    finally:
        conn.close()


def _finish_sync(db_path, sync_id, status, records=0, details=None, error=None):
    conn = db_core.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE meteorologia_sincronizacoes
               SET status=?, finalizado_em=?, registros=?, detalhes_json=?, erro=?
             WHERE id_sincronizacao=?
            """,
            (
                status,
                datetime.now().isoformat(timespec="seconds"),
                records,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                error,
                sync_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def sincronizar(db_path, dias=7, hoje=None, fetch_json=None):
    dias = max(1, min(int(dias or 7), 90))
    today = hoje or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    fetch = fetch_json or _fetch_json
    imported_at = datetime.now().isoformat(timespec="seconds")
    sync_id = _begin_sync(db_path, imported_at)

    try:
        catalog = fetch(f"{API_BASE}/estacoes/T")
        if not isinstance(catalog, list):
            raise RuntimeError("O catalogo de estacoes do INMET veio em formato inesperado.")
        stations = []
        for item in catalog:
            station = _station_record(item, imported_at)
            if station["uf"] == "PR" and station["codigo"]:
                stations.append(station)

        current_condition = None
        forecasts = []
        errors = []
        try:
            open_meteo_payload = fetch(OPEN_METEO_URL)
            current_condition = _current_record(open_meteo_payload, imported_at)
            forecasts = _forecast_records(open_meteo_payload, imported_at)
            if not forecasts:
                errors.append("previsao horaria: nenhum dado retornado")
        except RuntimeError as exc:
            errors.append(f"Open-Meteo: {exc}")

        summaries = []
        for offset in range(dias - 1, -1, -1):
            day = today - timedelta(days=offset)
            try:
                capital_data = fetch(f"{API_BASE}/condicao/capitais/{day.isoformat()}")
                curitiba = next(
                    (item for item in (capital_data or []) if str(item.get("CAPITAL") or "").strip().upper() == "CURITIBA"),
                    None,
                )
                if curitiba:
                    summaries.append(_capital_record(curitiba, day, imported_at))
                else:
                    errors.append(f"{day.isoformat()}: Curitiba nao retornada")
            except RuntimeError as exc:
                errors.append(f"{day.isoformat()}: {exc}")

        if not summaries:
            raise RuntimeError("Nenhum resumo diario de Curitiba foi retornado pelo INMET.")

        conn = db_core.connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE" if db_core.is_sqlite(db_path) else "BEGIN")
            for station in stations:
                conn.execute(
                    """
                    INSERT INTO meteorologia_estacoes
                        (codigo,nome,uf,situacao,tipo,entidade,latitude,longitude,altitude,
                         distancia_km,papel,inicio_operacao,fim_operacao,fonte,atualizado_em)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'INMET',?)
                    ON CONFLICT(codigo) DO UPDATE SET
                        nome=excluded.nome, uf=excluded.uf, situacao=excluded.situacao,
                        tipo=excluded.tipo, entidade=excluded.entidade, latitude=excluded.latitude,
                        longitude=excluded.longitude, altitude=excluded.altitude,
                        distancia_km=excluded.distancia_km, papel=excluded.papel,
                        inicio_operacao=excluded.inicio_operacao, fim_operacao=excluded.fim_operacao,
                        atualizado_em=excluded.atualizado_em
                    """,
                    (
                        station["codigo"],
                        station["nome"],
                        station["uf"],
                        station["situacao"],
                        station["tipo"],
                        station["entidade"],
                        station["latitude"],
                        station["longitude"],
                        station["altitude"],
                        station["distancia_km"],
                        station["papel"],
                        station["inicio_operacao"],
                        station["fim_operacao"],
                        station["atualizado_em"],
                    ),
                )
            for summary in summaries:
                conn.execute(
                    """
                    INSERT INTO meteorologia_resumos_diarios
                        (data,referencia,fonte,temperatura_min,temperatura_max,umidade_min,
                         precipitacao,provisorio,bruto_json,importado_em)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(data,referencia,fonte) DO UPDATE SET
                        temperatura_min=excluded.temperatura_min,
                        temperatura_max=excluded.temperatura_max,
                        umidade_min=excluded.umidade_min,
                        precipitacao=excluded.precipitacao,
                        provisorio=excluded.provisorio,
                        bruto_json=excluded.bruto_json,
                        importado_em=excluded.importado_em
                    """,
                    (
                        summary["data"],
                        summary["referencia"],
                        summary["fonte"],
                        summary["temperatura_min"],
                        summary["temperatura_max"],
                        summary["umidade_min"],
                        summary["precipitacao"],
                        summary["provisorio"],
                        summary["bruto_json"],
                        summary["importado_em"],
                    ),
                )
            if current_condition:
                conn.execute(
                    """
                    INSERT INTO meteorologia_condicoes_atuais
                        (observado_em,fonte,latitude,longitude,temperatura,sensacao_termica,
                         umidade,precipitacao,velocidade_vento,codigo_tempo,periodo_dia,
                         bruto_json,importado_em)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(observado_em,fonte) DO UPDATE SET
                        latitude=excluded.latitude, longitude=excluded.longitude,
                        temperatura=excluded.temperatura, sensacao_termica=excluded.sensacao_termica,
                        umidade=excluded.umidade, precipitacao=excluded.precipitacao,
                        velocidade_vento=excluded.velocidade_vento,
                        codigo_tempo=excluded.codigo_tempo, periodo_dia=excluded.periodo_dia,
                        bruto_json=excluded.bruto_json, importado_em=excluded.importado_em
                    """,
                    (
                        current_condition["observado_em"],
                        current_condition["fonte"],
                        current_condition["latitude"],
                        current_condition["longitude"],
                        current_condition["temperatura"],
                        current_condition["sensacao_termica"],
                        current_condition["umidade"],
                        current_condition["precipitacao"],
                        current_condition["velocidade_vento"],
                        current_condition["codigo_tempo"],
                        current_condition["periodo_dia"],
                        current_condition["bruto_json"],
                        current_condition["importado_em"],
                    ),
                )
            for forecast in forecasts:
                conn.execute(
                    """
                    INSERT INTO meteorologia_previsoes_horarias
                        (previsto_em,fonte,temperatura,sensacao_termica,umidade,
                         probabilidade_chuva,precipitacao,codigo_tempo,
                         velocidade_vento,rajada_vento,importado_em)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(previsto_em,fonte) DO UPDATE SET
                        temperatura=excluded.temperatura,
                        sensacao_termica=excluded.sensacao_termica,
                        umidade=excluded.umidade,
                        probabilidade_chuva=excluded.probabilidade_chuva,
                        precipitacao=excluded.precipitacao,
                        codigo_tempo=excluded.codigo_tempo,
                        velocidade_vento=excluded.velocidade_vento,
                        rajada_vento=excluded.rajada_vento,
                        importado_em=excluded.importado_em
                    """,
                    (
                        forecast["previsto_em"],
                        forecast["fonte"],
                        forecast["temperatura"],
                        forecast["sensacao_termica"],
                        forecast["umidade"],
                        forecast["probabilidade_chuva"],
                        forecast["precipitacao"],
                        forecast["codigo_tempo"],
                        forecast["velocidade_vento"],
                        forecast["rajada_vento"],
                        forecast["importado_em"],
                    ),
                )
            cutoff = (today - timedelta(days=1)).isoformat()
            conn.execute(
                """DELETE FROM meteorologia_previsoes_horarias
                    WHERE substr(CAST(previsto_em AS TEXT),1,10) < ?""",
                (cutoff,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        status = "parcial" if errors else "concluido"
        details = {
            "dias_solicitados": dias,
            "resumos": len(summaries),
            "estacoes_pr": len(stations),
            "condicao_atual": int(current_condition is not None),
            "previsoes_horarias": len(forecasts),
            "avisos": errors,
        }
        _finish_sync(db_path, sync_id, status, len(summaries), details)
        return {"status": status, "sincronizacao_id": sync_id, **details}
    except Exception as exc:
        _finish_sync(db_path, sync_id, "erro", error=str(exc))
        raise


ALERTA_CONFIG_FIELDS = {
    "expediente_inicio": (0, 23, int),
    "expediente_fim": (1, 24, int),
    "chuva_atencao_pct": (0, 100, float),
    "chuva_critica_mm_hora": (0, 100, float),
    "rajada_atencao_kmh": (0, 200, float),
    "rajada_critica_kmh": (0, 250, float),
    "sensacao_frio_atencao_c": (-30, 30, float),
    "sensacao_frio_critica_c": (-40, 25, float),
    "sensacao_calor_atencao_c": (15, 60, float),
    "sensacao_calor_critica_c": (20, 70, float),
}


def obter_configuracao_alertas(db_path):
    ensure_schema(db_path)
    conn = db_core.connect(db_path)
    try:
        row = conn.execute("SELECT * FROM meteorologia_alertas_config WHERE id=1").fetchone()
        return dict(row)
    finally:
        conn.close()


def atualizar_configuracao_alertas(db_path, values):
    current = obter_configuracao_alertas(db_path)
    updated = {}
    for field, (minimum, maximum, converter) in ALERTA_CONFIG_FIELDS.items():
        raw = values.get(field, current[field])
        try:
            value = converter(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Valor invalido para {field}.") from exc
        if value < minimum or value > maximum:
            raise ValueError(f"Valor fora do intervalo permitido para {field}.")
        updated[field] = value
    if updated["expediente_inicio"] >= updated["expediente_fim"]:
        raise ValueError("O inicio do expediente deve ser anterior ao fim.")
    if updated["rajada_atencao_kmh"] >= updated["rajada_critica_kmh"]:
        raise ValueError("A rajada critica deve ser maior que a rajada de atencao.")
    if updated["sensacao_frio_critica_c"] >= updated["sensacao_frio_atencao_c"]:
        raise ValueError("O limite critico de frio deve ser menor que o limite de atencao.")
    if updated["sensacao_calor_atencao_c"] >= updated["sensacao_calor_critica_c"]:
        raise ValueError("O limite critico de calor deve ser maior que o limite de atencao.")
    updated["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    conn = db_core.connect(db_path)
    try:
        conn.execute(
            """
            UPDATE meteorologia_alertas_config SET
                expediente_inicio=?,
                expediente_fim=?,
                chuva_atencao_pct=?,
                chuva_critica_mm_hora=?,
                rajada_atencao_kmh=?,
                rajada_critica_kmh=?,
                sensacao_frio_atencao_c=?,
                sensacao_frio_critica_c=?,
                sensacao_calor_atencao_c=?,
                sensacao_calor_critica_c=?,
                atualizado_em=?
            WHERE id=1
            """,
            (
                updated["expediente_inicio"],
                updated["expediente_fim"],
                updated["chuva_atencao_pct"],
                updated["chuva_critica_mm_hora"],
                updated["rajada_atencao_kmh"],
                updated["rajada_critica_kmh"],
                updated["sensacao_frio_atencao_c"],
                updated["sensacao_frio_critica_c"],
                updated["sensacao_calor_atencao_c"],
                updated["sensacao_calor_critica_c"],
                updated["atualizado_em"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return obter_configuracao_alertas(db_path)


def _next_workdays(start, quantity):
    days = []
    current = start
    while len(days) < quantity:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _risk_reasons(rows, config):
    critical = []
    attention = []
    codes = {row["codigo_tempo"] for row in rows if row["codigo_tempo"] is not None}
    gusts = [row["rajada_vento"] for row in rows if row["rajada_vento"] is not None]
    feels = [row["sensacao_termica"] for row in rows if row["sensacao_termica"] is not None]
    probabilities = [row["probabilidade_chuva"] for row in rows if row["probabilidade_chuva"] is not None]
    precipitation = [row["precipitacao"] for row in rows if row["precipitacao"] is not None]

    if codes.intersection({95, 96, 99}):
        critical.append("risco de tempestade")
    elif codes.intersection({51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}):
        attention.append("chuva prevista")
    if precipitation and max(precipitation) >= config["chuva_critica_mm_hora"]:
        critical.append(f"chuva intensa de até {max(precipitation):.1f} mm/h")
    elif probabilities and max(probabilities) >= config["chuva_atencao_pct"]:
        attention.append(f"chance de chuva de até {max(probabilities):.0f}%")
    if gusts and max(gusts) >= config["rajada_critica_kmh"]:
        critical.append(f"rajadas de até {max(gusts):.0f} km/h")
    elif gusts and max(gusts) >= config["rajada_atencao_kmh"]:
        attention.append(f"rajadas de até {max(gusts):.0f} km/h")
    if feels and min(feels) <= config["sensacao_frio_critica_c"]:
        critical.append(f"sensação de até {min(feels):.0f} °C")
    elif feels and min(feels) <= config["sensacao_frio_atencao_c"]:
        attention.append(f"sensação de até {min(feels):.0f} °C")
    if feels and max(feels) >= config["sensacao_calor_critica_c"]:
        critical.append(f"sensação de até {max(feels):.0f} °C")
    elif feels and max(feels) >= config["sensacao_calor_atencao_c"]:
        attention.append(f"sensação de até {max(feels):.0f} °C")
    return critical, attention


def resumo_trabalho(db_path, inicio=None, dias_uteis=5):
    ensure_schema(db_path)
    start = date.fromisoformat(inicio) if isinstance(inicio, str) else (inicio or date.today())
    workdays = _next_workdays(start, max(1, min(int(dias_uteis or 5), 10)))
    config = obter_configuracao_alertas(db_path)
    end = workdays[-1]
    conn = db_core.connect(db_path)
    try:
        if db_core.is_sqlite(db_path):
            hour_expression = "CAST(strftime('%H', previsto_em) AS INTEGER)"
        else:
            hour_expression = (
                "EXTRACT(HOUR FROM CAST(previsto_em AS timestamp))"
            )
        rows = conn.execute(
            f"""
            SELECT * FROM meteorologia_previsoes_horarias
             WHERE substr(CAST(previsto_em AS TEXT),1,10) BETWEEN ? AND ?
               AND {hour_expression} >= ?
               AND {hour_expression} < ?
             ORDER BY previsto_em
            """,
            (start.isoformat(), end.isoformat(), config["expediente_inicio"], config["expediente_fim"]),
        ).fetchall()
        latest_import = conn.execute(
            "SELECT MAX(importado_em) FROM meteorologia_previsoes_horarias"
        ).fetchone()[0]
    finally:
        conn.close()

    grouped = {}
    for row in rows:
        grouped.setdefault(row["previsto_em"][:10], []).append(dict(row))
    labels = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira")
    days = []
    for day in workdays:
        day_rows = grouped.get(day.isoformat(), [])
        if not day_rows:
            days.append({
                "data": day.isoformat(),
                "dia_semana": labels[day.weekday()],
                "nivel": "sem_dados",
                "nivel_label": "Sem previsão",
                "motivos": [],
                "janela": f"{config['expediente_inicio']:02d}h-{config['expediente_fim']:02d}h",
            })
            continue
        critical, attention = _risk_reasons(day_rows, config)
        reasons = critical if critical else attention
        level = "critico" if critical else ("atencao" if attention else "favoravel")
        level_label = {"critico": "Crítico", "atencao": "Atenção", "favoravel": "Favorável"}[level]
        temperatures = [row["temperatura"] for row in day_rows if row["temperatura"] is not None]
        probabilities = [row["probabilidade_chuva"] for row in day_rows if row["probabilidade_chuva"] is not None]
        gusts = [row["rajada_vento"] for row in day_rows if row["rajada_vento"] is not None]
        days.append({
            "data": day.isoformat(),
            "dia_semana": labels[day.weekday()],
            "nivel": level,
            "nivel_label": level_label,
            "motivos": reasons,
            "resumo": "; ".join(reasons) if reasons else "sem risco meteorológico relevante",
            "temperatura_min": min(temperatures) if temperatures else None,
            "temperatura_max": max(temperatures) if temperatures else None,
            "chuva_prob_max": max(probabilities) if probabilities else None,
            "rajada_max": max(gusts) if gusts else None,
            "janela": f"{config['expediente_inicio']:02d}h-{config['expediente_fim']:02d}h",
        })
    return {
        "dias": days,
        "configuracao": config,
        "previsao_atualizada_em": latest_import,
        "fonte": "Open-Meteo",
    }


def obter_painel(db_path, limite=30):
    limite = max(1, min(int(limite or 30), 366))
    conn = db_core.connect(db_path)
    try:
        latest = conn.execute(
            """SELECT * FROM meteorologia_resumos_diarios
               ORDER BY data DESC, id DESC LIMIT 1"""
        ).fetchone()
        current = conn.execute(
            """SELECT * FROM meteorologia_condicoes_atuais
               ORDER BY observado_em DESC, id DESC LIMIT 1"""
        ).fetchone()
        series = conn.execute(
            """
            SELECT data, temperatura_min, temperatura_max, umidade_min, precipitacao, provisorio
              FROM meteorologia_resumos_diarios
             ORDER BY data DESC, id DESC
             LIMIT ?
            """,
            (limite,),
        ).fetchall()
        stations = conn.execute(
            """
            SELECT * FROM meteorologia_estacoes
             WHERE codigo IN ('B806','A807')
             ORDER BY CASE papel WHEN 'principal' THEN 1 WHEN 'apoio' THEN 2 ELSE 3 END
            """
        ).fetchall()
        last_sync = conn.execute(
            "SELECT * FROM meteorologia_sincronizacoes ORDER BY id_sincronizacao DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    current_item = db_core.serialize_row(current) if current else None
    if current_item:
        current_item["descricao"] = _weather_description(current_item.get("codigo_tempo"))
    return {
        "atual": db_core.serialize_row(latest) if latest else None,
        "condicao_atual": current_item,
        "serie": [
            db_core.serialize_row(row) for row in reversed(series)
        ],
        "estacoes": [db_core.serialize_row(row) for row in stations],
        "ultima_sincronizacao": (
            db_core.serialize_row(last_sync) if last_sync else None
        ),
    }
