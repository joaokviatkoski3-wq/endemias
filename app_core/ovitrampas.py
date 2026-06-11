import csv
import hashlib
import os
from datetime import datetime
from pathlib import Path

from app_core import db as db_core


TABLE = "ovitrampas_leituras"


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ovitrampas_leituras (
            id_leitura          TEXT PRIMARY KEY,
            ovitrampa_id        TEXT NOT NULL,
            estado              TEXT,
            municipio           TEXT,
            distrito            TEXT,
            rua                 TEXT,
            numero              TEXT,
            complemento         TEXT,
            localizacao         TEXT,
            latitude            REAL,
            longitude           REAL,
            ano                 INTEGER NOT NULL,
            semana              INTEGER NOT NULL,
            data_envio_contagem TEXT,
            ovos                INTEGER DEFAULT 0,
            quem_enviou         TEXT,
            observacao          TEXT,
            lat_lng             TEXT,
            quarteirao          TEXT,
            data_instalacao     DATE,
            data_coleta         DATE,
            arquivo_origem      TEXT,
            importado_em        TEXT NOT NULL,
            UNIQUE(ovitrampa_id, ano, semana, data_instalacao, data_coleta, data_envio_contagem)
        );

        CREATE INDEX IF NOT EXISTS idx_ovitrampas_ano_semana ON ovitrampas_leituras(ano, semana);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_id ON ovitrampas_leituras(ovitrampa_id);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_distrito ON ovitrampas_leituras(distrito);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_coleta ON ovitrampas_leituras(data_coleta);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_ovos ON ovitrampas_leituras(ovos);
        """
    )


def importar_pasta(db_path, pasta, logger=None):
    paths = sorted(Path(pasta).glob("*.csv"), key=lambda p: p.name)
    total = {"arquivos": 0, "linhas": 0, "inseridos": 0, "duplicados": 0, "erros": []}
    for path in paths:
        result = importar_csv(db_path, path)
        total["arquivos"] += 1
        total["linhas"] += result["linhas"]
        total["inseridos"] += result["inseridos"]
        total["duplicados"] += result["duplicados"]
        total["erros"].extend(result["erros"])
        if logger:
            logger(f"{path.name}: {result['inseridos']} novo(s), {result['duplicados']} duplicado(s)")
    return total


def importar_csv(db_path, path):
    result = {"arquivo": os.path.basename(path), "linhas": 0, "inseridos": 0, "duplicados": 0, "erros": []}
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        agora = datetime.now().isoformat(timespec="seconds")
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for idx, row in enumerate(reader, start=2):
                if not any((v or "").strip() for v in row.values()):
                    continue
                result["linhas"] += 1
                try:
                    registro = _registro(row, result["arquivo"], agora)
                    inserted = _insert(conn, registro)
                    if inserted:
                        result["inseridos"] += 1
                    else:
                        result["duplicados"] += 1
                except Exception as exc:
                    result["erros"].append(f"Linha {idx}: {exc}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return result


def resumo(db_path, filtros=None):
    filtros = filtros or {}
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        where, params = _where(filtros)
        totais = dict(conn.execute(
            f"""SELECT COUNT(*) AS leituras,
                       COUNT(DISTINCT ovitrampa_id) AS ovitrampas,
                       COALESCE(SUM(ovos),0) AS ovos,
                       COALESCE(AVG(ovos),0) AS media_ovos,
                       SUM(CASE WHEN ovos > 0 THEN 1 ELSE 0 END) AS positivas,
                       MAX(ano) AS ultimo_ano,
                       MAX(CASE WHEN ano=(SELECT MAX(ano) FROM ovitrampas_leituras) THEN semana ELSE NULL END) AS ultima_semana
                  FROM ovitrampas_leituras {where}""",
            params,
        ).fetchone())
        por_distrito = [dict(row) for row in conn.execute(
            f"""SELECT COALESCE(distrito,'-') AS distrito, COUNT(*) AS leituras,
                       COUNT(DISTINCT ovitrampa_id) AS ovitrampas, COALESCE(SUM(ovos),0) AS ovos
                  FROM ovitrampas_leituras {where}
                 GROUP BY COALESCE(distrito,'-')
                 ORDER BY ovos DESC, leituras DESC, distrito
                 LIMIT 12""",
            params,
        )]
        por_semana = [dict(row) for row in conn.execute(
            f"""SELECT ano, semana, COUNT(*) AS leituras, COALESCE(SUM(ovos),0) AS ovos,
                       SUM(CASE WHEN ovos > 0 THEN 1 ELSE 0 END) AS positivas
                  FROM ovitrampas_leituras {where}
                 GROUP BY ano, semana
                 ORDER BY ano DESC, semana DESC
                 LIMIT 16""",
            params,
        )]
    finally:
        conn.close()
    return {"totais": totais, "por_distrito": por_distrito, "por_semana": por_semana}


def listar(db_path, filtros=None, limite=500):
    filtros = filtros or {}
    limite = max(1, min(int(limite or 500), 2000))
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        where, params = _where(filtros, busca=True)
        rows = [dict(row) for row in conn.execute(
            f"""SELECT *
                  FROM ovitrampas_leituras {where}
                 ORDER BY ano DESC, semana DESC, ovitrampa_id COLLATE NOCASE
                 LIMIT ?""",
            [*params, limite],
        )]
        total = conn.execute(f"SELECT COUNT(*) FROM ovitrampas_leituras {where}", params).fetchone()[0]
    finally:
        conn.close()
    return {"total": total, "registros": rows}


def distritos(db_path):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        return [row[0] for row in conn.execute(
            "SELECT DISTINCT distrito FROM ovitrampas_leituras WHERE distrito IS NOT NULL AND TRIM(distrito)<>'' ORDER BY distrito"
        )]
    finally:
        conn.close()


def _registro(row, arquivo, agora):
    ovitrampa_id = _text(row.get("Ovitrampa ID"))
    ano = _int(row.get("Ano"))
    semana = _int(row.get("Semana"))
    data_instalacao = _date(row.get("Data da instalação"))
    data_coleta = _date(row.get("Data de coleta"))
    data_envio = _datetime(row.get("Data do envio da contagem"))
    if not ovitrampa_id:
        raise ValueError("sem Ovitrampa ID")
    if not ano or not semana:
        raise ValueError("sem ano/semana")
    chave = "|".join([ovitrampa_id, str(ano), str(semana), data_instalacao or "", data_coleta or "", data_envio or ""])
    return {
        "id_leitura": hashlib.md5(chave.encode("utf-8")).hexdigest(),
        "ovitrampa_id": ovitrampa_id,
        "estado": _text(row.get("Estado")),
        "municipio": _text(row.get("Município")),
        "distrito": _title_distrito(row.get("Distrito")),
        "rua": _text(row.get("Rua")),
        "numero": _text(row.get("Número")),
        "complemento": _text(row.get("Complemento")),
        "localizacao": _text(row.get("Localização")),
        "latitude": _real(row.get("Latitude")),
        "longitude": _real(row.get("Longitude")),
        "ano": ano,
        "semana": semana,
        "data_envio_contagem": data_envio,
        "ovos": _int(row.get("Ovos")) or 0,
        "quem_enviou": _text(row.get("Quem enviou")),
        "observacao": _text(row.get("Observação")),
        "lat_lng": _text(row.get("Lat_lng")),
        "quarteirao": _text(row.get("Quarteirão")),
        "data_instalacao": data_instalacao,
        "data_coleta": data_coleta,
        "arquivo_origem": arquivo,
        "importado_em": agora,
    }


def _insert(conn, registro):
    cols = list(registro.keys())
    placeholders = ",".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT OR IGNORE INTO {TABLE} ({','.join(cols)}) VALUES ({placeholders})",
        [registro[col] for col in cols],
    )
    return cur.rowcount > 0


def _where(filtros, busca=False):
    clauses = []
    params = []
    if filtros.get("ano"):
        clauses.append("ano=?")
        params.append(_int(filtros.get("ano")))
    if filtros.get("semana"):
        clauses.append("semana=?")
        params.append(_int(filtros.get("semana")))
    if filtros.get("distrito"):
        clauses.append("distrito=?")
        params.append(filtros["distrito"])
    if filtros.get("positivas") == "1":
        clauses.append("ovos > 0")
    if busca and filtros.get("busca"):
        term = f"%{filtros['busca'].strip()}%"
        clauses.append("(ovitrampa_id LIKE ? OR rua LIKE ? OR complemento LIKE ? OR localizacao LIKE ? OR quarteirao LIKE ?)")
        params.extend([term] * 5)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in ("nan", "none") else None


def _int(value):
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text.replace(".", "").replace(",", ".")))
    except ValueError:
        return None


def _real(value):
    text = _text(value)
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _date(value):
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        return None


def _datetime(value):
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:19]).isoformat(sep=" ")
    except ValueError:
        return text


def _title_distrito(value):
    text = _text(value)
    return text.title() if text and text.isupper() else text
