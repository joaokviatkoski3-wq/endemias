import json
import math
from datetime import date, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app_core import db as db_core


API_BASE = "https://apitempo.inmet.gov.br"
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
CREATE INDEX IF NOT EXISTS idx_meteo_sync_inicio
    ON meteorologia_sincronizacoes(iniciado_em DESC);
"""


def ensure_schema(db_path):
    conn = db_core.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
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


def _begin_sync(db_path, started_at):
    ensure_schema(db_path)
    conn = db_core.connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO meteorologia_sincronizacoes(fonte,status,iniciado_em) VALUES (?,?,?)",
            ("INMET", "executando", started_at),
        )
        sync_id = cursor.lastrowid
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

        summaries = []
        errors = []
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
            conn.execute("BEGIN IMMEDIATE")
            for station in stations:
                conn.execute(
                    """
                    INSERT INTO meteorologia_estacoes
                        (codigo,nome,uf,situacao,tipo,entidade,latitude,longitude,altitude,
                         distancia_km,papel,inicio_operacao,fim_operacao,fonte,atualizado_em)
                    VALUES (:codigo,:nome,:uf,:situacao,:tipo,:entidade,:latitude,:longitude,:altitude,
                            :distancia_km,:papel,:inicio_operacao,:fim_operacao,'INMET',:atualizado_em)
                    ON CONFLICT(codigo) DO UPDATE SET
                        nome=excluded.nome, uf=excluded.uf, situacao=excluded.situacao,
                        tipo=excluded.tipo, entidade=excluded.entidade, latitude=excluded.latitude,
                        longitude=excluded.longitude, altitude=excluded.altitude,
                        distancia_km=excluded.distancia_km, papel=excluded.papel,
                        inicio_operacao=excluded.inicio_operacao, fim_operacao=excluded.fim_operacao,
                        atualizado_em=excluded.atualizado_em
                    """,
                    station,
                )
            for summary in summaries:
                conn.execute(
                    """
                    INSERT INTO meteorologia_resumos_diarios
                        (data,referencia,fonte,temperatura_min,temperatura_max,umidade_min,
                         precipitacao,provisorio,bruto_json,importado_em)
                    VALUES (:data,:referencia,:fonte,:temperatura_min,:temperatura_max,:umidade_min,
                            :precipitacao,:provisorio,:bruto_json,:importado_em)
                    ON CONFLICT(data,referencia,fonte) DO UPDATE SET
                        temperatura_min=excluded.temperatura_min,
                        temperatura_max=excluded.temperatura_max,
                        umidade_min=excluded.umidade_min,
                        precipitacao=excluded.precipitacao,
                        provisorio=excluded.provisorio,
                        bruto_json=excluded.bruto_json,
                        importado_em=excluded.importado_em
                    """,
                    summary,
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
            "avisos": errors,
        }
        _finish_sync(db_path, sync_id, status, len(summaries), details)
        return {"status": status, "sincronizacao_id": sync_id, **details}
    except Exception as exc:
        _finish_sync(db_path, sync_id, "erro", error=str(exc))
        raise


def obter_painel(db_path, limite=30):
    limite = max(1, min(int(limite or 30), 366))
    conn = db_core.connect(db_path)
    try:
        latest = conn.execute(
            "SELECT * FROM meteorologia_resumos_diarios ORDER BY date(data) DESC, id DESC LIMIT 1"
        ).fetchone()
        series = conn.execute(
            """
            SELECT data, temperatura_min, temperatura_max, umidade_min, precipitacao, provisorio
              FROM meteorologia_resumos_diarios
             ORDER BY date(data) DESC, id DESC
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
    return {
        "atual": dict(latest) if latest else None,
        "serie": [dict(row) for row in reversed(series)],
        "estacoes": [dict(row) for row in stations],
        "ultima_sincronizacao": dict(last_sync) if last_sync else None,
    }
