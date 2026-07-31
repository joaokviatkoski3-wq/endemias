import unittest
from datetime import date
from decimal import Decimal
from unittest import mock

from flask import Flask

from app_core import db as db_core
from blueprints import mapa, notificacoes, relatorio_agente


def _view_sem_decoradores(view):
    while hasattr(view, "__wrapped__"):
        view = view.__wrapped__
    return view


class _Cursor:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class MapaPostgreSQLCompatTests(unittest.TestCase):
    def test_api_principal_serializa_data_e_nao_usa_julianday(self):
        app = Flask(__name__)
        conn = mock.Mock()
        conn.backend = "postgresql"
        statements = []

        def execute(statement, params=()):
            statements.append((statement, params))
            if "GROUP BY v.id_localidade, v.quarteirao, v.tipo" in statement:
                return _Cursor(rows=[{
                    "id_localidade": 7,
                    "quarteirao": 12,
                    "tipo": "TBO",
                    "total_tipo": 1,
                    "normais": 1,
                    "fechados": 0,
                    "recuperados": 0,
                    "ultimo_trabalho": date(2026, 7, 31),
                }])
            return _Cursor(rows=[])

        conn.execute.side_effect = execute
        with (
            app.test_request_context("/api/mapa"),
            mock.patch.object(mapa.bh, "get_db", return_value=conn),
            mock.patch.object(mapa.esporotricose_core, "ensure_schema"),
            mock.patch.object(mapa.pe_core, "ensure_schema"),
            mock.patch.object(mapa.ovitrampas_core, "ensure_schema"),
        ):
            response = _view_sem_decoradores(mapa.api_mapa)()

        self.assertEqual(
            response.get_json()["7:12"]["ultimo_trabalho"],
            "2026-07-31",
        )
        pe_statement, pe_params = next(
            (sql, params)
            for sql, params in statements
            if "FROM pontos_estrategicos pe" in sql
        )
        self.assertNotIn("julianday", pe_statement)
        self.assertIn("SELECT MAX(v2.data)", pe_statement)
        self.assertEqual(len(pe_params), 1)
        conn.close.assert_called_once_with()

    def test_api_ovitrampas_usa_having_e_ordenacao_portaveis(self):
        app = Flask(__name__)
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.return_value = _Cursor(rows=[{
            "ovitrampa_id": "A-2",
            "rua": "Rua Teste",
            "numero": "10",
            "complemento": None,
            "localidade": "Centro",
            "bairro": None,
            "quarteirao": "3A",
            "responsavel": "Servidor",
            "latitude": Decimal("-25.123"),
            "longitude": Decimal("-49.456"),
            "leituras": 1,
            "positivas": 1,
            "ovos": Decimal("8"),
            "ultima_coleta": date(2026, 7, 30),
        }])

        with (
            app.test_request_context(
                "/api/mapa/ovitrampas?busca=rua&positivas=1&min_ovos=5"
            ),
            mock.patch.object(mapa.bh, "get_db", return_value=conn),
            mock.patch.object(mapa.ovitrampas_core, "ensure_schema"),
        ):
            response = _view_sem_decoradores(mapa.api_mapa_ovitrampas)()

        payload = response.get_json()
        self.assertEqual(payload["pontos"][0]["ultima_coleta"], "2026-07-30")
        self.assertEqual(payload["pontos"][0]["ovos"], 8.0)
        statement = conn.execute.call_args.args[0]
        self.assertIn(
            "LOWER(COALESCE(CAST(a.rua AS TEXT),'')) LIKE LOWER(?)",
            statement,
        )
        self.assertIn(
            "MAX(COALESCE(CAST(l.data_coleta AS TEXT)",
            statement,
        )
        self.assertIn("COUNT(DISTINCT CASE WHEN l.ovos > 0", statement)
        self.assertIn("COALESCE(SUM(l.ovos), 0) >= ?", statement)
        self.assertIn("substring(CAST(a.ovitrampa_id AS TEXT)", statement)
        self.assertNotIn("COLLATE NOCASE", statement)
        self.assertNotIn("HAVING positivas", statement)


class NotificacoesPostgreSQLCompatTests(unittest.TestCase):
    def test_destino_configurado_e_agregacao_postgresql(self):
        app = Flask(__name__)
        target = db_core.DatabaseTarget("postgresql", "endemias_teste")
        app.config["DB_TARGET"] = target
        foco = {"id_foco": "foco-1", "logradouro": "Rua A", "numero": "10"}

        with (
            app.test_request_context("/notificacoes/foco/foco-1"),
            mock.patch.object(notificacoes, "q1", return_value=foco),
            mock.patch.object(notificacoes, "q", side_effect=[[], []]) as query,
            mock.patch.object(notificacoes, "render_template", return_value="ok"),
        ):
            result = _view_sem_decoradores(notificacoes.foco_detalhe)("foco-1")
            configured = notificacoes._db_target()

        self.assertEqual(result, "ok")
        self.assertEqual(configured, target)
        historico_sql = query.call_args_list[0].args[0]
        self.assertIn("string_agg(DISTINCT CAST(a.nome AS TEXT), ', ')", historico_sql)
        self.assertNotIn("GROUP_CONCAT", historico_sql)

    def test_status_e_auditoria_compartilham_transacao(self):
        app = Flask(__name__)
        app.secret_key = "teste"
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.side_effect = [
            _Cursor(row=("pendente",)),
            _Cursor(),
            _Cursor(),
        ]

        with (
            app.test_request_context(
                "/notificacoes/foco/foco-1/status",
                method="POST",
                json={"status": "entregue"},
            ),
            mock.patch.object(notificacoes, "get_db", return_value=conn),
            mock.patch.object(notificacoes.audit, "registrar_evento") as auditar,
        ):
            response = _view_sem_decoradores(
                notificacoes.foco_status_rapido
            )("foco-1")

        self.assertTrue(response.get_json()["ok"])
        self.assertIs(auditar.call_args.kwargs["conn"], conn)
        conn.commit.assert_called_once_with()
        conn.rollback.assert_not_called()
        conn.close.assert_called_once_with()

    def test_falha_na_auditoria_desfaz_atualizacao_de_status(self):
        app = Flask(__name__)
        app.secret_key = "teste"
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.side_effect = [
            _Cursor(row=("pendente",)),
            _Cursor(),
            _Cursor(),
        ]

        with (
            app.test_request_context(
                "/notificacoes/foco/foco-1/status",
                method="POST",
                json={"status": "entregue"},
            ),
            mock.patch.object(notificacoes, "get_db", return_value=conn),
            mock.patch.object(
                notificacoes.audit,
                "registrar_evento",
                side_effect=RuntimeError("falha de auditoria"),
            ),
            mock.patch.object(app.logger, "exception"),
        ):
            response, status = _view_sem_decoradores(
                notificacoes.foco_status_rapido
            )("foco-1")

        self.assertEqual(status, 500)
        self.assertEqual(
            response.get_json()["erro"],
            "Nao foi possivel concluir a operacao.",
        )
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once_with()
        conn.close.assert_called_once_with()

    def test_conflito_postgresql_retorna_resposta_retentavel(self):
        class PostgreSQLConflict(Exception):
            pgcode = "40P01"

        app = Flask(__name__)
        with app.app_context():
            response, status = notificacoes._erro_banco(
                PostgreSQLConflict("deadlock detected"),
                "salvar notificacao",
            )

        self.assertEqual(status, 503)
        self.assertEqual(
            response.get_json()["erro"],
            "Banco de dados ocupado. Tente novamente.",
        )

    def test_falha_ao_abrir_conexao_de_escrita_retorna_json(self):
        app = Flask(__name__)
        app.secret_key = "teste"

        with (
            app.test_request_context(
                "/notificacoes/foco/foco-1/status",
                method="POST",
                json={"status": "entregue"},
            ),
            mock.patch.object(
                notificacoes,
                "get_db",
                side_effect=RuntimeError("connection pool exhausted"),
            ),
            mock.patch.object(app.logger, "exception"),
        ):
            response, status = _view_sem_decoradores(
                notificacoes.foco_status_rapido
            )("foco-1")

        self.assertEqual(status, 500)
        self.assertEqual(
            response.get_json()["erro"],
            "Nao foi possivel concluir a operacao.",
        )


class RelatorioAgentePostgreSQLCompatTests(unittest.TestCase):
    def test_helpers_geram_sql_especifico_por_backend(self):
        pg = mock.Mock(backend="postgresql")
        sqlite = mock.Mock(backend="sqlite")

        self.assertIn("EXTRACT(EPOCH", relatorio_agente._duration_expression(pg, "v"))
        self.assertIn("date_trunc('week'", relatorio_agente._week_start_expression(pg, "v.data"))
        self.assertIn("string_agg(DISTINCT", relatorio_agente._distinct_aggregate(pg, "v.data"))
        self.assertNotIn("julianday", relatorio_agente._duration_expression(pg, "v"))
        self.assertIn("julianday", relatorio_agente._duration_expression(sqlite, "v"))
        self.assertIn("strftime", relatorio_agente._week_start_expression(sqlite, "v.data"))
        self.assertIn("GROUP_CONCAT", relatorio_agente._distinct_aggregate(sqlite, "v.data"))

    def test_inspecao_de_coluna_usa_helper_dual(self):
        conn = mock.Mock()
        with mock.patch.object(
            relatorio_agente.db_core,
            "column_exists",
            return_value=True,
        ) as column_exists:
            result = relatorio_agente._has_column(
                conn,
                "tratamentos",
                "qtd_depositos_tratados",
            )

        self.assertTrue(result)
        column_exists.assert_called_once_with(
            conn,
            "tratamentos",
            "qtd_depositos_tratados",
        )

    def test_resumo_operacional_recebe_destino_postgresql(self):
        app = Flask(__name__)
        target = db_core.DatabaseTarget("postgresql", "endemias_teste")
        app.config["DB_TARGET"] = target
        resumo = {"totais": {"registros_total": 0}, "por_atividade": []}

        with (
            app.app_context(),
            mock.patch.object(
                relatorio_agente.producao_operacional,
                "resumo",
                return_value=resumo,
            ) as gerar,
        ):
            result = relatorio_agente._resumo_producao_agente(
                "Agente PG",
                "2026-07-01",
                "2026-07-31",
            )

        self.assertEqual(result["por_agente"][0]["agente"], "Agente PG")
        self.assertEqual(gerar.call_args.args[0], target)

    def test_laboratorio_serializa_datas_e_numeros_nativos(self):
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.side_effect = [
            _Cursor(row={"leituras": 2, "tubos": 2, "dias": 1, "positivas": 1}),
            _Cursor(rows=[{"mes": "2026-07", "leituras": Decimal("2")}]),
            _Cursor(rows=[{"dia": date(2026, 7, 31)}]),
        ]

        with mock.patch.object(
            relatorio_agente.producao_operacional,
            "_table_exists",
            return_value=True,
        ):
            result = relatorio_agente._laboratorio_larvas(
                conn,
                "Agente PG",
                "2026-07-01",
                "2026-07-31",
            )

        self.assertEqual(result["dias"], ["2026-07-31"])
        self.assertEqual(result["por_mes"][0]["leituras"], 2.0)
        month_sql = conn.execute.call_args_list[1].args[0]
        self.assertIn("substr(CAST(COALESCE(", month_sql)

    def test_duracao_serializa_decimal_postgresql(self):
        result = relatorio_agente._duracao_dict({
            "n": 3,
            "media": Decimal("12.5"),
            "minimo": Decimal("8.0"),
            "maximo": Decimal("20.0"),
        })

        self.assertEqual(
            result,
            {"n": 3, "media": 12.5, "minimo": 8.0, "maximo": 20.0},
        )


if __name__ == "__main__":
    unittest.main()
