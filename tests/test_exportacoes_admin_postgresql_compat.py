import unittest
from unittest import mock

from flask import Flask

from app_core import db as db_core
from app_core import diagnostico
from blueprints import admin, exportacoes
import gerar_consolidado


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

    def __iter__(self):
        return iter(self._rows)


class ExportacoesPostgreSQLCompatTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["DB_TARGET"] = db_core.DatabaseTarget(
            "postgresql",
            "endemias_teste",
        )

    def test_exportacao_visitas_usa_agregacoes_postgresql(self):
        with (
            self.app.test_request_context("/api/visitas/exportar"),
            mock.patch.object(exportacoes, "q", return_value=[]) as query,
        ):
            response = _view_sem_decoradores(exportacoes.exportar_visitas)()
            response.direct_passthrough = False

        self.assertEqual(response.status_code, 200)
        statement = query.call_args.args[0]
        self.assertIn("string_agg(nome, ', ' ORDER BY nome)", statement)
        self.assertIn("string_agg(item, '; ' ORDER BY ordem)", statement)
        self.assertIn("string_agg(CAST(num_tubo AS TEXT)", statement)
        self.assertNotIn("GROUP_CONCAT", statement)

    def test_exportacao_laboratorio_remove_group_by_incompleto(self):
        with (
            self.app.test_request_context(
                "/api/laboratorio/exportar?tubo=pg-001"
                "&d_ini=2026-01-01&d_fim=2026-12-31"
            ),
            mock.patch.object(exportacoes, "q", return_value=[]) as query,
        ):
            response = _view_sem_decoradores(exportacoes.exportar_laboratorio)()
            response.direct_passthrough = False

        self.assertEqual(response.status_code, 200)
        statement = query.call_args.args[0]
        self.assertIn("LOWER(c.num_tubo) LIKE LOWER(?)", statement)
        self.assertIn("string_agg(nome, ', ' ORDER BY nome)", statement)
        self.assertNotIn("GROUP BY rl.id_resultado", statement)
        self.assertNotIn("GROUP_CONCAT", statement)

    def test_busca_de_notificacoes_preserva_semantica_sem_diferenciar_caixa(self):
        with (
            self.app.test_request_context("/api/notificacoes/exportar?busca=Rua"),
            mock.patch.object(exportacoes, "q", return_value=[]) as query,
        ):
            response = _view_sem_decoradores(exportacoes.exportar_notificacoes)()
            response.direct_passthrough = False

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "LOWER(f.logradouro) LIKE LOWER(?)",
            query.call_args.args[0],
        )


class ConsolidadosPostgreSQLCompatTests(unittest.TestCase):
    def test_queries_postgresql_usam_string_agg_e_group_by_completo(self):
        visitas = gerar_consolidado.montar_query_visitas("TBO", "postgresql")
        coletas = gerar_consolidado.montar_query("TBO", "postgresql")

        self.assertIn("string_agg(a2.nome", visitas)
        self.assertIn("string_agg(dep, '; ' ORDER BY num_tubo)", visitas)
        self.assertIn("GROUP BY v.id_visita, c.id_coleta, r.id_resultado", coletas)
        self.assertNotIn("GROUP_CONCAT", visitas + coletas)

    def test_queries_sqlite_mantem_group_concat(self):
        self.assertIn(
            "GROUP_CONCAT",
            gerar_consolidado.montar_query_visitas("PE", "sqlite"),
        )


class DiagnosticoPostgreSQLCompatTests(unittest.TestCase):
    def test_integridade_postgresql_nao_executa_pragma(self):
        conn = mock.Mock(backend="postgresql")
        conn.execute.return_value = _Cursor(row=("endemias_teste", "17.5"))
        itens = []

        diagnostico._check_integridade(conn, itens)

        self.assertEqual(itens[0]["nivel"], "ok")
        self.assertIn("PostgreSQL", itens[0]["titulo"])
        self.assertNotIn("PRAGMA", conn.execute.call_args.args[0])

    def test_metadados_postgresql_usam_information_schema(self):
        conn = mock.Mock(backend="postgresql")
        conn.execute.return_value = _Cursor(rows=[("usuarios",), ("visitas",)])

        tabelas = diagnostico._tables(conn)

        self.assertEqual(tabelas, {"usuarios", "visitas"})
        self.assertIn("information_schema.tables", conn.execute.call_args.args[0])

    def test_backup_postgresql_e_informativo_sem_inspecionar_sqlite(self):
        itens = []
        diagnostico._check_backups("pasta-inexistente", itens, "postgresql")

        self.assertEqual(itens[0]["nivel"], "info")
        self.assertIn("PostgreSQL", itens[0]["titulo"])


class AdminPostgreSQLCompatTests(unittest.TestCase):
    def test_operacao_sqlite_e_bloqueada_com_postgresql(self):
        app = Flask(__name__)
        app.secret_key = "teste"
        app.config["DB_TARGET"] = db_core.DatabaseTarget(
            "postgresql",
            "endemias_teste",
        )
        app.register_blueprint(admin.bp)

        with app.test_request_context("/admin/sistema/backups/criar", method="POST"):
            response = _view_sem_decoradores(admin.admin_criar_backup)()

        self.assertEqual(response.status_code, 302)
        self.assertIn("indispon%C3%ADvel", response.location)

    def test_gerador_recebe_database_target_postgresql(self):
        app = Flask(__name__)
        app.config["DB_TARGET"] = db_core.DatabaseTarget(
            "postgresql",
            "endemias_teste",
        )
        with (
            app.test_request_context(
                "/saida/gerar-consolidados",
                method="POST",
                json={"tipo": "PE"},
            ),
            mock.patch("gerar_consolidado.gerar_todos", return_value=[]) as gerar,
        ):
            response = _view_sem_decoradores(exportacoes.gerar_consolidados)()

        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(
            gerar.call_args.kwargs["banco_dados"],
            db_core.DatabaseTarget("postgresql", "endemias_teste"),
        )


if __name__ == "__main__":
    unittest.main()
