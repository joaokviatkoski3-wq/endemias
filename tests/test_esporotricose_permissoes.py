import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app_core import esporotricose as esporotricose_core
from blueprints.esporotricose import bp


ROOT = Path(__file__).resolve().parents[1]


class EsporotricosePermissoesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "permissoes.db"
        self.app = Flask(
            __name__,
            template_folder=str(ROOT / "templates"),
            static_folder=str(ROOT / "static"),
        )
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="teste-permissoes",
            DB_PATH=str(self.db_path),
            ANEXOS_DIR=str(Path(self.tmp.name) / "anexos"),
        )
        self.app.register_blueprint(bp)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE usuarios (
                    id_usuario INTEGER PRIMARY KEY,
                    usuario TEXT NOT NULL,
                    nome TEXT NOT NULL,
                    nivel TEXT NOT NULL,
                    ativo INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO usuarios (id_usuario, usuario, nome, nivel, ativo)
                VALUES (?, ?, ?, ?, 1)
                """,
                [
                    (1, "leitor", "Usuário visualizador", "visualizador"),
                    (2, "operador", "Usuário operador", "operador"),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _client_logado(self, id_usuario):
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["uid"] = id_usuario
        return client

    def test_visualizador_nao_altera_dados_da_esporotricose(self):
        client = self._client_logado(1)
        operacoes = [
            ("PUT", "/api/esporotricose/visitas/visita-1"),
            ("PUT", "/api/esporotricose/animais/animal-1"),
            ("POST", "/api/esporotricose/animais/animal-1/buscas-ferido"),
            ("POST", "/api/esporotricose/doentes/status"),
            ("POST", "/api/esporotricose/doentes/estoque"),
            ("PUT", "/api/esporotricose/doentes/estoque/1"),
            ("DELETE", "/api/esporotricose/doentes/estoque/1"),
            ("PUT", "/api/esporotricose/doentes/estoque/automatico/1"),
            ("POST", "/api/esporotricose/doentes"),
            ("PUT", "/api/esporotricose/doentes/1"),
            ("DELETE", "/api/esporotricose/doentes/1"),
            ("POST", "/api/esporotricose/doentes/1/receitas"),
            ("PUT", "/api/esporotricose/doentes/receitas/1"),
            ("DELETE", "/api/esporotricose/doentes/receitas/1"),
            ("POST", "/api/esporotricose/doentes/receitas/1/entregas"),
            ("PUT", "/api/esporotricose/doentes/entregas/1"),
            ("DELETE", "/api/esporotricose/doentes/entregas/1"),
            ("POST", "/api/esporotricose/doentes/1/anexos"),
            ("DELETE", "/api/esporotricose/doentes/anexos/1"),
        ]

        for metodo, caminho in operacoes:
            with self.subTest(metodo=metodo, caminho=caminho):
                resposta = client.open(caminho, method=metodo, json={})
                self.assertEqual(resposta.status_code, 403)
                self.assertIn("permissão", resposta.get_json()["erro"])

    def test_visualizador_continua_acessando_consultas(self):
        client = self._client_logado(1)
        with (
            patch.object(esporotricose_core, "status_doentes", return_value=[]),
            patch.object(esporotricose_core, "estoque_medicacao", return_value={"movimentos": []}),
            patch.object(esporotricose_core, "obter_doente", return_value={"id_animal_doente": 1, "anexos": []}),
        ):
            caminhos = [
                "/api/esporotricose/doentes/status",
                "/api/esporotricose/doentes/estoque",
                "/api/esporotricose/doentes/1",
                "/api/esporotricose/doentes/1/anexos",
            ]
            for caminho in caminhos:
                with self.subTest(caminho=caminho):
                    self.assertEqual(client.get(caminho).status_code, 200)

    def test_visualizador_nao_abre_formularios_de_edicao(self):
        client = self._client_logado(1)
        with patch("app_core.auth.render_template", return_value="Sem permissão"):
            for caminho in [
                "/esporotricose/doentes/novo",
                "/esporotricose/doentes/1/editar",
            ]:
                with self.subTest(caminho=caminho):
                    self.assertEqual(client.get(caminho).status_code, 403)

    def test_operador_pode_criar_doente(self):
        client = self._client_logado(2)
        animal = {"id_animal_doente": 7, "animal": "Teste"}
        with (
            patch.object(esporotricose_core, "salvar_doente", return_value=7),
            patch.object(esporotricose_core, "obter_doente", return_value=animal),
        ):
            resposta = client.post("/api/esporotricose/doentes", json={"animal": "Teste"})

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.get_json(), animal)


if __name__ == "__main__":
    unittest.main()
