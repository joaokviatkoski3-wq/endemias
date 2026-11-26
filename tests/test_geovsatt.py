"""Fundação do GeoVSATT com banco SQLite sintético e sem acesso à produção."""

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import app
from app_core import auth, db, dominios, sessoes
from scripts.preparar_massa_web_teste import preparar


class GeoVSATTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(__file__).resolve().parents[1] / ".tmp_test_geovsatt"
        cls.scratch.mkdir(exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(dir=cls.scratch)
        cls.root = Path(cls.tmp.name)
        cls.seed = cls.root / "seed.db"
        preparar(cls.seed)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.scratch.rmdir()

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(dir=self.root))
        self.path = self.directory / "geo.db"
        shutil.copyfile(self.seed, self.path)
        connection = sqlite3.connect(self.path)
        connection.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=1")
        connection.commit()
        connection.close()
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


if __name__ == "__main__":
    unittest.main()
