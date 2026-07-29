import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_core import db as db_core


class DatabaseTargetTests(unittest.TestCase):
    def test_sqlite_remains_the_default_backend(self):
        target = db_core.configured_target({"DB_PATH": "endemias.db"})

        self.assertEqual(
            target,
            db_core.DatabaseTarget("sqlite", "endemias.db"),
        )

    def test_postgresql_target_uses_configured_database(self):
        target = db_core.configured_target(
            {
                "DB_BACKEND": "postgresql",
                "PG_DATABASE": "endemias_teste",
                "DB_PATH": "nao_usar.db",
            }
        )

        self.assertEqual(
            target,
            db_core.DatabaseTarget("postgresql", "endemias_teste"),
        )

    def test_unknown_backend_is_rejected(self):
        with self.assertRaisesRegex(
            db_core.DatabaseConfigurationError,
            "nao suportado",
        ):
            db_core.configured_target(
                {"DB_BACKEND": "desconhecido", "DB_PATH": "endemias.db"}
            )

    def test_legacy_path_still_opens_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.db"
            conn = db_core.connect(path)
            try:
                conn.execute("CREATE TABLE teste (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO teste (id) VALUES (?)", (1,))
                self.assertEqual(
                    conn.execute(
                        "SELECT id FROM teste WHERE id=?",
                        (1,),
                    ).fetchone()[0],
                    1,
                )
            finally:
                conn.close()


class PostgreSQLAdapterTests(unittest.TestCase):
    def test_qmark_translation_ignores_literals_and_comments(self):
        statement = (
            "SELECT '?' AS literal, \"?\" AS identifier "
            "FROM dados WHERE id=? -- ?\n"
            "AND texto='it''s ?' /* ? */ AND outro=?"
        )

        translated = db_core._qmark_to_pyformat(statement)

        self.assertEqual(translated.count("%s"), 2)
        self.assertIn("id=%s", translated)
        self.assertIn("outro=%s", translated)
        self.assertIn("'?' AS literal", translated)
        self.assertIn("-- ?", translated)
        self.assertIn("/* ? */", translated)

    def test_connection_translates_existing_execute_contract(self):
        raw_connection = mock.Mock()
        raw_cursor = mock.Mock()
        raw_connection.cursor.return_value = raw_cursor
        connection = db_core.PostgreSQLConnection(raw_connection)

        returned = connection.execute(
            "SELECT * FROM usuarios WHERE ativo=? LIMIT ?",
            (1, 2),
        )

        self.assertIsInstance(returned, db_core.PostgreSQLCursor)
        raw_cursor.execute.assert_called_once_with(
            "SELECT * FROM usuarios WHERE ativo=%s LIMIT %s",
            (1, 2),
        )

    def test_connect_dispatches_postgresql_target(self):
        raw_connection = mock.Mock()
        with mock.patch(
            "app_core.db.postgresql.connect",
            return_value=raw_connection,
        ) as connect:
            connection = db_core.connect(
                db_core.DatabaseTarget("postgresql", "endemias_teste")
            )

        self.assertIsInstance(connection, db_core.PostgreSQLConnection)
        connect.assert_called_once_with(database="endemias_teste")

    def test_executescript_fails_with_actionable_message(self):
        connection = db_core.PostgreSQLConnection(mock.Mock())

        with self.assertRaisesRegex(
            db_core.DatabaseCompatibilityError,
            "exclusivo do SQLite",
        ):
            connection.executescript("CREATE TABLE teste (id INTEGER);")


if __name__ == "__main__":
    unittest.main()
