import unittest
from unittest import mock

from app_core import import_history


class ImportHistoryPostgreSQLCompatibilityTests(unittest.TestCase):
    def test_schema_is_managed_by_postgresql_migrations(self):
        conn = mock.Mock()
        conn.backend = "postgresql"

        import_history.garantir_tabela_importacoes(lambda: conn, conn)

        conn.execute.assert_not_called()
        conn.commit.assert_not_called()

    def test_listing_uses_portable_iso_order(self):
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.return_value.fetchall.return_value = []

        result = import_history.listar_importacoes_recentes(
            lambda: conn,
            limite=5,
        )

        self.assertEqual(result, [])
        statement, parameters = conn.execute.call_args.args
        self.assertIn("ORDER BY criado_em DESC", statement)
        self.assertNotIn("datetime(criado_em)", statement)
        self.assertEqual(parameters, (5,))


if __name__ == "__main__":
    unittest.main()
