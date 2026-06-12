import hashlib
import os
import re
from datetime import datetime

import pandas as pd

from app_core import normalizadores


TABLE = "recolhimentos"
AGENTES_TABLE = "recolhimento_agentes"

MATERIAIS = (
    ("pneu", "Pneu", ("Pneu",)),
    ("louca_sanitaria", "Louça Sanitária", ("Louça Sanitária", "Louca Sanitaria")),
    ("tv", "TV", ("TV (tubo, carcaça, plástico)", "TV")),
    ("parachoque", "Parachoque", ("Parachoque",)),
    ("outros", "Outros", ("Outros",)),
)

AGENTES_CONHECIDOS = (
    "Ana Beatriz",
    "Adilson",
    "Adriana",
    "Alves",
    "Ana",
    "Atagil",
    "Azimir",
    "Ceccon",
    "Cecília",
    "Evaldo",
    "Fernando",
    "Henrique",
    "João",
    "Manoel",
    "Márcio",
    "Marlon",
    "Pedro",
    "Robson",
    "Tales",
    "Vanessa",
    "Viviane",
)

LOCALIDADES_PADRAO = {
    "sede": "Sede",
    "centro": "Sede",
    "cachoeira": "Cachoeira",
    "grasiela": "Graziela",
    "graziela": "Graziela",
    "lamenha": "Lamenha",
    "paraiso": "Paraíso",
    "paraíso": "Paraíso",
    "roma": "Roma",
    "rosana": "Rosana",
    "santa maria": "Santa Maria",
    "sao francisco": "São Francisco",
    "são francisco": "São Francisco",
    "sao joao batista": "São João Batista",
    "são joão batista": "São João Batista",
    "sao venancio": "São Venâncio",
    "são venâncio": "São Venâncio",
    "tamboara": "Tamboara",
    "tangua": "Tanguá",
    "tanguá": "Tanguá",
    "tranqueira": "Tranqueira",
}


class ValidationError(Exception):
    pass


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS recolhimentos (
            id_recolhimento TEXT PRIMARY KEY,
            kobo_uuid       TEXT UNIQUE,
            kobo_id         INTEGER,
            data            DATE NOT NULL,
            hora            TIME,
            inicio_registro TEXT,
            fim_registro    TEXT,
            localidade      TEXT,
            id_localidade   INTEGER REFERENCES localidades(id_localidade),
            agentes_texto   TEXT,
            pneu            INTEGER DEFAULT 0,
            louca_sanitaria INTEGER DEFAULT 0,
            tv              INTEGER DEFAULT 0,
            parachoque      INTEGER DEFAULT 0,
            outros          INTEGER DEFAULT 0,
            total_materiais INTEGER DEFAULT 0,
            origem_estrutura TEXT NOT NULL DEFAULT 'nova',
            arquivo_origem  TEXT,
            submission_time TEXT,
            processado_em   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recolhimento_agentes (
            id_recolhimento TEXT NOT NULL REFERENCES recolhimentos(id_recolhimento) ON DELETE CASCADE,
            id_agente       INTEGER NOT NULL REFERENCES agentes(id_agente),
            PRIMARY KEY (id_recolhimento, id_agente)
        );

        CREATE INDEX IF NOT EXISTS idx_recolhimentos_data ON recolhimentos(data);
        CREATE INDEX IF NOT EXISTS idx_recolhimentos_localidade ON recolhimentos(id_localidade);
        CREATE INDEX IF NOT EXISTS idx_recolhimentos_origem ON recolhimentos(origem_estrutura);
        CREATE INDEX IF NOT EXISTS idx_recolhimento_agentes_agente ON recolhimento_agentes(id_agente);
        """
    )


def is_new_format(path):
    df = pd.read_excel(path, sheet_name=0, nrows=1, engine="openpyxl")
    columns = set(df.columns)
    return {"start", "end", "Data", "Hora", "Localidade", "_uuid"}.issubset(columns)


def processar_arquivo(path, conn, logger, agora_iso, dry_run=False):
    estrutura = "nova" if is_new_format(path) else "legada"
    registros = parse_workbook(path, estrutura)
    logger.log(f"  Estrutura: {estrutura} | Recolhimentos: {len(registros)}")

    ensure_schema(conn)
    inseridos = duplicados = vinculos = materiais_novos = 0
    for registro in registros:
        registro["arquivo_origem"] = os.path.basename(path)
        registro["origem_estrutura"] = estrutura
        novo = _inserir_recolhimento(conn, registro, agora_iso)
        if novo:
            inseridos += 1
            materiais_novos += registro.get("total_materiais", 0) or 0
        else:
            duplicados += 1
        vinculos += _inserir_agentes(conn, registro["id_recolhimento"], registro.get("agentes_texto"))

    logger.log(
        f"  Recolhimentos novos: {inseridos} | Duplicados: {duplicados} | Vinculos agentes: {vinculos}",
        "ok",
    )
    return {
        "ok": True,
        "tipo": "RECOLHIMENTO",
        "visitas_novas": inseridos,
        "coletas_novas": 0,
        "materiais_novos": materiais_novos,
        "resultados_novos": 0,
        "duplicadas": duplicados,
    }


def parse_workbook(path, estrutura=None):
    df = pd.read_excel(path, sheet_name=0, engine="openpyxl").dropna(how="all")
    estrutura = estrutura or ("nova" if is_new_format(path) else "legada")
    registros = []
    for idx, row in df.iterrows():
        data = _date(_pick(row, ("Data",)))
        if not data:
            continue
        kobo_uuid = _uuid(row.get("_uuid")) if estrutura == "nova" else None
        chave = kobo_uuid or "|".join([
            str(idx),
            data or "",
            _text(_pick(row, ("Hora",))) or "",
            _text(_pick(row, ("Localidade",))) or "",
            _text(_pick(row, ("Agentes", "Nome do(s) agente(s)"))) or "",
        ])
        materiais = {campo: _int(_pick(row, colunas)) or 0 for campo, _, colunas in MATERIAIS}
        registros.append({
            "id_recolhimento": _hash("recolhimento", estrutura, chave),
            "kobo_uuid": kobo_uuid,
            "kobo_id": _int(row.get("_id")),
            "data": data,
            "hora": _time(_pick(row, ("Hora",))),
            "inicio_registro": _datetime(row.get("start")) if estrutura == "nova" else None,
            "fim_registro": _datetime(row.get("end")) if estrutura == "nova" else None,
            "localidade": _localidade(_pick(row, ("Localidade",))),
            "agentes_texto": _agentes(row, estrutura),
            "submission_time": _datetime(row.get("_submission_time")) if estrutura == "nova" else None,
            **materiais,
            "total_materiais": sum(materiais.values()),
        })
    return registros


def resumo(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros)
    try:
        totais = dict(conn.execute(
            f"""SELECT
                    COUNT(*) AS registros,
                    COALESCE(SUM(total_materiais),0) AS total_materiais,
                    COALESCE(SUM(pneu),0) AS pneu,
                    COALESCE(SUM(louca_sanitaria),0) AS louca_sanitaria,
                    COALESCE(SUM(tv),0) AS tv,
                    COALESCE(SUM(parachoque),0) AS parachoque,
                    COALESCE(SUM(outros),0) AS outros,
                    COUNT(DISTINCT data) AS dias,
                    COUNT(DISTINCT localidade) AS localidades
                FROM recolhimentos r {where}""",
            params,
        ).fetchone())
        por_localidade = [dict(r) for r in conn.execute(
            f"""SELECT COALESCE(localidade,'-') AS localidade,
                       COUNT(*) AS registros,
                       COALESCE(SUM(total_materiais),0) AS total
                  FROM recolhimentos r {where}
                 GROUP BY COALESCE(localidade,'-')
                 ORDER BY total DESC, localidade
                 LIMIT 12""",
            params,
        )]
        por_mes = [dict(r) for r in conn.execute(
            f"""SELECT substr(data,1,7) AS mes, COALESCE(SUM(total_materiais),0) AS total
                  FROM recolhimentos r {where}
                 GROUP BY substr(data,1,7)
                 ORDER BY mes""",
            params,
        )]
    finally:
        conn.close()
    return {
        "totais": {k: (v or 0) for k, v in totais.items()},
        "por_localidade": por_localidade,
        "por_mes": por_mes,
    }


def listar(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros, busca=True)
    try:
        rows = [dict(r) for r in conn.execute(
            f"""SELECT r.*,
                       (SELECT GROUP_CONCAT(a.nome, ', ')
                          FROM recolhimento_agentes ra
                          JOIN agentes a ON a.id_agente=ra.id_agente
                         WHERE ra.id_recolhimento=r.id_recolhimento) AS agentes
                  FROM recolhimentos r
                  {where}
                 ORDER BY r.data DESC, r.hora DESC, r.localidade
                 LIMIT 500""",
            params,
        )]
    finally:
        conn.close()
    return {"registros": rows, "total": len(rows)}


def localidades(db_path):
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT DISTINCT localidade AS nome
               FROM recolhimentos
              WHERE localidade IS NOT NULL AND TRIM(localidade)<>''
              ORDER BY localidade"""
        )]
    finally:
        conn.close()


def agentes(db_path):
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT DISTINCT a.nome
                 FROM recolhimento_agentes ra
                 JOIN agentes a ON a.id_agente=ra.id_agente
                ORDER BY a.nome"""
        )]
    finally:
        conn.close()


def _where(filtros, busca=False):
    clauses = ["WHERE 1=1"]
    params = []
    if filtros.get("d_ini"):
        clauses.append("AND r.data>=?")
        params.append(filtros["d_ini"])
    if filtros.get("d_fim"):
        clauses.append("AND r.data<=?")
        params.append(filtros["d_fim"])
    if filtros.get("localidade"):
        clauses.append("AND r.localidade=?")
        params.append(filtros["localidade"])
    if filtros.get("origem"):
        clauses.append("AND r.origem_estrutura=?")
        params.append(filtros["origem"])
    if filtros.get("agente"):
        clauses.append(
            """AND EXISTS (
                   SELECT 1 FROM recolhimento_agentes ra
                   JOIN agentes a ON a.id_agente=ra.id_agente
                  WHERE ra.id_recolhimento=r.id_recolhimento AND a.nome=?
               )"""
        )
        params.append(filtros["agente"])
    if busca and filtros.get("busca"):
        termo = f"%{filtros['busca']}%"
        clauses.append(
            "AND (r.localidade LIKE ? OR r.agentes_texto LIKE ? OR r.arquivo_origem LIKE ?)"
        )
        params.extend([termo, termo, termo])
    return " ".join(clauses), params


def _inserir_recolhimento(conn, registro, agora_iso):
    cur = conn.cursor()
    cur.execute(
        """INSERT OR IGNORE INTO recolhimentos (
            id_recolhimento, kobo_uuid, kobo_id, data, hora, inicio_registro, fim_registro,
            localidade, id_localidade, agentes_texto, pneu, louca_sanitaria, tv,
            parachoque, outros, total_materiais, origem_estrutura, arquivo_origem,
            submission_time, processado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            registro["id_recolhimento"],
            registro.get("kobo_uuid"),
            registro.get("kobo_id"),
            registro["data"],
            registro.get("hora"),
            registro.get("inicio_registro"),
            registro.get("fim_registro"),
            registro.get("localidade"),
            _obter_ou_criar_localidade(conn, registro.get("localidade")),
            registro.get("agentes_texto"),
            registro.get("pneu", 0),
            registro.get("louca_sanitaria", 0),
            registro.get("tv", 0),
            registro.get("parachoque", 0),
            registro.get("outros", 0),
            registro.get("total_materiais", 0),
            registro.get("origem_estrutura", "nova"),
            registro.get("arquivo_origem"),
            registro.get("submission_time"),
            agora_iso,
        ),
    )
    return cur.rowcount > 0


def _inserir_agentes(conn, id_recolhimento, agentes_texto):
    total = 0
    for nome in _split_agentes(agentes_texto):
        id_agente = _obter_ou_criar_agente(conn, nome)
        cur = conn.execute(
            "INSERT OR IGNORE INTO recolhimento_agentes(id_recolhimento, id_agente) VALUES (?,?)",
            (id_recolhimento, id_agente),
        )
        total += cur.rowcount
    return total


def _obter_ou_criar_agente(conn, nome):
    row = conn.execute("SELECT id_agente FROM agentes WHERE nome=?", (nome,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO agentes(nome) VALUES (?)", (nome,))
    return cur.lastrowid


def _obter_ou_criar_localidade(conn, nome):
    nome = normalizadores.normalizar_localidade(nome)
    if not nome:
        return None
    row = conn.execute("SELECT id_localidade FROM localidades WHERE nome=?", (nome,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO localidades(nome, cod_localidade) VALUES (?,NULL)", (nome,))
    return cur.lastrowid


def _agentes(row, estrutura):
    texto = _text(_pick(row, ("Nome do(s) agente(s)", "Agentes")))
    marcados = []
    if estrutura == "nova":
        for col, val in row.items():
            if str(col).startswith("Nome do(s) agente(s)/") and _int(val) == 1:
                marcados.append(str(col).split("/", 1)[1].strip())
    if marcados:
        return ", ".join(marcados)
    return texto


def _split_agentes(texto):
    if not texto:
        return []
    texto = str(texto).strip()
    nomes = []
    conhecidos = sorted(AGENTES_CONHECIDOS, key=len, reverse=True)
    padrao = re.compile(
        rf"(^|\s|,|/|;)({'|'.join(re.escape(nome) for nome in conhecidos)})(?=\s|,|/|;|$)",
        re.I,
    )
    restante = padrao.sub(" ", texto).strip()
    for match in padrao.finditer(texto):
        nome = next((n for n in AGENTES_CONHECIDOS if n.lower() == match.group(2).lower()), match.group(2))
        if nome not in nomes:
            nomes.append(nome)
    for parte in re.split(r",|/|;|\be\b|\s{2,}", restante):
        parte = parte.strip()
        if parte and parte not in nomes:
            nomes.append(parte)
    return nomes


def _pick(row, names):
    for name in names:
        if name in row:
            return row.get(name)
    return None


def _hash(*parts):
    return hashlib.md5(":".join(str(p or "") for p in parts).encode("utf-8")).hexdigest()


def _uuid(value):
    text = _text(value)
    if not text:
        return None
    return text[5:] if text.startswith("uuid:") else text


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
        num = int(float(str(value).replace(",", ".")))
        return num if num >= 0 else None
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


def _time(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return pd.to_datetime(str(value), errors="coerce").strftime("%H:%M")
    except Exception:
        return None


def _datetime(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return pd.to_datetime(value).isoformat()
    except Exception:
        return None


def _localidade(value):
    text = _text(value)
    if not text:
        return None
    return normalizadores.normalizar_localidade(text)
