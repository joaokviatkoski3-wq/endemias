import sqlite3
import unittest

import app as endemias_app
from app_core import ajuda


class AjudaTests(unittest.TestCase):
    def test_contexto_prioriza_artigos_da_pagina_atual(self):
        resultado = ajuda.consultar(rota="/registro-geografico")
        ids = [artigo["id"] for artigo in resultado["contexto"]]
        self.assertIn("registro-geografico-consulta", ids)
        self.assertIn("registro-geografico-edicao", ids)

    def test_busca_encontra_termos_com_acentos(self):
        resultado = ajuda.consultar(consulta="impressão quarteirão", rota="/")
        ids = [artigo["id"] for artigo in resultado["artigos"]]
        self.assertIn("registro-geografico-impressao", ids)

    def test_busca_sem_resultado_retorna_lista_vazia(self):
        resultado = ajuda.consultar(consulta="zxqv sem correspondencia")
        self.assertEqual(resultado["artigos"], [])

    def test_api_exige_login_e_retorna_contexto_para_usuario_logado(self):
        endemias_app.app.config["TESTING"] = True
        client = endemias_app.app.test_client()
        self.assertEqual(client.get("/api/ajuda").status_code, 302)

        conn = sqlite3.connect(endemias_app.DB_PATH)
        try:
            user = conn.execute(
                "SELECT id_usuario, nome, nivel FROM usuarios WHERE ativo=1 ORDER BY id_usuario LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(user)
        with client.session_transaction() as session:
            session["uid"], session["nome"], session["nivel"] = user
        response = client.get("/api/ajuda?rota=/ovitrampas&q=diario")
        self.assertEqual(response.status_code, 200)
        ids = [artigo["id"] for artigo in response.get_json()["artigos"]]
        self.assertIn("ovitrampas-diarios", ids)

        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        html = page.data.decode("utf-8")
        self.assertIn('id="help-launcher"', html)
        self.assertIn('/static/js/ajuda.js', html)


if __name__ == "__main__":
    unittest.main()
