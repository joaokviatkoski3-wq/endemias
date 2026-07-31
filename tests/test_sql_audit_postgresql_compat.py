import unittest
from unittest import mock

from app_core import esporotricose


class SQLAuditPostgreSQLCompatTests(unittest.TestCase):
    def test_insert_idempotente_usa_sintaxe_do_backend(self):
        postgresql = mock.Mock(backend="postgresql")
        sqlite = mock.Mock(backend="sqlite")
        statement = "INSERT INTO tabela(id) VALUES (?)"

        self.assertEqual(
            esporotricose._insert_ignore_sql(postgresql, statement),
            statement + " ON CONFLICT DO NOTHING",
        )
        self.assertEqual(
            esporotricose._insert_ignore_sql(sqlite, statement),
            "INSERT OR IGNORE INTO tabela(id) VALUES (?)",
        )

    def test_importacao_de_visita_nao_emite_insert_or_ignore_no_postgresql(self):
        conn = mock.Mock(backend="postgresql")
        cur = mock.Mock(backend="postgresql")
        cur.rowcount = 1
        conn.cursor.return_value = cur
        visita = {
            "id_visita": "visita-pg",
            "kobo_uuid": "uuid-pg",
            "data": "2026-07-31",
        }

        with mock.patch.object(
            esporotricose,
            "_obter_ou_criar_localidade",
            return_value=1,
        ):
            inseriu = esporotricose._inserir_visita(
                conn,
                visita,
                "2026-07-31T12:00:00",
            )

        self.assertTrue(inseriu)
        statement = cur.execute.call_args.args[0]
        self.assertIn("ON CONFLICT DO NOTHING", statement)
        self.assertNotIn("INSERT OR IGNORE", statement)

    def test_nova_localidade_recupera_id_pelo_helper_dual(self):
        cur = mock.Mock(backend="postgresql")
        cur.fetchone.return_value = None

        with mock.patch.object(
            esporotricose.db_core,
            "insert_and_get_id",
            return_value=42,
        ) as inserir:
            result = esporotricose._obter_ou_criar_localidade(
                cur,
                "Bairro Teste",
            )

        self.assertEqual(result, 42)
        inserir.assert_called_once_with(
            cur,
            "INSERT INTO localidades(nome, cod_localidade) VALUES (?,NULL)",
            ("Bairro Teste",),
            "id_localidade",
        )


if __name__ == "__main__":
    unittest.main()
