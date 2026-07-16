import sqlite3
import unittest
from pathlib import Path

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

    def test_contexto_da_aba_prioriza_artigo_especifico(self):
        resultado = ajuda.consultar(
            rota="/registro-geografico", contexto="Edição em lotes"
        )
        self.assertEqual(resultado["contexto"][0]["id"], "registro-geografico-logradouros")

    def test_contexto_composto_reconhece_subaba_ativa(self):
        resultado = ajuda.consultar(
            rota="/esporotricose", contexto="Doentes > Lista", limite=120
        )
        ids = [artigo["id"] for artigo in resultado["contexto"]]
        self.assertIn("esporo-data-notificacao", ids)

    def test_catalogo_completo_retorna_categorias_e_total(self):
        resultado = ajuda.consultar(rota="/", limite=120, nivel="admin")
        self.assertEqual(resultado["total"], len(ajuda.ARTIGOS))
        self.assertEqual(len(resultado["artigos"]), len(ajuda.ARTIGOS))
        self.assertEqual(
            sum(categoria["total"] for categoria in resultado["categorias"]),
            resultado["total"],
        )
        self.assertIn("Esporotricose", [item["nome"] for item in resultado["categorias"]])

    def test_limite_invalido_usa_padrao_sem_falhar(self):
        resultado = ajuda.consultar(limite="invalido")
        self.assertEqual(len(resultado["artigos"]), 12)

    def test_artigo_administrativo_respeita_nivel_do_usuario(self):
        resultado = ajuda.consultar(consulta="backup", nivel="visualizador")
        ids = [artigo["id"] for artigo in resultado["artigos"]]
        self.assertNotIn("central-backup", ids)
        self.assertNotIn("backups", ids)

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
        self.assertIn('id="help-category-select"', html)
        self.assertIn('id="help-search-clear"', html)
        self.assertIn('id="help-results-count"', html)
        self.assertIn('/static/js/ajuda.js', html)

        javascript = (
            Path(__file__).resolve().parents[1] / "static" / "js" / "ajuda.js"
        ).read_text(encoding="utf-8")
        self.assertIn("limite: '120'", javascript)
        self.assertIn("join(' > ')", javascript)


if __name__ == "__main__":
    unittest.main()
