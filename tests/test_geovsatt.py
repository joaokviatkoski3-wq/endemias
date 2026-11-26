"""Fundação do GeoVSATT com banco SQLite sintético e sem acesso à produção."""

import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import app
from app_core import auth, db, dominios, geovsatt_busca, registro_geografico, sessoes
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

    def test_malha_importada_substitui_o_desenho_e_preserva_vinculo_rg(self):
        client = self.client()
        nome = db.scalar(str(self.path), "SELECT nome FROM localidades WHERE id_localidade=1")
        geometria = {"type": "Polygon", "coordinates": [[[-49.3, -25.3], [-49.2, -25.3],
                       [-49.2, -25.25], [-49.3, -25.3]]]}
        for versao, (codigo, props) in enumerate((
            ("quarteiroes-qgis", {"Localidade": nome, "id_Q": "0001", "id_Q_antig": "A"}),
            ("localidades-areas-dispersas", {"nome": nome, "cod_loc": None}),
            ("limite-municipal", {}),
        ), 1):
            dados = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": props,
                     "geometry": geometria}]}
            resposta = client.post("/geovsatt/admin/importar", data={"nome": codigo, "codigo": codigo,
                "grupo": "Território", "fonte": "QGIS sintético",
                "geojson": (io.BytesIO(json.dumps(dados).encode()), f"{codigo}.geojson")})
            self.assertEqual(resposta.status_code, 303)
            self.assertEqual(client.post(f"/geovsatt/admin/camadas/{codigo}/versoes/{versao}/publicar").status_code, 303)
        camadas = {item['id']: item for item in client.get("/api/geovsatt/catalogo").json["camadas"]}
        self.assertNotIn("quarteiroes-qgis", camadas)
        self.assertNotIn("localidades-areas-dispersas", camadas)
        self.assertTrue(camadas["limite-municipal"]["disponivel"])
        quarteirao, = client.get("/api/geovsatt/camadas/quarteiroes").json["features"]
        self.assertEqual(quarteirao["geometry"], geometria)
        self.assertEqual(quarteirao["properties"]["chave"], "1:1")
        self.assertEqual(quarteirao["properties"]["id_Q_antig"], "A")
        localidade, = client.get("/api/geovsatt/camadas/localidades").json["features"]
        self.assertEqual(localidade["geometry"]["type"], "Polygon")
        self.assertEqual(localidade["properties"]["id_localidade"], 1)
        self.assertEqual(client.get("/api/geovsatt/quarteiroes/1/1").status_code, 200)

    def test_camadas_operacionais_e_perfis(self):
        client = self.client()
        ambiental = self.client(uid=3)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("""INSERT INTO ovitrampas_armadilhas(ovitrampa_id,localidade,latitude,longitude,atualizado_em)
                            VALUES('001','Ensaio',-25.301,-49.301,'2026-11-26')""")
            conn.execute("""INSERT INTO ovitrampas_leituras(id_leitura,ovitrampa_id,ano,semana,ovos,importado_em)
                            VALUES('teste','001',2026,45,12,'2026-11-26')""")
            conn.execute("""INSERT INTO pontos_estrategicos(codigo_pe,nome,latitude,longitude,criado_em,atualizado_em)
                            VALUES('001','Ponto de ensaio',-25.301,-49.301,'2026-11-26','2026-11-26')""")
            conn.execute("""INSERT INTO acoes_setor(tipo,data,local,coordenadas,criado_em)
                            VALUES('vistoria','2026-11-26','Ação de ensaio','-25.301, -49.301','2026-11-26')""")
        for codigo in ("ovitrampas", "pontos_estrategicos", "acoes_atendimentos"):
            url = f"/api/geovsatt/camadas/{codigo}"
            resultado = client.get(url)
            self.assertEqual(resultado.status_code, 200)
            ponto = next(p for p in resultado.json["features"] if p["geometry"]["coordinates"] == [-49.301, -25.301])
            self.assertNotIn("responsavel", ponto["properties"])
            self.assertEqual(ambiental.get(url).status_code, 404)
        dados = client.get("/api/geovsatt/camadas/ovitrampas").json["features"]
        self.assertTrue(any(p["properties"]["resultado"] == "Positiva" for p in dados))

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
        self.assertEqual(admin.post(gerencia, data={**configuracao, "codigo": "bairros"}).location, camada + "/importar")
        self.assertIn(b"Importar rascunho", admin.get(camada + "/importar").data)
        self.assertIn((camada + "/importar").encode(), admin.get("/geovsatt/admin/atualizar").data)

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

    def test_nova_camada_e_arquivo_formam_uma_operacao(self):
        admin = self.client()
        rota = "/geovsatt/admin/importar"
        self.assertEqual(self.client(uid=2).get(rota).status_code, 403)
        form = admin.get(rota)
        self.assertIn(b'type="file"', form.data)
        self.assertIn(b'/geovsatt/admin/atualizar', admin.get("/geovsatt/admin/camadas").data)
        campos = {"codigo": "nova", "nome": "Nova camada", "grupo": "Território", "fonte": "Massa fictícia"}
        erro = admin.post(rota, data={**campos, "geojson": (io.BytesIO(b"[]"), "invalido.geojson")})
        self.assertEqual(erro.status_code, 400)
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM geovsatt_camadas"), 0)
        dados = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                 "geometry": {"type": "Point", "coordinates": [-49.3, -25.3]}}]}
        ok = admin.post(rota, data={**campos, "geojson": (io.BytesIO(json.dumps(dados).encode()), "nova.geojson")})
        self.assertEqual(ok.location, "/geovsatt/admin/camadas/nova#versoes")
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM geovsatt_versoes WHERE ativa=0"), 1)

    def test_esporotricose_agrega_coordenadas_e_restringe_a_origem(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("""INSERT INTO esporotricose_doentes_animais(chave,nome,tutor,latitude,longitude,criado_em,atualizado_em)
                            VALUES ('ficticio','Animal de ensaio','Tutor de ensaio',-25.301,-49.301,'2026-11-26','2026-11-26')""")
        admin = self.client()
        comum = self.client(uid=2)
        ambiental = self.client(uid=3)
        rota = "/api/geovsatt/camadas/esporotricose"
        self.assertEqual(comum.get(rota).status_code, 404)
        self.assertEqual(ambiental.get(rota).status_code, 404)
        alvo = admin.get(rota)
        self.assertEqual(alvo.status_code, 200)
        self.assertNotIn(b'Tutor de ensaio', alvo.data)
        ponto, = alvo.json["features"]
        self.assertEqual(ponto["geometry"]["coordinates"], [-49.301, -25.301])
        admin.post("/geovsatt/admin/camadas/esporotricose", data={"nome": "Esporotricose animal",
                   "grupo": "Vigilância", "usuarios": ["2", "3"]})
        self.assertEqual(comum.get(rota).status_code, 404)
        agregado = ambiental.get(rota)
        self.assertEqual(agregado.status_code, 200)
        ponto, = agregado.json["features"]
        self.assertEqual(ponto["properties"]["animais"], 1)
        self.assertNotEqual(ponto["geometry"]["coordinates"], [-49.301, -25.301])

    def test_seletor_cep_e_base_de_satelite_no_mapa(self):
        client = self.client()
        mapa = client.get("/geovsatt")
        self.assertIn(b"CEP / BrasilAPI", mapa.data)
        self.assertIn(b'value="sentinel"', mapa.data)
        self.assertIn(b'value="esri"', mapa.data)
        self.assertLess(mapa.data.index(b'value="none"'), mapa.data.index(b'value="esri"'))
        with patch.dict(self.geo.config, {"GEOVSATT_ESRI_LICENSED": False}):
            self.assertNotIn(b'value="esri"', client.get("/geovsatt").data)
        csp = mapa.headers.get("Content-Security-Policy") or mapa.headers["Content-Security-Policy-Report-Only"]
        self.assertIn("https://tiles.maps.eox.at", csp)

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

    def test_endereco_completo_rg_busca_numero_exato_e_respeita_permissoes(self):
        termos = {"logradouro": "Rua Doutor João de Souza", "numero": "10", "localidade": "Localidade Ficticia",
                  "quarteirao": "0001", "observacao": "Praça Segredo Fictício"}
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("""
                UPDATE registro_geografico_imoveis SET logradouro=?,observacao=?,busca_normalizada=? WHERE id_imovel=1
            """, (termos["logradouro"], termos["observacao"], registro_geografico._busca_normalizada(termos)))
        permitido = self.client(uid=2)
        url = "/api/geovsatt/busca"
        consulta = "R. Dr. Joao de Souza, nº 010, Localidade Fictícia, Almirante Tamandaré - PR, 83500-000"
        resposta = permitido.post(url, json={"q": consulta})
        item, = resposta.json["resultados"]
        self.assertEqual(item["titulo"], "Rua Doutor João de Souza, 10")
        self.assertEqual(item["chave"], "1:1")
        self.assertEqual(item["imoveis"], [1])
        self.assertIn("Localidade Ficticia · Q. 1", item["subtitulo"])
        self.assertEqual(permitido.post(url, json={"q": "Doutor João de Souza 100"}).json["resultados"], [])
        self.assertEqual(permitido.post(url, json={"q": "Praça Segredo Fictício"}).json["resultados"], [])
        self.assertEqual(self.client(uid=3).post(url, json={"q": consulta}).json["resultados"], [])
        sugestao = permitido.post(url, json={"q": "João de Sou", "sugestao": True}).json["resultados"]
        self.assertEqual(sugestao[0]["titulo"], "Rua Doutor João de Souza")
        self.assertEqual(self.client(uid=3).post(url, json={"q": "João de Sou", "sugestao": True}).json["resultados"], [])
        self.client().post("/geovsatt/admin/camadas/quarteiroes", data={"nome": "Quarteirões", "grupo": "Território"})
        self.assertEqual(permitido.post(url, json={"q": consulta}).json["resultados"], [])

    def test_cep_passa_somente_o_codigo_e_identifica_origem(self):
        with patch.object(geovsatt_busca._CEP_HTTP, "open") as pedir:
            resposta = MagicMock(status=200)
            resposta.read.return_value = json.dumps({
                "street": "Rua Fictícia", "city": "Almirante Tamandaré", "state": "PR",
                "location": {"coordinates": {"longitude": "-49.3", "latitude": "-25.3"}},
            }).encode()
            pedir.return_value.__enter__.return_value = resposta
            client = self.client()
            self.assertEqual(client.get("/api/geovsatt/cep/abc").status_code, 400)
            pedir.assert_not_called()
            cep = client.get("/api/geovsatt/cep/83500-000").json
            self.assertEqual(cep["logradouro"], "Rua Fictícia")
            self.assertTrue(cep["municipio_rg"])
            self.assertNotIn("location", cep)
            requisicao = pedir.call_args.args[0]
            self.assertEqual(requisicao.full_url, "https://brasilapi.com.br/api/cep/v2/83500000")
            resposta.read.assert_called_once_with(16_385)
            pedir.side_effect = HTTPError(requisicao.full_url, 404, "Not found", {}, io.BytesIO())
            self.assertEqual(client.get("/api/geovsatt/cep/83500-000").status_code, 404)
            pedir.side_effect = HTTPError(requisicao.full_url, 301, "Moved", {}, io.BytesIO())
            self.assertEqual(client.get("/api/geovsatt/cep/83500-000").status_code, 502)


if __name__ == "__main__":
    unittest.main()
