"""Inventario estrutural do SQLite sem exportar valores de negocio."""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from app_core import schema_metadata


def _ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def _storage_classes(conn, table, column):
    sql = (
        f"SELECT typeof({_ident(column)}) AS storage_class, COUNT(*) AS total "
        f"FROM {_ident(table)} GROUP BY typeof({_ident(column)})"
    )
    return {
        row["storage_class"]: row["total"]
        for row in conn.execute(sql).fetchall()
    }


def _temporal_profile(conn, table, column, declared_type):
    declared_type = declared_type.upper()
    if declared_type not in {"DATE", "TIME"}:
        return None

    value = f"TRIM(CAST({_ident(column)} AS TEXT))"
    if declared_type == "DATE":
        categories = {
            "null": f"{_ident(column)} IS NULL",
            "empty": f"{_ident(column)} IS NOT NULL AND {value} = ''",
            "iso_date": (
                f"{value} GLOB "
                "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
                f"AND date({value}) IS NOT NULL"
            ),
            "other": "1 = 1",
        }
    else:
        categories = {
            "null": f"{_ident(column)} IS NULL",
            "empty": f"{_ident(column)} IS NOT NULL AND {value} = ''",
            "hour_minute": (
                f"{value} GLOB '[0-9][0-9]:[0-9][0-9]' "
                f"AND time({value}) IS NOT NULL"
            ),
            "hour_minute_second": (
                f"{value} GLOB '[0-9][0-9]:[0-9][0-9]:[0-9][0-9]' "
                f"AND time({value}) IS NOT NULL"
            ),
            "other": "1 = 1",
        }

    profile = {}
    already_counted = []
    for category, condition in categories.items():
        if category == "other":
            excluded = " OR ".join(f"({item})" for item in already_counted)
            condition = f"NOT ({excluded})" if excluded else "1 = 1"
        total = conn.execute(
            f"SELECT COUNT(*) FROM {_ident(table)} WHERE {condition}"
        ).fetchone()[0]
        profile[category] = total
        if category != "other":
            already_counted.append(condition)
    return profile


def _columns(conn, table):
    columns = []
    for row in conn.execute(f"PRAGMA table_info({_ident(table)})").fetchall():
        columns.append(
            {
                "position": row["cid"],
                "name": row["name"],
                "declared_type": row["type"] or "",
                "not_null": bool(row["notnull"]),
                "default": row["dflt_value"],
                "primary_key_position": row["pk"],
                "storage_classes": _storage_classes(conn, table, row["name"]),
                "temporal_profile": _temporal_profile(
                    conn,
                    table,
                    row["name"],
                    row["type"] or "",
                ),
            }
        )
    return columns


def _indexes(conn, table):
    indexes = []
    for row in conn.execute(f"PRAGMA index_list({_ident(table)})").fetchall():
        schema_row = conn.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'index' AND name = ?
            """,
            (row["name"],),
        ).fetchone()
        columns = [
            info["name"]
            for info in conn.execute(
                f"PRAGMA index_info({_ident(row['name'])})"
            ).fetchall()
            if info["name"] is not None
        ]
        indexes.append(
            {
                "name": row["name"],
                "unique": bool(row["unique"]),
                "origin": row["origin"],
                "partial": bool(row["partial"]),
                "columns": columns,
                "create_sql": schema_row["sql"] if schema_row else None,
            }
        )
    return indexes


def _foreign_keys(conn, table):
    return [
        {
            "id": row["id"],
            "position": row["seq"],
            "target_table": row["table"],
            "source_column": row["from"],
            "target_column": row["to"],
            "on_update": row["on_update"],
            "on_delete": row["on_delete"],
            "match": row["match"],
        }
        for row in conn.execute(
            f"PRAGMA foreign_key_list({_ident(table)})"
        ).fetchall()
    ]


def _non_null_storage_classes(column):
    return {
        storage_class
        for storage_class, total in column["storage_classes"].items()
        if storage_class != "null" and total
    }


def _declared_affinity(declared_type):
    value = declared_type.upper()
    if not value or "BLOB" in value:
        return "any"
    if "INT" in value:
        return "integer"
    if any(token in value for token in ("CHAR", "CLOB", "TEXT")):
        return "text"
    if any(token in value for token in ("REAL", "FLOA", "DOUB")):
        return "real"
    return "numeric"


def _type_mismatch(column):
    storage = _non_null_storage_classes(column)
    if not storage:
        return False
    affinity = _declared_affinity(column["declared_type"])
    allowed = {
        "integer": {"integer"},
        "text": {"text"},
        "any": {"integer", "real", "text", "blob"},
        "real": {"integer", "real"},
        "numeric": {"integer", "real", "text"},
    }[affinity]
    return not storage.issubset(allowed)


def build_inventory(db_path):
    """Le o banco em uma transacao consistente e retorna apenas metadados."""
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Banco SQLite nao encontrado: {path}")

    uri = f"{path.as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_key_violations = len(
            conn.execute("PRAGMA foreign_key_check").fetchall()
        )
        table_rows = conn.execute(
            f"""
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
              AND name NOT IN ({','.join('?' for _ in schema_metadata.INTERNAL_TABLES)})
            ORDER BY name
            """,
            schema_metadata.INTERNAL_TABLES,
        ).fetchall()

        tables = []
        for table_row in table_rows:
            name = table_row["name"]
            tables.append(
                {
                    "name": name,
                    "row_count": conn.execute(
                        f"SELECT COUNT(*) FROM {_ident(name)}"
                    ).fetchone()[0],
                    "create_sql": table_row["sql"],
                    "columns": _columns(conn, name),
                    "indexes": _indexes(conn, name),
                    "foreign_keys": _foreign_keys(conn, name),
                }
            )

        triggers = [
            {"name": row["name"], "table": row["tbl_name"], "sql": row["sql"]}
            for row in conn.execute(
                """
                SELECT name, tbl_name, sql
                FROM sqlite_master
                WHERE type = 'trigger'
                ORDER BY name
                """
            ).fetchall()
        ]
        views = [
            {"name": row["name"], "sql": row["sql"]}
            for row in conn.execute(
                """
                SELECT name, sql
                FROM sqlite_master
                WHERE type = 'view'
                ORDER BY name
                """
            ).fetchall()
        ]
        conn.rollback()
    finally:
        conn.close()

    mixed_columns = []
    type_mismatches = []
    missing_primary_keys = []
    invalid_temporal_columns = []
    duplicate_indexes = []
    for table in tables:
        if not any(col["primary_key_position"] for col in table["columns"]):
            missing_primary_keys.append(table["name"])
        index_signatures = {}
        for index in table["indexes"]:
            signature = (index["unique"], tuple(index["columns"]))
            index_signatures.setdefault(signature, []).append(index["name"])
        for (unique, columns), names in index_signatures.items():
            if len(names) > 1:
                duplicate_indexes.append(
                    {
                        "table": table["name"],
                        "unique": unique,
                        "columns": list(columns),
                        "indexes": sorted(names),
                    }
                )
        for column in table["columns"]:
            classes = sorted(_non_null_storage_classes(column))
            item = {
                "table": table["name"],
                "column": column["name"],
                "declared_type": column["declared_type"],
                "storage_classes": classes,
            }
            if len(classes) > 1:
                mixed_columns.append(item)
            if _type_mismatch(column):
                type_mismatches.append(item)
            if column["temporal_profile"] and (
                column["temporal_profile"].get("empty", 0)
                or column["temporal_profile"].get("other", 0)
            ):
                invalid_temporal_columns.append(
                    {
                        "table": table["name"],
                        "column": column["name"],
                        "declared_type": column["declared_type"],
                        "profile": column["temporal_profile"],
                    }
                )

    return {
        "format_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": {
            "filename": path.name,
            "size_bytes": os.path.getsize(path),
            "sqlite_version": sqlite3.sqlite_version,
            "journal_mode": journal_mode,
            "quick_check": integrity,
            "foreign_key_violations": foreign_key_violations,
        },
        "summary": {
            "tables": len(tables),
            "columns": sum(len(table["columns"]) for table in tables),
            "rows": sum(table["row_count"] for table in tables),
            "indexes": sum(len(table["indexes"]) for table in tables),
            "foreign_keys": sum(len(table["foreign_keys"]) for table in tables),
            "triggers": len(triggers),
            "views": len(views),
            "mixed_storage_columns": len(mixed_columns),
            "type_mismatches": len(type_mismatches),
            "tables_without_primary_key": len(missing_primary_keys),
            "invalid_temporal_columns": len(invalid_temporal_columns),
            "duplicate_indexes": len(duplicate_indexes),
        },
        "issues": {
            "mixed_storage_columns": mixed_columns,
            "type_mismatches": type_mismatches,
            "tables_without_primary_key": missing_primary_keys,
            "invalid_temporal_columns": invalid_temporal_columns,
            "duplicate_indexes": duplicate_indexes,
        },
        "tables": tables,
        "triggers": triggers,
        "views": views,
    }


def write_inventory(inventory, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def summary_lines(inventory, largest_limit=15):
    db = inventory["database"]
    summary = inventory["summary"]
    yield f"Integridade: {db['quick_check']}"
    yield f"Violacoes de chave estrangeira: {db['foreign_key_violations']}"
    yield f"Tabelas: {summary['tables']}"
    yield f"Colunas: {summary['columns']}"
    yield f"Registros: {summary['rows']}"
    yield f"Indices: {summary['indexes']}"
    yield f"Chaves estrangeiras: {summary['foreign_keys']}"
    yield f"Colunas com armazenamento misto: {summary['mixed_storage_columns']}"
    yield f"Incompatibilidades de tipo: {summary['type_mismatches']}"
    yield (
        "Colunas temporais que exigem limpeza: "
        f"{summary['invalid_temporal_columns']}"
    )
    yield f"Indices duplicados: {summary['duplicate_indexes']}"
    yield f"Tabelas sem chave primaria: {summary['tables_without_primary_key']}"
    yield ""
    yield "Maiores tabelas:"
    largest = sorted(
        inventory["tables"],
        key=lambda table: (-table["row_count"], table["name"]),
    )
    for table in largest[:largest_limit]:
        yield f"- {table['name']}: {table['row_count']}"
