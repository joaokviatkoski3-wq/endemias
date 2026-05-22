import sqlite3


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
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
