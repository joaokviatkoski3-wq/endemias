import sqlite3
import unittest
from datetime import date
from unittest import mock

from flask import Flask

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

    def test_filtros_de_data_normalizam_prefixo_iso_sem_funcao_sqlite(self):
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
        self.assertIn("substr(COALESCE(a.data_fim,a.data),1,10)>=?", statement)
        self.assertIn("substr(a.data,1,10)<=?", statement)
        self.assertNotIn("date(", statement.lower())
        self.assertEqual(parameters, ["2026-07-01", "2026-07-31"])

    def test_filtro_inclui_data_legada_com_sufixo_de_hora(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(
                """
                CREATE TABLE acoes_setor (
                    id_acao INTEGER PRIMARY KEY,
                    tipo TEXT,
                    situacao TEXT,
                    data TEXT,
                    data_fim TEXT,
                    periodo TEXT,
                    hora_inicio TEXT,
                    tipo_atividade_realizada TEXT,
                    publico_alvo TEXT,
                    recurso_utilizado TEXT
                );
                CREATE TABLE acoes_setor_anexos (
                    id_anexo INTEGER PRIMARY KEY,
                    id_acao INTEGER,
                    restrito INTEGER
                );
                CREATE TABLE acoes_setor_agentes (
                    id_acao INTEGER,
                    id_agente INTEGER
                );
                CREATE TABLE agentes (
                    id_agente INTEGER PRIMARY KEY,
                    nome TEXT
                );
                INSERT INTO acoes_setor
                    (id_acao, tipo, situacao, data, data_fim, periodo)
                VALUES
                    (1, 'vistoria', 'realizada',
                     '2020-05-01 00:00:00', '2020-05-01 23:59:59', 'manha');
                """
            )
            target = db_core.DatabaseTarget("sqlite", ":memory:")
            with (
                mock.patch.object(
                    acoes_setor.bh,
                    "db_target",
                    return_value=target,
                ),
                mock.patch.object(
                    acoes_setor,
                    "_usuario_admin",
                    return_value=True,
                ),
                mock.patch.object(
                    acoes_setor.bh,
                    "q",
                    side_effect=lambda sql, params=(): conn.execute(
                        sql, params
                    ).fetchall(),
                ),
            ):
                registros = acoes_setor._consultar_acoes(
                    {
                        "data_inicio": "2020-05-01",
                        "data_fim": "2020-05-01",
                    }
                )
        finally:
            conn.close()

        self.assertEqual([item["id_acao"] for item in registros], [1])

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

    def test_linha_com_data_nativa_e_agentes_sao_normalizados(self):
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
                "agentes_raw": "2:Zulu|1:Ágata",
            }
        )

        self.assertEqual(item["data"], "2026-07-31")
        self.assertEqual(
            [agente["id_agente"] for agente in item["agentes"]],
            [1, 2],
        )
        self.assertEqual(item["agentes_nomes"], "Ágata, Zulu")

    def test_anexo_com_data_nativa_e_serializado(self):
        item = acoes_setor._anexo_dict(
            {
                "id_anexo": 11,
                "restrito": 0,
                "criado_em": date(2026, 7, 31),
            },
            pode_gerenciar_restritos=False,
        )

        self.assertEqual(item["criado_em"], "2026-07-31")
        self.assertFalse(item["restrito"])

    def test_erro_concorrente_retorna_resposta_retentavel(self):
        class PostgreSQLConflict(Exception):
            pgcode = "40P01"

        app = Flask(__name__)
        with app.app_context():
            response, status = acoes_setor._erro_banco(
                PostgreSQLConflict("deadlock detected"),
                "salvar registro",
            )

        self.assertEqual(status, 503)
        self.assertEqual(
            response.get_json()["erro"],
            "Banco de dados ocupado. Tente novamente.",
        )

    def test_falha_ao_abrir_conexao_de_anexo_retorna_json(self):
        app = Flask(__name__)
        view = acoes_setor.api_excluir_anexo
        while hasattr(view, "__wrapped__"):
            view = view.__wrapped__

        with (
            app.test_request_context(
                "/api/acoes-setor/anexos/1",
                method="DELETE",
            ),
            mock.patch.object(acoes_setor, "ensure_schema"),
            mock.patch.object(
                acoes_setor.bh,
                "get_db",
                side_effect=RuntimeError("connection pool exhausted"),
            ),
            mock.patch.object(app.logger, "exception"),
        ):
            response, status = view(1)

        self.assertEqual(status, 500)
        self.assertEqual(
            response.get_json()["erro"],
            "Nao foi possivel concluir a operacao.",
        )


if __name__ == "__main__":
    unittest.main()
