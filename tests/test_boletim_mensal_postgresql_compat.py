import sqlite3
import unittest
from unittest import mock

from flask import Flask

from app_core import db as db_core
from app_core import boletim_mensal as boletim_core
from blueprints import boletim_mensal


def _view_sem_decoradores(view):
    while hasattr(view, "__wrapped__"):
        view = view.__wrapped__
    return view


class BoletimMensalPostgreSQLCompatTests(unittest.TestCase):
    def test_schema_postgresql_fica_sob_responsabilidade_das_migracoes(self):
        target = db_core.DatabaseTarget("postgresql", "endemias_teste")

        with mock.patch.object(boletim_core.db_core, "connect") as connect:
            boletim_core.ensure_schema(target)

        connect.assert_not_called()

    def test_inspecao_de_tabela_usa_helper_dual(self):
        conn = mock.Mock()
        with mock.patch.object(
            boletim_core.db_core,
            "table_exists",
            return_value=True,
        ) as table_exists:
            existe = boletim_core._table_exists(conn, "recolhimentos")

        self.assertTrue(existe)
        table_exists.assert_called_once_with(conn, "recolhimentos")

    def test_substituicao_de_itens_usa_sql_portavel(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                CREATE TABLE boletim_mensal_itens (
                    id_item INTEGER PRIMARY KEY AUTOINCREMENT,
                    ano_mes TEXT NOT NULL,
                    chave TEXT NOT NULL,
                    origem TEXT NOT NULL,
                    ordem INTEGER NOT NULL,
                    indicador TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    unidade TEXT,
                    ativo INTEGER NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    UNIQUE(ano_mes, chave)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO boletim_mensal_itens
                    (ano_mes, chave, origem, ordem, indicador, quantidade,
                     unidade, ativo, atualizado_em)
                VALUES ('2026-07', 'antigo', 'manual', 10, 'Antigo', 1,
                        'registro', 1, '2026-07-01T08:00:00')
                """
            )

            resumo = boletim_core.substituir_itens(
                conn,
                "2026-07",
                [
                    {
                        "chave": "visitas_pve",
                        "origem": "auto",
                        "ordem": 20,
                        "indicador": "Vistorias PVE ajustadas",
                        "quantidade": "7",
                        "unidade": "visitas",
                        "ativo": True,
                    },
                    {
                        "origem": "manual",
                        "indicador": "Linha manual",
                        "quantidade": "invalida",
                        "ativo": False,
                    },
                ],
            )
            rows = conn.execute(
                """SELECT chave, origem, quantidade, ativo
                     FROM boletim_mensal_itens
                    ORDER BY ordem"""
            ).fetchall()
        finally:
            conn.close()

        self.assertEqual(resumo, {"ano_mes": "2026-07", "itens": 2, "ativos": 1})
        self.assertEqual(rows[0]["chave"], "visitas_pve")
        self.assertEqual(rows[0]["quantidade"], 7)
        self.assertTrue(rows[1]["chave"].startswith("manual_"))
        self.assertEqual(rows[1]["quantidade"], 0)
        self.assertEqual(rows[1]["ativo"], 0)

    def test_rota_de_leitura_encaminha_destino_postgresql(self):
        app = Flask(__name__)
        target = db_core.DatabaseTarget("postgresql", "endemias_teste")
        app.config["DB_TARGET"] = target
        esperado = {
            "periodo": {"ano_mes": "2026-07"},
            "linhas": [],
            "total": 0,
        }

        with (
            app.test_request_context(
                "/api/boletim-mensal?mes=2026-07&modo=auto"
            ),
            mock.patch.object(
                boletim_mensal.boletim_core,
                "boletim",
                return_value=esperado,
            ) as gerar,
        ):
            response = _view_sem_decoradores(boletim_mensal.api_boletim)()

        self.assertEqual(response.get_json(), esperado)
        gerar.assert_called_once_with(target, "2026-07", usar_salvos=False)

    def test_salvamento_e_auditoria_compartilham_transacao(self):
        app = Flask(__name__)
        app.secret_key = "teste"
        target = db_core.DatabaseTarget("postgresql", "endemias_teste")
        app.config["DB_TARGET"] = target
        conn = mock.Mock()
        conn.backend = "postgresql"
        resumo = {"ano_mes": "2026-07", "itens": 2, "ativos": 1}
        resultado = {
            "periodo": {"ano_mes": "2026-07"},
            "linhas": [],
            "total": 0,
        }

        with (
            app.test_request_context(
                "/api/boletim-mensal",
                method="POST",
                json={"mes": "2026-07", "linhas": []},
            ),
            mock.patch.object(boletim_mensal.bh, "get_db", return_value=conn),
            mock.patch.object(boletim_mensal.boletim_core, "ensure_schema"),
            mock.patch.object(
                boletim_mensal.boletim_core,
                "substituir_itens",
                return_value=resumo,
            ) as substituir,
            mock.patch.object(
                boletim_mensal.audit,
                "registrar_evento",
            ) as auditar,
            mock.patch.object(
                boletim_mensal.boletim_core,
                "boletim",
                return_value=resultado,
            ),
        ):
            response = _view_sem_decoradores(boletim_mensal.api_salvar)()

        self.assertTrue(response.get_json()["ok"])
        substituir.assert_called_once_with(conn, "2026-07", [])
        self.assertIs(auditar.call_args.kwargs["conn"], conn)
        conn.commit.assert_called_once_with()
        conn.rollback.assert_not_called()
        conn.close.assert_called_once_with()

    def test_falha_na_auditoria_desfaz_o_fechamento(self):
        app = Flask(__name__)
        app.secret_key = "teste"
        target = db_core.DatabaseTarget("postgresql", "endemias_teste")
        app.config["DB_TARGET"] = target
        conn = mock.Mock()
        conn.backend = "postgresql"

        with (
            app.test_request_context(
                "/api/boletim-mensal",
                method="POST",
                json={"mes": "2026-07", "linhas": []},
            ),
            mock.patch.object(boletim_mensal.bh, "get_db", return_value=conn),
            mock.patch.object(boletim_mensal.boletim_core, "ensure_schema"),
            mock.patch.object(
                boletim_mensal.boletim_core,
                "substituir_itens",
                return_value={"ano_mes": "2026-07", "itens": 0, "ativos": 0},
            ),
            mock.patch.object(
                boletim_mensal.audit,
                "registrar_evento",
                side_effect=RuntimeError("falha de auditoria"),
            ),
            mock.patch.object(boletim_mensal.logging, "exception"),
        ):
            response, status = _view_sem_decoradores(
                boletim_mensal.api_salvar
            )()

        self.assertEqual(status, 500)
        self.assertEqual(
            response.get_json()["erro"],
            "Erro ao salvar boletim mensal.",
        )
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once_with()
        conn.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
