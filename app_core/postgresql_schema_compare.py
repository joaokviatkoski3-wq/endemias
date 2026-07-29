"""Comparacao do esquema PostgreSQL com o inventario SQLite de origem."""

from app_core import postgresql_schema


def _actual_columns(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                table_name,
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                is_identity,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name <> 'endemias_schema_migrations'
            ORDER BY table_name, ordinal_position
            """
        )
        return {
            (row[0], row[1]): {
                "type": row[2],
                "max_length": row[3],
                "nullable": row[4] == "YES",
                "identity": row[5] == "YES",
                "has_default": row[6] is not None,
            }
            for row in cursor.fetchall()
        }


def _actual_summary(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name <> 'endemias_schema_migrations'
            """
        )
        tables = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name <> 'endemias_schema_migrations'
            """
        )
        columns = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT contype, COUNT(*)
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname = 'public'
              AND c.conrelid <> 'endemias_schema_migrations'::regclass
              AND contype IN ('p', 'u', 'f', 'c')
            GROUP BY contype
            """
        )
        constraints = dict(cursor.fetchall())
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name <> 'endemias_schema_migrations'
              AND is_identity = 'YES'
            """
        )
        identities = cursor.fetchone()[0]
    return {
        "tables": tables,
        "columns": columns,
        "primary_keys": constraints.get("p", 0),
        "unique_constraints": constraints.get("u", 0),
        "foreign_keys": constraints.get("f", 0),
        "check_constraints": constraints.get("c", 0),
        "identity_columns": identities,
    }


def _actual_constraint_names(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.contype, c.conname
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname = 'public'
              AND c.conrelid <> 'endemias_schema_migrations'::regclass
              AND c.contype IN ('p', 'u', 'f', 'c')
            """
        )
        result = {"p": set(), "u": set(), "f": set(), "c": set()}
        for constraint_type, name in cursor.fetchall():
            result[constraint_type].add(name)
        return result


def _actual_explicit_index_names(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT index_class.relname
            FROM pg_index index_data
            JOIN pg_class table_class
              ON table_class.oid = index_data.indrelid
            JOIN pg_class index_class
              ON index_class.oid = index_data.indexrelid
            JOIN pg_namespace namespace
              ON namespace.oid = table_class.relnamespace
            LEFT JOIN pg_constraint constraint_data
              ON constraint_data.conindid = index_class.oid
            WHERE namespace.nspname = 'public'
              AND table_class.relname <> 'endemias_schema_migrations'
              AND constraint_data.oid IS NULL
            """
        )
        return {row[0] for row in cursor.fetchall()}


def compare(conn, inventory):
    expected_summary = postgresql_schema.expected_summary(inventory)
    actual_summary = _actual_summary(conn)
    expected_columns = postgresql_schema.expected_columns(inventory)
    actual_columns = _actual_columns(conn)
    expected_constraints = postgresql_schema.expected_constraint_names(inventory)
    actual_constraints = _actual_constraint_names(conn)
    expected_indexes = postgresql_schema.expected_explicit_index_names(inventory)
    actual_indexes = _actual_explicit_index_names(conn)

    differences = []
    for key in (
        "tables",
        "columns",
        "primary_keys",
        "unique_constraints",
        "foreign_keys",
        "check_constraints",
        "identity_columns",
    ):
        if expected_summary[key] != actual_summary[key]:
            differences.append(
                f"{key}: esperado {expected_summary[key]}, "
                f"encontrado {actual_summary[key]}"
            )

    missing_columns = sorted(set(expected_columns) - set(actual_columns))
    extra_columns = sorted(set(actual_columns) - set(expected_columns))
    for item in missing_columns:
        differences.append(f"coluna ausente: {item[0]}.{item[1]}")
    for item in extra_columns:
        differences.append(f"coluna excedente: {item[0]}.{item[1]}")
    for key in sorted(set(expected_columns) & set(actual_columns)):
        if expected_columns[key] != actual_columns[key]:
            differences.append(
                f"coluna divergente: {key[0]}.{key[1]} "
                f"esperado={expected_columns[key]} "
                f"encontrado={actual_columns[key]}"
            )

    constraint_labels = {
        "p": "chave primaria",
        "u": "restricao unica",
        "f": "chave estrangeira",
        "c": "restricao check",
    }
    for constraint_type, label in constraint_labels.items():
        missing = sorted(
            expected_constraints[constraint_type]
            - actual_constraints[constraint_type]
        )
        extra = sorted(
            actual_constraints[constraint_type]
            - expected_constraints[constraint_type]
        )
        differences.extend(f"{label} ausente: {name}" for name in missing)
        differences.extend(f"{label} excedente: {name}" for name in extra)

    missing_indexes = sorted(expected_indexes - actual_indexes)
    extra_indexes = sorted(actual_indexes - expected_indexes)
    for name in missing_indexes:
        differences.append(f"indice explicito ausente: {name}")
    for name in extra_indexes:
        differences.append(f"indice explicito excedente: {name}")

    return {
        "ok": not differences,
        "expected": expected_summary,
        "actual": {
            **actual_summary,
            "explicit_indexes_found": len(expected_indexes & actual_indexes),
        },
        "differences": differences,
    }
