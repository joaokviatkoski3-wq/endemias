"""Validacao e normalizacao de datas no cadastro de Pontos Estrategicos."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from flask import Flask

from app_core import db as db_core
from app_core import pontos_estrategicos as pe_core
from blueprints import pontos_estrategicos as pe_blueprint


class PontosEstrategicosDatasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.conn = db_core.connect(Path(self.temp.name) / "pe.db")
        self.conn.executescript(
            """
            CREATE TABLE localidades (
                id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cod_localidade TEXT
            );
            CREATE TABLE visitas (
                id_visita TEXT PRIMARY KEY, tipo TEXT, data DATE NOT NULL,
                id_localidade INTEGER, quarteirao INTEGER, id_pe INTEGER, codigo_pe TEXT
            );
            CREATE TABLE focos_positivos (
                id_foco INTEGER PRIMARY KEY AUTOINCREMENT, gera_notificacao INTEGER,
                id_localidade INTEGER, quarteirao INTEGER
            );
            """
        )
        pe_core.ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    @staticmethod
    def _payload(codigo, **campos):
        payload = {
            "codigo_pe": codigo,
            "nome": f"PE {codigo}",
            "situacao": 1,
        }
        payload.update(campos)
        return payload

    def test_criacao_normaliza_datas_vazias_e_nat_para_null(self):
        valores = (None, "", "   ", "NaT", "nat", pd.NaT)
        for indice, valor in enumerate(valores, 1):
            with self.subTest(valor=repr(valor)):
                codigo = f"PE-DATA-{indice}"
                self.assertTrue(
                    pe_core.salvar(
                        self.conn,
                        self._payload(
                            codigo,
                            data_inclusao=valor,
                            data_desativacao=valor,
                        ),
                    )
                )
                row = self.conn.execute(
                    """SELECT data_inclusao, data_desativacao
                         FROM pontos_estrategicos WHERE codigo_pe=?""",
                    (codigo,),
                ).fetchone()
                self.assertIsNone(row["data_inclusao"])
                self.assertIsNone(row["data_desativacao"])

    def test_edicao_normaliza_datas_vazias_e_nat_para_null(self):
        self.assertTrue(
            pe_core.salvar(
                self.conn,
                self._payload(
                    "PE-EDICAO-DATA",
                    data_inclusao="2026-08-01",
                    data_desativacao="2026-08-02",
                ),
            )
        )
        id_pe = self.conn.execute(
            "SELECT id_pe FROM pontos_estrategicos WHERE codigo_pe='PE-EDICAO-DATA'"
        ).fetchone()["id_pe"]

        self.assertTrue(
            pe_core.salvar(
                self.conn,
                self._payload(
                    "PE-EDICAO-DATA",
                    data_inclusao=" NaT ",
                    data_desativacao=pd.NaT,
                ),
                id_pe=id_pe,
            )
        )
        row = self.conn.execute(
            """SELECT data_inclusao, data_desativacao
                 FROM pontos_estrategicos WHERE id_pe=?""",
            (id_pe,),
        ).fetchone()
        self.assertIsNone(row["data_inclusao"])
        self.assertIsNone(row["data_desativacao"])

    def test_data_nao_vazia_invalida_impede_persistencia(self):
        self.assertTrue(
            pe_core.salvar(
                self.conn,
                self._payload("PE-DATA-INVALIDA", data_inclusao="2026-08-01"),
            )
        )
        id_pe = self.conn.execute(
            "SELECT id_pe FROM pontos_estrategicos WHERE codigo_pe='PE-DATA-INVALIDA'"
        ).fetchone()["id_pe"]

        with self.assertRaisesRegex(pe_core.DataValidationError, "Data de inclusao invalida"):
            pe_core.salvar(
                self.conn,
                self._payload("PE-DATA-INVALIDA", data_inclusao="31/02/2026"),
                id_pe=id_pe,
            )

        row = self.conn.execute(
            "SELECT data_inclusao FROM pontos_estrategicos WHERE id_pe=?",
            (id_pe,),
        ).fetchone()
        self.assertEqual(row["data_inclusao"], "2026-08-01")

    def test_rotas_de_data_invalida_retornam_400_sem_erro_interno(self):
        app = Flask(__name__)
        payload = self._payload("PE-HTTP-DATA", data_inclusao="31/02/2026")
        criar = pe_blueprint.api_criar.__wrapped__.__wrapped__
        atualizar = pe_blueprint.api_atualizar.__wrapped__.__wrapped__

        with mock.patch.object(pe_blueprint.bh, "db_target", return_value=self.conn):
            with app.test_request_context("/api/pontos-estrategicos", method="POST", json=payload):
                resposta_criar, status_criar = criar()
            with app.test_request_context("/api/pontos-estrategicos/1", method="POST", json=payload):
                resposta_atualizar, status_atualizar = atualizar(1)

        for resposta, status in (
            (resposta_criar, status_criar),
            (resposta_atualizar, status_atualizar),
        ):
            self.assertEqual(status, 400)
            self.assertNotEqual(status, 500)
            self.assertIn("Data de inclusao invalida", resposta.get_json()["erro"])

    def test_tela_exibe_a_mensagem_de_erro_da_api(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "pontos_estrategicos.html"
        ).read_text(encoding="utf-8")

        self.assertIn("catch (erro)", template)
        self.assertIn("toast(erro.message", template)


if __name__ == "__main__":
    unittest.main()
