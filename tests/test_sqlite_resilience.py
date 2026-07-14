import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from app_core import db as db_core
from app_core import sqlite_maintenance


class SQLiteResilienceTests(unittest.TestCase):
    def test_connect_uses_resilient_connection_and_cursor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = db_core.connect(Path(tmpdir) / "test.db")
            try:
                self.assertIsInstance(conn, db_core.ResilientConnection)
                self.assertIsInstance(conn.cursor(), db_core.ResilientCursor)
                self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
                self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 1)
            finally:
                conn.close()

    def test_retry_locked_retries_busy_and_returns_result(self):
        calls = 0

        def operation():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        with mock.patch("app_core.db.time.sleep") as sleep:
            self.assertEqual(db_core._retry_locked(operation), "ok")

        self.assertEqual(calls, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_retry_locked_does_not_hide_other_operational_errors(self):
        with mock.patch("app_core.db.time.sleep") as sleep:
            with self.assertRaisesRegex(sqlite3.OperationalError, "no such table"):
                db_core._retry_locked(
                    lambda: (_ for _ in ()).throw(
                        sqlite3.OperationalError("no such table: missing")
                    )
                )

        sleep.assert_not_called()

    def test_second_writer_waits_for_short_transaction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "concurrent.db"
            first = db_core.connect(db_path)
            first.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
            first.commit()
            first.execute("BEGIN IMMEDIATE")
            first.execute("INSERT INTO items(name) VALUES ('first')")

            errors = []

            def insert_second():
                conn = db_core.connect(db_path)
                try:
                    conn.execute("INSERT INTO items(name) VALUES ('second')")
                    conn.commit()
                except Exception as exc:  # pragma: no cover - reported by assertion
                    errors.append(exc)
                finally:
                    conn.close()

            worker = threading.Thread(target=insert_second)
            worker.start()
            time.sleep(0.1)
            first.commit()
            worker.join(timeout=3)

            try:
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(first.execute("SELECT COUNT(*) FROM items").fetchone()[0], 2)
            finally:
                first.close()


class SQLiteMaintenanceTests(unittest.TestCase):
    def test_ensure_performance_indexes_is_idempotent_and_removes_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "maintenance.db"
            conn = db_core.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE visitas (
                    id_visita TEXT PRIMARY KEY,
                    id_localidade INTEGER,
                    data TEXT,
                    tipo TEXT,
                    quarteirao INTEGER
                );
                CREATE INDEX visitas_quarteirao_idx ON visitas(quarteirao);
                CREATE TABLE registro_geografico_imoveis (
                    id_imovel INTEGER PRIMARY KEY,
                    id_quarteirao INTEGER,
                    ordem INTEGER
                );
                """
            )
            conn.commit()
            conn.close()

            sqlite_maintenance.ensure_performance_indexes(db_path)
            sqlite_maintenance.ensure_performance_indexes(db_path)

            conn = db_core.connect(db_path)
            try:
                status = sqlite_maintenance.performance_index_status(conn)
                indexes = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                }
                self.assertTrue(status["ok"])
                self.assertIn("idx_visitas_quarteirao", indexes)
                self.assertNotIn("visitas_quarteirao_idx", indexes)
                self.assertEqual(
                    sqlite_maintenance._index_columns(
                        conn, "idx_rg_imoveis_quarteirao_ordem"
                    ),
                    ("id_quarteirao", "ordem", "id_imovel"),
                )
                self.assertEqual(
                    sqlite_maintenance._index_columns(
                        conn, "idx_visitas_localidade_data_tipo"
                    ),
                    ("id_localidade", "data", "tipo"),
                )
            finally:
                conn.close()

    def test_ensure_performance_indexes_tolerates_database_without_domain_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "empty.db"
            sqlite_maintenance.ensure_performance_indexes(db_path)
            conn = db_core.connect(db_path)
            try:
                status = sqlite_maintenance.performance_index_status(conn)
                self.assertFalse(status["ok"])
                self.assertEqual(status["presentes"], 0)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
