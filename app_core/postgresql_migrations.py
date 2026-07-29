"""Executor transacional de migracoes SQL PostgreSQL."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


MIGRATION_PATTERN = re.compile(r"^(?P<version>[0-9]{4})_[a-z0-9_]+\.sql$")
HISTORY_TABLE = "endemias_schema_migrations"
ADVISORY_LOCK_ID = 1840364291


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str
    checksum: str


def discover(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise MigrationError(f"Diretorio de migracoes ausente: {directory}")
    migrations = []
    versions = set()
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_PATTERN.match(path.name)
        if not match:
            raise MigrationError(f"Nome de migracao invalido: {path.name}")
        version = match.group("version")
        if version in versions:
            raise MigrationError(f"Versao de migracao duplicada: {version}")
        versions.add(version)
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=version,
                name=path.name,
                path=path,
                sql=sql,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
    if not migrations:
        raise MigrationError(f"Nenhuma migracao encontrada em: {directory}")
    return migrations


def _history_exists(cursor):
    cursor.execute("SELECT to_regclass('public.endemias_schema_migrations')")
    return cursor.fetchone()[0] is not None


def applied(cursor):
    if not _history_exists(cursor):
        return {}
    cursor.execute(
        """
        SELECT version, name, checksum, applied_at
        FROM endemias_schema_migrations
        ORDER BY version
        """
    )
    return {
        row[0]: {
            "name": row[1],
            "checksum": row[2],
            "applied_at": row[3],
        }
        for row in cursor.fetchall()
    }


def status(conn, directory):
    migrations = discover(directory)
    with conn.cursor() as cursor:
        applied_map = applied(cursor)
    result = []
    for migration in migrations:
        record = applied_map.get(migration.version)
        state = "pending"
        if record:
            state = (
                "applied"
                if record["checksum"] == migration.checksum
                else "checksum_mismatch"
            )
        result.append(
            {
                "version": migration.version,
                "name": migration.name,
                "state": state,
            }
        )
    return result


def apply_pending(conn, directory):
    migrations = discover(directory)
    applied_now = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_ID,))
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS endemias_schema_migrations (
                    version varchar(4) PRIMARY KEY,
                    name text NOT NULL,
                    checksum char(64) NOT NULL,
                    applied_at timestamp with time zone NOT NULL
                        DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            applied_map = applied(cursor)
            for migration in migrations:
                record = applied_map.get(migration.version)
                if record:
                    if record["checksum"] != migration.checksum:
                        raise MigrationError(
                            "Migracao aplicada foi modificada: "
                            f"{migration.name}"
                        )
                    continue
                cursor.execute(migration.sql)
                cursor.execute(
                    """
                    INSERT INTO endemias_schema_migrations
                        (version, name, checksum)
                    VALUES (%s, %s, %s)
                    """,
                    (migration.version, migration.name, migration.checksum),
                )
                applied_now.append(migration.name)
        conn.commit()
        return applied_now
    except Exception:
        conn.rollback()
        raise
