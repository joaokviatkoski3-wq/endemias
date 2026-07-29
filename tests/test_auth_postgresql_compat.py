import unittest
from unittest import mock

from app_core import audit
from app_core import auth
from app_core import db as db_core


class PostgreSQLSchemaRuntimeTests(unittest.TestCase):
    def test_auth_schema_is_managed_by_postgresql_migrations(self):
        conn = mock.Mock()
        conn.backend = "postgresql"

        auth.garantir_tabela_login_tentativas(lambda: conn, conn)

        conn.execute.assert_not_called()
        conn.commit.assert_not_called()

    def test_audit_schema_is_managed_by_postgresql_migrations(self):
        conn = mock.Mock()
        conn.backend = "postgresql"

        audit.garantir_tabela_auditoria(lambda: conn, conn)

        conn.execute.assert_not_called()
        conn.commit.assert_not_called()

    def test_audit_filters_use_portable_iso_date_expressions(self):
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.return_value.fetchall.return_value = []

        result = audit.listar_eventos(
            lambda: conn,
            {"d_ini": "2026-07-01", "d_fim": "2026-07-31"},
            limite=10,
        )

        self.assertEqual(result, [])
        statement, parameters = conn.execute.call_args.args
        self.assertIn("substr(criado_em, 1, 10) >= ?", statement)
        self.assertIn("substr(criado_em, 1, 10) <= ?", statement)
        self.assertNotIn("datetime(criado_em)", statement)
        self.assertEqual(
            parameters,
            ["2026-07-01", "2026-07-31", 10],
        )
        conn.close.assert_called_once()

    def test_sqlite_connection_exposes_backend(self):
        self.assertEqual(db_core.ResilientConnection.backend, "sqlite")


if __name__ == "__main__":
    unittest.main()
