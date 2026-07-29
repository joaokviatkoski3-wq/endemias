"""Copia transacional e validada do SQLite para o PostgreSQL."""

import base64
import hashlib
import json
import math
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from pathlib import Path

from app_core import postgresql_schema


class DataMigrationError(RuntimeError):
    pass


def _normalized(value):
    return postgresql_schema.normalize_identifier(value)


def table_load_order(inventory):
    tables = {table["name"]: table for table in inventory["tables"]}
    dependencies = {name: set() for name in tables}
    for table in inventory["tables"]:
        for foreign_key in table["foreign_keys"]:
            target = foreign_key["target_table"]
            if target not in tables:
                raise DataMigrationError(
                    f"Tabela referenciada ausente no inventario: {target}"
                )
            if target != table["name"]:
                dependencies[table["name"]].add(target)

    order = []
    remaining = {name: set(items) for name, items in dependencies.items()}
    while remaining:
        ready = sorted(name for name, items in remaining.items() if not items)
        if not ready:
            cycle = ", ".join(sorted(remaining))
            raise DataMigrationError(
                f"Ciclo de chaves estrangeiras impede a carga: {cycle}"
            )
        for name in ready:
            order.append(name)
            remaining.pop(name)
        for items in remaining.values():
            items.difference_update(ready)
    return order


@contextmanager
def sqlite_snapshot(source_path):
    """Cria copia temporaria consistente, incluindo alteracoes presentes no WAL."""
    source_path = Path(source_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Banco SQLite nao encontrado: {source_path}")

    with tempfile.TemporaryDirectory(prefix="endemias-pg-") as directory:
        snapshot_path = Path(directory) / "endemias_snapshot.db"
        source = sqlite3.connect(
            f"{source_path.as_uri()}?mode=ro",
            uri=True,
            timeout=30,
        )
        destination = sqlite3.connect(snapshot_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        yield snapshot_path


def _parse_date(value, table, column, cleanups):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nat":
        key = f"{table}.{column}"
        cleanups[key] = cleanups.get(key, 0) + 1
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise DataMigrationError(
            f"Data invalida em {table}.{column}: formato nao reconhecido."
        ) from exc


def _parse_time(value, table, column, cleanups):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nat":
        key = f"{table}.{column}"
        cleanups[key] = cleanups.get(key, 0) + 1
        return None
    try:
        return datetime_time.fromisoformat(text)
    except ValueError as exc:
        raise DataMigrationError(
            f"Horario invalido em {table}.{column}: formato nao reconhecido."
        ) from exc


def convert_value(value, table, column, cleanups):
    declared_type = (column.get("declared_type") or "").upper()
    if declared_type == "DATE":
        return _parse_date(value, table, column["name"], cleanups)
    if declared_type == "TIME":
        return _parse_time(value, table, column["name"], cleanups)
    return value


def convert_row(row, table, columns, cleanups):
    return tuple(
        convert_value(value, table, column, cleanups)
        for value, column in zip(row, columns)
    )


def _canonical_value(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if math.isnan(value):
            return {"float": "NaN"}
        if math.isinf(value):
            return {"float": "Infinity" if value > 0 else "-Infinity"}
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            "bytes": base64.b64encode(bytes(value)).decode("ascii"),
        }
    raise TypeError(f"Tipo sem serializacao canonica: {type(value).__name__}")


def row_digest(row):
    payload = json.dumps(
        [_canonical_value(value) for value in row],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).digest()


def table_checksum(row_digests):
    digest = hashlib.sha256()
    for item in sorted(row_digests):
        digest.update(item)
    return digest.hexdigest()


def _destination_nonempty_tables(cursor, tables, sql_module):
    nonempty = []
    for table in tables:
        cursor.execute(
            sql_module.SQL("SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)").format(
                sql_module.Identifier(_normalized(table))
            )
        )
        if cursor.fetchone()[0]:
            nonempty.append(table)
    return nonempty


def _truncate_destination(cursor, tables, sql_module):
    identifiers = [
        sql_module.Identifier(_normalized(table))
        for table in sorted(tables)
    ]
    cursor.execute(
        sql_module.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
            sql_module.SQL(", ").join(identifiers)
        )
    )


def _reset_identities(cursor, inventory, sql_module):
    reset = 0
    for table in inventory["tables"]:
        primary_key = [
            column
            for column in table["columns"]
            if column["primary_key_position"]
        ]
        if (
            len(primary_key) != 1
            or "AUTOINCREMENT" not in (table.get("create_sql") or "").upper()
        ):
            continue
        column = primary_key[0]["name"]
        relation = f"public.{_normalized(table['name'])}"
        cursor.execute(
            sql_module.SQL(
                """
                SELECT setval(
                    pg_get_serial_sequence(%s, %s),
                    COALESCE(MAX({column}), 1),
                    MAX({column}) IS NOT NULL
                )
                FROM {table}
                """
            ).format(
                column=sql_module.Identifier(_normalized(column)),
                table=sql_module.Identifier(_normalized(table["name"])),
            ),
            (relation, _normalized(column)),
        )
        reset += 1
    return reset


def _postgres_table_checksum(cursor, table, columns, sql_module):
    column_sql = sql_module.SQL(", ").join(
        sql_module.Identifier(_normalized(column["name"]))
        for column in columns
    )
    cursor.execute(
        sql_module.SQL("SELECT {} FROM {}").format(
            column_sql,
            sql_module.Identifier(_normalized(table)),
        )
    )
    count = 0
    digests = []
    while True:
        rows = cursor.fetchmany(2000)
        if not rows:
            break
        count += len(rows)
        digests.extend(row_digest(row) for row in rows)
    return count, table_checksum(digests)


def migrate_snapshot(
    sqlite_path,
    pg_conn,
    inventory,
    *,
    replace=False,
    batch_size=1000,
    progress=None,
):
    """Copia e valida todos os dados; confirma somente se tudo coincidir."""
    try:
        from psycopg2 import sql
        from psycopg2.extras import execute_values
    except ImportError as exc:
        raise DataMigrationError("Driver psycopg2 nao esta disponivel.") from exc

    started = time.monotonic()
    table_map = {table["name"]: table for table in inventory["tables"]}
    order = table_load_order(inventory)
    cleanups = {}
    source_results = {}
    sqlite_conn = sqlite3.connect(
        f"{Path(sqlite_path).resolve().as_uri()}?mode=ro",
        uri=True,
        timeout=30,
    )
    sqlite_conn.row_factory = sqlite3.Row

    try:
        sqlite_conn.execute("BEGIN")
        if sqlite_conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise DataMigrationError("O snapshot SQLite falhou no quick_check.")
        if sqlite_conn.execute("PRAGMA foreign_key_check").fetchall():
            raise DataMigrationError(
                "O snapshot SQLite possui chaves estrangeiras invalidas."
            )

        with pg_conn.cursor() as cursor:
            nonempty = _destination_nonempty_tables(cursor, order, sql)
            if nonempty and not replace:
                raise DataMigrationError(
                    "O destino ja possui dados. Use --substituir somente no "
                    "banco de teste para refazer a carga."
                )
            if nonempty:
                _truncate_destination(cursor, order, sql)

            for position, table_name in enumerate(order, start=1):
                table = table_map[table_name]
                columns = sorted(
                    table["columns"],
                    key=lambda item: item["position"],
                )
                source_columns = ", ".join(
                    '"' + column["name"].replace('"', '""') + '"'
                    for column in columns
                )
                source_cursor = sqlite_conn.execute(
                    f'SELECT {source_columns} FROM "'
                    + table_name.replace('"', '""')
                    + '"'
                )
                target_columns = sql.SQL(", ").join(
                    sql.Identifier(_normalized(column["name"]))
                    for column in columns
                )
                insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
                    sql.Identifier(_normalized(table_name)),
                    target_columns,
                ).as_string(pg_conn)

                row_count = 0
                digests = []
                while True:
                    rows = source_cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    converted = [
                        convert_row(row, table_name, columns, cleanups)
                        for row in rows
                    ]
                    execute_values(
                        cursor,
                        insert_sql,
                        converted,
                        page_size=batch_size,
                    )
                    row_count += len(converted)
                    digests.extend(row_digest(row) for row in converted)

                source_results[table_name] = {
                    "rows": row_count,
                    "checksum": table_checksum(digests),
                }
                if progress:
                    progress(position, len(order), table_name, row_count)

            identities_reset = _reset_identities(cursor, inventory, sql)

            target_results = {}
            differences = []
            for table_name in order:
                table = table_map[table_name]
                columns = sorted(
                    table["columns"],
                    key=lambda item: item["position"],
                )
                row_count, checksum = _postgres_table_checksum(
                    cursor,
                    table_name,
                    columns,
                    sql,
                )
                target_results[table_name] = {
                    "rows": row_count,
                    "checksum": checksum,
                }
                if source_results[table_name] != target_results[table_name]:
                    differences.append(table_name)

            if differences:
                raise DataMigrationError(
                    "Validacao de dados divergiu nas tabelas: "
                    + ", ".join(differences)
                )

        pg_conn.commit()
        sqlite_conn.rollback()
    except Exception:
        pg_conn.rollback()
        sqlite_conn.rollback()
        raise
    finally:
        sqlite_conn.close()

    return {
        "tables": len(order),
        "rows": sum(item["rows"] for item in source_results.values()),
        "identities_reset": identities_reset,
        "cleanups": dict(sorted(cleanups.items())),
        "source": source_results,
        "target": target_results,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
