import hashlib
import os
import re

import pandas as pd

from app_core import recolhimentos as agentes_core
from app_core import normalizadores


TABLE = "amostras_animais"
AGENTES_TABLE = "amostra_animais_agentes"

ESPECIE_COLS = (
    "Qual a espécie da serpente?",
    "Qual a espécie do escorpião?",
    "Qual a espécie da lagarta?",
    "Qual a espécie da aranha?",
    "Qual a espécie do carrapato?",
)


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS amostras_animais (
            id_amostra       TEXT PRIMARY KEY,
            kobo_uuid        TEXT UNIQUE,
            kobo_id          INTEGER,
            data             DATE NOT NULL,
            hora             TIME,
            inicio_registro  TEXT,
            fim_registro     TEXT,
            agentes_texto    TEXT,
            motivo_visita    TEXT,
            animal_motivador TEXT,
            animal_motivador_outro TEXT,
            localidade       TEXT,
            id_localidade    INTEGER REFERENCES localidades(id_localidade),
            quarteirao       INTEGER,
            tipo_imovel      TEXT,
            visita           TEXT,
            logradouro       TEXT,
            numero           TEXT,
            sequencia        TEXT,
            morador          TEXT,
            ocorrencia_residencia TEXT,
            onde             TEXT,
            houve_acidente   TEXT,
            houve_captura    TEXT,
            local_captura    TEXT,
            tipo_animal      TEXT,
            animal_capturado TEXT,
            especie_serpente TEXT,
            especie_escorpiao TEXT,
            especie_lagarta  TEXT,
            especie_aranha   TEXT,
            especie_carrapato TEXT,
            especie_resumo   TEXT,
            quantidade       INTEGER DEFAULT 0,
            origem_estrutura TEXT NOT NULL DEFAULT 'nova',
            arquivo_origem   TEXT,
            submission_time  TEXT,
            processado_em    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS amostra_animais_agentes (
            id_amostra TEXT NOT NULL REFERENCES amostras_animais(id_amostra) ON DELETE CASCADE,
            id_agente  INTEGER NOT NULL REFERENCES agentes(id_agente),
            PRIMARY KEY (id_amostra, id_agente)
        );

        CREATE INDEX IF NOT EXISTS idx_amostras_animais_data ON amostras_animais(data);
        CREATE INDEX IF NOT EXISTS idx_amostras_animais_localidade ON amostras_animais(id_localidade);
        CREATE INDEX IF NOT EXISTS idx_amostras_animais_tipo ON amostras_animais(tipo_animal);
        CREATE INDEX IF NOT EXISTS idx_amostras_animais_motivo ON amostras_animais(motivo_visita);
        CREATE INDEX IF NOT EXISTS idx_amostra_animais_agentes_agente ON amostra_animais_agentes(id_agente);
        """
    )


def is_new_format(path):
    df = pd.read_excel(path, sheet_name=0, nrows=1, engine="openpyxl")
    columns = set(df.columns)
    return {"start", "end", "Data", "Hora", "_uuid", "Motivo da visita"}.issubset(columns)


def processar_arquivo(path, conn, logger, agora_iso, dry_run=False):
    estrutura = "nova" if is_new_format(path) else "legada"
    registros = parse_workbook(path, estrutura)
    logger.log(f"  Estrutura: {estrutura} | Amostras animais: {len(registros)}")

    ensure_schema(conn)
    inseridos = duplicados = vinculos = animais_novos = acidentes = capturas = 0
    for registro in registros:
        registro["arquivo_origem"] = os.path.basename(path)
        registro["origem_estrutura"] = estrutura
        novo = _inserir_amostra(conn, registro, agora_iso)
        if novo:
            inseridos += 1
            animais_novos += registro.get("quantidade", 0) or 0
            acidentes += 1 if _sim(registro.get("houve_acidente")) else 0
            capturas += 1 if _sim(registro.get("houve_captura")) else 0
        else:
            duplicados += 1
        vinculos += _inserir_agentes(conn, registro["id_amostra"], registro.get("agentes_texto"))

    logger.log(
        f"  Amostras novas: {inseridos} | Duplicadas: {duplicados} | Vinculos agentes: {vinculos}",
        "ok",
    )
    return {
        "ok": True,
        "tipo": "AMOSTRA_ANIMAIS",
        "visitas_novas": inseridos,
        "coletas_novas": animais_novos,
        "animais_novos": animais_novos,
        "acidentes_novos": acidentes,
        "capturas_novas": capturas,
        "resultados_novos": 0,
        "duplicadas": duplicados,
    }


def parse_workbook(path, estrutura=None):
    df = pd.read_excel(path, sheet_name=0, engine="openpyxl").dropna(how="all")
    estrutura = estrutura or ("nova" if is_new_format(path) else "legada")
    registros = []
    for idx, row in df.iterrows():
        data = _date(row.get("Data"))
        if not data:
            continue
        kobo_uuid = _uuid(row.get("_uuid")) if estrutura == "nova" else None
        chave = kobo_uuid or "|".join([
            str(idx),
            data,
            _text(row.get("Hora")) or "",
            _text(_pick(row, ("Agentes", "Nome do(s) agente(s)"))) or "",
            _text(row.get("Logradouro")) or "",
            _text(row.get("Número")) or "",
        ])
        especie = _especie_resumo(row)
        tipo_animal = _text(row.get("Tipo de animal:")) or _text(row.get("Animal"))
        registros.append({
            "id_amostra": _hash("amostra_animais", estrutura, chave),
            "kobo_uuid": kobo_uuid,
            "kobo_id": _int(row.get("_id")),
            "data": data,
            "hora": _time(row.get("Hora")),
            "inicio_registro": _datetime(row.get("start")) if estrutura == "nova" else None,
            "fim_registro": _datetime(row.get("end")) if estrutura == "nova" else None,
            "agentes_texto": _agentes(row, estrutura),
            "motivo_visita": _text(row.get("Motivo da visita")),
            "animal_motivador": _text(row.get("Tipo de animal que motivou a visita:")) or _text(row.get("Animal")),
            "animal_motivador_outro": _text(row.get("Digite o animal:")),
            "localidade": agentes_core._localidade(row.get("Localidade")),
            "quarteirao": _int(row.get("Quarteirão")),
            "tipo_imovel": _text(row.get("Tipo do imóvel")) or _text(row.get("Imóvel")),
            "visita": _text(row.get("Visita")),
            "logradouro": _text(row.get("Logradouro")),
            "numero": _text(row.get("Número")),
            "sequencia": _text(row.get("Sequência")),
            "morador": _text(row.get("Morador")),
            "ocorrencia_residencia": _text(row.get("Ocorrência da residência")),
            "onde": _text(row.get("Onde?")),
            "houve_acidente": _text(row.get("Houve acidente?")),
            "houve_captura": _text(row.get("Houve captura?")),
            "local_captura": _text(row.get("Local da captura")),
            "tipo_animal": tipo_animal,
            "animal_capturado": _text(row.get("Qual animal foi capturado?")),
            "especie_serpente": _text(row.get("Qual a espécie da serpente?")),
            "especie_escorpiao": _text(row.get("Qual a espécie do escorpião?")),
            "especie_lagarta": _text(row.get("Qual a espécie da lagarta?")),
            "especie_aranha": _text(row.get("Qual a espécie da aranha?")),
            "especie_carrapato": _text(row.get("Qual a espécie do carrapato?")),
            "especie_resumo": especie,
            "quantidade": _int(row.get("Quantidade:")) or _int(row.get("Quantidade")) or 0,
            "submission_time": _datetime(row.get("_submission_time")) if estrutura == "nova" else None,
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
                    COALESCE(SUM(quantidade),0) AS quantidade,
                    SUM(CASE WHEN LOWER(COALESCE(houve_acidente,''))='sim' THEN 1 ELSE 0 END) AS acidentes,
                    SUM(CASE WHEN LOWER(COALESCE(houve_captura,''))='sim' THEN 1 ELSE 0 END) AS capturas,
                    SUM(CASE WHEN LOWER(COALESCE(motivo_visita,''))='reclamação' OR LOWER(COALESCE(motivo_visita,''))='reclamacao' THEN 1 ELSE 0 END) AS reclamacoes,
                    SUM(CASE WHEN LOWER(COALESCE(motivo_visita,''))='investigação' OR LOWER(COALESCE(motivo_visita,''))='investigacao' THEN 1 ELSE 0 END) AS investigacoes,
                    COUNT(DISTINCT localidade) AS localidades
                FROM amostras_animais a {where}""",
            params,
        ).fetchone())
        por_tipo = [dict(r) for r in conn.execute(
            f"""SELECT COALESCE(tipo_animal, animal_motivador, '-') AS tipo, COUNT(*) AS registros, COALESCE(SUM(quantidade),0) AS quantidade
                  FROM amostras_animais a {where}
                 GROUP BY COALESCE(tipo_animal, animal_motivador, '-')
                 ORDER BY registros DESC, tipo LIMIT 12""",
            params,
        )]
        por_localidade = [dict(r) for r in conn.execute(
            f"""SELECT COALESCE(localidade,'-') AS localidade, COUNT(*) AS registros, COALESCE(SUM(quantidade),0) AS quantidade
                  FROM amostras_animais a {where}
                 GROUP BY COALESCE(localidade,'-')
                 ORDER BY registros DESC, localidade LIMIT 12""",
            params,
        )]
    finally:
        conn.close()
    return {"totais": {k: (v or 0) for k, v in totais.items()}, "por_tipo": por_tipo, "por_localidade": por_localidade}


def listar(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros, busca=True)
    try:
        rows = [dict(r) for r in conn.execute(
            f"""SELECT a.*,
                       (SELECT GROUP_CONCAT(ag.nome, ', ')
                          FROM amostra_animais_agentes aa
                          JOIN agentes ag ON ag.id_agente=aa.id_agente
                         WHERE aa.id_amostra=a.id_amostra) AS agentes
                  FROM amostras_animais a {where}
                 ORDER BY a.data DESC, a.hora DESC, a.localidade
                 LIMIT 500""",
            params,
        )]
    finally:
        conn.close()
    return {"registros": rows, "total": len(rows)}


def localidades(db_path):
    return _distinct(db_path, "localidade")


def agentes(db_path):
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT DISTINCT ag.nome
                 FROM amostra_animais_agentes aa
                 JOIN agentes ag ON ag.id_agente=aa.id_agente
                ORDER BY ag.nome"""
        )]
    finally:
        conn.close()


def opcoes(db_path, coluna):
    if coluna not in {"motivo_visita", "tipo_animal", "animal_motivador"}:
        return []
    return _distinct(db_path, coluna)


def _distinct(db_path, coluna):
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    try:
        return [dict(r) for r in conn.execute(
            f"""SELECT DISTINCT {coluna} AS nome
                  FROM amostras_animais
                 WHERE {coluna} IS NOT NULL AND TRIM({coluna})<>''
                 ORDER BY {coluna}"""
        )]
    finally:
        conn.close()


def _where(filtros, busca=False):
    clauses = ["WHERE 1=1"]
    params = []
    for key, col in (
        ("d_ini", "data>="),
        ("d_fim", "data<="),
    ):
        if filtros.get(key):
            clauses.append(f"AND a.{col}?")
            params.append(filtros[key])
    for key, col in (
        ("localidade", "localidade"),
        ("motivo", "motivo_visita"),
        ("tipo_animal", "tipo_animal"),
        ("acidente", "houve_acidente"),
        ("captura", "houve_captura"),
        ("origem", "origem_estrutura"),
    ):
        if filtros.get(key):
            clauses.append(f"AND a.{col}=?")
            params.append(filtros[key])
    if filtros.get("agente"):
        clauses.append(
            """AND EXISTS (
                   SELECT 1 FROM amostra_animais_agentes aa
                   JOIN agentes ag ON ag.id_agente=aa.id_agente
                  WHERE aa.id_amostra=a.id_amostra AND ag.nome=?
               )"""
        )
        params.append(filtros["agente"])
    if busca and filtros.get("busca"):
        termo = f"%{filtros['busca']}%"
        clauses.append(
            """AND (a.localidade LIKE ? OR a.logradouro LIKE ? OR a.morador LIKE ?
                    OR a.agentes_texto LIKE ? OR a.tipo_animal LIKE ? OR a.especie_resumo LIKE ?)"""
        )
        params.extend([termo] * 6)
    return " ".join(clauses), params


def _inserir_amostra(conn, registro, agora_iso):
    cur = conn.cursor()
    cur.execute(
        """INSERT OR IGNORE INTO amostras_animais (
            id_amostra, kobo_uuid, kobo_id, data, hora, inicio_registro, fim_registro,
            agentes_texto, motivo_visita, animal_motivador, animal_motivador_outro,
            localidade, id_localidade, quarteirao, tipo_imovel, visita, logradouro,
            numero, sequencia, morador, ocorrencia_residencia, onde, houve_acidente,
            houve_captura, local_captura, tipo_animal, animal_capturado,
            especie_serpente, especie_escorpiao, especie_lagarta, especie_aranha,
            especie_carrapato, especie_resumo, quantidade, origem_estrutura,
            arquivo_origem, submission_time, processado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            registro["id_amostra"], registro.get("kobo_uuid"), registro.get("kobo_id"),
            registro["data"], registro.get("hora"), registro.get("inicio_registro"),
            registro.get("fim_registro"), registro.get("agentes_texto"),
            registro.get("motivo_visita"), registro.get("animal_motivador"),
            registro.get("animal_motivador_outro"), registro.get("localidade"),
            _obter_ou_criar_localidade(conn, registro.get("localidade")),
            registro.get("quarteirao"), registro.get("tipo_imovel"), registro.get("visita"),
            registro.get("logradouro"), registro.get("numero"), registro.get("sequencia"),
            registro.get("morador"), registro.get("ocorrencia_residencia"), registro.get("onde"),
            registro.get("houve_acidente"), registro.get("houve_captura"),
            registro.get("local_captura"), registro.get("tipo_animal"),
            registro.get("animal_capturado"), registro.get("especie_serpente"),
            registro.get("especie_escorpiao"), registro.get("especie_lagarta"),
            registro.get("especie_aranha"), registro.get("especie_carrapato"),
            registro.get("especie_resumo"), registro.get("quantidade", 0),
            registro.get("origem_estrutura", "nova"), registro.get("arquivo_origem"),
            registro.get("submission_time"), agora_iso,
        ),
    )
    return cur.rowcount > 0


def _inserir_agentes(conn, id_amostra, agentes_texto):
    total = 0
    for nome in _split_agentes(agentes_texto):
        id_agente = _obter_ou_criar_agente(conn, nome)
        cur = conn.execute(
            "INSERT OR IGNORE INTO amostra_animais_agentes(id_amostra, id_agente) VALUES (?,?)",
            (id_amostra, id_agente),
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
                marcados.append(_normalizar_agente(str(col).split("/", 1)[1].strip()))
    return ", ".join(marcados) if marcados else _normalizar_agentes_texto(texto)


def _split_agentes(texto):
    return agentes_core._split_agentes(_normalizar_agentes_texto(texto))


def _normalizar_agentes_texto(texto):
    texto = _text(texto)
    if not texto:
        return None
    return re.sub(r"\bFernado\b", "Fernando", texto)


def _normalizar_agente(nome):
    return "Fernando" if nome == "Fernado" else nome


def _especie_resumo(row):
    for col in ESPECIE_COLS:
        valor = _text(row.get(col))
        if valor:
            return valor
    return _text(row.get("Qual animal foi capturado?")) or _text(row.get("Digite o animal:"))


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


def _sim(value):
    return (_text(value) or "").lower() == "sim"


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
