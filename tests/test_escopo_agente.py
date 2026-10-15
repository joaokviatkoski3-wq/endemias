import tempfile
import unittest
from pathlib import Path

from flask import Flask, jsonify

from app_core import app_setup
from app_core import db as db_core
from app_core import escopo_agente
from app_core import modules as modules_core
from app_core import usuarios as usuarios_core


class TestEscopoAgente(unittest.TestCase):
    def test_nivel_restrito(self):
        self.assertTrue(escopo_agente.nivel_restrito({"nivel": "usuario"}))
        self.assertFalse(escopo_agente.nivel_restrito({"nivel": "visualizador"}))
        self.assertFalse(escopo_agente.nivel_restrito({}))
        self.assertFalse(escopo_agente.nivel_restrito(None))

    def test_redigir_agentes(self):
        chaves = {"joao"}
        payload = {
            "agentes": "João, Maria",
            "laboratorista": "Maria",
            "morador": "Carlos",
            "por_agente": [{"agente": "Maria", "total": 3}],
            "por_laboratorista": [{"agente": "Maria", "total": 1}],
            "eventos": [{"agentes": ["João", "Maria"], "titulo": "Campo"}],
            "aninhado": {"agente": "Maria", "endereco": "Rua A"},
        }
        resultado = escopo_agente.redigir_agentes(payload, chaves)
        self.assertEqual(resultado["agentes"], "João, —")
        self.assertEqual(resultado["laboratorista"], "—")
        self.assertEqual(resultado["morador"], "Carlos")
        self.assertEqual(resultado["por_agente"], [])
        self.assertEqual(resultado["por_laboratorista"], [])
        self.assertEqual(resultado["eventos"][0]["agentes"], ["João", "—"])
        self.assertEqual(resultado["eventos"][0]["titulo"], "Campo")

    def test_redigir_sem_vinculo_oculta_tudo(self):
        resultado = escopo_agente.redigir_agentes(
            {"agentes": "João, Maria"}, set()
        )
        self.assertEqual(resultado["agentes"], "—, —")

    def test_redigir_nome_completo_proprio(self):
        # O proprio agente pode aparecer pelo nome completo.
        chaves = {"joao", "joaosilva"}
        resultado = escopo_agente.redigir_agentes(
            {"agentes": "João Silva, Maria"}, chaves
        )
        self.assertEqual(resultado["agentes"], "João Silva, —")

    def test_filtrar_agentes(self):
        chaves = {"joao"}
        self.assertEqual(escopo_agente.filtrar_agentes(["João", "Maria"], chaves), ["João"])
        self.assertEqual(
            escopo_agente.filtrar_agentes(
                [{"id_agente": 1, "nome": "João"}, {"id_agente": 2, "nome": "Maria"}],
                chaves,
            ),
            [{"id_agente": 1, "nome": "João"}],
        )
        self.assertEqual(escopo_agente.filtrar_agentes(["João", "Maria"], set()), [])

    def test_agente_proprio_resolve_por_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            caminho = str(Path(tmpdir) / "teste.db")
            target = db_core.DatabaseTarget("sqlite", caminho)
            conn = db_core.connect(target)
            conn.execute(
                "CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, "
                "nome TEXT, nome_completo TEXT, ativo INTEGER DEFAULT 1)"
            )
            conn.execute(
                "INSERT INTO agentes (id_agente, nome, nome_completo, ativo) "
                "VALUES (1, 'João', 'João Silva', 1)"
            )
            conn.commit()
            conn.close()

            agente = escopo_agente.agente_proprio(target, {"id_agente": 1})
            self.assertEqual(agente["nome"], "João")
            self.assertIn("joao", agente["chaves"])
            self.assertIn("joaosilva", agente["chaves"])

            self.assertIsNone(escopo_agente.agente_proprio(target, {}))
            self.assertIsNone(escopo_agente.agente_proprio(target, {"id_agente": None}))
            self.assertIsNone(escopo_agente.agente_proprio(target, {"id_agente": 999}))

    def test_agente_proprio_inativo_retorna_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            caminho = str(Path(tmpdir) / "teste.db")
            target = db_core.DatabaseTarget("sqlite", caminho)
            conn = db_core.connect(target)
            conn.execute(
                "CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, "
                "nome TEXT, nome_completo TEXT, ativo INTEGER DEFAULT 1)"
            )
            conn.execute(
                "INSERT INTO agentes (id_agente, nome, nome_completo, ativo) "
                "VALUES (1, 'João', 'João Silva', 0)"
            )
            conn.commit()
            conn.close()
            self.assertIsNone(escopo_agente.agente_proprio(target, {"id_agente": 1}))


class TestNivelUsuario(unittest.TestCase):
    def test_valid_levels_inclui_usuario(self):
        self.assertIn("usuario", usuarios_core.VALID_LEVELS)

    def test_hierarquias_incluem_usuario(self):
        self.assertEqual(modules_core.LEVEL_ORDER.get("usuario"), 1)

    def test_criar_usuario_aceita_nivel_usuario(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            caminho = str(Path(tmpdir) / "teste.db")
            target = db_core.DatabaseTarget("sqlite", caminho)
            conn = db_core.connect(target)
            conn.execute(
                """CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY,
                nome TEXT, nome_completo TEXT, ativo INTEGER DEFAULT 1)"""
            )
            conn.execute(
                "CREATE TABLE usuarios ("
                "id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, nome TEXT, "
                "senha_hash TEXT, nivel TEXT, ativo INTEGER, criado_em TEXT, "
                "acesso_laboratorio INTEGER, somente_laboratorio INTEGER, id_agente INTEGER)"
            )
            conn.execute(
                "INSERT INTO agentes (id_agente, nome, ativo) VALUES (1, 'João', 1)"
            )
            conn.commit()
            conn.close()

            novo_id = usuarios_core.criar(
                target,
                {
                    "usuario": "joao.campo",
                    "nome": "João",
                    "senha": "senha-segura-123",
                    "nivel": "usuario",
                    "id_agente": 1,
                },
            )
            self.assertGreater(novo_id, 0)


class TestRedacaoViaApp(unittest.TestCase):
    def _montar_app(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        caminho = str(Path(tmpdir.name) / "teste.db")
        target = db_core.DatabaseTarget("sqlite", caminho)
        conn = db_core.connect(target)
        conn.execute(
            "CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, "
            "nome TEXT, nome_completo TEXT, ativo INTEGER DEFAULT 1)"
        )
        conn.execute(
            "INSERT INTO agentes (id_agente, nome, ativo) VALUES (1, 'João', 1)"
        )
        conn.execute(
            "CREATE TABLE usuarios (id_usuario INTEGER PRIMARY KEY, nome TEXT, "
            "nivel TEXT, ativo INTEGER, id_agente INTEGER)"
        )
        conn.execute(
            "INSERT INTO usuarios (id_usuario, nome, nivel, ativo, id_agente) "
            "VALUES (1, 'João', 'usuario', 1, 1)"
        )
        conn.commit()
        conn.close()

        app = Flask(__name__)
        app.secret_key = "teste"
        app.config["DB_TARGET"] = target
        app.config["TESTING"] = True

        @app.route("/api/exemplo")
        def exemplo():
            return jsonify({
                "agentes": "João, Maria",
                "por_agente": [{"agente": "Maria", "total": 2}],
                "morador": "Carlos",
            })

        app_setup.register_response_redaction(app)
        return app

    def test_redige_resposta_json_para_usuario_restrito(self):
        app = self._montar_app()
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["uid"] = 1
        resp = client.get("/api/exemplo")
        self.assertEqual(resp.status_code, 200)
        dados = resp.get_json()
        self.assertEqual(dados["agentes"], "João, —")
        self.assertEqual(dados["por_agente"], [])
        self.assertEqual(dados["morador"], "Carlos")

    def test_nao_redige_para_outros_niveis(self):
        app = self._montar_app()
        conn = db_core.connect(app.config["DB_TARGET"])
        conn.execute("UPDATE usuarios SET nivel='visualizador' WHERE id_usuario=1")
        conn.commit()
        conn.close()
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["uid"] = 1
        resp = client.get("/api/exemplo")
        self.assertEqual(resp.get_json()["agentes"], "João, Maria")


if __name__ == "__main__":
    unittest.main()
