import csv
import hashlib
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from app_core import db as db_core
from app_core import normalizadores


TIPOS = {
    "R": "Residencia",
    "C": "Comercio",
    "O": "Outros",
    "TB": "Terreno baldio",
    "PE": "Ponto estrategico",
    "A": "Pendente para atualizacao",
    "REF": "Referencia do quarteirao",
}
TIPOS_NAO_CONTABILIZAVEIS = {"REF"}
MEDIA_PESSOAS_POR_RESIDENCIA = 2.93
FONTE_POPULACAO = "Fonte: IBGE Censo 2022"
CAMPOS_EDICAO_LOTE = {
    "logradouro": "Logradouro",
    "numero": "Numero",
    "sequencia": "Sequencia",
    "lado": "Lado",
    "tipo": "Tipo",
    "observacao": "Observacao",
}
ABREVIACOES_LOGRADOURO = {
    "r": "rua",
    "av": "avenida",
    "aven": "avenida",
    "rod": "rodovia",
    "rodv": "rodovia",
    "estr": "estrada",
    "tv": "travessa",
    "trav": "travessa",
    "prof": "professor",
    "profa": "professora",
    "dr": "doutor",
    "dra": "doutora",
    "sr": "senhor",
    "sra": "senhora",
    "cel": "coronel",
    "mal": "marechal",
    "pref": "prefeito",
    "pres": "presidente",
    "ver": "vereador",
    "dep": "deputado",
    "pe": "padre",
}
PREFIXOS_LOGRADOURO = {"rua", "avenida", "rodovia", "estrada", "travessa", "alameda", "viela"}
PALAVRAS_FRACAS_LOGRADOURO = PREFIXOS_LOGRADOURO | {
    "da",
    "de",
    "do",
    "das",
    "dos",
    "e",
    "sao",
    "santo",
    "santa",
    "jose",
    "joao",
    "maria",
    "senhor",
    "senhora",
    "professor",
    "professora",
    "doutor",
    "doutora",
    "padre",
    "coronel",
    "marechal",
    "prefeito",
    "presidente",
    "vereador",
    "deputado",
}


def _norm(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _normalizar_logradouro(value):
    text = _norm(value)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    tokens = [ABREVIACOES_LOGRADOURO.get(token, token) for token in text.split()]
    return " ".join(tokens)


def _sem_prefixo_logradouro(value):
    tokens = _normalizar_logradouro(value).split()
    while tokens and tokens[0] in PREFIXOS_LOGRADOURO:
        tokens.pop(0)
    return " ".join(tokens)


def _levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            custo = 0 if ca == cb else 1
            atual.append(min(atual[j - 1] + 1, anterior[j] + 1, anterior[j - 1] + custo))
        anterior = atual
    return anterior[-1]


def _similaridade_texto(a, b):
    a = str(a or "")
    b = str(b or "")
    if not a and not b:
        return 100
    tamanho = max(len(a), len(b), 1)
    return round((1 - (_levenshtein(a, b) / tamanho)) * 100)


def _similaridade_logradouro(a, b):
    norm_a = _normalizar_logradouro(a)
    norm_b = _normalizar_logradouro(b)
    if norm_a == norm_b:
        return 100, "normalizacao igual"
    score = _similaridade_texto(norm_a, norm_b)
    sem_prefixo = _similaridade_texto(_sem_prefixo_logradouro(a), _sem_prefixo_logradouro(b))
    return max(score, sem_prefixo), "nomes parecidos"


def _score_maximo_por_tamanho(a, b):
    maior = max(len(a or ""), len(b or ""), 1)
    menor = min(len(a or ""), len(b or ""))
    return round((menor / maior) * 100)


def _similaridade_item_logradouro(item_a, item_b):
    if item_a["normalizado"] == item_b["normalizado"]:
        return 100, "normalizacao igual"
    score = _similaridade_texto(item_a["normalizado"], item_b["normalizado"])
    sem_prefixo = _similaridade_texto(item_a["sem_prefixo"], item_b["sem_prefixo"])
    return max(score, sem_prefixo), "nomes parecidos"


def _chaves_candidato_logradouro(normalizado, sem_prefixo):
    chaves = set()
    if normalizado:
        chaves.add(f"norm:{normalizado}")
    if sem_prefixo:
        chaves.add(f"bare:{sem_prefixo}")
        if len(sem_prefixo) >= 4:
            chaves.add(f"prefix:{sem_prefixo[:4]}")
    for token in set(normalizado.split()) | set(sem_prefixo.split()):
        if len(token) >= 3 and token not in PALAVRAS_FRACAS_LOGRADOURO:
            chaves.add(f"token:{token}")
    return chaves


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _manual_origin_key():
    return f"rg-manual:{uuid.uuid4().hex}"


def _is_postgresql(conn):
    return getattr(conn, "backend", "sqlite") == "postgresql"


def _numeric_text_order(conn, expression):
    if _is_postgresql(conn):
        return (
            f"CAST(NULLIF(substring(CAST({expression} AS TEXT) "
            "FROM '^[0-9]+'), '') AS BIGINT)"
        )
    return f"CAST({expression} AS INTEGER)"


def _string_aggregate(conn, expression, separator=", ", distinct=False):
    if _is_postgresql(conn):
        distinct_sql = "DISTINCT " if distinct else ""
        cast_expression = f"CAST({expression} AS TEXT)"
        return (
            f"string_agg({distinct_sql}{cast_expression}, '{separator}' "
            f"ORDER BY {cast_expression})"
        )
    if distinct:
        return f"GROUP_CONCAT(DISTINCT {expression})"
    return f"GROUP_CONCAT({expression}, '{separator}')"


def _table_cols(conn, table):
    if _is_postgresql(conn):
        return {
            row["column_name"]
            for row in conn.execute(
                """SELECT column_name
                     FROM information_schema.columns
                    WHERE table_schema=current_schema()
                      AND table_name=?""",
                (table,),
            ).fetchall()
        }
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _contabilizavel(row):
    return (row.get("tipo") or "") not in TIPOS_NAO_CONTABILIZAVEIS


def ensure_schema(conn_or_path, base_dir=None):
    if not hasattr(conn_or_path, "execute") and not db_core.is_sqlite(conn_or_path):
        return
    close = not hasattr(conn_or_path, "execute")
    conn = db_core.connect(conn_or_path) if close else conn_or_path
    try:
        if _is_postgresql(conn):
            return
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS registro_geografico_quarteiroes (
                id_quarteirao INTEGER PRIMARY KEY AUTOINCREMENT,
                id_localidade INTEGER NOT NULL REFERENCES localidades(id_localidade),
                localidade TEXT NOT NULL,
                quarteirao TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                atualizado_por_usuario_id INTEGER,
                atualizado_por_usuario_nome TEXT,
                atualizado_por_em TEXT,
                UNIQUE(id_localidade, quarteirao)
            );

            CREATE TABLE IF NOT EXISTS registro_geografico_imoveis (
                id_imovel INTEGER PRIMARY KEY AUTOINCREMENT,
                id_quarteirao INTEGER NOT NULL REFERENCES registro_geografico_quarteiroes(id_quarteirao),
                ordem INTEGER,
                id_localidade INTEGER NOT NULL REFERENCES localidades(id_localidade),
                localidade TEXT NOT NULL,
                quarteirao TEXT NOT NULL,
                logradouro TEXT NOT NULL,
                numero TEXT NOT NULL DEFAULT 'SN',
                sequencia TEXT,
                lado TEXT,
                tipo TEXT,
                condominio INTEGER,
                observacao TEXT,
                data_atualizacao DATE,
                agentes_texto TEXT,
                busca_normalizada TEXT,
                chave_origem TEXT UNIQUE,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS registro_geografico_imovel_agentes (
                id_imovel INTEGER NOT NULL REFERENCES registro_geografico_imoveis(id_imovel) ON DELETE CASCADE,
                id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
                PRIMARY KEY(id_imovel, id_agente)
            );

            CREATE INDEX IF NOT EXISTS idx_rg_imoveis_localidade ON registro_geografico_imoveis(id_localidade, quarteirao);
            CREATE INDEX IF NOT EXISTS idx_rg_imoveis_logradouro ON registro_geografico_imoveis(logradouro);
            CREATE INDEX IF NOT EXISTS idx_rg_imoveis_tipo ON registro_geografico_imoveis(tipo);
            CREATE INDEX IF NOT EXISTS idx_rg_imoveis_data ON registro_geografico_imoveis(data_atualizacao);
            CREATE INDEX IF NOT EXISTS idx_rg_imoveis_quarteirao_ordem ON registro_geografico_imoveis(id_quarteirao, ordem, id_imovel);
            """
        )
        cols = _table_cols(conn, "registro_geografico_imoveis")
        if "ordem" not in cols:
            conn.execute("ALTER TABLE registro_geografico_imoveis ADD COLUMN ordem INTEGER")
        if "agentes_texto" not in cols:
            conn.execute("ALTER TABLE registro_geografico_imoveis ADD COLUMN agentes_texto TEXT")
        if "busca_normalizada" not in cols:
            conn.execute("ALTER TABLE registro_geografico_imoveis ADD COLUMN busca_normalizada TEXT")
        cols_quarteiroes = _table_cols(conn, "registro_geografico_quarteiroes")
        if "atualizado_por_usuario_id" not in cols_quarteiroes:
            conn.execute("ALTER TABLE registro_geografico_quarteiroes ADD COLUMN atualizado_por_usuario_id INTEGER")
        if "atualizado_por_usuario_nome" not in cols_quarteiroes:
            conn.execute("ALTER TABLE registro_geografico_quarteiroes ADD COLUMN atualizado_por_usuario_nome TEXT")
        if "atualizado_por_em" not in cols_quarteiroes:
            conn.execute("ALTER TABLE registro_geografico_quarteiroes ADD COLUMN atualizado_por_em TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rg_imoveis_ordem ON registro_geografico_imoveis(ordem, id_imovel)")
        if not conn.execute("SELECT 1 FROM registro_geografico_imoveis LIMIT 1").fetchone():
            _importar_csv_inicial(conn, base_dir)
        _preencher_ordem(conn)
        _preencher_busca_normalizada(conn)
        if close and conn.in_transaction:
            conn.commit()
    finally:
        if close:
            conn.close()


def _csv_inicial(base_dir):
    if not base_dir:
        return None
    base = Path(base_dir)
    candidatos = sorted(base.glob("Registro Geogr*.csv"))
    return candidatos[0] if candidatos else None


def _abrir_csv(path):
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                sample = f.read(2048)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;")
                except csv.Error:
                    dialect = csv.excel
                rows = list(csv.DictReader(f, dialect=dialect))
            return rows
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _parse_data(value):
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _data_br(value):
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return value


def _parse_int(value):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return int(float(value.replace(",", ".")))
    except ValueError:
        return None


def _quarteirao(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if text.replace(".0", "").isdigit():
        return str(int(float(text))).zfill(4)
    return text


def _quarteirao_display(value):
    text = str(value or "").strip()
    if text.replace(".0", "").isdigit():
        return str(int(float(text)))
    return text


def _chave(row, linha=None):
    if linha is not None:
        return f"rg-csv:{linha}"
    base = "|".join(
        str(row.get(k) or "").strip()
        for k in ("localidade", "quarteirao", "logradouro", "numero", "sequencia", "lado", "tipo", "observacao")
    )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _busca_normalizada(row):
    return _norm(
        " ".join(
            str(row.get(k) or "")
            for k in (
                "localidade",
                "quarteirao",
                "logradouro",
                "numero",
                "sequencia",
                "lado",
                "tipo",
                "observacao",
                "agentes_texto",
            )
        )
    )


def _preencher_busca_normalizada(conn):
    rows = conn.execute(
        """SELECT id_imovel, localidade, quarteirao, logradouro, numero, sequencia, lado,
                  tipo, observacao, agentes_texto
             FROM registro_geografico_imoveis
            WHERE busca_normalizada IS NULL OR busca_normalizada=''"""
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE registro_geografico_imoveis SET busca_normalizada=? WHERE id_imovel=?",
            (_busca_normalizada(dict(row)), row["id_imovel"]),
        )


def _preencher_ordem(conn):
    rows = conn.execute(
        """SELECT id_imovel, chave_origem
             FROM registro_geografico_imoveis
            WHERE ordem IS NULL OR ordem<=0
            ORDER BY id_imovel"""
    ).fetchall()
    if not rows:
        return
    max_ordem = conn.execute("SELECT COALESCE(MAX(ordem), 0) FROM registro_geografico_imoveis").fetchone()[0] or 0
    proxima = max_ordem + 1
    for row in rows:
        origem = str(row["chave_origem"] or "")
        ordem = None
        if origem.startswith("rg-csv:"):
            try:
                ordem = int(origem.split(":", 1)[1])
            except (TypeError, ValueError):
                ordem = None
        if not ordem:
            ordem = proxima
            proxima += 1
        conn.execute("UPDATE registro_geografico_imoveis SET ordem=? WHERE id_imovel=?", (ordem, row["id_imovel"]))


def _mapas(conn):
    localidades = {
        _norm(row["nome"]): {"id": row["id_localidade"], "nome": row["nome"]}
        for row in conn.execute("SELECT id_localidade, nome FROM localidades")
    }
    agentes = {
        _norm(row["nome"]): {"id": row["id_agente"], "nome": row["nome"]}
        for row in conn.execute("SELECT id_agente, nome FROM agentes")
    }
    return localidades, agentes


def _localidade_canonica(value):
    return normalizadores.normalizar_localidade(value) or str(value or "").strip()


def _split_agentes(texto):
    texto = str(texto or "").replace(";", ",")
    return [parte.strip() for parte in texto.split(",") if parte.strip()]


def _importar_csv_inicial(conn, base_dir):
    path = _csv_inicial(base_dir)
    if not path:
        return {"importados": 0, "arquivo": None}
    rows = _abrir_csv(path)
    localidades, agentes = _mapas(conn)
    ausentes = sorted(
        {
            str(r.get("Localidade") or "").strip()
            for r in rows
            if _norm(_localidade_canonica(r.get("Localidade"))) not in localidades
        }
    )
    if ausentes:
        raise ValueError("Localidades do Registro Geografico ausentes no banco: " + ", ".join(ausentes[:20]))

    agora = _now()
    quarteiroes = {}
    importados = 0
    with conn:
        for linha, raw in enumerate(rows, 1):
            loc = localidades[_norm(_localidade_canonica(raw.get("Localidade")))]
            q = _quarteirao(raw.get("Quarteirão") or raw.get("Quarteirao"))
            if not q:
                continue
            q_key = (loc["id"], q)
            if q_key not in quarteiroes:
                row_q = conn.execute(
                    "SELECT id_quarteirao FROM registro_geografico_quarteiroes WHERE id_localidade=? AND quarteirao=?",
                    q_key,
                ).fetchone()
                if row_q:
                    quarteiroes[q_key] = row_q["id_quarteirao"]
                else:
                    cur = conn.execute(
                        """INSERT INTO registro_geografico_quarteiroes
                           (id_localidade, localidade, quarteirao, criado_em, atualizado_em)
                           VALUES (?, ?, ?, ?, ?)""",
                        (loc["id"], loc["nome"], q, agora, agora),
                    )
                    quarteiroes[q_key] = cur.lastrowid
            tipo = str(raw.get("Tipo") or "").strip().upper() or None
            if tipo and tipo not in TIPOS:
                tipo = None
            numero = str(raw.get("Número") or raw.get("Numero") or "").strip() or "SN"
            agentes_texto = str(raw.get("Agentes") or "").strip()
            item = {
                "localidade": loc["nome"],
                "quarteirao": q,
                "logradouro": str(raw.get("Logradouro") or raw.get("Logradouros") or "").strip() or "Sem logradouro",
                "numero": numero,
                "sequencia": str(raw.get("Sequência") or raw.get("Sequencia") or "").strip(),
                "lado": str(raw.get("Lado") or "").strip(),
                "tipo": tipo,
                "observacao": str(raw.get("Observação") or raw.get("Observacao") or "").strip(),
                "agentes_texto": agentes_texto,
            }
            cur = conn.execute(
                """INSERT OR IGNORE INTO registro_geografico_imoveis
                   (id_quarteirao, ordem, id_localidade, localidade, quarteirao, logradouro, numero, sequencia, lado,
                    tipo, condominio, observacao, data_atualizacao, agentes_texto, busca_normalizada, chave_origem, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    quarteiroes[q_key],
                    linha,
                    loc["id"],
                    loc["nome"],
                    q,
                    item["logradouro"],
                    item["numero"],
                    item["sequencia"] or None,
                    item["lado"] or None,
                    item["tipo"],
                    _parse_int(raw.get("Condomínio") or raw.get("Condominio")),
                    item["observacao"] or None,
                    _parse_data(raw.get("Data atualização") or raw.get("Data atualizacao")),
                    agentes_texto or None,
                    _busca_normalizada(item),
                    _chave(item, linha),
                    agora,
                    agora,
                ),
            )
            if cur.rowcount:
                importados += 1
                id_imovel = cur.lastrowid
            else:
                id_imovel = conn.execute(
                    "SELECT id_imovel FROM registro_geografico_imoveis WHERE chave_origem=?",
                    (_chave(item, linha),),
                ).fetchone()["id_imovel"]
            for nome_agente in _split_agentes(agentes_texto):
                ag = agentes.get(_norm(nome_agente))
                if ag:
                    conn.execute(
                        "INSERT OR IGNORE INTO registro_geografico_imovel_agentes (id_imovel, id_agente) VALUES (?, ?)",
                        (id_imovel, ag["id"]),
                    )
    return {"importados": importados, "arquivo": str(path)}


def opcoes(db_path, base_dir=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        return {
            "localidades": [dict(r) for r in conn.execute("SELECT id_localidade, nome FROM localidades ORDER BY nome")],
            "agentes": [dict(r) for r in conn.execute("SELECT id_agente, nome FROM agentes WHERE COALESCE(ativo,1)=1 ORDER BY nome")],
            "tipos": [{"codigo": k, "nome": v} for k, v in TIPOS.items()],
        }
    finally:
        conn.close()


def quarteiroes_por_localidade(db_path, id_localidade, base_dir=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        ordem_numerica = _numeric_text_order(conn, "q.quarteirao")
        rows = conn.execute(
            f"""SELECT q.quarteirao,
                      SUM(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') NOT IN ('REF') THEN 1 ELSE 0 END) AS imoveis
                 FROM registro_geografico_quarteiroes q
                 LEFT JOIN registro_geografico_imoveis i ON i.id_quarteirao=q.id_quarteirao
                WHERE q.id_localidade=?
                GROUP BY q.id_quarteirao, q.quarteirao
                ORDER BY {ordem_numerica}, q.quarteirao""",
            (id_localidade,),
        ).fetchall()
        return [
            {
                "quarteirao": _quarteirao_display(row["quarteirao"]),
                "quarteirao_raw": row["quarteirao"],
                "imoveis": db_core.serialize_row(row)["imoveis"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def _where(filtros):
    where = []
    params = []
    busca = _norm(filtros.get("busca"))
    if busca:
        like = f"%{busca}%"
        where.append("i.busca_normalizada LIKE ?")
        params.append(like)
    if filtros.get("localidade"):
        localidades = filtros["localidade"]
        if not isinstance(localidades, (list, tuple)):
            localidades = [localidades]
        localidades = [str(item).strip() for item in localidades if str(item or "").strip()]
        if localidades:
            where.append(f"i.id_localidade IN ({','.join('?' for _ in localidades)})")
            params.extend(localidades)
    if filtros.get("quarteirao"):
        quarteiroes = filtros["quarteirao"]
        if not isinstance(quarteiroes, (list, tuple)):
            quarteiroes = [quarteiroes]
        quarteiroes = [_quarteirao(str(item).strip()) for item in quarteiroes if str(item or "").strip()]
        if quarteiroes:
            where.append(f"i.quarteirao IN ({','.join('?' for _ in quarteiroes)})")
            params.extend(quarteiroes)
    if filtros.get("tipo"):
        where.append("i.tipo=?")
        params.append(filtros["tipo"])
    if filtros.get("atualizacao") == "atualizados":
        where.append("i.data_atualizacao IS NOT NULL")
    elif filtros.get("atualizacao") == "pendentes":
        where.append("i.data_atualizacao IS NULL")
    if filtros.get("agente"):
        where.append("EXISTS (SELECT 1 FROM registro_geografico_imovel_agentes ia WHERE ia.id_imovel=i.id_imovel AND ia.id_agente=?)")
        params.append(filtros["agente"])
    return (" WHERE " + " AND ".join(where)) if where else "", params


def _where_lote(filtros):
    filtros = filtros or {}
    where = []
    params = []
    if filtros.get("localidade"):
        localidades = filtros["localidade"]
        if not isinstance(localidades, (list, tuple)):
            localidades = [localidades]
        localidades = [str(item).strip() for item in localidades if str(item or "").strip()]
        if localidades:
            where.append(f"id_localidade IN ({','.join('?' for _ in localidades)})")
            params.extend(localidades)
    if filtros.get("quarteirao"):
        quarteiroes = filtros["quarteirao"]
        if not isinstance(quarteiroes, (list, tuple)):
            quarteiroes = [quarteiroes]
        quarteiroes = [_quarteirao(str(item).strip()) for item in quarteiroes if str(item or "").strip()]
        if quarteiroes:
            where.append(f"quarteirao IN ({','.join('?' for _ in quarteiroes)})")
            params.extend(quarteiroes)
    return (" WHERE " + " AND ".join(where)) if where else "", params


def logradouros_similares(db_path, filtros=None, score_min=78, limite=80, base_dir=None):
    ensure_schema(db_path, base_dir)
    score_min = max(0, min(int(score_min or 78), 100))
    limite = max(1, min(int(limite or 80), 200))
    conn = db_core.connect(db_path)
    try:
        where, params = _where_lote(filtros or {})
        localidades_agg = _string_aggregate(conn, "localidade", ",", distinct=True)
        rows = conn.execute(
            f"""
            SELECT logradouro,
                   COUNT(*) AS imoveis,
                   COUNT(DISTINCT id_quarteirao) AS quarteiroes,
                   {localidades_agg} AS localidades
              FROM registro_geografico_imoveis
              {where}
             WHERE_TRIM
             GROUP BY logradouro
             ORDER BY COUNT(*) DESC, logradouro
            """.replace("WHERE_TRIM", ("AND" if where else "WHERE") + " TRIM(COALESCE(logradouro,''))<>''"),
            params,
        ).fetchall()
        itens = []
        for row in rows:
            logradouro = row["logradouro"] or ""
            normalizado = _normalizar_logradouro(logradouro)
            sem_prefixo = _sem_prefixo_logradouro(logradouro)
            itens.append(
                {
                    "logradouro": logradouro,
                    "normalizado": normalizado,
                    "sem_prefixo": sem_prefixo,
                    "imoveis": row["imoveis"] or 0,
                    "quarteiroes": row["quarteiroes"] or 0,
                    "localidades": sorted([item for item in str(row["localidades"] or "").split(",") if item]),
                }
            )
        indice = {}
        for idx, item in enumerate(itens):
            for chave in _chaves_candidato_logradouro(item["normalizado"], item["sem_prefixo"]):
                indice.setdefault(chave, []).append(idx)
        candidatos = set()
        for chave, bucket in indice.items():
            if len(bucket) > 320 and not chave.startswith(("norm:", "bare:")):
                continue
            for pos, idx_a in enumerate(bucket):
                for idx_b in bucket[pos + 1 :]:
                    candidatos.add((idx_a, idx_b) if idx_a < idx_b else (idx_b, idx_a))
        pares = []
        for idx_a, idx_b in candidatos:
            item_a = itens[idx_a]
            item_b = itens[idx_b]
            if item_a["normalizado"] != item_b["normalizado"]:
                maximo_possivel = max(
                    _score_maximo_por_tamanho(item_a["normalizado"], item_b["normalizado"]),
                    _score_maximo_por_tamanho(item_a["sem_prefixo"], item_b["sem_prefixo"]),
                )
                if maximo_possivel < score_min:
                    continue
            score, motivo = _similaridade_item_logradouro(item_a, item_b)
            if score < score_min:
                continue
            pares.append({"score": score, "motivo": motivo, "a": item_a, "b": item_b})
        pares.sort(key=lambda item: (-item["score"], -min(item["a"]["imoveis"], item["b"]["imoveis"]), item["a"]["logradouro"]))
        return {
            "pares": pares[:limite],
            "total_pares": len(pares),
            "total_logradouros": len(itens),
            "total_comparacoes": len(candidatos),
            "score_min": score_min,
            "limite": limite,
        }
    finally:
        conn.close()


def sugestoes_logradouros(db_path, busca="", id_localidade=None, limite=12, base_dir=None):
    ensure_schema(db_path, base_dir)
    termo = _normalizar_logradouro(busca)
    if len(termo) < 2:
        return {"sugestoes": [], "total": 0}
    limite = max(1, min(int(limite or 12), 30))
    loc_id = int(id_localidade) if str(id_localidade or "").strip().isdigit() else None
    conn = db_core.connect(db_path)
    try:
        localidades_agg = _string_aggregate(conn, "localidade", ",", distinct=True)
        rows = conn.execute(
            f"""
            SELECT logradouro,
                   COUNT(*) AS imoveis,
                   COUNT(DISTINCT id_quarteirao) AS quarteiroes,
                   {localidades_agg} AS localidades,
                   MAX(CASE WHEN id_localidade=? THEN 1 ELSE 0 END) AS mesma_localidade
              FROM registro_geografico_imoveis
             WHERE TRIM(COALESCE(logradouro,''))<>''
             GROUP BY logradouro
            """,
            (loc_id or 0,),
        ).fetchall()
        sugestoes = []
        for row in rows:
            logradouro = row["logradouro"] or ""
            normalizado = _normalizar_logradouro(logradouro)
            sem_prefixo = _sem_prefixo_logradouro(logradouro)
            if termo not in normalizado and termo not in sem_prefixo:
                continue
            inicio = normalizado.startswith(termo) or sem_prefixo.startswith(termo)
            sugestoes.append(
                {
                    "logradouro": logradouro,
                    "imoveis": row["imoveis"] or 0,
                    "quarteiroes": row["quarteiroes"] or 0,
                    "localidades": sorted([item for item in str(row["localidades"] or "").split(",") if item]),
                    "mesma_localidade": bool(row["mesma_localidade"]),
                    "score": (40 if row["mesma_localidade"] else 0) + (30 if inicio else 0) + min(row["imoveis"] or 0, 30),
                }
            )
        sugestoes.sort(key=lambda item: (-item["score"], -item["imoveis"], item["logradouro"].lower()))
        return {"sugestoes": sugestoes[:limite], "total": len(sugestoes)}
    finally:
        conn.close()


def _campo_lote(payload):
    campo = str((payload or {}).get("campo") or "logradouro").strip()
    if campo not in CAMPOS_EDICAO_LOTE:
        raise ValueError("Campo de edicao em lote invalido.")
    return campo


def _modo_lote(payload):
    modo = str((payload or {}).get("modo") or "exato").strip().lower()
    if modo not in {"exato", "contem"}:
        raise ValueError("Modo de substituicao invalido.")
    return modo


def _valor_campo_lote(campo, value):
    text = str(value or "").strip()
    if campo == "logradouro":
        if not text:
            raise ValueError("Logradouro nao pode ficar vazio.")
        return text
    if campo == "numero":
        return text or "SN"
    if campo == "tipo":
        text = text.upper()
        if text and text not in TIPOS:
            raise ValueError("Tipo de imovel invalido.")
        return text or None
    return text or None


def _texto_busca_lote(payload):
    busca = str((payload or {}).get("busca") or "")
    if not busca.strip():
        raise ValueError("Informe o texto que sera localizado.")
    return busca


def _match_lote(valor, busca, modo, case_sensitive=False):
    valor = str(valor or "")
    if not case_sensitive:
        valor_cmp = valor.lower()
        busca_cmp = busca.lower()
    else:
        valor_cmp = valor
        busca_cmp = busca
    if modo == "exato":
        return valor_cmp == busca_cmp
    return busca_cmp in valor_cmp


def _substituir_lote(valor, busca, novo, modo, case_sensitive=False):
    valor = str(valor or "")
    if modo == "exato":
        return novo
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.sub(re.escape(busca), novo, valor, flags=flags)


def _formatar_alteracao_lote(row, campo, antes, depois):
    return {
        "id_imovel": row["id_imovel"],
        "localidade": row["localidade"],
        "quarteirao": _quarteirao_display(row["quarteirao"]),
        "logradouro": row["logradouro"],
        "numero": row["numero"],
        "tipo": row["tipo"],
        "campo": campo,
        "campo_label": CAMPOS_EDICAO_LOTE[campo],
        "antes": antes or "",
        "depois": depois or "",
    }


def _calcular_substituicoes_lote(conn, payload, amostra_limite=150):
    payload = payload or {}
    campo = _campo_lote(payload)
    modo = _modo_lote(payload)
    busca = _texto_busca_lote(payload)
    novo = str(payload.get("novo") or "")
    case_sensitive = bool(payload.get("case_sensitive"))
    where, params = _where_lote(payload.get("filtros") or {})
    ordem_numerica = _numeric_text_order(conn, "quarteirao")
    rows = conn.execute(
        f"""
        SELECT id_imovel, id_localidade, localidade, quarteirao, logradouro, numero, sequencia,
               lado, tipo, observacao, agentes_texto
          FROM registro_geografico_imoveis
          {where}
         ORDER BY localidade, {ordem_numerica}, quarteirao, COALESCE(ordem, id_imovel), id_imovel
        """,
        params,
    ).fetchall()
    alteracoes = []
    amostra = []
    for row_raw in rows:
        row = dict(row_raw)
        antes = row.get(campo) or ""
        if not _match_lote(antes, busca, modo, case_sensitive):
            continue
        depois = _valor_campo_lote(campo, _substituir_lote(antes, busca, novo, modo, case_sensitive))
        if (row.get(campo) or None) == depois:
            continue
        row[campo] = depois
        alteracao = {
            "id_imovel": row["id_imovel"],
            "campo": campo,
            "depois": depois,
            "busca_normalizada": _busca_normalizada(row),
            "amostra": _formatar_alteracao_lote(row, campo, antes, depois),
        }
        alteracoes.append(alteracao)
        if len(amostra) < amostra_limite:
            amostra.append(alteracao["amostra"])
    return {
        "campo": campo,
        "campo_label": CAMPOS_EDICAO_LOTE[campo],
        "modo": modo,
        "total": len(alteracoes),
        "amostra": amostra,
        "alteracoes": alteracoes,
    }


def preview_substituicao_lote(db_path, payload, base_dir=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        dados = _calcular_substituicoes_lote(conn, payload)
        dados.pop("alteracoes", None)
        return dados
    finally:
        conn.close()


def aplicar_substituicao_lote(db_path, payload, base_dir=None, usuario_id=None, usuario_nome=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        dados = _calcular_substituicoes_lote(conn, payload)
        campo = dados["campo"]
        agora = _now()
        with conn:
            quarteiroes_atualizados = set()
            for item in dados["alteracoes"]:
                conn.execute(
                    f"""UPDATE registro_geografico_imoveis
                           SET {campo}=?, busca_normalizada=?, atualizado_em=?
                         WHERE id_imovel=?""",
                    (item["depois"], item["busca_normalizada"], agora, item["id_imovel"]),
                )
                row_q = conn.execute(
                    "SELECT id_quarteirao FROM registro_geografico_imoveis WHERE id_imovel=?",
                    (item["id_imovel"],),
                ).fetchone()
                if row_q:
                    quarteiroes_atualizados.add(row_q["id_quarteirao"])
            for id_quarteirao in quarteiroes_atualizados:
                _marcar_atualizacao_sistema(conn, id_quarteirao, usuario_id, usuario_nome, agora)
        return {
            "ok": True,
            "campo": campo,
            "campo_label": dados["campo_label"],
            "atualizados": len(dados["alteracoes"]),
            "amostra": dados["amostra"],
        }
    finally:
        conn.close()


def listar(db_path, filtros=None, limite=500, base_dir=None):
    filtros = filtros or {}
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        where, params = _where(filtros)
        total = conn.execute(f"SELECT COUNT(*) FROM registro_geografico_imoveis i{where}", params).fetchone()[0]
        limite_sql = "" if limite in (None, "", "todos") else " LIMIT ?"
        params_lista = list(params)
        if limite_sql:
            params_lista.append(max(1, min(int(limite or 500), 2000)))
        agentes_agg = _string_aggregate(conn, "a.nome")
        rows = conn.execute(
            f"""
            SELECT i.*,
                   {agentes_agg} AS agentes
              FROM registro_geografico_imoveis i
              LEFT JOIN registro_geografico_imovel_agentes ia ON ia.id_imovel=i.id_imovel
              LEFT JOIN agentes a ON a.id_agente=ia.id_agente
              {where}
             GROUP BY i.id_imovel
             ORDER BY COALESCE(i.ordem, i.id_imovel), i.id_imovel
             {limite_sql}
            """,
            params_lista,
        ).fetchall()
        return {"registros": [_formatar(dict(r)) for r in rows], "total": total, "totais": totais(conn, filtros)}
    finally:
        conn.close()


def totais(conn, filtros=None):
    where, params = _where(filtros or {})
    row = conn.execute(
        f"""
        SELECT SUM(CASE WHEN COALESCE(tipo,'') NOT IN ('REF') THEN 1 ELSE 0 END) AS imoveis,
               COUNT(DISTINCT id_quarteirao) AS quarteiroes,
               SUM(CASE WHEN data_atualizacao IS NOT NULL AND COALESCE(tipo,'') NOT IN ('REF') THEN 1 ELSE 0 END) AS atualizados,
               SUM(CASE WHEN tipo='PE' THEN 1 ELSE 0 END) AS pe,
               SUM(CASE WHEN tipo='TB' THEN 1 ELSE 0 END) AS tb,
               SUM(CASE WHEN COALESCE(tipo,'') NOT IN ('REF') THEN CASE WHEN COALESCE(condominio,0)>0 THEN condominio ELSE 1 END ELSE 0 END) AS imoveis_reais,
               SUM(CASE WHEN tipo='R' THEN CASE WHEN COALESCE(condominio,0)>0 THEN condominio ELSE 1 END ELSE 0 END) AS residencias_reais
          FROM registro_geografico_imoveis i
          {where}
        """,
        params,
    ).fetchone()
    data = db_core.serialize_row(row) if row else {}
    residencias_reais = data.get("residencias_reais") or 0
    data["media_pessoas_por_residencia"] = MEDIA_PESSOAS_POR_RESIDENCIA
    data["populacao_aproximada"] = round(residencias_reais * MEDIA_PESSOAS_POR_RESIDENCIA)
    data["fonte_populacao"] = FONTE_POPULACAO
    return data


def acompanhamento_atualizacoes(db_path, filtros=None, base_dir=None):
    ensure_schema(db_path, base_dir)
    filtros = filtros or {}
    conn = db_core.connect(db_path)
    try:
        where = []
        params = []
        localidades = filtros.get("localidade") or []
        if not isinstance(localidades, (list, tuple)):
            localidades = [localidades]
        localidades = [str(item).strip() for item in localidades if str(item or "").strip()]
        if localidades:
            where.append(f"q.id_localidade IN ({','.join('?' for _ in localidades)})")
            params.extend(localidades)
        busca = _norm(filtros.get("busca"))
        if busca:
            where.append("(LOWER(q.localidade) LIKE ? OR LOWER(q.quarteirao) LIKE ?)")
            params.extend([f"%{busca}%", f"%{busca}%"])
        if filtros.get("agente"):
            where.append(
                """EXISTS (
                    SELECT 1
                      FROM registro_geografico_imoveis ia_i
                      JOIN registro_geografico_imovel_agentes ia_a ON ia_a.id_imovel=ia_i.id_imovel
                     WHERE ia_i.id_quarteirao=q.id_quarteirao
                       AND ia_i.data_atualizacao IS NOT NULL
                       AND COALESCE(ia_i.tipo,'') <> 'REF'
                       AND ia_a.id_agente=?
                )"""
            )
            params.append(filtros["agente"])

        having = []
        having_params = []
        if filtros.get("d_ini"):
            having.append("MAX(CASE WHEN COALESCE(i.tipo,'') <> 'REF' THEN i.data_atualizacao END) >= ?")
            having_params.append(filtros["d_ini"])
        if filtros.get("d_fim"):
            having.append("MAX(CASE WHEN COALESCE(i.tipo,'') <> 'REF' THEN i.data_atualizacao END) <= ?")
            having_params.append(filtros["d_fim"])

        where_sql = " WHERE " + " AND ".join(where) if where else ""
        having_sql = " HAVING " + " AND ".join(having) if having else ""
        agentes_agg = _string_aggregate(
            conn,
            """CASE WHEN i.id_imovel IS NOT NULL
                           AND COALESCE(i.tipo,'') <> 'REF'
                           AND i.data_atualizacao IS NOT NULL
                      THEN a.nome END""",
            ",",
            distinct=True,
        )
        ordem_numerica = _numeric_text_order(conn, "q.quarteirao")
        rows = conn.execute(
            f"""
            SELECT q.id_localidade,
                   q.localidade,
                   q.quarteirao,
                   q.atualizado_por_usuario_nome AS atualizado_por_usuario,
                   q.atualizado_por_em AS atualizado_por_em,
                   SUM(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') <> 'REF' THEN 1 ELSE 0 END) AS linhas,
                   SUM(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') <> 'REF' AND i.data_atualizacao IS NOT NULL THEN 1 ELSE 0 END) AS atualizadas,
                   MAX(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') <> 'REF' THEN i.data_atualizacao END) AS ultima_atualizacao,
                   {agentes_agg} AS agentes,
                   SUM(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') <> 'REF' THEN CASE WHEN COALESCE(i.condominio,0)>0 THEN i.condominio ELSE 1 END ELSE 0 END) AS imoveis_reais,
                   SUM(CASE WHEN i.id_imovel IS NOT NULL AND i.tipo='R' THEN CASE WHEN COALESCE(i.condominio,0)>0 THEN i.condominio ELSE 1 END ELSE 0 END) AS residencias_reais
              FROM registro_geografico_quarteiroes q
              LEFT JOIN registro_geografico_imoveis i ON i.id_quarteirao=q.id_quarteirao
              LEFT JOIN registro_geografico_imovel_agentes ia ON ia.id_imovel=i.id_imovel
              LEFT JOIN agentes a ON a.id_agente=ia.id_agente
              {where_sql}
             GROUP BY q.id_quarteirao, q.id_localidade, q.localidade, q.quarteirao,
                      q.atualizado_por_usuario_nome, q.atualizado_por_em
             {having_sql}
             ORDER BY q.localidade, {ordem_numerica}, q.quarteirao
            """,
            params + having_params,
        ).fetchall()
    finally:
        conn.close()

    registros = []
    for row in rows:
        item = db_core.serialize_row(row)
        linhas = item["linhas"] or 0
        atualizadas = item["atualizadas"] or 0
        if not linhas:
            situacao = "sem_cadastro"
        elif not atualizadas:
            situacao = "pendente"
        elif atualizadas == linhas:
            situacao = "atualizado"
        else:
            situacao = "parcial"
        if filtros.get("situacao") and filtros["situacao"] != situacao:
            continue
        residencias = item["residencias_reais"] or 0
        registros.append({
            "id_localidade": item["id_localidade"],
            "localidade": item["localidade"],
            "quarteirao": _quarteirao_display(item["quarteirao"]),
            "quarteirao_raw": item["quarteirao"],
            "situacao": situacao,
            "linhas": linhas,
            "atualizadas": atualizadas,
            "percentual": round((atualizadas / linhas) * 100) if linhas else 0,
            "ultima_atualizacao": item["ultima_atualizacao"] or "",
            "atualizado_por_usuario": item["atualizado_por_usuario"] or "",
            "atualizado_por_em": item["atualizado_por_em"] or "",
            "agentes": item["agentes"] or "",
            "imoveis_reais": item["imoveis_reais"] or 0,
            "populacao_aproximada": round(residencias * MEDIA_PESSOAS_POR_RESIDENCIA),
        })

    totais_status = {"atualizado": 0, "parcial": 0, "pendente": 0, "sem_cadastro": 0}
    for item in registros:
        totais_status[item["situacao"]] += 1
    elegiveis = len(registros) - totais_status["sem_cadastro"]
    concluidos = totais_status["atualizado"]
    return {
        "registros": registros,
        "totais": {
            "quarteiroes": len(registros),
            **totais_status,
            "percentual_concluido": round((concluidos / elegiveis) * 100) if elegiveis else 0,
        },
    }


def resumo_mapa(db_path, base_dir=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        quarteiroes = {}
        ordem_numerica = _numeric_text_order(conn, "q.quarteirao")
        rows = conn.execute(
            f"""
            SELECT q.id_localidade,
                   q.localidade,
                   q.quarteirao,
                   SUM(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') NOT IN ('REF') THEN 1 ELSE 0 END) AS imoveis,
                   SUM(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') NOT IN ('REF') AND COALESCE(i.condominio,0)>0 THEN i.condominio
                            WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') NOT IN ('REF') THEN 1 ELSE 0 END) AS imoveis_reais,
                   SUM(CASE WHEN i.tipo='R' THEN CASE WHEN COALESCE(i.condominio,0)>0 THEN i.condominio ELSE 1 END ELSE 0 END) AS residencias_reais,
                   SUM(CASE WHEN i.data_atualizacao IS NOT NULL AND COALESCE(i.tipo,'') NOT IN ('REF') THEN 1 ELSE 0 END) AS atualizados
              FROM registro_geografico_quarteiroes q
              LEFT JOIN registro_geografico_imoveis i ON i.id_quarteirao=q.id_quarteirao
             GROUP BY q.id_quarteirao, q.id_localidade, q.localidade, q.quarteirao
             ORDER BY q.id_localidade, {ordem_numerica}, q.quarteirao
            """
        ).fetchall()
        for raw_row in rows:
            row = db_core.serialize_row(raw_row)
            residencias_reais = row["residencias_reais"] or 0
            display = _quarteirao_display(row["quarteirao"])
            chave = f"{row['id_localidade']}:{display}"
            quarteiroes[chave] = {
                "chave": chave,
                "id_localidade": row["id_localidade"],
                "localidade": row["localidade"],
                "quarteirao": display,
                "quarteirao_raw": row["quarteirao"],
                "imoveis": row["imoveis"] or 0,
                "imoveis_reais": row["imoveis_reais"] or 0,
                "residencias_reais": residencias_reais,
                "populacao_aproximada": round(residencias_reais * MEDIA_PESSOAS_POR_RESIDENCIA),
                "atualizados": row["atualizados"] or 0,
                "tipos": {},
            }

        tipo_rows = conn.execute(
            """
            SELECT q.id_localidade,
                   q.quarteirao,
                   COALESCE(i.tipo, '') AS tipo,
                   SUM(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') NOT IN ('REF') THEN 1 ELSE 0 END) AS imoveis,
                   SUM(CASE WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') NOT IN ('REF') AND COALESCE(i.condominio,0)>0 THEN i.condominio
                            WHEN i.id_imovel IS NOT NULL AND COALESCE(i.tipo,'') NOT IN ('REF') THEN 1 ELSE 0 END) AS imoveis_reais
              FROM registro_geografico_quarteiroes q
              LEFT JOIN registro_geografico_imoveis i ON i.id_quarteirao=q.id_quarteirao
             GROUP BY q.id_quarteirao, q.id_localidade, q.quarteirao, COALESCE(i.tipo, '')
            """
        ).fetchall()
        for raw_row in tipo_rows:
            row = db_core.serialize_row(raw_row)
            if not (row["imoveis"] or 0) or (row["tipo"] or "") in TIPOS_NAO_CONTABILIZAVEIS:
                continue
            tipo = row["tipo"] or ""
            chave = f"{row['id_localidade']}:{_quarteirao_display(row['quarteirao'])}"
            if chave not in quarteiroes:
                continue
            quarteiroes[chave]["tipos"][tipo or "sem_tipo"] = {
                "codigo": tipo,
                "label": TIPOS.get(tipo, "Sem tipo" if not tipo else tipo),
                "imoveis": row["imoveis"] or 0,
                "imoveis_reais": row["imoveis_reais"] or 0,
            }

        total = {
            "quarteiroes": len(quarteiroes),
            "imoveis": sum(item["imoveis"] for item in quarteiroes.values()),
            "imoveis_reais": sum(item["imoveis_reais"] for item in quarteiroes.values()),
            "residencias_reais": sum(item["residencias_reais"] for item in quarteiroes.values()),
            "populacao_aproximada": sum(item["populacao_aproximada"] for item in quarteiroes.values()),
        }
        return {
            "quarteiroes": quarteiroes,
            "total": total,
            "tipos": [{"codigo": codigo, "nome": nome} for codigo, nome in TIPOS.items()],
            "media_pessoas_por_residencia": MEDIA_PESSOAS_POR_RESIDENCIA,
            "fonte_populacao": FONTE_POPULACAO,
        }
    finally:
        conn.close()


def obter(db_path, id_imovel, base_dir=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        row = conn.execute("SELECT * FROM registro_geografico_imoveis WHERE id_imovel=?", (id_imovel,)).fetchone()
        if not row:
            return None
        data = _formatar(dict(row))
        data["agentes_ids"] = [
            r["id_agente"]
            for r in conn.execute(
                "SELECT id_agente FROM registro_geografico_imovel_agentes WHERE id_imovel=? ORDER BY id_agente",
                (id_imovel,),
            )
        ]
        return data
    finally:
        conn.close()


def quarteirao(db_path, id_localidade, quarteirao_numero, base_dir=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        q = _quarteirao(quarteirao_numero)
        cols_localidades = _table_cols(conn, "localidades")
        loc_select = "id_localidade, nome"
        if "cod_localidade" in cols_localidades:
            loc_select += ", cod_localidade"
        loc = conn.execute(f"SELECT {loc_select} FROM localidades WHERE id_localidade=?", (id_localidade,)).fetchone()
        if not loc:
            raise ValueError("Localidade nao encontrada no cadastro.")
        agentes_agg = _string_aggregate(conn, "a.nome")
        rows = conn.execute(
            f"""
            SELECT i.*,
                   {agentes_agg} AS agentes
              FROM registro_geografico_imoveis i
              LEFT JOIN registro_geografico_imovel_agentes ia ON ia.id_imovel=i.id_imovel
              LEFT JOIN agentes a ON a.id_agente=ia.id_agente
             WHERE i.id_localidade=? AND i.quarteirao=?
             GROUP BY i.id_imovel
             ORDER BY COALESCE(i.ordem, i.id_imovel), i.id_imovel
            """,
            (id_localidade, q),
        ).fetchall()
        registros = [_formatar(dict(r)) for r in rows]
        resumo = _resumo_quarteirao(registros)
        agentes_ids = []
        data_atualizacao = ""
        if registros:
            data_atualizacao = registros[0].get("data_atualizacao") or ""
            agentes_ids = [
                r["id_agente"]
                for r in conn.execute(
                    """SELECT DISTINCT ia.id_agente
                         FROM registro_geografico_imovel_agentes ia
                         JOIN registro_geografico_imoveis i ON i.id_imovel=ia.id_imovel
                        WHERE i.id_localidade=? AND i.quarteirao=?
                        ORDER BY ia.id_agente""",
                    (id_localidade, q),
                )
            ]
        return {
            "localidade": dict(loc),
            "quarteirao": _quarteirao_display(q),
            "quarteirao_raw": q,
            "registros": registros,
            "data_atualizacao": data_atualizacao,
            "data_atualizacao_br": _data_br(data_atualizacao),
            "agentes_ids": agentes_ids,
            "agentes": ", ".join({r.get("agentes") or "" for r in registros if r.get("agentes")}),
            "resumo": resumo,
            "data_emissao": datetime.now().strftime("%d-%m-%Y"),
        }
    finally:
        conn.close()


def _resumo_quarteirao(registros):
    tipos = {"R": "Residências", "C": "Comércios", "TB": "Terrenos baldios", "PE": "Pontos estratégicos", "O": "Outros"}
    resumo = []
    total_sem = 0
    total_com = 0
    residencias_com = 0
    for codigo, label in tipos.items():
        itens = [r for r in registros if (r.get("tipo") or "") == codigo]
        sem = len(itens)
        if codigo == "R":
            com = sum((r.get("condominio") or 0) if (r.get("condominio") or 0) > 0 else 1 for r in itens)
            residencias_com = com
        else:
            com = sem
        total_sem += sem
        total_com += com
        resumo.append({"codigo": codigo, "label": label, "sem_condominio": sem, "com_condominio": com})
    outros_codigos = [
        r for r in registros
        if (r.get("tipo") or "") not in tipos and _contabilizavel(r)
    ]
    if outros_codigos:
        sem = len(outros_codigos)
        com = sum((r.get("condominio") or 0) if (r.get("condominio") or 0) > 0 else 1 for r in outros_codigos)
        total_sem += sem
        total_com += com
        resumo.append({"codigo": "", "label": "Sem tipo", "sem_condominio": sem, "com_condominio": com})
    return {
        "linhas": resumo,
        "total_sem_condominio": total_sem,
        "total_com_condominio": total_com,
        "residencias_com_condominio": residencias_com,
        "media_pessoas_por_residencia": MEDIA_PESSOAS_POR_RESIDENCIA,
        "populacao_aproximada": round(residencias_com * MEDIA_PESSOAS_POR_RESIDENCIA),
        "fonte_populacao": FONTE_POPULACAO,
    }


def _dados_payload(conn, payload, atual=None):
    loc_id = int(payload.get("id_localidade") or (atual["id_localidade"] if atual else 0))
    loc = conn.execute("SELECT id_localidade, nome FROM localidades WHERE id_localidade=?", (loc_id,)).fetchone()
    if not loc:
        raise ValueError("Localidade nao encontrada no cadastro.")
    q = _quarteirao(payload.get("quarteirao") or (atual["quarteirao"] if atual else ""))
    if not q:
        raise ValueError("Informe o quarteirao.")
    logradouro = str(payload.get("logradouro") or "").strip()
    if not logradouro:
        raise ValueError("Informe o logradouro.")
    tipo = str(payload.get("tipo") or "").strip().upper() or None
    if tipo and tipo not in TIPOS:
        raise ValueError("Tipo de imovel invalido.")
    return {
        "loc": loc,
        "quarteirao": q,
        "logradouro": logradouro,
        "numero": str(payload.get("numero") or "SN").strip() or "SN",
        "sequencia": str(payload.get("sequencia") or "").strip() or None,
        "lado": str(payload.get("lado") or "").strip() or None,
        "tipo": tipo,
        "condominio": _parse_int(payload.get("condominio")),
        "observacao": str(payload.get("observacao") or "").strip() or None,
        "data_atualizacao": _parse_data(payload.get("data_atualizacao")),
    }


def _dados_linha_quarteirao(base, row):
    return {
        "loc": base["loc"],
        "quarteirao": base["quarteirao"],
        "logradouro": str(row.get("logradouro") or "").strip() or "Sem logradouro",
        "numero": str(row.get("numero") or "SN").strip() or "SN",
        "sequencia": str(row.get("sequencia") or "").strip() or None,
        "lado": str(row.get("lado") or "").strip() or None,
        "tipo": (str(row.get("tipo") or "").strip().upper() or None),
        "condominio": _parse_int(row.get("condominio")),
        "observacao": str(row.get("observacao") or "").strip() or None,
        "data_atualizacao": base["data_atualizacao"],
    }


def _garantir_quarteirao(conn, dados, agora):
    loc = dados["loc"]
    row = conn.execute(
        "SELECT id_quarteirao FROM registro_geografico_quarteiroes WHERE id_localidade=? AND quarteirao=?",
        (loc["id_localidade"], dados["quarteirao"]),
    ).fetchone()
    if row:
        return row["id_quarteirao"]
    return db_core.insert_and_get_id(
        conn,
        """INSERT INTO registro_geografico_quarteiroes
           (id_localidade, localidade, quarteirao, criado_em, atualizado_em)
           VALUES (?, ?, ?, ?, ?)""",
        (loc["id_localidade"], loc["nome"], dados["quarteirao"], agora, agora),
        "id_quarteirao",
    )


def _marcar_atualizacao_sistema(conn, id_quarteirao, usuario_id=None, usuario_nome=None, agora=None):
    if not usuario_nome:
        return
    momento = agora or _now()
    conn.execute(
        """UPDATE registro_geografico_quarteiroes
              SET atualizado_por_usuario_id=?, atualizado_por_usuario_nome=?, atualizado_por_em=?, atualizado_em=?
            WHERE id_quarteirao=?""",
        (usuario_id, str(usuario_nome).strip(), momento, momento, id_quarteirao),
    )


def _salvar_agentes_e_busca(conn, id_imovel, dados, agentes_ids):
    conn.execute("DELETE FROM registro_geografico_imovel_agentes WHERE id_imovel=?", (id_imovel,))
    nomes = []
    for id_agente in [int(x) for x in (agentes_ids or []) if str(x).strip().isdigit()]:
        ag = conn.execute("SELECT nome FROM agentes WHERE id_agente=?", (id_agente,)).fetchone()
        if ag:
            nomes.append(ag["nome"])
            conn.execute(
                """INSERT INTO registro_geografico_imovel_agentes (id_imovel, id_agente)
                   VALUES (?, ?)
                   ON CONFLICT (id_imovel, id_agente) DO NOTHING""",
                (id_imovel, id_agente),
            )
    busca_row = {
        "localidade": dados["loc"]["nome"],
        "quarteirao": dados["quarteirao"],
        "logradouro": dados["logradouro"],
        "numero": dados["numero"],
        "sequencia": dados["sequencia"],
        "lado": dados["lado"],
        "tipo": dados["tipo"],
        "observacao": dados["observacao"],
        "agentes_texto": ", ".join(nomes),
    }
    conn.execute(
        "UPDATE registro_geografico_imoveis SET agentes_texto=?, busca_normalizada=? WHERE id_imovel=?",
        (", ".join(nomes) or None, _busca_normalizada(busca_row), id_imovel),
    )


def criar(db_path, payload, base_dir=None, usuario_id=None, usuario_nome=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        dados = _dados_payload(conn, payload)
        agora = _now()
        after_id = payload.get("after_id")
        with conn:
            if after_id:
                row_after = conn.execute("SELECT ordem FROM registro_geografico_imoveis WHERE id_imovel=?", (after_id,)).fetchone()
                if not row_after:
                    raise ValueError("Linha de referencia nao encontrada.")
                ordem = int(row_after["ordem"] or 0) + 1
                conn.execute("UPDATE registro_geografico_imoveis SET ordem=ordem+1 WHERE ordem>=?", (ordem,))
            else:
                ordem = (conn.execute("SELECT COALESCE(MAX(ordem), 0) FROM registro_geografico_imoveis").fetchone()[0] or 0) + 1
            id_quarteirao = _garantir_quarteirao(conn, dados, agora)
            loc = dados["loc"]
            id_imovel = db_core.insert_and_get_id(
                conn,
                """INSERT INTO registro_geografico_imoveis
                   (id_quarteirao, ordem, id_localidade, localidade, quarteirao, logradouro, numero,
                    sequencia, lado, tipo, condominio, observacao, data_atualizacao,
                    chave_origem, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    id_quarteirao,
                    ordem,
                    loc["id_localidade"],
                    loc["nome"],
                    dados["quarteirao"],
                    dados["logradouro"],
                    dados["numero"],
                    dados["sequencia"],
                    dados["lado"],
                    dados["tipo"],
                    dados["condominio"],
                    dados["observacao"],
                    dados["data_atualizacao"],
                    _manual_origin_key(),
                    agora,
                    agora,
                ),
                "id_imovel",
            )
            _salvar_agentes_e_busca(conn, id_imovel, dados, payload.get("agentes_ids") or [])
            _marcar_atualizacao_sistema(conn, id_quarteirao, usuario_id, usuario_nome, agora)
        return obter(db_path, id_imovel, base_dir)
    finally:
        conn.close()


def salvar_quarteirao(db_path, payload, base_dir=None, usuario_id=None, usuario_nome=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        loc_id = int(payload.get("id_localidade") or 0)
        loc = conn.execute("SELECT id_localidade, nome FROM localidades WHERE id_localidade=?", (loc_id,)).fetchone()
        if not loc:
            raise ValueError("Localidade nao encontrada no cadastro.")
        q = _quarteirao(payload.get("quarteirao"))
        if not q:
            raise ValueError("Informe o quarteirao.")
        origem_loc_id = int(payload.get("origem_id_localidade") or loc_id)
        origem_q = _quarteirao(payload.get("origem_quarteirao") or q)
        linhas = payload.get("linhas") or []
        if not isinstance(linhas, list):
            raise ValueError("Linhas invalidas.")
        data_atualizacao = _parse_data(payload.get("data_atualizacao")) or None
        agentes_ids = payload.get("agentes_ids") or []
        deleted_ids = [int(x) for x in (payload.get("deleted_ids") or []) if str(x).strip().isdigit()]
        agora = _now()
        with conn:
            atuais = conn.execute(
                "SELECT id_imovel, ordem FROM registro_geografico_imoveis WHERE id_localidade=? AND quarteirao=? ORDER BY COALESCE(ordem,id_imovel)",
                (origem_loc_id, origem_q),
            ).fetchall()
            atuais_ids = {r["id_imovel"] for r in atuais}
            if deleted_ids:
                conn.executemany("DELETE FROM registro_geografico_imoveis WHERE id_imovel=?", [(i,) for i in deleted_ids if i in atuais_ids])
            atuais_validos = [r for r in atuais if r["id_imovel"] not in deleted_ids]
            base_ordem = min([r["ordem"] for r in atuais_validos if r["ordem"]] or [None])
            if base_ordem is None:
                base_ordem = (conn.execute("SELECT COALESCE(MAX(ordem), 0) FROM registro_geografico_imoveis").fetchone()[0] or 0) + 1

            novos = [row for row in linhas if not str(row.get("id_imovel") or "").strip()]
            if novos:
                conn.execute(
                    "UPDATE registro_geografico_imoveis SET ordem=ordem+? WHERE ordem>=? AND NOT (id_localidade=? AND quarteirao=?)",
                    (len(novos), base_ordem + len(atuais_validos), origem_loc_id, origem_q),
                )

            base = {"loc": loc, "quarteirao": q, "data_atualizacao": data_atualizacao}
            id_quarteirao = _garantir_quarteirao(conn, base, agora)
            ordem = base_ordem
            salvos = []
            for row in linhas:
                if str(row.get("_delete") or "") == "1":
                    continue
                dados = _dados_linha_quarteirao(base, row)
                tipo = dados["tipo"]
                if tipo and tipo not in TIPOS:
                    raise ValueError("Tipo de imovel invalido.")
                id_imovel = int(row.get("id_imovel") or 0) if str(row.get("id_imovel") or "").isdigit() else None
                if id_imovel and id_imovel not in atuais_ids:
                    raise ValueError("Linha de imovel nao pertence a este quarteirao.")
                if id_imovel:
                    conn.execute(
                        """UPDATE registro_geografico_imoveis
                              SET id_quarteirao=?, ordem=?, id_localidade=?, localidade=?, quarteirao=?, logradouro=?,
                                  numero=?, sequencia=?, lado=?, tipo=?, condominio=?, observacao=?,
                                  data_atualizacao=?, atualizado_em=?
                            WHERE id_imovel=?""",
                        (
                            id_quarteirao,
                            ordem,
                            loc["id_localidade"],
                            loc["nome"],
                            q,
                            dados["logradouro"],
                            dados["numero"],
                            dados["sequencia"],
                            dados["lado"],
                            dados["tipo"],
                            dados["condominio"],
                            dados["observacao"],
                            data_atualizacao,
                            agora,
                            id_imovel,
                        ),
                    )
                else:
                    id_imovel = db_core.insert_and_get_id(
                        conn,
                        """INSERT INTO registro_geografico_imoveis
                           (id_quarteirao, ordem, id_localidade, localidade, quarteirao, logradouro, numero,
                            sequencia, lado, tipo, condominio, observacao, data_atualizacao,
                            chave_origem, criado_em, atualizado_em)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            id_quarteirao,
                            ordem,
                            loc["id_localidade"],
                            loc["nome"],
                            q,
                            dados["logradouro"],
                            dados["numero"],
                            dados["sequencia"],
                            dados["lado"],
                            dados["tipo"],
                            dados["condominio"],
                            dados["observacao"],
                            data_atualizacao,
                            _manual_origin_key(),
                            agora,
                            agora,
                        ),
                        "id_imovel",
                    )
                _salvar_agentes_e_busca(conn, id_imovel, dados, agentes_ids)
                salvos.append(id_imovel)
                ordem += 1
            restantes = atuais_ids - set(deleted_ids) - set(salvos)
            if restantes:
                placeholders = ",".join("?" for _ in restantes)
                conn.execute(f"DELETE FROM registro_geografico_imoveis WHERE id_imovel IN ({placeholders})", tuple(restantes))
            if origem_loc_id != loc_id or origem_q != q:
                origem_row = conn.execute(
                    """SELECT q.id_quarteirao, COUNT(i.id_imovel) AS imoveis
                         FROM registro_geografico_quarteiroes q
                         LEFT JOIN registro_geografico_imoveis i ON i.id_quarteirao=q.id_quarteirao
                        WHERE q.id_localidade=? AND q.quarteirao=?
                        GROUP BY q.id_quarteirao""",
                    (origem_loc_id, origem_q),
                ).fetchone()
                if origem_row and not int(origem_row["imoveis"] or 0):
                    conn.execute(
                        "DELETE FROM registro_geografico_quarteiroes WHERE id_quarteirao=?",
                        (origem_row["id_quarteirao"],),
                    )
            _marcar_atualizacao_sistema(conn, id_quarteirao, usuario_id, usuario_nome, agora)
        return quarteirao(db_path, loc_id, q, base_dir)
    finally:
        conn.close()


def limpar_quarteirao(db_path, payload, base_dir=None, usuario_id=None, usuario_nome=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        loc_id = int(payload.get("id_localidade") or 0)
        loc = conn.execute("SELECT id_localidade, nome FROM localidades WHERE id_localidade=?", (loc_id,)).fetchone()
        if not loc:
            raise ValueError("Localidade nao encontrada no cadastro.")
        q = _quarteirao(payload.get("quarteirao"))
        if not q:
            raise ValueError("Informe o quarteirao.")
        agora = _now()
        with conn:
            row_q = conn.execute(
                "SELECT id_quarteirao FROM registro_geografico_quarteiroes WHERE id_localidade=? AND quarteirao=?",
                (loc_id, q),
            ).fetchone()
            if not row_q:
                row_q = {"id_quarteirao": _garantir_quarteirao(conn, {"loc": loc, "quarteirao": q}, agora)}
            ids = [
                row["id_imovel"]
                for row in conn.execute(
                    "SELECT id_imovel FROM registro_geografico_imoveis WHERE id_localidade=? AND quarteirao=?",
                    (loc_id, q),
                )
            ]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(
                    f"DELETE FROM registro_geografico_imovel_agentes WHERE id_imovel IN ({placeholders})",
                    tuple(ids),
                )
                conn.execute(
                    f"DELETE FROM registro_geografico_imoveis WHERE id_imovel IN ({placeholders})",
                    tuple(ids),
                )
            conn.execute(
                "UPDATE registro_geografico_quarteiroes SET atualizado_em=? WHERE id_quarteirao=?",
                (agora, row_q["id_quarteirao"]),
            )
            _marcar_atualizacao_sistema(conn, row_q["id_quarteirao"], usuario_id, usuario_nome, agora)
        dados = quarteirao(db_path, loc_id, q, base_dir)
        dados["removidos"] = len(ids)
        return dados
    finally:
        conn.close()


def excluir_quarteirao(db_path, payload, base_dir=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        loc_id = int(payload.get("id_localidade") or 0)
        loc = conn.execute("SELECT id_localidade, nome FROM localidades WHERE id_localidade=?", (loc_id,)).fetchone()
        if not loc:
            raise ValueError("Localidade nao encontrada no cadastro.")
        q = _quarteirao(payload.get("quarteirao"))
        if not q:
            raise ValueError("Informe o quarteirao.")
        with conn:
            row_q = conn.execute(
                "SELECT id_quarteirao FROM registro_geografico_quarteiroes WHERE id_localidade=? AND quarteirao=?",
                (loc_id, q),
            ).fetchone()
            if not row_q:
                raise ValueError("Quarteirao nao encontrado no cadastro.")
            ids = [
                row["id_imovel"]
                for row in conn.execute(
                    "SELECT id_imovel FROM registro_geografico_imoveis WHERE id_quarteirao=?",
                    (row_q["id_quarteirao"],),
                )
            ]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(
                    f"DELETE FROM registro_geografico_imovel_agentes WHERE id_imovel IN ({placeholders})",
                    tuple(ids),
                )
                conn.execute(
                    f"DELETE FROM registro_geografico_imoveis WHERE id_imovel IN ({placeholders})",
                    tuple(ids),
                )
            conn.execute(
                "DELETE FROM registro_geografico_quarteiroes WHERE id_quarteirao=?",
                (row_q["id_quarteirao"],),
            )
        return {
            "localidade": dict(loc),
            "quarteirao": _quarteirao_display(q),
            "quarteirao_raw": q,
            "removidos": len(ids),
        }
    finally:
        conn.close()


def salvar(db_path, id_imovel, payload, base_dir=None, usuario_id=None, usuario_nome=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        atual = conn.execute("SELECT * FROM registro_geografico_imoveis WHERE id_imovel=?", (id_imovel,)).fetchone()
        if not atual:
            raise ValueError("Imovel do Registro Geografico nao encontrado.")
        dados = _dados_payload(conn, payload, atual)
        agora = _now()
        with conn:
            id_quarteirao = _garantir_quarteirao(conn, dados, agora)
            loc = dados["loc"]
            conn.execute(
                """UPDATE registro_geografico_imoveis
                      SET id_quarteirao=?, id_localidade=?, localidade=?, quarteirao=?, logradouro=?,
                          numero=?, sequencia=?, lado=?, tipo=?, condominio=?, observacao=?,
                          data_atualizacao=?, atualizado_em=?
                    WHERE id_imovel=?""",
                (
                    id_quarteirao,
                    loc["id_localidade"],
                    loc["nome"],
                    dados["quarteirao"],
                    dados["logradouro"],
                    dados["numero"],
                    dados["sequencia"],
                    dados["lado"],
                    dados["tipo"],
                    dados["condominio"],
                    dados["observacao"],
                    dados["data_atualizacao"],
                    agora,
                    id_imovel,
                ),
            )
            _salvar_agentes_e_busca(conn, id_imovel, dados, payload.get("agentes_ids") or [])
            _marcar_atualizacao_sistema(conn, id_quarteirao, usuario_id, usuario_nome, agora)
        return obter(db_path, id_imovel, base_dir)
    finally:
        conn.close()


def excluir(db_path, id_imovel, base_dir=None):
    ensure_schema(db_path, base_dir)
    conn = db_core.connect(db_path)
    try:
        with conn:
            row = conn.execute("SELECT id_imovel, ordem FROM registro_geografico_imoveis WHERE id_imovel=?", (id_imovel,)).fetchone()
            if not row:
                raise ValueError("Imovel do Registro Geografico nao encontrado.")
            conn.execute("DELETE FROM registro_geografico_imoveis WHERE id_imovel=?", (id_imovel,))
            if row["ordem"]:
                conn.execute("UPDATE registro_geografico_imoveis SET ordem=ordem-1 WHERE ordem>?", (row["ordem"],))
        return True
    finally:
        conn.close()


def _formatar(row):
    row = db_core.serialize_row(row)
    row["tipo_label"] = TIPOS.get(row.get("tipo") or "", row.get("tipo") or "")
    row["condominio"] = row.get("condominio") or 0
    row["agentes"] = row.get("agentes") or row.get("agentes_texto") or ""
    row["quarteirao_raw"] = row.get("quarteirao") or ""
    row["quarteirao"] = _quarteirao_display(row.get("quarteirao"))
    return row
