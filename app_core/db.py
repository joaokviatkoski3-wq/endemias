import sqlite3
import threading
import time


BUSY_TIMEOUT_MS = 5000
_RETRY_DELAYS_SECONDS = (0.05, 0.15)
_metrics_lock = threading.Lock()
_metrics = {
    "connections": 0,
    "lock_retries": 0,
    "lock_failures": 0,
    "last_lock_at": None,
}


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
    def cursor(self, factory=ResilientCursor):
        return super().cursor(factory)

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        return self.cursor().executemany(sql, seq_of_parameters)

    def commit(self):
        return _retry_locked(lambda: super(ResilientConnection, self).commit())


def connection_metrics():
    with _metrics_lock:
        return dict(_metrics)


def connect(db_path):
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


def query(db_path, sql, params=()):
    conn = connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_one(db_path, sql, params=()):
    conn = connect(db_path)
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def scalar(db_path, sql, params=()):
    conn = connect(db_path)
    try:
        val = conn.execute(sql, params).fetchone()
        return val[0] if val else 0
    finally:
        conn.close()
