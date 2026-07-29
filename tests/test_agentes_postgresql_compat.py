import unittest
from unittest import mock

from app_core import agentes


class AgentesPostgreSQLCompatibilityTests(unittest.TestCase):
    def test_schema_is_managed_by_postgresql_migrations(self):
        conn = mock.Mock()
        conn.backend = "postgresql"

        agentes.ensure_schema(conn)

        conn.execute.assert_not_called()
        conn.commit.assert_not_called()
        conn.close.assert_not_called()

    def test_insert_returns_postgresql_identity(self):
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.return_value.fetchone.return_value = [42]

        result = agentes._insert_id(
            conn,
            "INSERT INTO agentes(nome) VALUES (?)",
            ("Servidor",),
        )

        self.assertEqual(result, 42)
        statement, parameters = conn.execute.call_args.args
        self.assertEqual(
            statement,
            "INSERT INTO agentes(nome) VALUES (?) RETURNING id_agente",
        )
        self.assertEqual(parameters, ("Servidor",))

    def test_table_detection_uses_information_schema(self):
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.return_value.fetchone.return_value = [1]

        self.assertTrue(agentes._table_exists(conn, "agentes"))

        statement, parameters = conn.execute.call_args.args
        self.assertIn("information_schema.tables", statement)
        self.assertEqual(parameters, ("agentes",))

    def test_postgresql_get_or_create_populates_full_name(self):
        conn = mock.Mock()
        conn.backend = "postgresql"
        select_cursor = mock.Mock()
        select_cursor.fetchone.return_value = None
        insert_cursor = mock.Mock()
        insert_cursor.fetchone.return_value = [7]
        conn.execute.side_effect = [select_cursor, insert_cursor]

        result = agentes.obter_ou_criar(conn, "Servidor Novo")

        self.assertEqual(result, 7)
        statement, parameters = conn.execute.call_args_list[1].args
        self.assertIn("nome_completo", statement)
        self.assertTrue(statement.endswith("RETURNING id_agente"))
        self.assertEqual(parameters, ("Servidor Novo", "Servidor Novo"))

    def test_date_values_are_normalized_for_history_sorting(self):
        from datetime import date

        self.assertEqual(agentes._iso_date(date(2026, 7, 29)), "2026-07-29")
        self.assertEqual(agentes._iso_date("2026-07-29"), "2026-07-29")
        self.assertEqual(agentes._iso_date(None), "")


if __name__ == "__main__":
    unittest.main()
