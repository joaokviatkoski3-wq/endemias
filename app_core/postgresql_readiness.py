"""Validacoes finais de uma carga SQLite no PostgreSQL descartavel."""

from app_core import postgresql_data_migration


class PostgreSQLReadinessError(RuntimeError):
    pass


def validate_migration_report(report, database):
    if report.get("database") != str(database):
        raise PostgreSQLReadinessError(
            "O relatorio de carga pertence a outro banco PostgreSQL."
        )
    source = report.get("source")
    target = report.get("target")
    if not isinstance(source, dict) or not source:
        raise PostgreSQLReadinessError("Relatorio de origem ausente ou vazio.")
    if not isinstance(target, dict) or set(target) != set(source):
        raise PostgreSQLReadinessError(
            "As tabelas de origem e destino divergem no relatorio."
        )
    differences = [name for name in source if source[name] != target[name]]
    if differences:
        raise PostgreSQLReadinessError(
            "Contagens ou checksums divergentes no relatorio: "
            + ", ".join(sorted(differences))
        )
    rows = sum(int(item.get("rows", 0)) for item in target.values())
    if int(report.get("tables", -1)) != len(target):
        raise PostgreSQLReadinessError("Total de tabelas incoerente no relatorio.")
    if int(report.get("rows", -1)) != rows:
        raise PostgreSQLReadinessError("Total de registros incoerente no relatorio.")
    return {"tables": len(target), "rows": rows, "target": target}


def validate_constraints(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT conrelid::regclass::text, conname
              FROM pg_constraint
             WHERE connamespace = 'public'::regnamespace
               AND contype IN ('c', 'f', 'p', 'u')
               AND NOT convalidated
             ORDER BY 1, 2
            """
        )
        pending = cursor.fetchall()
    if pending:
        names = ", ".join(f"{table}.{name}" for table, name in pending[:10])
        raise PostgreSQLReadinessError(
            "Existem constraints PostgreSQL nao validadas: " + names
        )
    return {"unvalidated": 0}


def _identity_matches(max_value, last_value, is_called):
    if max_value is None:
        return int(last_value) == 1 and not bool(is_called)
    return int(last_value) == int(max_value) and bool(is_called)


def validate_identities(conn):
    try:
        from psycopg2 import sql
    except ImportError as exc:
        raise PostgreSQLReadinessError(
            "Driver psycopg2 nao esta disponivel."
        ) from exc

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT cls.relname,
                   att.attname,
                   pg_get_serial_sequence(
                       format('%I.%I', ns.nspname, cls.relname),
                       att.attname
                   )
              FROM pg_class cls
              JOIN pg_namespace ns ON ns.oid = cls.relnamespace
              JOIN pg_attribute att ON att.attrelid = cls.oid
             WHERE ns.nspname = 'public'
               AND cls.relkind = 'r'
               AND att.attidentity IN ('a', 'd')
             ORDER BY cls.relname, att.attname
            """
        )
        identities = cursor.fetchall()
        failures = []
        for table, column, sequence in identities:
            if not sequence or "." not in sequence:
                failures.append(f"{table}.{column}: sequencia ausente")
                continue
            schema, sequence_name = sequence.split(".", 1)
            cursor.execute(
                sql.SQL("SELECT MAX({}) FROM {}.{}").format(
                    sql.Identifier(column),
                    sql.Identifier("public"),
                    sql.Identifier(table),
                )
            )
            max_value = cursor.fetchone()[0]
            cursor.execute(
                sql.SQL("SELECT last_value, is_called FROM {}.{}").format(
                    sql.Identifier(schema),
                    sql.Identifier(sequence_name),
                )
            )
            last_value, is_called = cursor.fetchone()
            if not _identity_matches(max_value, last_value, is_called):
                failures.append(
                    f"{table}.{column}: max={max_value}, "
                    f"last_value={last_value}, is_called={is_called}"
                )
    if failures:
        raise PostgreSQLReadinessError(
            "Identidades PostgreSQL desalinhadas: " + "; ".join(failures[:10])
        )
    return {"identities": len(identities), "failures": 0}


def validate_current_data(conn, inventory, expected_target, progress=None):
    current = postgresql_data_migration.postgres_snapshot_results(
        conn,
        inventory,
        progress=progress,
    )
    differences = [
        name
        for name in sorted(set(current) | set(expected_target))
        if current.get(name) != expected_target.get(name)
    ]
    if differences:
        raise PostgreSQLReadinessError(
            "O PostgreSQL mudou desde a carga validada: "
            + ", ".join(differences)
        )
    return {
        "tables": len(current),
        "rows": sum(item["rows"] for item in current.values()),
    }
