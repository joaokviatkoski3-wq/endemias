"""Fundação do GeoVSATT com banco SQLite sintético e sem acesso à produção."""

import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import app
from app_core import auth, db, dominios, sessoes
from scripts.preparar_massa_web_teste import preparar


class GeoVSATTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix=".tmp_test_geovsatt-", dir=Path(__file__).resolve().parents[1])
        cls.root = Path(cls.tmp.name)
        cls.seed = cls.root / "seed.db"
        preparar(cls.seed)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(dir=self.root))
        self.path = self.directory / "geo.db"
        shutil.copyfile(self.seed, self.path)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=1")
        common = {
            "DB_PATH": str(self.path),
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SETORES_ENABLED": True,
            "TERMOS_USO_ENABLED": False,
            "UPLOAD_TEMP": str(self.directory / "uploads"),
            "BACKUP_DIR": str(self.directory / "backups"),
            "BACKUP_COMPLETO_DIR": str(self.directory / "completos"),
            "KOBO_CONFIG_PATH": str(self.directory / "kobo.json"),
        }
        self.geo = app.create_app({**common, "SETOR": "geo"})
        self.endemias = app.create_app({**common, "SETOR": "endemias"})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE usuarios SET setor='ambiental' WHERE id_usuario=3")

    def client(self, application=None, uid=1):
        application = application or self.geo
        client = application.test_client()
        user = db.query_one(str(self.path), "SELECT * FROM usuarios WHERE id_usuario=?", (uid,))
        with application.app_context(), client.session_transaction() as session:
            session.update(
                uid=uid,
                nome=user["nome"],
                auth_token=auth.token_sessao(user["senha_hash"]),
                sessao_id=sessoes.criar(str(self.path), user),
            )
        return client

    def test_home_abre_mapa_novo_com_marca_e_popup(self):
        client = self.client()
        self.assertEqual(client.get("/").location, "/geovsatt")
        response = client.get("/geovsatt")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"geovsatt-symbol.svg", response.data)
        self.assertIn(b'id="geo-map"', response.data)
        self.assertIn(b'id="release-dialog"', response.data)
        self.assertNotIn(b"server.arcgisonline.com", response.data)

    def test_login_real_registra_auditoria_no_setor_geo(self):
        client = self.geo.test_client()
        response = client.post("/login", data={"usuario": "admin", "senha": "SenhaSomenteDeTeste123!"})
        self.assertEqual(response.status_code, 302)
        event = db.query_one(str(self.path), "SELECT setor FROM auditoria_eventos WHERE acao='login_sucesso' ORDER BY id_evento DESC LIMIT 1")
        self.assertEqual(event["setor"], "geo")

    def test_camadas_reais_busca_e_detalhe_rg(self):
        client = self.client()
        blocks = client.get("/api/geovsatt/camadas/quarteiroes")
        self.assertEqual(blocks.status_code, 200, blocks.json)
        self.assertGreater(len(blocks.json["features"]), 1000)
        self.assertEqual(blocks.json["metadata"]["camada"], "quarteiroes")
        streets = client.get("/api/geovsatt/camadas/logradouros")
        self.assertGreater(len(streets.json["features"]), 2000)
        localities = client.get("/api/geovsatt/camadas/localidades")
        self.assertTrue(localities.json["metadata"]["derivada"])
        self.assertGreater(len(localities.json["features"]), 1)
        summary = client.get("/api/geovsatt/busca?q=Localidade").json["resultados"]
        self.assertTrue(summary)
        detail = client.get("/api/geovsatt/quarteiroes/1/1")
        self.assertEqual(detail.status_code, 200, detail.json)
        self.assertIn("populacao_aproximada", detail.json["resumo"])

    def test_fronteira_geo_e_catalogo_administrativo(self):
        geo = self.client()
        self.assertEqual(geo.get("/visitas").status_code, 403)
        self.assertTrue(geo.get("/api/geovsatt/catalogo").json["pode_configurar"])
        self.assertEqual(self.client(self.endemias).get("/geovsatt").status_code, 403)

    def test_portal_e_dispatcher_incluem_geo(self):
        portal = dominios.portal_application("vsatt.com.br", external=False).test_client()
        response = portal.get("/", base_url="https://vsatt.com.br")
        self.assertIn(b"https://geo.vsatt.com.br", response.data)
        self.assertIn(b"geovsatt-logo.svg", response.data)
        dispatcher = dominios.application(self.endemias)
        self.assertIn("geo.vsatt.com.br", dispatcher.applications)
        self.assertEqual(dispatcher.applications["geo.vsatt.com.br"].config["SETOR"], "geo")

    def test_catalogo_importacao_publicacao_historico_e_acesso(self):
        admin = self.client()
        visualizador = self.client(uid=2)
        ambiental = self.client(uid=3)
        indicado = self.client(uid=4)
        gerencia = "/geovsatt/admin/camadas"
        camada = gerencia + "/bairros"
        api = "/api/geovsatt/camadas/bairros"
        configuracao = {"nome": "Limites de bairros", "grupo": "Território"}

        self.assertEqual(visualizador.get(gerencia).status_code, 403)
        self.assertEqual(visualizador.post(gerencia, data=configuracao).status_code, 403)
        self.assertEqual(admin.post(gerencia, data={**configuracao, "codigo": "bairros"}).location, camada)
        self.assertIn(b"Importar rascunho", admin.get(camada).data)

        def importar(nome, coords):
            dados = {"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {"nome": nome},
                "geometry": {"type": "Point", "coordinates": coords},
            }]}
            return admin.post(camada + "/importar", data={
                "geojson": (io.BytesIO(json.dumps(dados).encode()), "qgis.geojson"), "fonte": "QGIS sintético",
            }, follow_redirects=True)

        self.assertIn(b"Fei", importar("Inválido", [700000, 7220000]).data)
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM geovsatt_versoes"), 0)
        self.assertIn(b"Vers", importar("Primeira", [-49.3, -25.3]).data)
        self.assertEqual(admin.get(api).status_code, 404)
        self.assertEqual(admin.post(camada + "/versoes/1/publicar").status_code, 303)
        self.assertEqual(visualizador.get(api).status_code, 404)
        self.assertEqual(ambiental.get(camada + "/versoes/1/geojson").status_code, 403)

        admin.post(camada, data={**configuracao, "niveis": ["visualizador", "operador"], "setores": "endemias",
                                 "usuarios": "4", "cor": "#338899", "atributo_cor": "nome",
                                 "regras_cor": "Primeira = #024680", "visivel_inicial": "1", "rotulo": "nome"})
        resposta = visualizador.get(api)
        self.assertEqual(resposta.json["features"][0]["properties"]["nome"], "Primeira")
        self.assertIn("no-store", resposta.headers["Cache-Control"])
        self.assertEqual(ambiental.get(api).status_code, 404)
        self.assertEqual(indicado.get(api).status_code, 200)
        self.assertNotIn(b'data-layer="bairros"', ambiental.get("/geovsatt").data)
        self.assertIn(b'data-layer="bairros"', visualizador.get("/geovsatt").data)
        entrada = next(item for item in visualizador.get("/api/geovsatt/catalogo").json["camadas"] if item["id"] == "bairros")
        self.assertEqual(entrada["estilo"]["cores"], {"Primeira": "#024680"})
        self.assertNotIn("config", entrada)

        importar("Segunda", [-49.4, -25.4])
        admin.post(camada + "/versoes/2/publicar")
        self.assertEqual(visualizador.get(api).json["features"][0]["properties"]["nome"], "Segunda")
        admin.post(camada + "/versoes/1/publicar")
        admin.post(camada + "/versoes/999/publicar")
        self.assertEqual(visualizador.get(api).json["features"][0]["properties"]["nome"], "Primeira")
        admin.post(camada + "/versoes/1/metadados", data={"fonte": "Cartografia homologada", "data_referencia": "2026-11-26"})
        self.assertIn(b"Cartografia homologada", admin.get(camada).data)
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM geovsatt_versoes WHERE ativa=1"), 1)
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM auditoria_eventos WHERE acao='geovsatt_versao_publicada'"), 3)

    def test_permissao_camada_nativa_tambem_protege_busca_e_detalhe(self):
        admin = self.client()
        comum = self.client(uid=2)
        ambiental = self.client(uid=3)
        self.assertEqual(comum.get("/api/geovsatt/quarteiroes/1/1").status_code, 200)
        self.assertEqual(ambiental.get("/api/geovsatt/quarteiroes/1/1").status_code, 403)
        admin.post("/geovsatt/admin/camadas/quarteiroes", data={"nome": "Quarteirões", "grupo": "Território"})
        self.assertEqual(comum.get("/api/geovsatt/camadas/quarteiroes").status_code, 404)
        self.assertEqual(comum.get("/api/geovsatt/quarteiroes/1/1").status_code, 403)
        self.assertNotIn(b'data-layer="quarteiroes"', comum.get("/geovsatt").data)
        self.assertTrue(all(item["tipo"] == "localidade"
                            for item in comum.get("/api/geovsatt/busca?q=Localidade").json["resultados"]))


if __name__ == "__main__":
    unittest.main()
