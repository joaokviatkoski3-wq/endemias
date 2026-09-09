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


TABLE = "logradouros_oficiais"
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


def _is_postgresql(conn):
    return getattr(conn, "backend", "sqlite") == "postgresql"


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
            """
        )
        conn.commit()
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
        row = conn.execute(
            f"""SELECT COUNT(*) AS trechos,
                       COUNT(DISTINCT nome_normalizado) AS nomes_normalizados,
                       COUNT(DISTINCT localidade) AS localidades,
                       MAX(importado_em) AS ultima_importacao
                  FROM {TABLE} WHERE ativo=1"""
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
        where, params = "WHERE ativo=1", []
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
        inserted = updated = unchanged = 0
        for record in records:
            previous = existing.get(record["id_logradouro"])
            values = (
                record["id_logradouro"], record["nome"], record["nome_normalizado"],
                record["localidade"], 1, record["origem_hash"], now, now,
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
                           SET nome=?, nome_normalizado=?, localidade=?, ativo=1,
                               origem_hash=?, atualizado_em=?
                         WHERE id_logradouro=?""",
                    (
                        record["nome"], record["nome_normalizado"], record["localidade"],
                        record["origem_hash"], now, record["id_logradouro"],
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
