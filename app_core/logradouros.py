"""Cadastro oficial de logradouros e importacao segura de CSV.

O cadastro conserva cada ``id_logr`` da fonte municipal. Nomes repetidos sao
esperados: representam trechos diferentes de uma mesma rua e nao devem ser
fundidos durante a importacao.
"""

import csv
import hashlib
import io
import unicodedata
from datetime import datetime

from app_core import db as db_core
from app_core import enderecos as enderecos_core


TABLE = "logradouros_oficiais"
ENDERECOS_TABLE = "enderecos_normalizados"
VINCULOS_TABLE = "visitas_enderecos_normalizados"
REQUIRED_COLUMNS = {"nome", "localidade", "id_logr"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _text(value):
    return " ".join(str(value or "").strip().split())


def normalizar_nome(value):
    """Chave de comparacao, sem alterar a grafia oficial exibida."""
    text = unicodedata.normalize("NFKD", _text(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.replace(".", " ").replace("-", " ").split())


def normalizar_logradouro(value):
    """Chave comum usada na conciliacao, inclusive para abreviacoes."""
    return enderecos_core.normalizar_logradouro(value)


def _is_postgresql(conn):
    return getattr(conn, "backend", "sqlite") == "postgresql"


def _ativo_verdadeiro_sql(conn):
    """Expressao SQL compativel com a coluna ativa de cada backend."""
    return "ativo=TRUE" if _is_postgresql(conn) else "ativo=1"


def _ativo_verdadeiro_valor(conn):
    return True if _is_postgresql(conn) else 1


def ensure_schema(target):
    conn = db_core.connect(target)
    try:
        if _is_postgresql(conn):
            return
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                id_logradouro TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                nome_normalizado TEXT NOT NULL,
                localidade TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                origem_hash TEXT NOT NULL,
                importado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_logradouros_nome_normalizado
                ON {TABLE}(nome_normalizado);
            CREATE INDEX IF NOT EXISTS idx_logradouros_ativo_nome
                ON {TABLE}(ativo, nome);

            CREATE TABLE IF NOT EXISTS {ENDERECOS_TABLE} (
                id_endereco INTEGER PRIMARY KEY AUTOINCREMENT,
                chave_endereco TEXT NOT NULL UNIQUE,
                logradouro_normalizado TEXT NOT NULL,
                logradouro_oficial TEXT NOT NULL,
                numero_normalizado TEXT NOT NULL,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                confirmado_por TEXT
            );
            CREATE TABLE IF NOT EXISTS {VINCULOS_TABLE} (
                id_visita TEXT PRIMARY KEY,
                id_endereco INTEGER NOT NULL REFERENCES {ENDERECOS_TABLE}(id_endereco),
                logradouro_bruto TEXT,
                numero_bruto TEXT,
                confirmado_em TEXT NOT NULL,
                confirmado_por TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_visitas_enderecos_id_endereco
                ON {VINCULOS_TABLE}(id_endereco);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _catalogo_por_nome(conn):
    ativo = _ativo_verdadeiro_sql(conn)
    catalogo = {}
    for row in conn.execute(
        f"SELECT id_logradouro, nome FROM {TABLE} WHERE {ativo} ORDER BY nome, id_logradouro"
    ):
        chave = normalizar_logradouro(row["nome"])
        if chave:
            catalogo.setdefault(chave, []).append(dict(row))
    return catalogo


def _visitas_positivas_sem_vinculo(conn):
    return conn.execute(
        f"""
        SELECT v.id_visita, v.logradouro, v.numero, v.data, v.tipo,
               COALESCE(l.nome, v.localidade) AS localidade, v.quarteirao
          FROM visitas v
          LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
          LEFT JOIN {VINCULOS_TABLE} ve ON ve.id_visita=v.id_visita
         WHERE ve.id_visita IS NULL
           AND TRIM(COALESCE(v.logradouro, ''))<>''
           AND EXISTS (
               SELECT 1
                 FROM coletas c
                 JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
                WHERE c.id_visita=v.id_visita
                  AND (COALESCE(rl.aegypt_larvas,0) + COALESCE(rl.aegypt_pupas,0) +
                       COALESCE(rl.aegypt_exuvias,0) + COALESCE(rl.aegypt_adulto,0)) > 0
           )
         ORDER BY v.data DESC, v.id_visita DESC
        """
    ).fetchall()


def previa_visitas_positivas(target, limite=100):
    """Agrupa enderecos positivos ainda sem vinculo, somente para revisao."""
    ensure_schema(target)
    try:
        limite = max(1, min(int(limite or 100), 300))
    except (TypeError, ValueError):
        limite = 100
    conn = db_core.connect(target)
    try:
        catalogo = _catalogo_por_nome(conn)
        grupos = {}
        for row in _visitas_positivas_sem_vinculo(conn):
            logradouro = str(row["logradouro"] or "").strip()
            numero = str(row["numero"] or "").strip()
            chave_logradouro = normalizar_logradouro(logradouro)
            chave_numero = enderecos_core.normalizar_numero(numero)
            chave_comparacao = f"{chave_logradouro}\x1f{chave_numero}"
            grupo = grupos.setdefault(
                chave_comparacao,
                {
                    "chave": hashlib.sha256(chave_comparacao.encode("utf-8")).hexdigest(),
                    "logradouro_normalizado": chave_logradouro,
                    "numero_normalizado": chave_numero,
                    "enderecos_informados": set(),
                    "visitas": [],
                    "localidades": set(),
                    "quarteiroes": set(),
                },
            )
            grupo["enderecos_informados"].add(
                f"{logradouro}{', ' + numero if numero else ''}"
            )
            grupo["visitas"].append(str(row["id_visita"]))
            if row["localidade"]:
                grupo["localidades"].add(str(row["localidade"]))
            if row["quarteirao"] not in (None, ""):
                grupo["quarteiroes"].add(str(row["quarteirao"]))

        resultado = []
        for grupo in grupos.values():
            candidatos = catalogo.get(grupo["logradouro_normalizado"], [])
            nomes = sorted({item["nome"] for item in candidatos}, key=str.casefold)
            if not grupo["numero_normalizado"]:
                situacao = "sem_numero"
            elif not candidatos:
                situacao = "nao_encontrado"
            else:
                situacao = "pronto_para_revisar"
            resultado.append(
                {
                    "chave": grupo["chave"],
                    "logradouro_normalizado": grupo["logradouro_normalizado"],
                    "numero_normalizado": grupo["numero_normalizado"],
                    "enderecos_informados": sorted(grupo["enderecos_informados"], key=str.casefold),
                    "visitas": sorted(grupo["visitas"]),
                    "quantidade_visitas": len(grupo["visitas"]),
                    "localidades": sorted(grupo["localidades"], key=str.casefold),
                    "quarteiroes": sorted(grupo["quarteiroes"]),
                    "nome_oficial": nomes[0] if len(nomes) == 1 else None,
                    "trechos_oficiais": len(candidatos),
                    "situacao": situacao,
                }
            )
        resultado.sort(
            key=lambda item: (-item["quantidade_visitas"], item["enderecos_informados"][0].casefold())
        )
        return {
            "grupos": resultado[:limite],
            "total_grupos": len(resultado),
            "total_visitas": sum(item["quantidade_visitas"] for item in resultado),
            "catalogo_disponivel": bool(catalogo),
            "limite": limite,
        }
    finally:
        conn.close()


def confirmar_grupo_visitas_positivas(target, chave, nome_oficial, confirmado_por=None):
    """Cria o endereco canonico e vincula apenas o grupo explicitamente aprovado."""
    previa = previa_visitas_positivas(target, limite=300)
    grupo = next((item for item in previa["grupos"] if item["chave"] == str(chave or "")), None)
    if not grupo:
        raise ValueError("O grupo nao esta mais pendente de revisao.")
    if grupo["situacao"] != "pronto_para_revisar":
        raise ValueError("Somente grupos com rua oficial e numero informado podem ser confirmados.")
    if nome_oficial != grupo["nome_oficial"]:
        raise ValueError("A sugestao oficial mudou; atualize a previa antes de confirmar.")

    conn = db_core.connect(target)
    try:
        agora = _now()
        chave_endereco = grupo["chave"]
        existente = conn.execute(
            f"SELECT id_endereco FROM {ENDERECOS_TABLE} WHERE chave_endereco=?",
            (chave_endereco,),
        ).fetchone()
        if existente:
            id_endereco = existente["id_endereco"]
            conn.execute(
                f"UPDATE {ENDERECOS_TABLE} SET logradouro_oficial=?, atualizado_em=?, confirmado_por=? WHERE id_endereco=?",
                (nome_oficial, agora, confirmado_por, id_endereco),
            )
        else:
            id_endereco = db_core.insert_and_get_id(
                conn,
                f"""INSERT INTO {ENDERECOS_TABLE}
                       (chave_endereco,logradouro_normalizado,logradouro_oficial,numero_normalizado,
                        criado_em,atualizado_em,confirmado_por)
                    VALUES (?,?,?,?,?,?,?)""",
                (
                    chave_endereco, grupo["logradouro_normalizado"], nome_oficial,
                    grupo["numero_normalizado"], agora, agora, confirmado_por,
                ),
                "id_endereco",
            )
        rows = conn.execute(
            f"SELECT id_visita, logradouro, numero FROM visitas WHERE id_visita IN ({','.join('?' * len(grupo['visitas']))})",
            grupo["visitas"],
        ).fetchall()
        conn.executemany(
            f"""INSERT INTO {VINCULOS_TABLE}
                   (id_visita,id_endereco,logradouro_bruto,numero_bruto,confirmado_em,confirmado_por)
                VALUES (?,?,?,?,?,?)""",
            [
                (row["id_visita"], id_endereco, row["logradouro"], row["numero"], agora, confirmado_por)
                for row in rows
            ],
        )
        conn.commit()
        return {"id_endereco": id_endereco, "nome_oficial": nome_oficial, "numero": grupo["numero_normalizado"], "visitas_vinculadas": len(rows)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _decode_csv(content):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Nao foi possivel ler o CSV enviado.")


def _parse_csv(content):
    if not content:
        raise ValueError("O arquivo CSV esta vazio.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("O CSV excede o limite de 5 MB.")
    text = _decode_csv(content)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    columns = {str(name or "").strip().casefold() for name in reader.fieldnames or []}
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError("CSV sem coluna(s) obrigatoria(s): " + ", ".join(sorted(missing)))

    records = []
    ids = set()
    for number, raw in enumerate(reader, start=2):
        row = {str(key or "").strip().casefold(): value for key, value in raw.items()}
        identifier = _text(row.get("id_logr"))
        name = _text(row.get("nome"))
        locality = _text(row.get("localidade"))
        if not identifier or not name or not locality:
            raise ValueError(f"Linha {number}: id_logr, nome e localidade sao obrigatorios.")
        if identifier in ids:
            raise ValueError(f"Linha {number}: id_logr repetido no arquivo ({identifier}).")
        ids.add(identifier)
        normalized = normalizar_nome(name)
        if not normalized:
            raise ValueError(f"Linha {number}: nome invalido.")
        fingerprint = hashlib.sha256(
            f"{identifier}\x1f{name}\x1f{locality}".encode("utf-8")
        ).hexdigest()
        records.append(
            {
                "id_logradouro": identifier,
                "nome": name,
                "nome_normalizado": normalized,
                "localidade": locality,
                "origem_hash": fingerprint,
            }
        )
    if not records:
        raise ValueError("O CSV nao contem logradouros.")
    return records


def resumo(target):
    ensure_schema(target)
    conn = db_core.connect(target)
    try:
        ativo = _ativo_verdadeiro_sql(conn)
        row = conn.execute(
            f"""SELECT COUNT(*) AS trechos,
                       COUNT(DISTINCT nome_normalizado) AS nomes_normalizados,
                       COUNT(DISTINCT localidade) AS localidades,
                       MAX(importado_em) AS ultima_importacao
                  FROM {TABLE} WHERE {ativo}"""
        ).fetchone()
        return db_core.serialize_row(row)
    finally:
        conn.close()


def listar(target, busca="", limite=300):
    ensure_schema(target)
    try:
        limite = max(1, min(int(limite or 300), 1000))
    except (TypeError, ValueError):
        limite = 300
    search = _text(busca)
    normalized_search = normalizar_nome(search)
    conn = db_core.connect(target)
    try:
        where, params = f"WHERE {_ativo_verdadeiro_sql(conn)}", []
        if search:
            where += " AND (nome_normalizado LIKE ? OR LOWER(localidade) LIKE LOWER(?))"
            params.extend([f"%{normalized_search}%", f"%{search}%"])
        rows = conn.execute(
            f"""SELECT id_logradouro, nome, localidade, atualizado_em
                  FROM {TABLE} {where}
                 ORDER BY nome, localidade, id_logradouro LIMIT ?""",
            params + [limite],
        ).fetchall()
        return {"registros": [db_core.serialize_row(row) for row in rows], "limite": limite}
    finally:
        conn.close()


def importar_csv(target, content):
    records = _parse_csv(content)
    ensure_schema(target)
    conn = db_core.connect(target)
    try:
        existing = {
            row["id_logradouro"]: row["origem_hash"]
            for row in conn.execute(f"SELECT id_logradouro, origem_hash FROM {TABLE}")
        }
        now = _now()
        ativo = _ativo_verdadeiro_valor(conn)
        inserted = updated = unchanged = 0
        for record in records:
            previous = existing.get(record["id_logradouro"])
            values = (
                record["id_logradouro"], record["nome"], record["nome_normalizado"],
                record["localidade"], ativo, record["origem_hash"], now, now,
            )
            if previous is None:
                conn.execute(
                    f"""INSERT INTO {TABLE}
                           (id_logradouro,nome,nome_normalizado,localidade,ativo,
                            origem_hash,importado_em,atualizado_em)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    values,
                )
                inserted += 1
            elif previous != record["origem_hash"]:
                conn.execute(
                    f"""UPDATE {TABLE}
                           SET nome=?, nome_normalizado=?, localidade=?, ativo=?,
                               origem_hash=?, atualizado_em=?
                         WHERE id_logradouro=?""",
                    (
                        record["nome"], record["nome_normalizado"], record["localidade"],
                        ativo, record["origem_hash"], now, record["id_logradouro"],
                    ),
                )
                updated += 1
            else:
                unchanged += 1
        conn.commit()
        return {
            "linhas": len(records), "inseridos": inserted,
            "atualizados": updated, "sem_alteracao": unchanged,
            "observacao": "IDs ausentes do arquivo foram preservados; nenhuma linha e excluida automaticamente.",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
