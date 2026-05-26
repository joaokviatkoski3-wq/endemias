import hashlib
import sqlite3
import unicodedata
from datetime import datetime

import pandas as pd

from app_core import recolhimentos as normalizadores


TABLE = "pontos_estrategicos"


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pontos_estrategicos (
            id_pe           INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_pe       TEXT NOT NULL UNIQUE,
            localidade      TEXT,
            id_localidade   INTEGER REFERENCES localidades(id_localidade),
            quarteirao      INTEGER,
            nome            TEXT NOT NULL,
            logradouro      TEXT,
            numero          TEXT,
            situacao        INTEGER NOT NULL DEFAULT 1,
            data_inclusao   DATE,
            data_desativacao DATE,
            cnpj            TEXT,
            razao_social    TEXT,
            telefone        TEXT,
            tipo            TEXT,
            latitude        REAL,
            longitude       REAL,
            observacoes     TEXT,
            chave_origem    TEXT UNIQUE,
            criado_em       TEXT NOT NULL,
            atualizado_em   TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_pe_codigo ON pontos_estrategicos(codigo_pe);
        CREATE INDEX IF NOT EXISTS idx_pe_situacao ON pontos_estrategicos(situacao);
        CREATE INDEX IF NOT EXISTS idx_pe_localidade ON pontos_estrategicos(id_localidade);
        CREATE INDEX IF NOT EXISTS idx_pe_tipo ON pontos_estrategicos(tipo);
        """
    )


def importar_csv_inicial(csv_path, db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    df = pd.read_csv(csv_path, sep=None, engine="python", encoding="utf-8-sig").dropna(how="all")
    inseridos = duplicados = 0
    try:
        conn.execute("BEGIN")
        for _, row in df.iterrows():
            payload = registro_de_linha_csv(row)
            if inserir(conn, payload):
                inseridos += 1
            else:
                duplicados += 1
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return {"inseridos": inseridos, "duplicados": duplicados}


def registro_de_linha_csv(row):
    payload = {
        "localidade": _localidade(_pick(row, ("Localidade",))),
        "quarteirao": _int(_pick(row, ("Quarteirão", "Quarteirao"))),
        "nome": _text(_pick(row, ("Local", "Nome"))) or "Ponto estrategico",
        "logradouro": _text(_pick(row, ("Logradouro",))),
        "numero": _text(_pick(row, ("Número", "Numero"))),
        "situacao": _situacao(_pick(row, ("Situação", "Situacao"))),
        "data_inclusao": _date(_pick(row, ("DATA INCLUSÃO", "DATA INCLUSAO", "Data Inclusão"))),
        "data_desativacao": _date(_pick(row, ("DATA DESATIVAÇÃO", "DATA DESATIVACAO", "Data Desativação"))),
        "cnpj": _text(_pick(row, ("CNPJ",))),
        "razao_social": _text(_pick(row, ("RAZÃO SOCIAL", "RAZAO SOCIAL", "Razão Social"))),
        "telefone": _text(_pick(row, ("TELEFONE", "Telefone"))),
        "tipo": _text(_pick(row, ("TIPO", "Tipo"))),
        "latitude": _real(_pick(row, ("LATITUDE", "Latitude"))),
        "longitude": _real(_pick(row, ("LONGITUDE", "Longitude"))),
        "observacoes": _text(_pick(row, ("OBSERVAÇÕES", "OBSERVACOES", "Observações"))),
    }
    payload["chave_origem"] = chave_origem(payload)
    return payload


def listar(db_path, filtros=None):
    filtros = filtros or {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    where, params = _where(filtros)
    try:
        rows = [
            dict(r)
            for r in conn.execute(
                f"""SELECT * FROM pontos_estrategicos pe
                    {where}
                    ORDER BY situacao DESC, localidade, quarteirao, nome
                    LIMIT 1000""",
                params,
            )
        ]
        totais = dict(
            conn.execute(
                f"""SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN situacao=1 THEN 1 ELSE 0 END) AS ativos,
                        SUM(CASE WHEN situacao=0 THEN 1 ELSE 0 END) AS inativos,
                        SUM(CASE WHEN tipo IS NULL OR TRIM(tipo)='' THEN 1 ELSE 0 END) AS sem_tipo,
                        SUM(CASE WHEN telefone IS NULL OR TRIM(telefone)='' THEN 1 ELSE 0 END) AS sem_telefone,
                        SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) AS sem_coordenadas
                   FROM pontos_estrategicos pe
                   {where}""",
                params,
            ).fetchone()
        )
    finally:
        conn.close()
    return {"registros": rows, "total": len(rows), "totais": {k: (v or 0) for k, v in totais.items()}}


def opcoes(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    try:
        localidades = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT localidade FROM pontos_estrategicos WHERE localidade IS NOT NULL ORDER BY localidade"
            )
        ]
        tipos = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT tipo FROM pontos_estrategicos WHERE tipo IS NOT NULL AND TRIM(tipo)<>'' ORDER BY tipo"
            )
        ]
    finally:
        conn.close()
    return {"localidades": localidades, "tipos": tipos}


def obter(db_path, id_pe):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    try:
        row = conn.execute("SELECT * FROM pontos_estrategicos WHERE id_pe=?", (id_pe,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def salvar(db_path, payload, id_pe=None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    try:
        conn.execute("BEGIN")
        result = atualizar(conn, id_pe, payload) if id_pe else inserir(conn, payload)
        conn.execute("COMMIT")
        return result
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def inserir(conn, payload):
    agora = datetime.now().isoformat(timespec="seconds")
    codigo = _text(payload.get("codigo_pe")) or proximo_codigo(conn)
    localidade = _localidade(payload.get("localidade"))
    cur = conn.execute(
        """INSERT OR IGNORE INTO pontos_estrategicos (
            codigo_pe, localidade, id_localidade, quarteirao, nome, logradouro, numero,
            situacao, data_inclusao, data_desativacao, cnpj, razao_social, telefone,
            tipo, latitude, longitude, observacoes, chave_origem, criado_em, atualizado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            codigo,
            localidade,
            _obter_ou_criar_localidade(conn, localidade),
            _int(payload.get("quarteirao")),
            _text(payload.get("nome")) or "Ponto estrategico",
            _text(payload.get("logradouro")),
            _text(payload.get("numero")),
            _situacao(payload.get("situacao")),
            _date(payload.get("data_inclusao")),
            _date(payload.get("data_desativacao")),
            _text(payload.get("cnpj")),
            _text(payload.get("razao_social")),
            _text(payload.get("telefone")),
            _text(payload.get("tipo")),
            _real(payload.get("latitude")),
            _real(payload.get("longitude")),
            _text(payload.get("observacoes")),
            payload.get("chave_origem") or chave_origem(payload),
            agora,
            agora,
        ),
    )
    return cur.rowcount > 0


def atualizar(conn, id_pe, payload):
    atual = conn.execute("SELECT * FROM pontos_estrategicos WHERE id_pe=?", (id_pe,)).fetchone()
    if not atual:
        return False
    localidade = _localidade(payload.get("localidade"))
    agora = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """UPDATE pontos_estrategicos SET
            localidade=?, id_localidade=?, quarteirao=?, nome=?, logradouro=?, numero=?,
            situacao=?, data_inclusao=?, data_desativacao=?, cnpj=?, razao_social=?,
            telefone=?, tipo=?, latitude=?, longitude=?, observacoes=?, atualizado_em=?
         WHERE id_pe=?""",
        (
            localidade,
            _obter_ou_criar_localidade(conn, localidade),
            _int(payload.get("quarteirao")),
            _text(payload.get("nome")) or "Ponto estrategico",
            _text(payload.get("logradouro")),
            _text(payload.get("numero")),
            _situacao(payload.get("situacao")),
            _date(payload.get("data_inclusao")),
            _date(payload.get("data_desativacao")),
            _text(payload.get("cnpj")),
            _text(payload.get("razao_social")),
            _text(payload.get("telefone")),
            _text(payload.get("tipo")),
            _real(payload.get("latitude")),
            _real(payload.get("longitude")),
            _text(payload.get("observacoes")),
            agora,
            id_pe,
        ),
    )
    return True


def definir_situacao(db_path, id_pe, situacao):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    data_desativacao = datetime.now().date().isoformat() if int(situacao) == 0 else None
    try:
        cur = conn.execute(
            """UPDATE pontos_estrategicos
                  SET situacao=?, data_desativacao=?, atualizado_em=?
                WHERE id_pe=?""",
            (int(situacao), data_desativacao, datetime.now().isoformat(timespec="seconds"), id_pe),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def proximo_codigo(conn):
    row = conn.execute(
        """SELECT codigo_pe FROM pontos_estrategicos
           WHERE codigo_pe LIKE 'PE-%'
           ORDER BY CAST(substr(codigo_pe,4) AS INTEGER) DESC
           LIMIT 1"""
    ).fetchone()
    atual = int(str(row[0])[3:]) if row else 0
    return f"PE-{atual + 1:04d}"


def chave_origem(payload):
    base = "|".join(str(payload.get(k) or "").strip().lower() for k in (
        "localidade", "quarteirao", "nome", "logradouro", "numero"
    ))
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def _where(filtros):
    clauses = ["WHERE 1=1"]
    params = []
    if filtros.get("situacao") in ("0", "1", 0, 1):
        clauses.append("AND pe.situacao=?")
        params.append(int(filtros["situacao"]))
    if filtros.get("localidade"):
        clauses.append("AND pe.localidade=?")
        params.append(filtros["localidade"])
    if filtros.get("tipo"):
        clauses.append("AND pe.tipo=?")
        params.append(filtros["tipo"])
    if filtros.get("busca"):
        termo = f"%{filtros['busca']}%"
        clauses.append(
            """AND (pe.codigo_pe LIKE ? OR pe.nome LIKE ? OR pe.logradouro LIKE ?
                    OR pe.numero LIKE ? OR pe.cnpj LIKE ? OR pe.razao_social LIKE ?)"""
        )
        params.extend([termo] * 6)
    return " ".join(clauses), params


def _obter_ou_criar_localidade(conn, nome):
    if not nome:
        return None
    row = conn.execute("SELECT id_localidade FROM localidades WHERE nome=?", (nome,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO localidades(nome, cod_localidade) VALUES (?,NULL)", (nome,))
    return cur.lastrowid


def _pick(row, names):
    normalizados = {_normalizar_coluna(k): k for k in row.keys()}
    for name in names:
        if name in row:
            return row.get(name)
        chave = normalizados.get(_normalizar_coluna(name))
        if chave:
            return row.get(chave)
    return None


def _normalizar_coluna(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.strip().lower().split())


def _localidade(value):
    return normalizadores._localidade(value)


def _text(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip()
    return text if text and text.lower() not in ("nan", "none") else None


def _int(value):
    try:
        if value is None or pd.isna(value):
            return None
    except Exception:
        if value is None:
            return None
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return None


def _real(value):
    try:
        if value is None or pd.isna(value):
            return None
    except Exception:
        if value is None:
            return None
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def _date(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return pd.to_datetime(value).date().isoformat()
    except Exception:
        return None


def _situacao(value):
    if str(value).strip().lower() in ("0", "0.0", "inativo", "inativa"):
        return 0
    return 1
