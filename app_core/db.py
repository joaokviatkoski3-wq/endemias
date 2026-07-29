import sqlite3
import threading
import time
from dataclasses import dataclass

from app_core import postgresql


BUSY_TIMEOUT_MS = 5000
_RETRY_DELAYS_SECONDS = (0.05, 0.15)
_metrics_lock = threading.Lock()
_metrics = {
    "connections": 0,
    "lock_retries": 0,
    "lock_failures": 0,
    "last_lock_at": None,
}


class DatabaseConfigurationError(RuntimeError):
    pass


class DatabaseCompatibilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseTarget:
    backend: str
    location: str


def configured_target(config):
    explicit = config.get("DB_TARGET")
    if explicit is not None:
        return _coerce_target(explicit)

    backend = str(config.get("DB_BACKEND") or "sqlite").strip().lower()
    if backend == "sqlite":
        location = config.get("DB_PATH")
    elif backend in {"postgres", "postgresql"}:
        backend = "postgresql"
        location = (
            config.get("PG_DATABASE")
            or config.get("ENDEMIAS_PG_DATABASE")
            or postgresql.DEFAULT_DATABASE
        )
    else:
        raise DatabaseConfigurationError(
            f"Banco nao suportado: {backend or '(vazio)'}."
        )

    if not location:
        raise DatabaseConfigurationError(
            f"Destino obrigatorio para o banco {backend}."
        )
    return DatabaseTarget(backend, str(location))


def _coerce_target(target):
    if isinstance(target, DatabaseTarget):
        return target
    return DatabaseTarget("sqlite", str(target))


def is_sqlite(target):
    return _coerce_target(target).backend == "sqlite"


def _qmark_to_pyformat(statement):
    """Converte placeholders fora de literais e comentarios SQL."""
    result = []
    index = 0
    state = "normal"
    while index < len(statement):
        char = statement[index]
        following = statement[index + 1] if index + 1 < len(statement) else ""

        if state == "normal":
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "-" and following == "-":
                result.extend((char, following))
                index += 2
                state = "line_comment"
                continue
            elif char == "/" and following == "*":
                result.extend((char, following))
                index += 2
                state = "block_comment"
                continue
            elif char == "?":
                result.append("%s")
                index += 1
                continue
        elif state == "single":
            if char == "'" and following == "'":
                result.extend((char, following))
                index += 2
                continue
            if char == "'":
                state = "normal"
        elif state == "double":
            if char == '"' and following == '"':
                result.extend((char, following))
                index += 2
                continue
            if char == '"':
                state = "normal"
        elif state == "line_comment":
            if char in "\r\n":
                state = "normal"
        elif state == "block_comment":
            if char == "*" and following == "/":
                result.extend((char, following))
                index += 2
                state = "normal"
                continue

        result.append(char)
        index += 1
    return "".join(result)


def _is_lock_error(exc):
    error_code = getattr(exc, "sqlite_errorcode", None)
    if error_code is not None:
        return (error_code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message


def _record_lock(metric):
    with _metrics_lock:
        _metrics[metric] += 1
        _metrics["last_lock_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def _retry_locked(operation):
    for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            if not _is_lock_error(exc):
                raise
            if attempt >= len(_RETRY_DELAYS_SECONDS):
                _record_lock("lock_failures")
                raise
            _record_lock("lock_retries")
            time.sleep(_RETRY_DELAYS_SECONDS[attempt])


class ResilientCursor(sqlite3.Cursor):
    def execute(self, sql, parameters=()):
        return _retry_locked(lambda: super(ResilientCursor, self).execute(sql, parameters))

    def executemany(self, sql, seq_of_parameters):
        return _retry_locked(
            lambda: super(ResilientCursor, self).executemany(sql, seq_of_parameters)
        )


class ResilientConnection(sqlite3.Connection):
    backend = "sqlite"

    def cursor(self, factory=ResilientCursor):
        return super().cursor(factory)

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        return self.cursor().executemany(sql, seq_of_parameters)

    def commit(self):
        return _retry_locked(lambda: super(ResilientConnection, self).commit())


class PostgreSQLCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, statement, parameters=()):
        self._cursor.execute(_qmark_to_pyformat(statement), parameters)
        return self

    def executemany(self, statement, seq_of_parameters):
        self._cursor.executemany(
            _qmark_to_pyformat(statement),
            seq_of_parameters,
        )
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchmany(self, size=None):
        if size is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(size)

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        return self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._cursor.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PostgreSQLConnection:
    backend = "postgresql"
    row_factory = None

    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        try:
            from psycopg2.extras import DictCursor
        except ImportError as exc:
            raise DatabaseCompatibilityError(
                "Driver psycopg2 nao esta disponivel."
            ) from exc
        return PostgreSQLCursor(
            self._connection.cursor(cursor_factory=DictCursor)
        )

    def execute(self, statement, parameters=()):
        return self.cursor().execute(statement, parameters)

    def executemany(self, statement, seq_of_parameters):
        return self.cursor().executemany(statement, seq_of_parameters)

    def executescript(self, script):
        raise DatabaseCompatibilityError(
            "executescript e exclusivo do SQLite; use uma migracao PostgreSQL."
        )

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._connection.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def connection_metrics():
    with _metrics_lock:
        return dict(_metrics)


def _connect_sqlite(db_path):
    conn = sqlite3.connect(
        db_path,
        timeout=BUSY_TIMEOUT_MS / 1000,
        factory=ResilientConnection,
    )
    with _metrics_lock:
        _metrics["connections"] += 1
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def connect(target):
    target = _coerce_target(target)
    if target.backend == "sqlite":
        return _connect_sqlite(target.location)
    if target.backend == "postgresql":
        return PostgreSQLConnection(
            postgresql.connect(database=target.location)
        )
    raise DatabaseConfigurationError(
        f"Banco nao suportado: {target.backend or '(vazio)'}."
    )


def query(target, sql, params=()):
    conn = connect(target)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_one(target, sql, params=()):
    conn = connect(target)
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def scalar(target, sql, params=()):
    conn = connect(target)
    try:
        val = conn.execute(sql, params).fetchone()
        return val[0] if val else 0
    finally:
        conn.close()
