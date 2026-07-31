import unittest
from datetime import date
from unittest import mock

from app_core import db as db_core
from blueprints import acoes_setor


class AcoesSetorPostgreSQLCompatTests(unittest.TestCase):
    def test_schema_postgresql_fica_sob_responsabilidade_das_migracoes(self):
        conn = mock.Mock()
        conn.backend = "postgresql"

        acoes_setor.ensure_schema(conn)

        conn.execute.assert_not_called()
        conn.executescript.assert_not_called()
        conn.commit.assert_not_called()
        conn.close.assert_not_called()

    def test_consulta_postgresql_usa_agregacao_portavel(self):
        target = db_core.DatabaseTarget("postgresql", "endemias_teste")
        with (
            mock.patch.object(acoes_setor.bh, "db_target", return_value=target),
            mock.patch.object(acoes_setor, "_usuario_admin", return_value=True),
        ):
            statement = acoes_setor._base_query()

        self.assertIn("string_agg", statement)
        self.assertIn("CAST(ag.id_agente AS TEXT)", statement)
        self.assertNotIn("GROUP_CONCAT", statement)

    def test_filtros_de_data_comparam_texto_iso_sem_funcao_sqlite(self):
        target = db_core.DatabaseTarget("postgresql", "endemias_teste")
        with (
            mock.patch.object(acoes_setor.bh, "db_target", return_value=target),
            mock.patch.object(acoes_setor, "_usuario_admin", return_value=True),
            mock.patch.object(acoes_setor.bh, "q", return_value=[]) as query,
        ):
            result = acoes_setor._consultar_acoes(
                {"data_inicio": "2026-07-01", "data_fim": "2026-07-31"}
            )

        self.assertEqual(result, [])
        statement, parameters = query.call_args.args
        self.assertIn("COALESCE(a.data_fim,a.data)>=?", statement)
        self.assertIn("a.data<=?", statement)
        self.assertNotIn("date(", statement.lower())
        self.assertEqual(parameters, ["2026-07-01", "2026-07-31"])

    def test_criacao_retorna_identidade_e_vincula_agente_portavelmente(self):
        conn = mock.Mock()
        conn.backend = "postgresql"
        payload = acoes_setor._acao_payload(
            {
                "tipo": "vistoria",
                "situacao": "realizada",
                "data": "2026-07-31",
                "periodo": "manha",
                "agentes": [17],
            }
        )

        with mock.patch.object(
            acoes_setor.db_core,
            "insert_and_get_id",
            return_value=41,
        ) as insert_id:
            result = acoes_setor._criar_acao(conn, payload, "Usuario Teste")

        self.assertEqual(result, 41)
        self.assertEqual(insert_id.call_args.args[-1], "id_acao")
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertTrue(any("ON CONFLICT DO NOTHING" in sql for sql in statements))
        self.assertFalse(any("INSERT OR IGNORE" in sql for sql in statements))

    def test_linha_com_data_nativa_e_serializada(self):
        item = acoes_setor._acao_dict(
            {
                "id_acao": 9,
                "tipo": "reuniao",
                "situacao": "realizada",
                "data": date(2026, 7, 31),
                "periodo": "tarde",
                "tipo_atividade_realizada": None,
                "publico_alvo": None,
                "recurso_utilizado": None,
                "agentes_raw": None,
            }
        )

        self.assertEqual(item["data"], "2026-07-31")
        self.assertEqual(item["agentes"], [])


if __name__ == "__main__":
    unittest.main()
