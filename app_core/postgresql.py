"""Infraestrutura isolada para a migracao gradual ao PostgreSQL.

O sistema de producao ainda usa SQLite. Este modulo atende somente as
ferramentas de migracao ate que a compatibilidade do aplicativo esteja pronta.
"""

import os


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5432
DEFAULT_USER = "endemias_app"
DEFAULT_DATABASE = "endemias_teste"
DEFAULT_CONNECT_TIMEOUT = 5
DEFAULT_SSLMODE = "prefer"
DEFAULT_APPLICATION_NAME = "endemias_migracao"


class PostgreSQLConfigurationError(RuntimeError):
    pass


class PostgreSQLDriverError(RuntimeError):
    pass


def _positive_int(value, name):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PostgreSQLConfigurationError(
            f"{name} deve ser um numero inteiro positivo."
        ) from exc
    if parsed <= 0:
        raise PostgreSQLConfigurationError(
            f"{name} deve ser um numero inteiro positivo."
        )
    return parsed


def connection_parameters(database=None, env=None):
    """Retorna parametros libpq sem incluir nem registrar a senha."""
    env = os.environ if env is None else env
    database = (
        database
        or env.get("ENDEMIAS_PG_DATABASE")
        or env.get("PGDATABASE")
        or DEFAULT_DATABASE
    )
    if not str(database).strip():
        raise PostgreSQLConfigurationError("O nome do banco PostgreSQL e obrigatorio.")

    return {
        "host": env.get("ENDEMIAS_PG_HOST") or env.get("PGHOST") or DEFAULT_HOST,
        "port": _positive_int(
            env.get("ENDEMIAS_PG_PORT") or env.get("PGPORT") or DEFAULT_PORT,
            "A porta PostgreSQL",
        ),
        "dbname": str(database).strip(),
        "user": env.get("ENDEMIAS_PG_USER") or env.get("PGUSER") or DEFAULT_USER,
        "connect_timeout": _positive_int(
            env.get("ENDEMIAS_PG_CONNECT_TIMEOUT") or DEFAULT_CONNECT_TIMEOUT,
            "O tempo limite da conexao",
        ),
        "sslmode": env.get("ENDEMIAS_PG_SSLMODE")
        or env.get("PGSSLMODE")
        or DEFAULT_SSLMODE,
        "application_name": env.get("ENDEMIAS_PG_APPLICATION_NAME")
        or DEFAULT_APPLICATION_NAME,
    }


def connection_summary(database=None, env=None):
    params = connection_parameters(database=database, env=env)
    return {
        "host": params["host"],
        "port": params["port"],
        "database": params["dbname"],
        "user": params["user"],
        "sslmode": params["sslmode"],
    }


def connect(database=None, env=None):
    """Abre conexao usando pgpass/libpq; nenhuma senha e lida pelo projeto."""
    try:
        import psycopg2
    except ImportError as exc:
        raise PostgreSQLDriverError(
            "Driver PostgreSQL ausente. Execute: pip install -r requirements.txt"
        ) from exc

    return psycopg2.connect(**connection_parameters(database=database, env=env))


def probe(database=None, env=None, write_test=True):
    """Confere identidade, configuracao e permissao transacional do banco."""
    conn = connect(database=database, env=env)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    current_setting('server_version'),
                    current_setting('TimeZone'),
                    pg_encoding_to_char(encoding)
                FROM pg_database
                WHERE datname = current_database()
                """
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("O PostgreSQL nao retornou os dados do banco atual.")

            if write_test:
                cursor.execute(
                    """
                    CREATE TEMPORARY TABLE endemias_connection_probe (
                        id integer PRIMARY KEY
                    ) ON COMMIT DROP
                    """
                )
                cursor.execute(
                    "INSERT INTO endemias_connection_probe (id) VALUES (%s)",
                    (1,),
                )
        conn.rollback()
        return {
            "database": row[0],
            "user": row[1],
            "server_version": row[2],
            "timezone": row[3],
            "encoding": row[4],
            "write_test": bool(write_test),
        }
    finally:
        conn.close()
