import hashlib
import sqlite3
import unicodedata
from datetime import datetime

import pandas as pd

from app_core import recolhimentos as normalizadores


TABLE = "pontos_estrategicos"


PE_ALIAS_SEED = (
    ("Barracão Reciclar e Limpar - Rua Aides Ângelo de Oliveira", None, "PE-0026"),
    ("Borracharia (Antunes - pai) - Rodovia dos Minérios", None, "PE-0021"),
    ("Borracharia (Davi) - Rodovia dos Minérios", None, "PE-0023"),
    ("Borracharia (prox celeste) - Rodovia Dos Minérios", None, "PE-0007"),
    ("Borracharia - Rio Tanguá", None, "PE-0008"),
    ("Borracharia DPC - Rodovia dos Minérios", None, "PE-0022"),
    ("Borracharia Maurício - Rodovia Dos Minérios", None, "PE-0007"),
    ("Borracharia Nezinho - Rodovia dos Minérios - 7643", None, "PE-0012"),
    ("Borracharia Pedra Branca - Rodovia dos Minérios - KM16", None, "PE-0010"),
    ("Borracharia Polaco - Antonio Stochero", None, "PE-0006"),
    ("Borracharia do Nei - Rodovia Dos Minérios - 14365", None, "PE-0001"),
    ("Borracharia do Nei - Rodovia Dos Minérios - 14745", None, "PE-0001"),
    ("Cal Barigui - Pedro Teixeira Alves", None, "PE-0019"),
    ("Cal Chimelli - Antonio Stochero", None, "PE-0005"),
    ("Cal Eloi - Pedro Teixeira Alves", None, "PE-0020"),
    ("CEMITERIO", "Rosana", "PE-0042"),
    ("Cemitério - Cel. João Cândido de Oliveira - 750", None, "PE-0015"),
    ("Cemitério - João Berquó", None, "PE-0002"),
    ("Cemitério Evangélico - Mauricio Rosseman - S/N", None, "PE-0041"),
    ("Cemitério Prado - Prof Alberto Piekarz", None, "PE-0042"),
    ("Cemitério Vaticano - Mauricio Rosseman - 665", None, "PE-0040"),
    ("CONDOMINIO", "Rosana", "PE-0043"),
    ("Conserto Máquinas", None, "PE-0024"),
    ("Conserto Máquinas - Rua Barigui", None, "PE-0024"),
    ("Ferro Velho (Proprietário Bruno) - Rua São Gabriel", None, "PE-0025"),
    ("Ferro Velho - Alisson", None, "PE-0029"),
    ("Ferro Velho Brito - Rodovia dos Minérios", None, "PE-0034"),
    ("Ferro Velho Campo Grande - Gervásio Czeluziniak", None, "PE-0004"),
    ("Ferro Velho Nunes - Contorno Norte - S/N", None, "PE-0039"),
    ("Ferro Velho Nunes - Rod. Vereador Admar Bertolli - S/N", None, "PE-0039"),
    ("Ferro Velho Pernambuco - Rod. Edmar Bertolli - 74", None, "PE-0032"),
    ("Ferro Velho Pernambuco - Rod. Vereador Admar Bertolli - 74", None, "PE-0032"),
    ("Ferro Velho do Paulo - Rua Campo de Minas", None, "PE-0031"),
    ("Ferro Velho do Paulo - Rua Campos de Minas", None, "PE-0031"),
    ("LYX", "Rosana", "PE-0043"),
    ("Lyx New Jersey - José Real Prado - 3715", "Rosana", "PE-0043"),
    ("Meio Ambiente - Trav. Rio Cachoeirinha", None, "PE-0009"),
    ("Metalurgica - Pref. Eurípedes de Siqueira", None, "PE-0011"),
    ("Metalurgica - Prof. Eurípedes de Siqueira", None, "PE-0011"),
    ("ORPEC - Wadislau Bugalski", None, "PE-0028"),
    ("Patio de Obras - Pedro Teixeira Alves", None, "PE-0017"),
    ("Posto Rodoviário - Rodovia Dos Minérios - KM21", None, "PE-0003"),
    ("Reciclagem (Valdecir) - Rua Alexandre de Cristo", None, "PE-0027"),
    ("Reciclagem - Carlos", None, "PE-0030"),
    ("Reciclagem Antenor - Rodovia dos Minérios", None, "PE-0035"),
    ("Reciclagem Ernesto Silva - Antonio Soares de Britto - 85", None, "PE-0033"),
    ("Reciclagem Garcia - Iraydes da Cruz Guimarães - 7733", None, "PE-0038"),
    ("Reciclagem Ilha Nova - José Platner - 24", None, "PE-0014"),
    ("Reciclagem Marques - Francisco Kriger - 36", None, "PE-0036"),
    ("Reciclagem Marques - Francisco Kruger - 36", None, "PE-0036"),
    ("Reciclagem da Ilha - Constância Wolf", None, "PE-0013"),
    ("Reciclagem no TB - Constância Wolf", None, "PE-0013"),
    ("Reciclagrem Carlos", None, "PE-0030"),
    ("Tas Construtora - Iraydes da Cruz Guimarães", None, "PE-0037"),
    ("Terreno ao Lado Câmara Municipal - José Carlos Colodel", None, "PE-0016"),
)


def ensure_schema(conn):
    em_transacao = conn.in_transaction
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

        CREATE TABLE IF NOT EXISTS pontos_estrategicos_alias (
            id_alias              INTEGER PRIMARY KEY AUTOINCREMENT,
            alias_logradouro      TEXT NOT NULL,
            alias_normalizado     TEXT NOT NULL,
            localidade            TEXT,
            localidade_normalizada TEXT NOT NULL DEFAULT '',
            codigo_pe             TEXT NOT NULL REFERENCES pontos_estrategicos(codigo_pe),
            observacoes           TEXT,
            ativo                 INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
            criado_em             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(alias_normalizado, localidade_normalizada)
        );

        CREATE INDEX IF NOT EXISTS idx_pe_alias_lookup
            ON pontos_estrategicos_alias(alias_normalizado, localidade_normalizada, ativo);
        """
    )
    _ensure_visitas_vinculo_schema(conn)
    _seed_aliases(conn)
    if not em_transacao and conn.in_transaction:
        conn.commit()


def _ensure_visitas_vinculo_schema(conn):
    if not _table_exists(conn, "visitas"):
        return
    cols = _table_columns(conn, "visitas")
    if "id_pe" not in cols:
        conn.execute("ALTER TABLE visitas ADD COLUMN id_pe INTEGER")
    if "codigo_pe" not in cols:
        conn.execute("ALTER TABLE visitas ADD COLUMN codigo_pe TEXT")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_visitas_id_pe ON visitas(id_pe);
        CREATE INDEX IF NOT EXISTS idx_visitas_codigo_pe ON visitas(codigo_pe);
        """
    )


def _seed_aliases(conn):
    agora = datetime.now().isoformat(timespec="seconds")
    for alias, localidade, codigo_pe in PE_ALIAS_SEED:
        if not conn.execute("SELECT 1 FROM pontos_estrategicos WHERE codigo_pe=?", (codigo_pe,)).fetchone():
            continue
        conn.execute(
            """INSERT OR IGNORE INTO pontos_estrategicos_alias (
                   alias_logradouro, alias_normalizado, localidade, localidade_normalizada,
                   codigo_pe, observacoes, ativo, criado_em, atualizado_em
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                _text(alias),
                normalizar_alias(alias),
                _text(localidade),
                normalizar_alias(localidade),
                codigo_pe,
                "alias inicial para visitas PE antigas",
                1,
                agora,
                agora,
            ),
        )
        conn.execute(
            """UPDATE pontos_estrategicos_alias
                  SET alias_logradouro=?,
                      localidade=?,
                      codigo_pe=?,
                      ativo=1,
                      atualizado_em=?
                WHERE alias_normalizado=?
                  AND localidade_normalizada=?
                  AND (observacoes IS NULL OR observacoes='alias inicial para visitas PE antigas')""",
            (
                _text(alias),
                _text(localidade),
                codigo_pe,
                agora,
                normalizar_alias(alias),
                normalizar_alias(localidade),
            ),
        )


def resolver_alias_visita(conn, logradouro, localidade=None):
    alias = normalizar_alias(logradouro)
    if not alias:
        return None
    localidade_norm = normalizar_alias(localidade)
    row = None
    if localidade_norm:
        row = conn.execute(
            """SELECT pe.id_pe, pe.codigo_pe
                 FROM pontos_estrategicos_alias a
                 JOIN pontos_estrategicos pe ON pe.codigo_pe=a.codigo_pe
                WHERE a.ativo=1
                  AND a.alias_normalizado=?
                  AND a.localidade_normalizada=?
                ORDER BY pe.situacao DESC, pe.codigo_pe
                LIMIT 1""",
            (alias, localidade_norm),
        ).fetchone()
    if not row:
        row = conn.execute(
            """SELECT pe.id_pe, pe.codigo_pe
                 FROM pontos_estrategicos_alias a
                 JOIN pontos_estrategicos pe ON pe.codigo_pe=a.codigo_pe
                WHERE a.ativo=1
                  AND a.alias_normalizado=?
                  AND a.localidade_normalizada=''
                ORDER BY pe.situacao DESC, pe.codigo_pe
                LIMIT 1""",
            (alias,),
        ).fetchone()
    if not row:
        return None
    try:
        return {"id_pe": row["id_pe"], "codigo_pe": row["codigo_pe"]}
    except (TypeError, IndexError):
        return {"id_pe": row[0], "codigo_pe": row[1]}


def vincular_visitas_existentes_por_alias(conn):
    if not _table_exists(conn, "visitas"):
        return {"atualizadas": 0, "sem_alias": 0}
    ensure_schema(conn)
    rows = conn.execute(
        """SELECT id_visita, logradouro, localidade
             FROM visitas
            WHERE tipo='PE'
              AND (id_pe IS NULL OR codigo_pe IS NULL)
              AND logradouro IS NOT NULL
              AND TRIM(logradouro)<>''"""
    ).fetchall()
    atualizadas = sem_alias = 0
    for row in rows:
        try:
            id_visita = row["id_visita"]
            logradouro = row["logradouro"]
            localidade = row["localidade"]
        except (TypeError, IndexError):
            id_visita, logradouro, localidade = row[0], row[1], row[2]
        vinculo = resolver_alias_visita(conn, logradouro, localidade)
        if not vinculo:
            sem_alias += 1
            continue
        conn.execute(
            "UPDATE visitas SET id_pe=?, codigo_pe=? WHERE id_visita=?",
            (vinculo["id_pe"], vinculo["codigo_pe"], id_visita),
        )
        atualizadas += 1
    return {"atualizadas": atualizadas, "sem_alias": sem_alias}


def normalizar_alias(value):
    text = _text(value)
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("rod.", "rodovia").replace("trav.", "travessa")
    text = text.replace("prof.", "professor").replace("pref.", "prefeito")
    text = text.replace("  ", " ")
    text = " ".join(text.split())
    text = text.replace(" -  ", " - ").replace("  - ", " - ").replace("-  ", "- ")
    return text


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _table_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


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
        _seed_aliases(conn)
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


def listar(db_path, filtros=None, limite=1000):
    filtros = filtros or {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    _ensure_optional_modules(conn)
    where, params = _where(filtros)
    limit_clause = "" if limite is None else "LIMIT ?"
    query_params = list(params)
    if limite is not None:
        query_params.append(int(limite))
    try:
        rows = [
            _completar_status_operacional(dict(r))
            for r in conn.execute(
                f"""SELECT pe.*,
                        (
                            SELECT MAX(v.data)
                             FROM visitas v
                             WHERE v.tipo='PE'
                               AND (
                                   v.id_pe=pe.id_pe
                                   OR (v.id_pe IS NULL AND v.id_localidade=pe.id_localidade AND v.quarteirao=pe.quarteirao)
                               )
                        ) AS ultima_visita_pe,
                        (
                            SELECT COUNT(DISTINCT v.id_visita)
                              FROM visitas v
                             WHERE v.tipo='PE'
                               AND (
                                   v.id_pe=pe.id_pe
                                   OR (v.id_pe IS NULL AND v.id_localidade=pe.id_localidade AND v.quarteirao=pe.quarteirao)
                               )
                        ) AS visitas_pe_total,
                        (
                            SELECT MAX(b.data)
                             FROM bri_registros b
                             WHERE b.destino_tratamento='Ponto Estratégico'
                               AND (
                                   b.id_pe=pe.id_pe
                                   OR (b.id_pe IS NULL AND b.id_localidade=pe.id_localidade AND b.quarteirao=pe.quarteirao)
                               )
                        ) AS ultimo_bri,
                        (
                            SELECT COUNT(*)
                              FROM bri_registros b
                             WHERE b.destino_tratamento='Ponto Estratégico'
                               AND (
                                   b.id_pe=pe.id_pe
                                   OR (b.id_pe IS NULL AND b.id_localidade=pe.id_localidade AND b.quarteirao=pe.quarteirao)
                               )
                        ) AS bri_total,
                        (
                            SELECT COUNT(*)
                              FROM focos_positivos f
                             WHERE f.gera_notificacao=1
                               AND f.id_localidade=pe.id_localidade
                               AND f.quarteirao=pe.quarteirao
                        ) AS focos_total
                    FROM pontos_estrategicos pe
                    {where}
                    ORDER BY situacao DESC, localidade, quarteirao, nome
                    {limit_clause}""",
                query_params,
            )
        ]
        rows = _filtrar_status_calculado(rows, filtros)
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
    totais = {k: (v or 0) for k, v in totais.items()}
    if filtros.get("atrasados") or filtros.get("pendencias"):
        totais = _totais_de_rows(rows)
    return {"registros": rows, "total": len(rows), "totais": totais}


def resumo_operacional(db_path, filtros=None):
    filtros = filtros or {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    _ensure_optional_modules(conn)
    where, params = _where(filtros)
    d_ini = filtros.get("d_ini") or "0001-01-01"
    d_fim = filtros.get("d_fim") or "9999-12-31"
    try:
        totais = dict(conn.execute(
            f"""SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN pe.situacao=1 THEN 1 ELSE 0 END) AS ativos,
                    SUM(CASE WHEN pe.situacao=0 THEN 1 ELSE 0 END) AS inativos,
                    SUM(CASE WHEN pe.situacao=1 AND (pe.latitude IS NULL OR pe.longitude IS NULL) THEN 1 ELSE 0 END) AS ativos_sem_coordenada,
                    SUM(CASE WHEN pe.situacao=1 AND (pe.tipo IS NULL OR TRIM(pe.tipo)='') THEN 1 ELSE 0 END) AS ativos_sem_tipo,
                    SUM(CASE WHEN pe.situacao=1 AND (pe.telefone IS NULL OR TRIM(pe.telefone)='') THEN 1 ELSE 0 END) AS ativos_sem_telefone
               FROM pontos_estrategicos pe
               {where}""",
            params,
        ).fetchone())

        visitados_periodo = conn.execute(
            f"""SELECT COUNT(DISTINCT pe.id_pe)
                  FROM pontos_estrategicos pe
                  JOIN visitas v ON v.tipo='PE'
                   AND (
                       v.id_pe=pe.id_pe
                       OR (v.id_pe IS NULL AND v.id_localidade=pe.id_localidade AND v.quarteirao=pe.quarteirao)
                   )
                 {where}
                   AND v.data BETWEEN ? AND ?""",
            params + [d_ini, d_fim],
        ).fetchone()[0]

        bri_periodo = conn.execute(
            f"""SELECT COUNT(DISTINCT pe.id_pe)
                  FROM pontos_estrategicos pe
                  JOIN bri_registros b ON b.destino_tratamento='Ponto Estratégico'
                   AND (
                       b.id_pe=pe.id_pe
                       OR (b.id_pe IS NULL AND b.id_localidade=pe.id_localidade AND b.quarteirao=pe.quarteirao)
                   )
                 {where}
                   AND b.data BETWEEN ? AND ?""",
            params + [d_ini, d_fim],
        ).fetchone()[0]

        focos_periodo = conn.execute(
            f"""SELECT COUNT(DISTINCT pe.id_pe)
                  FROM pontos_estrategicos pe
                  JOIN focos_positivos f ON f.gera_notificacao=1
                   AND f.id_localidade=pe.id_localidade
                   AND f.quarteirao=pe.quarteirao
                 {where}
                   AND f.data BETWEEN ? AND ?""",
            params + [d_ini, d_fim],
        ).fetchone()[0]

        atrasados = conn.execute(
            f"""SELECT COUNT(*) FROM (
                    SELECT pe.id_pe, MAX(v.data) AS ultima_visita
                      FROM pontos_estrategicos pe
                      LEFT JOIN visitas v ON v.tipo='PE'
                       AND (
                           v.id_pe=pe.id_pe
                           OR (v.id_pe IS NULL AND v.id_localidade=pe.id_localidade AND v.quarteirao=pe.quarteirao)
                       )
                     {where}
                       AND pe.situacao=1
                     GROUP BY pe.id_pe
                    HAVING ultima_visita IS NULL OR julianday('now') - julianday(ultima_visita) > 20
                ) sub""",
            params,
        ).fetchone()[0]

        pendencias = [
            _completar_status_operacional(dict(r))
            for r in conn.execute(
                f"""SELECT pe.*,
                        MAX(v.data) AS ultima_visita_pe,
                        COUNT(DISTINCT v.id_visita) AS visitas_pe_total,
                        (
                            SELECT MAX(b.data) FROM bri_registros b
                            WHERE b.destino_tratamento='Ponto Estratégico'
                               AND (
                                   b.id_pe=pe.id_pe
                                   OR (b.id_pe IS NULL AND b.id_localidade=pe.id_localidade AND b.quarteirao=pe.quarteirao)
                               )
                        ) AS ultimo_bri,
                        (
                            SELECT COUNT(*) FROM bri_registros b
                             WHERE b.destino_tratamento='Ponto Estratégico'
                               AND (
                                   b.id_pe=pe.id_pe
                                   OR (b.id_pe IS NULL AND b.id_localidade=pe.id_localidade AND b.quarteirao=pe.quarteirao)
                               )
                        ) AS bri_total,
                        (
                            SELECT COUNT(*) FROM focos_positivos f
                             WHERE f.gera_notificacao=1
                               AND f.id_localidade=pe.id_localidade
                               AND f.quarteirao=pe.quarteirao
                        ) AS focos_total
                    FROM pontos_estrategicos pe
                    LEFT JOIN visitas v ON v.tipo='PE'
                     AND (
                         v.id_pe=pe.id_pe
                         OR (v.id_pe IS NULL AND v.id_localidade=pe.id_localidade AND v.quarteirao=pe.quarteirao)
                     )
                    {where}
                      AND pe.situacao=1
                    GROUP BY pe.id_pe
                   HAVING ultima_visita_pe IS NULL OR julianday('now') - julianday(ultima_visita_pe) > 20
                       OR pe.latitude IS NULL OR pe.longitude IS NULL
                       OR pe.tipo IS NULL OR TRIM(pe.tipo)=''
                   ORDER BY
                       CASE WHEN ultima_visita_pe IS NULL THEN 0 ELSE 1 END,
                       ultima_visita_pe,
                       pe.localidade,
                       pe.quarteirao
                   LIMIT 12""",
                params,
            )
        ]
    finally:
        conn.close()

    dados = {k: (v or 0) for k, v in totais.items()}
    dados.update({
        "visitados_periodo": visitados_periodo or 0,
        "bri_periodo": bri_periodo or 0,
        "focos_periodo": focos_periodo or 0,
        "atrasados": atrasados or 0,
    })
    return {"totais": dados, "pendencias": pendencias}


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


def _completar_status_operacional(row):
    ultima = row.get("ultima_visita_pe")
    if ultima:
        try:
            dias = (datetime.now().date() - datetime.fromisoformat(str(ultima)).date()).days
        except Exception:
            dias = None
    else:
        dias = None
    row["dias_sem_visita"] = dias
    row["visita_atrasada"] = int(row.get("situacao") == 1 and (dias is None or dias > 20))
    row["pendencias_cadastro"] = [
        label
        for label, ok in (
            ("sem tipo", bool(_text(row.get("tipo")))),
            ("sem telefone", bool(_text(row.get("telefone")))),
            ("sem coordenada", row.get("latitude") is not None and row.get("longitude") is not None),
        )
        if not ok
    ]
    return row


def _filtrar_status_calculado(rows, filtros):
    if filtros.get("atrasados") in ("1", 1, True, "true", "sim"):
        rows = [r for r in rows if r.get("visita_atrasada")]
    if filtros.get("pendencias") in ("1", 1, True, "true", "sim"):
        rows = [r for r in rows if r.get("visita_atrasada") or r.get("pendencias_cadastro")]
    return rows


def _totais_de_rows(rows):
    return {
        "total": len(rows),
        "ativos": sum(1 for r in rows if r.get("situacao") == 1),
        "inativos": sum(1 for r in rows if r.get("situacao") == 0),
        "sem_tipo": sum(1 for r in rows if not _text(r.get("tipo"))),
        "sem_telefone": sum(1 for r in rows if not _text(r.get("telefone"))),
        "sem_coordenadas": sum(1 for r in rows if r.get("latitude") is None or r.get("longitude") is None),
    }


def _ensure_optional_modules(conn):
    from app_core import bri as bri_core

    bri_core.ensure_schema(conn)


def _where(filtros):
    clauses = ["WHERE 1=1"]
    params = []
    if filtros.get("situacao") in ("0", "1", 0, 1):
        clauses.append("AND pe.situacao=?")
        params.append(int(filtros["situacao"]))
    if isinstance(filtros.get("localidade"), (list, tuple)):
        valores = [v for v in filtros.get("localidade") if v]
        if valores:
            clauses.append(f"AND pe.localidade IN ({','.join('?' * len(valores))})")
            params.extend(valores)
    elif filtros.get("localidade"):
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
