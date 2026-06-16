import csv
import hashlib
import sqlite3
import unicodedata
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
}
MEDIA_PESSOAS_POR_RESIDENCIA = 2.93
FONTE_POPULACAO = "Fonte: IBGE Censo 2022"


def _norm(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _table_cols(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema(conn_or_path, base_dir=None):
    close = False
    if isinstance(conn_or_path, (str, bytes, Path)):
        conn = db_core.connect(str(conn_or_path))
        close = True
    else:
        conn = conn_or_path
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS registro_geografico_quarteiroes (
                id_quarteirao INTEGER PRIMARY KEY AUTOINCREMENT,
                id_localidade INTEGER NOT NULL REFERENCES localidades(id_localidade),
                localidade TEXT NOT NULL,
                quarteirao TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
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
            """
        )
        cols = _table_cols(conn, "registro_geografico_imoveis")
        if "ordem" not in cols:
            conn.execute("ALTER TABLE registro_geografico_imoveis ADD COLUMN ordem INTEGER")
        if "agentes_texto" not in cols:
            conn.execute("ALTER TABLE registro_geografico_imoveis ADD COLUMN agentes_texto TEXT")
        if "busca_normalizada" not in cols:
            conn.execute("ALTER TABLE registro_geografico_imoveis ADD COLUMN busca_normalizada TEXT")
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
        rows = conn.execute(
            """SELECT quarteirao, COUNT(*) AS imoveis
                 FROM registro_geografico_imoveis
                WHERE id_localidade=?
                GROUP BY quarteirao
                ORDER BY CAST(quarteirao AS INTEGER), quarteirao""",
            (id_localidade,),
        ).fetchall()
        return [
            {"quarteirao": _quarteirao_display(row["quarteirao"]), "quarteirao_raw": row["quarteirao"], "imoveis": row["imoveis"]}
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
        where.append("i.id_localidade=?")
        params.append(filtros["localidade"])
    if filtros.get("quarteirao"):
        where.append("i.quarteirao=?")
        params.append(_quarteirao(filtros["quarteirao"]))
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
        rows = conn.execute(
            f"""
            SELECT i.*,
                   GROUP_CONCAT(a.nome, ', ') AS agentes
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
        SELECT COUNT(*) AS imoveis,
               COUNT(DISTINCT id_quarteirao) AS quarteiroes,
               SUM(CASE WHEN data_atualizacao IS NOT NULL THEN 1 ELSE 0 END) AS atualizados,
               SUM(CASE WHEN tipo='PE' THEN 1 ELSE 0 END) AS pe,
               SUM(CASE WHEN tipo='TB' THEN 1 ELSE 0 END) AS tb,
               SUM(CASE WHEN COALESCE(condominio,0)>0 THEN condominio ELSE 1 END) AS imoveis_reais
          FROM registro_geografico_imoveis i
          {where}
        """,
        params,
    ).fetchone()
    data = dict(row) if row else {}
    imoveis_reais = data.get("imoveis_reais") or 0
    data["media_pessoas_por_residencia"] = MEDIA_PESSOAS_POR_RESIDENCIA
    data["populacao_aproximada"] = round(imoveis_reais * MEDIA_PESSOAS_POR_RESIDENCIA)
    data["fonte_populacao"] = FONTE_POPULACAO
    return data


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
        loc = conn.execute("SELECT id_localidade, nome FROM localidades WHERE id_localidade=?", (id_localidade,)).fetchone()
        if not loc:
            raise ValueError("Localidade nao encontrada no cadastro.")
        rows = conn.execute(
            """
            SELECT i.*,
                   GROUP_CONCAT(a.nome, ', ') AS agentes
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
    for codigo, label in tipos.items():
        itens = [r for r in registros if (r.get("tipo") or "") == codigo]
        sem = len(itens)
        if codigo == "R":
            com = sum((r.get("condominio") or 0) if (r.get("condominio") or 0) > 0 else 1 for r in itens)
        else:
            com = sem
        total_sem += sem
        total_com += com
        resumo.append({"codigo": codigo, "label": label, "sem_condominio": sem, "com_condominio": com})
    outros_codigos = [r for r in registros if (r.get("tipo") or "") not in tipos]
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
        "media_pessoas_por_residencia": MEDIA_PESSOAS_POR_RESIDENCIA,
        "populacao_aproximada": round(total_com * MEDIA_PESSOAS_POR_RESIDENCIA),
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
    cur = conn.execute(
        """INSERT INTO registro_geografico_quarteiroes
           (id_localidade, localidade, quarteirao, criado_em, atualizado_em)
           VALUES (?, ?, ?, ?, ?)""",
        (loc["id_localidade"], loc["nome"], dados["quarteirao"], agora, agora),
    )
    return cur.lastrowid


def _salvar_agentes_e_busca(conn, id_imovel, dados, agentes_ids):
    conn.execute("DELETE FROM registro_geografico_imovel_agentes WHERE id_imovel=?", (id_imovel,))
    nomes = []
    for id_agente in [int(x) for x in (agentes_ids or []) if str(x).strip().isdigit()]:
        ag = conn.execute("SELECT nome FROM agentes WHERE id_agente=?", (id_agente,)).fetchone()
        if ag:
            nomes.append(ag["nome"])
            conn.execute(
                "INSERT OR IGNORE INTO registro_geografico_imovel_agentes (id_imovel, id_agente) VALUES (?, ?)",
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


def criar(db_path, payload, base_dir=None):
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
            cur = conn.execute(
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
                    f"rg-manual:{agora}:{ordem}",
                    agora,
                    agora,
                ),
            )
            id_imovel = cur.lastrowid
            _salvar_agentes_e_busca(conn, id_imovel, dados, payload.get("agentes_ids") or [])
        return obter(db_path, id_imovel, base_dir)
    finally:
        conn.close()


def salvar_quarteirao(db_path, payload, base_dir=None):
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
                (loc_id, q),
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
                    (len(novos), base_ordem + len(atuais_validos), loc_id, q),
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
                    cur = conn.execute(
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
                            f"rg-manual:{agora}:{ordem}",
                            agora,
                            agora,
                        ),
                    )
                    id_imovel = cur.lastrowid
                _salvar_agentes_e_busca(conn, id_imovel, dados, agentes_ids)
                salvos.append(id_imovel)
                ordem += 1
            restantes = atuais_ids - set(deleted_ids) - set(salvos)
            if restantes:
                placeholders = ",".join("?" for _ in restantes)
                conn.execute(f"DELETE FROM registro_geografico_imoveis WHERE id_imovel IN ({placeholders})", tuple(restantes))
        return quarteirao(db_path, loc_id, q, base_dir)
    finally:
        conn.close()


def salvar(db_path, id_imovel, payload, base_dir=None):
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
    row["tipo_label"] = TIPOS.get(row.get("tipo") or "", row.get("tipo") or "")
    row["condominio"] = row.get("condominio") or 0
    row["agentes"] = row.get("agentes") or row.get("agentes_texto") or ""
    row["quarteirao_raw"] = row.get("quarteirao") or ""
    row["quarteirao"] = _quarteirao_display(row.get("quarteirao"))
    return row
