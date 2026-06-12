import hashlib
import os

import pandas as pd

from app_core import recolhimentos as agentes_core
from app_core import normalizadores
from app_core import pontos_estrategicos as pe_core


TABLE = "bri_registros"
AGENTES_TABLE = "bri_agentes"


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS bri_registros (
            id_bri                 TEXT PRIMARY KEY,
            kobo_uuid              TEXT UNIQUE,
            kobo_id                INTEGER,
            sispncd                TEXT,
            data                   DATE NOT NULL,
            hora                   TIME,
            inicio_registro        TEXT,
            fim_registro           TEXT,
            agentes_texto          TEXT,
            destino_tratamento     TEXT,
            local_tratamento       TEXT,
            localidade             TEXT,
            id_localidade          INTEGER REFERENCES localidades(id_localidade),
            logradouro             TEXT,
            quarteirao             INTEGER,
            numero                 TEXT,
            numero_ovitrampa       TEXT,
            quantidade_carga       REAL DEFAULT 0,
            tratou_imovel_extra    TEXT,
            qual_imovel_extra      TEXT,
            depositos_tratados_extra INTEGER,
            quantidade_carga_extra REAL DEFAULT 0,
            origem_estrutura       TEXT NOT NULL DEFAULT 'nova',
            arquivo_origem         TEXT,
            submission_time        TEXT,
            processado_em          TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bri_agentes (
            id_bri    TEXT NOT NULL REFERENCES bri_registros(id_bri) ON DELETE CASCADE,
            id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
            PRIMARY KEY (id_bri, id_agente)
        );

        CREATE INDEX IF NOT EXISTS idx_bri_data ON bri_registros(data);
        CREATE INDEX IF NOT EXISTS idx_bri_localidade ON bri_registros(id_localidade);
        CREATE INDEX IF NOT EXISTS idx_bri_destino ON bri_registros(destino_tratamento);
        CREATE INDEX IF NOT EXISTS idx_bri_sispncd ON bri_registros(sispncd);
        CREATE INDEX IF NOT EXISTS idx_bri_agentes_agente ON bri_agentes(id_agente);
        """
    )
    _ensure_vinculo_pe_schema(conn)


def _ensure_vinculo_pe_schema(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(bri_registros)")}
    if "id_pe" not in cols:
        conn.execute("ALTER TABLE bri_registros ADD COLUMN id_pe INTEGER")
    if "codigo_pe" not in cols:
        conn.execute("ALTER TABLE bri_registros ADD COLUMN codigo_pe TEXT")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_bri_id_pe ON bri_registros(id_pe);
        CREATE INDEX IF NOT EXISTS idx_bri_codigo_pe ON bri_registros(codigo_pe);
        """
    )


def is_new_format(path):
    df = pd.read_excel(path, sheet_name=0, nrows=1, engine="openpyxl")
    columns = set(df.columns)
    return {"start", "end", "Digite a data", "Digite a hora", "_uuid"}.issubset(columns)


def processar_arquivo(path, conn, logger, agora_iso, dry_run=False):
    estrutura = "nova" if is_new_format(path) else "legada"
    registros = parse_workbook(path, estrutura)
    logger.log(f"  Estrutura: {estrutura} | BRI: {len(registros)}")

    ensure_schema(conn)
    inseridos = duplicados = vinculos = 0
    carga_total = 0
    for registro in registros:
        registro["arquivo_origem"] = os.path.basename(path)
        registro["origem_estrutura"] = estrutura
        novo = _inserir_bri(conn, registro, agora_iso)
        if novo:
            inseridos += 1
            carga_total += registro.get("quantidade_carga", 0) or 0
            carga_total += registro.get("quantidade_carga_extra", 0) or 0
        else:
            duplicados += 1
        vinculos += _inserir_agentes(conn, registro["id_bri"], registro.get("agentes_texto"))

    logger.log(
        f"  BRI novos: {inseridos} | Duplicados: {duplicados} | Vinculos agentes: {vinculos}",
        "ok",
    )
    return {
        "ok": True,
        "tipo": "BRI",
        "visitas_novas": inseridos,
        "coletas_novas": 0,
        "carga_nova": carga_total,
        "resultados_novos": 0,
        "duplicadas": duplicados,
    }


def parse_workbook(path, estrutura=None):
    df = pd.read_excel(path, sheet_name=0, engine="openpyxl").dropna(how="all")
    estrutura = estrutura or ("nova" if is_new_format(path) else "legada")
    registros = []
    for idx, row in df.iterrows():
        data = _date(_pick(row, ("Digite a data", "Data")))
        if not data:
            continue
        destino = _text(row.get("Onde vai ser realizado o tratamento?"))
        end = _endereco(row, destino, estrutura)
        kobo_uuid = _uuid(row.get("_uuid")) if estrutura == "nova" else None
        chave = kobo_uuid or "|".join([
            str(idx),
            _text(row.get("SISPNCD")) or "",
            data,
            _text(_pick(row, ("Digite a hora", "Hora"))) or "",
            end.get("localidade") or "",
            end.get("logradouro") or "",
            str(end.get("numero") or ""),
        ])
        registros.append({
            "id_bri": _hash("bri", estrutura, chave),
            "kobo_uuid": kobo_uuid,
            "kobo_id": _int(row.get("_id")),
            "sispncd": _text(row.get("SISPNCD")),
            "data": data,
            "hora": _time(_pick(row, ("Digite a hora", "Hora"))),
            "inicio_registro": _datetime(row.get("start")) if estrutura == "nova" else None,
            "fim_registro": _datetime(row.get("end")) if estrutura == "nova" else None,
            "agentes_texto": _agentes(row, estrutura),
            "destino_tratamento": destino,
            "local_tratamento": _text(row.get("Onde foi realizado o tratamento?")),
            "numero_ovitrampa": _text(row.get("Número da Ovitrampa")),
            "quantidade_carga": _real(row.get("Quantidade de carga")) or 0,
            "tratou_imovel_extra": _text(row.get("Foi tratado algum imóvel além do PE ou da Ovitrampa?")),
            "qual_imovel_extra": _text(row.get("Qual imóvel?")),
            "depositos_tratados_extra": _int(row.get("Quantidade depósitos tratados")),
            "quantidade_carga_extra": _real(row.get("Quantidade de carga.1")) or 0,
            "submission_time": _datetime(row.get("_submission_time")) if estrutura == "nova" else None,
            **end,
        })
    return registros


def resumo(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    pe_core.ensure_schema(conn)
    where, params = _where(filtros)
    try:
        totais = dict(conn.execute(
            f"""SELECT
                    COUNT(*) AS registros,
                    COALESCE(SUM(quantidade_carga),0) AS carga,
                    COALESCE(SUM(quantidade_carga_extra),0) AS carga_extra,
                    SUM(CASE WHEN destino_tratamento='Ovitrampa' THEN 1 ELSE 0 END) AS ovitrampas,
                    SUM(CASE WHEN destino_tratamento='Ponto Estratégico' THEN 1 ELSE 0 END) AS pontos_estrategicos,
                    SUM(CASE WHEN destino_tratamento='Outro' THEN 1 ELSE 0 END) AS outros,
                    SUM(CASE WHEN tratou_imovel_extra='Sim' THEN 1 ELSE 0 END) AS extras,
                    COUNT(DISTINCT b.localidade) AS localidades,
                    SUM(CASE WHEN b.destino_tratamento='Ponto Estratégico' AND (
                        SELECT COUNT(*) FROM pontos_estrategicos pe
                         WHERE pe.id_pe=b.id_pe
                            OR (b.id_pe IS NULL AND pe.id_localidade=b.id_localidade AND pe.quarteirao=b.quarteirao)
                    ) = 1 THEN 1 ELSE 0 END) AS vinculados_pe,
                    SUM(CASE WHEN b.destino_tratamento='Ponto Estratégico' AND (
                        SELECT COUNT(*) FROM pontos_estrategicos pe
                         WHERE pe.id_pe=b.id_pe
                            OR (b.id_pe IS NULL AND pe.id_localidade=b.id_localidade AND pe.quarteirao=b.quarteirao)
                    ) > 1 THEN 1 ELSE 0 END) AS ambiguos_pe,
                    SUM(CASE WHEN b.destino_tratamento='Ponto Estratégico' AND (
                        SELECT COUNT(*) FROM pontos_estrategicos pe
                         WHERE pe.id_pe=b.id_pe
                            OR (b.id_pe IS NULL AND pe.id_localidade=b.id_localidade AND pe.quarteirao=b.quarteirao)
                    ) = 0 THEN 1 ELSE 0 END) AS sem_vinculo_pe
                FROM bri_registros b
                {where}""",
            params,
        ).fetchone())
        por_destino = [dict(r) for r in conn.execute(
            f"""SELECT COALESCE(destino_tratamento,'-') AS destino,
                       COUNT(*) AS registros,
                       COALESCE(SUM(quantidade_carga + quantidade_carga_extra),0) AS carga
                  FROM bri_registros b {where}
                 GROUP BY COALESCE(destino_tratamento,'-')
                 ORDER BY registros DESC, destino""",
            params,
        )]
        por_localidade = [dict(r) for r in conn.execute(
            f"""SELECT COALESCE(localidade,'-') AS localidade,
                       COUNT(*) AS registros,
                       COALESCE(SUM(quantidade_carga + quantidade_carga_extra),0) AS carga
                  FROM bri_registros b {where}
                 GROUP BY COALESCE(localidade,'-')
                 ORDER BY registros DESC, localidade LIMIT 12""",
            params,
        )]
    finally:
        conn.close()
    return {"totais": {k: (v or 0) for k, v in totais.items()}, "por_destino": por_destino, "por_localidade": por_localidade}


def listar(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    pe_core.ensure_schema(conn)
    where, params = _where(filtros, busca=True)
    try:
        rows = [dict(r) for r in conn.execute(
            f"""SELECT b.*,
                       CASE WHEN b.destino_tratamento='Ponto Estratégico' THEN (
                           SELECT COUNT(*) FROM pontos_estrategicos pe
                            WHERE pe.id_pe=b.id_pe
                               OR (b.id_pe IS NULL AND pe.id_localidade=b.id_localidade AND pe.quarteirao=b.quarteirao)
                       ) ELSE 0 END AS pe_vinculos,
                       CASE WHEN b.destino_tratamento='Ponto Estratégico' THEN (
                           SELECT pe.codigo_pe FROM pontos_estrategicos pe
                            WHERE pe.id_pe=b.id_pe
                               OR (b.id_pe IS NULL AND pe.id_localidade=b.id_localidade AND pe.quarteirao=b.quarteirao)
                            ORDER BY pe.situacao DESC, pe.codigo_pe
                            LIMIT 1
                       ) END AS codigo_pe,
                       CASE WHEN b.destino_tratamento='Ponto Estratégico' THEN (
                           SELECT pe.nome FROM pontos_estrategicos pe
                            WHERE pe.id_pe=b.id_pe
                               OR (b.id_pe IS NULL AND pe.id_localidade=b.id_localidade AND pe.quarteirao=b.quarteirao)
                            ORDER BY pe.situacao DESC, pe.codigo_pe
                            LIMIT 1
                       ) END AS ponto_estrategico,
                       (SELECT GROUP_CONCAT(a.nome, ', ')
                          FROM bri_agentes ba
                          JOIN agentes a ON a.id_agente=ba.id_agente
                         WHERE ba.id_bri=b.id_bri) AS agentes
                  FROM bri_registros b
                  {where}
                 ORDER BY b.data DESC, b.hora DESC, b.localidade
                 LIMIT 500""",
            params,
        )]
    finally:
        conn.close()
    return {"registros": rows, "total": len(rows)}


def vincular_registros_pe_por_alias(conn):
    ensure_schema(conn)
    pe_core.ensure_schema(conn)
    rows = conn.execute(
        """SELECT id_bri, logradouro, local_tratamento, localidade
             FROM bri_registros
            WHERE destino_tratamento='Ponto Estratégico'
              AND (id_pe IS NULL OR codigo_pe IS NULL)
              AND logradouro IS NOT NULL
              AND TRIM(logradouro)<>''"""
    ).fetchall()
    atualizados = sem_alias = 0
    for row in rows:
        try:
            id_bri = row["id_bri"]
            logradouro = row["logradouro"]
            local_tratamento = row["local_tratamento"]
            localidade = row["localidade"]
        except (TypeError, IndexError):
            id_bri, logradouro, local_tratamento, localidade = row[0], row[1], row[2], row[3]
        vinculo = _resolver_pe_vinculo(conn, {
            "logradouro": logradouro,
            "local_tratamento": local_tratamento,
            "localidade": localidade,
        })
        if not vinculo:
            sem_alias += 1
            continue
        conn.execute(
            "UPDATE bri_registros SET id_pe=?, codigo_pe=? WHERE id_bri=?",
            (vinculo["id_pe"], vinculo["codigo_pe"], id_bri),
        )
        atualizados += 1
    return {"atualizados": atualizados, "sem_alias": sem_alias}


def localidades(db_path):
    return _distinct(db_path, "localidade")


def agentes(db_path):
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT DISTINCT a.nome
                 FROM bri_agentes ba
                 JOIN agentes a ON a.id_agente=ba.id_agente
                ORDER BY a.nome"""
        )]
    finally:
        conn.close()


def _distinct(db_path, coluna):
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    try:
        return [dict(r) for r in conn.execute(
            f"""SELECT DISTINCT {coluna} AS nome
                  FROM bri_registros
                 WHERE {coluna} IS NOT NULL AND TRIM({coluna})<>''
                 ORDER BY {coluna}"""
        )]
    finally:
        conn.close()


def _where(filtros, busca=False):
    clauses = ["WHERE 1=1"]
    params = []
    if filtros.get("d_ini"):
        clauses.append("AND b.data>=?")
        params.append(filtros["d_ini"])
    if filtros.get("d_fim"):
        clauses.append("AND b.data<=?")
        params.append(filtros["d_fim"])
    for key, col in (
        ("localidade", "localidade"),
        ("destino", "destino_tratamento"),
        ("extra", "tratou_imovel_extra"),
        ("origem", "origem_estrutura"),
    ):
        if filtros.get(key):
            clauses.append(f"AND b.{col}=?")
            params.append(filtros[key])
    if filtros.get("agente"):
        clauses.append(
            """AND EXISTS (
                   SELECT 1 FROM bri_agentes ba
                   JOIN agentes a ON a.id_agente=ba.id_agente
                  WHERE ba.id_bri=b.id_bri AND a.nome=?
               )"""
        )
        params.append(filtros["agente"])
    if busca and filtros.get("busca"):
        termo = f"%{filtros['busca']}%"
        clauses.append(
            """AND (b.sispncd LIKE ? OR b.localidade LIKE ? OR b.logradouro LIKE ?
                    OR b.numero_ovitrampa LIKE ? OR b.agentes_texto LIKE ? OR b.local_tratamento LIKE ?)"""
        )
        params.extend([termo] * 6)
    return " ".join(clauses), params


def _endereco(row, destino, estrutura):
    if estrutura == "nova" and destino == "Ovitrampa":
        return {
            "localidade": agentes_core._localidade(row.get("Localidade.1")),
            "logradouro": _text(row.get("Logradouro.1")),
            "quarteirao": _int(row.get("Quarteirão.1")),
            "numero": _text(row.get("Número.1")),
        }
    if estrutura == "nova" and destino == "Ponto Estratégico":
        return {
            "localidade": agentes_core._localidade(row.get("localidade")),
            "logradouro": _text(row.get("logradouro")),
            "quarteirao": _int(row.get("quarteirao")),
            "numero": _text(row.get("numero")),
        }
    return {
        "localidade": agentes_core._localidade(row.get("Localidade")),
        "logradouro": _text(row.get("Logradouro")),
        "quarteirao": _int(row.get("Quarteirão")),
        "numero": _text(row.get("Número")),
    }


def _inserir_bri(conn, registro, agora_iso):
    cur = conn.cursor()
    pe_vinculo = _resolver_pe_vinculo(conn, registro) if registro.get("destino_tratamento") == "Ponto Estratégico" else None
    cur.execute(
        """INSERT OR IGNORE INTO bri_registros (
            id_bri, kobo_uuid, kobo_id, sispncd, data, hora, inicio_registro, fim_registro,
            agentes_texto, destino_tratamento, local_tratamento, localidade, id_localidade,
            logradouro, quarteirao, numero, numero_ovitrampa, quantidade_carga,
            tratou_imovel_extra, qual_imovel_extra, depositos_tratados_extra,
            quantidade_carga_extra, origem_estrutura, arquivo_origem, submission_time,
            processado_em, id_pe, codigo_pe
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            registro["id_bri"], registro.get("kobo_uuid"), registro.get("kobo_id"),
            registro.get("sispncd"), registro["data"], registro.get("hora"),
            registro.get("inicio_registro"), registro.get("fim_registro"),
            registro.get("agentes_texto"), registro.get("destino_tratamento"),
            registro.get("local_tratamento"), registro.get("localidade"),
            _obter_ou_criar_localidade(conn, registro.get("localidade")),
            registro.get("logradouro"), registro.get("quarteirao"), registro.get("numero"),
            registro.get("numero_ovitrampa"), registro.get("quantidade_carga", 0),
            registro.get("tratou_imovel_extra"), registro.get("qual_imovel_extra"),
            registro.get("depositos_tratados_extra"), registro.get("quantidade_carga_extra", 0),
            registro.get("origem_estrutura", "nova"), registro.get("arquivo_origem"),
            registro.get("submission_time"), agora_iso,
            pe_vinculo.get("id_pe") if pe_vinculo else None,
            pe_vinculo.get("codigo_pe") if pe_vinculo else None,
        ),
    )
    return cur.rowcount > 0


def _resolver_pe_vinculo(conn, registro):
    logradouro = registro.get("logradouro")
    localidade = registro.get("localidade")
    vinculo = pe_core.resolver_alias_visita(conn, logradouro, localidade)
    if vinculo:
        return vinculo
    local = registro.get("local_tratamento")
    if local and logradouro:
        return pe_core.resolver_alias_visita(conn, f"{local} - {logradouro}", localidade)
    return None


def _inserir_agentes(conn, id_bri, agentes_texto):
    total = 0
    for nome in _split_agentes(agentes_texto):
        id_agente = _obter_ou_criar_agente(conn, nome)
        cur = conn.execute(
            "INSERT OR IGNORE INTO bri_agentes(id_bri, id_agente) VALUES (?,?)",
            (id_bri, id_agente),
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
    return ", ".join(marcados) if marcados else texto


def _split_agentes(texto):
    return agentes_core._split_agentes(texto)


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


def _real(value):
    try:
        if value is None or pd.isna(value):
            return None
    except Exception:
        if value is None:
            return None
    try:
        num = float(str(value).replace(",", "."))
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
