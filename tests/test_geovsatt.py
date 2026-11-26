"""Fundação do GeoVSATT com banco SQLite sintético e sem acesso à produção."""

import csv
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from collections import OrderedDict
from base64 import b64decode
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree as ET

from PIL import Image
from shapely.geometry import box, mapping, shape

import app
from app_core import auth, db, dominios, geovsatt_busca, geovsatt_openfreemap, liraa, liraa_kobo, registro_geografico, sessoes
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
            "ANEXOS_DIR": str(self.directory / "anexos"),
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
        self.assertIn(b'id="geo-composicao"', response.data)
        self.assertIn(b'id="release-dialog"', response.data)
        self.assertIn(b'id="geo-detail-source"', response.data)
        self.assertIn(b'id="geo-key-logradouros"', response.data)
        self.assertIn(b'id="geo-calor-camada"', response.data)
        self.assertNotIn(b"server.arcgisonline.com", response.data)

    def test_login_real_registra_auditoria_no_setor_geo(self):
        client = self.geo.test_client()
        response = client.post("/login", data={"usuario": "admin", "senha": "SenhaSomenteDeTeste123!"})
        self.assertEqual(response.status_code, 302)
        event = db.query_one(str(self.path), "SELECT setor FROM auditoria_eventos WHERE acao='login_sucesso' ORDER BY id_evento DESC LIMIT 1")
        self.assertEqual(event["setor"], "geo")

    def test_manifesto_e_worker_geo_tem_escopo_proprio_e_pagina_sem_dados(self):
        client = self.geo.test_client()
        manifest_url = "/geovsatt/manifest.webmanifest"
        with closing(client.get(manifest_url)) as manifest:
            self.assertEqual(manifest.status_code, 200)
            self.assertEqual(manifest.mimetype, "application/manifest+json")
            dados = json.loads(manifest.data)
        self.assertEqual(dados["start_url"], "/geovsatt")
        self.assertEqual(dados["scope"], "/geovsatt")
        for icone in dados["icons"]:
            dimensoes = tuple(map(int, icone["sizes"].split("x")))
            with closing(client.get(icone["src"])) as resposta, Image.open(io.BytesIO(resposta.data)) as imagem:
                self.assertEqual(imagem.size, dimensoes)
        with closing(client.get("/geovsatt-sw.js")) as worker:
            self.assertEqual(worker.headers["Service-Worker-Allowed"], "/geovsatt")
            self.assertEqual(worker.mimetype, "application/javascript")
            self.assertIn("no-store", worker.headers["Cache-Control"])
        self.assertEqual(self.endemias.test_client().get(manifest_url).status_code, 403)
        self.assertNotEqual(client.get("/geovsatt").status_code, 200)
        pagina = client.get("/geovsatt/offline")
        self.assertEqual(pagina.status_code, 200)
        self.assertIn(b"GeoVSATT offline", pagina.data)
        self.assertIn(b'id="geo-map"', pagina.data)
        self.assertIn(b'data-pode-rg="0" hidden', pagina.data)
        self.assertIn(b'name="csrf-token" content=""', pagina.data)
        self.assertNotIn(b'data-conta=', pagina.data)
        self.assertNotIn(b'action="/logout"', pagina.data)
        self.assertIn(b'geovsatt_campo.mjs', pagina.data)

    def test_pacote_offline_exige_permissao_de_download_e_usa_dados_do_mapa(self):
        admin = self.client()
        comum = self.client(uid=2)
        rota = "/api/geovsatt/pacote-offline"
        escolhas = {"camadas": ["localidades", "logradouros", "localidades"]}
        self.assertNotEqual(self.geo.test_client().post(rota, json=escolhas).status_code, 200)
        self.assertEqual(comum.post(rota, json=escolhas).status_code, 403)
        self.assertEqual(admin.post(rota, json={"camadas": [["logradouros"]]}).status_code, 400)
        self.assertEqual(admin.post(rota, json={"camadas": ["camada-desconhecida"]}).status_code, 403)
        resposta = admin.post(rota, json=escolhas)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("no-store", resposta.headers["Cache-Control"])
        self.assertEqual(resposta.json["formato"], 1)
        self.assertEqual(resposta.json["usuario"], 1)
        self.assertEqual([item["id"] for item in resposta.json["camadas"]], ["localidades", "logradouros"])
        self.assertEqual(resposta.json["dados"]["localidades"], admin.get("/api/geovsatt/camadas/localidades").json)
        self.assertEqual(resposta.json["dados"]["logradouros"], admin.get("/api/geovsatt/camadas/logradouros").json)

    def test_base_openfreemap_offline_aceita_recorte_explicito_e_estilo_local(self):
        cliente = self.client(uid=2)
        rota = "/api/geovsatt/pacote-offline/openfreemap"
        recorte = [-49.31, -25.33, -49.309, -25.329]
        self.assertNotEqual(self.geo.test_client().post(rota, json={"recorte": recorte, "limite": 1000}).status_code, 200)
        self.assertEqual(cliente.post(rota, json={"recorte": [-180, -90, 180, 90], "limite": 1000}).status_code, 400)
        self.assertEqual(cliente.post(rota, json={"recorte": recorte, "limite": 0}).status_code, 400)
        preparo = cliente.post("/api/geovsatt/pacote-offline", json={"camadas": [], "openfreemap": True})
        self.assertEqual(preparo.status_code, 200)
        self.assertEqual(preparo.json["camadas"], [])

        origem = "https://tiles.openfreemap.org"
        def upstream(path, **opcoes):
            if path == "/styles/positron":
                return json.dumps({"sources": {"openmaptiles": {"url": origem + "/backup_planet"}},
                                   "sprite": origem + "/sprites/teste/ofm",
                                   "glyphs": origem + "/fonts/{fontstack}/{range}.pbf",
                                   "layers": [{"id": "ruas", "type": "symbol", "source": "openmaptiles",
                                               "layout": {"text-field": ["get", "name"], "text-font": ["Noto Sans Regular"]}},
                                              {"id": "outra", "type": "raster", "source": "ne2_shaded"}]}).encode()
            if path == "/backup_planet":
                return json.dumps({"maxzoom": 14, "tiles": [origem + "/backup_planet/ensaio/{z}/{x}/{y}.pbf"]}).encode()
            return b"dados ficticios"

        with patch.object(geovsatt_openfreemap, "_recurso", side_effect=upstream):
            resposta = cliente.post(rota, json={"recorte": recorte, "limite": 50_000})
            self.assertEqual(resposta.mimetype, "application/x-ndjson")
            self.assertIn("no-store", resposta.headers["Cache-Control"])
            linhas = [json.loads(linha) for linha in resposta.data.splitlines()]
            plano = linhas[1]
            self.assertEqual([item["id"] for item in plano["estilo"]["layers"]], ["ruas"])
            self.assertTrue(plano["estilo"]["glyphs"].startswith("geovsatt-ofm://"))
            self.assertEqual(plano["estilo"]["sources"]["openmaptiles"]["bounds"], recorte)
            self.assertEqual(linhas[-1], {"concluido": True})
            self.assertEqual(len(linhas[2:-1]), plano["total"])
            excedida = cliente.post(rota, json={"recorte": recorte, "limite": 50})
            self.assertIn("erro", json.loads(excedida.data.splitlines()[-1]))
            self.assertNotIn(b'"concluido"', excedida.data)

    def test_pacote_offline_rg_explicito_entrega_campos_do_mapa_e_estimativa(self):
        admin = self.client()
        with closing(sqlite3.connect(self.path)) as conn:
            nome = conn.execute("SELECT nome FROM localidades WHERE id_localidade=1").fetchone()[0]
        forma = {"type": "Feature", "properties": {"Localidade": nome, "id_Q": "0001"},
                 "geometry": mapping(box(-49.31, -25.33, -49.30, -25.32))}
        coleta = io.BytesIO(json.dumps({"type": "FeatureCollection", "features": [forma]}).encode())
        slug = "quarteiroes-qgis"
        self.assertEqual(admin.post("/geovsatt/admin/importar", data={
            "nome": "Quarteirões de ensaio", "codigo": slug, "grupo": "Território", "fonte": "Ensaio",
            "geojson": (coleta, "quarteiroes.geojson"),
        }).status_code, 303)
        self.assertEqual(admin.post(f"/geovsatt/admin/camadas/{slug}/versoes/1/publicar").status_code, 303)
        rota = "/api/geovsatt/pacote-offline"
        self.assertEqual(admin.post(rota, json={"camadas": ["localidades"], "enderecos": True}).status_code, 403)
        dados = admin.post(rota, json={"camadas": ["quarteiroes"]}).json
        self.assertNotIn("rg", dados)
        self.assertEqual(dados["populacao"]["media"], 2.93)
        dados = admin.post(rota, json={"camadas": ["quarteiroes"], "enderecos": True}).json
        no_mapa = admin.get("/api/geovsatt/quarteiroes/1/1").json
        bloco = dados["rg"]["1:1"]
        self.assertEqual(bloco["resumo"], no_mapa["resumo"])
        self.assertEqual(bloco["registros"][0]["logradouro"], no_mapa["registros"][0]["logradouro"])
        self.assertEqual(set(bloco["registros"][0]), {"id_imovel", "logradouro", "numero", "sequencia",
                                                      "tipo", "tipo_label", "agentes"})

    def test_cadastro_equipamentos_preserva_acervo_historico_e_permissoes(self):
        admin = self.client()
        comum = self.client(uid=2)
        cadastro = "/geovsatt/admin/equipamentos"
        camada = "/geovsatt/admin/camadas/predios_publicos"
        mapa = "/api/geovsatt/camadas/predios_publicos"
        self.assertEqual(comum.get(cadastro).status_code, 403)
        self.assertEqual(comum.post(cadastro + "/novo", data={}).status_code, 403)
        ref = Path(self.geo.config["BASE_DIR"]) / "dados_referencia/equipamentos_publicos.csv"
        with ref.open(encoding="utf-8-sig", newline="") as arquivo:
            origem = next(row for row in csv.DictReader(arquivo) if row["servicos_no_local"] and row["horario"])
        ponto = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(origem["longitude"]), float(origem["latitude"])]},
                 "properties": {"nome": origem["nome"], "tipo": origem["tipo"], "campo_qgis": "preservado"}}
        dados = io.BytesIO(json.dumps({"type": "FeatureCollection", "features": [ponto]}).encode())
        self.assertEqual(admin.post("/geovsatt/admin/importar", data={"nome": "Equipamentos", "codigo": "predios_publicos",
            "grupo": "Equipamentos", "fonte": "Referência de teste", "geojson": (dados, "equip.geojson")}).status_code, 303)
        self.assertEqual(admin.post(camada + "/versoes/1/publicar").status_code, 303)
        prefill = admin.get(cadastro + "/novo?latitude=-25.312345&longitude=-49.321234")
        self.assertIn(b'value="-25.312345"', prefill.data)
        inicial = admin.get(mapa).json["features"][0]["properties"]
        self.assertEqual(inicial["servicos_no_local"], origem["servicos_no_local"])
        self.assertNotIn("telefone", inicial)

        novo = {"nome": "Posto de ensaio", "tipo": "SAÚDE", "latitude": "-25,31", "longitude": "-49.32",
                "versao": "1", "cep": "83500000", "servicos_no_local": "Atendimento de ensaio"}
        self.assertEqual(admin.post(cadastro + "/novo", data={**novo, "latitude": "95"}).status_code, 400)
        self.assertEqual(admin.post(cadastro + "/novo", data=novo).status_code, 303)
        self.assertEqual(admin.post(cadastro + "/novo", data=novo).status_code, 409)
        versao = admin.get(mapa).json
        self.assertEqual(versao["metadata"]["versao"], 2)
        self.assertEqual(len(versao["features"]), 2)
        self.assertEqual(versao["features"][1]["geometry"]["coordinates"], [-49.32, -25.31])
        self.assertEqual(versao["features"][1]["properties"]["cep"], "83500-000")
        self.assertIn(b"Posto de ensaio", admin.get(cadastro + "?q=posto").data)
        editado = {**novo, "versao": "2", "nome": "Equipamento corrigido", "horario": origem["horario"],
                   "servicos_no_local": origem["servicos_no_local"]}
        self.assertEqual(admin.post(cadastro + "/2/0/editar", data=editado).status_code, 303)
        pontos = admin.get(mapa).json["features"]
        self.assertEqual(pontos[0]["properties"]["campo_qgis"], "preservado")
        self.assertEqual(pontos[0]["properties"]["nome"], "Equipamento corrigido")
        self.assertEqual(pontos[1]["properties"]["nome"], "Posto de ensaio")
        self.assertEqual(len(admin.get(camada + "/versoes/1/geojson").json["features"]), 1)
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM auditoria_eventos WHERE acao='geovsatt_equipamento_salvo'"), 2)

    def test_composicoes_privadas_restauram_configuracao_e_reavaliam_permissoes(self):
        rota = "/api/geovsatt/composicoes"
        admin = self.client()
        titular = self.client(uid=2)
        outro = self.client(uid=3)
        dados = {"titulo": "Mapa em retrato", "nota": "Visita de ensaio", "orientacao": "retrato", "layout": "lateral",
                 "base": "esri", "legenda": True, "centro": [-25.31, -49.30], "zoom": 16,
                 "camadas": ["quarteiroes", "logradouros"], "filtros": {"logradouros": [{"field": "nome", "match": "filled", "value": ""}]}}
        invalida = {**dados, "camadas": [*dados["camadas"], "esporotricose"]}
        self.assertEqual(titular.post(rota, json=invalida).status_code, 400)
        criada = titular.post(rota, json=dados)
        self.assertEqual(criada.status_code, 201, criada.json)
        item = f'{rota}/{criada.json["id_composicao"]}'
        self.assertEqual(titular.get(rota).json[0]["titulo"], "Mapa em retrato")
        self.assertEqual(titular.get(item).json["configuracao"], dados)
        vetorial = titular.post(rota, json=dados | {"base": "openfreemap"})
        self.assertEqual(vetorial.status_code, 201)
        self.assertEqual(titular.get(f'{rota}/{vetorial.json["id_composicao"]}').json["configuracao"]["base"], "openfreemap")
        self.assertEqual(outro.get(rota).json, [])
        self.assertEqual(admin.get(item).status_code, 404)
        entrada = {**dados, "titulo": "Nova revisão", "atualizada_em": criada.json["atualizada_em"]}
        self.assertEqual(admin.put(item, json=entrada).status_code, 404)
        self.assertEqual(titular.put(item, json=entrada).status_code, 200)
        self.assertEqual(titular.put(item, json=entrada).status_code, 409)
        admin.post("/geovsatt/admin/camadas/logradouros", data={"nome": "Logradouros", "grupo": "Território"})
        with patch.dict(self.geo.config, {"GEOVSATT_ESRI_LICENSED": False}):
            revisada = titular.get(item).json
        self.assertEqual(revisada["camadas_indisponiveis"], 1)
        self.assertTrue(revisada["base_indisponivel"])
        self.assertEqual(revisada["configuracao"]["base"], "none")
        self.assertEqual(revisada["configuracao"]["camadas"], ["quarteiroes"])
        self.assertEqual(revisada["configuracao"]["filtros"], {})

    def test_ortofoto_privada_com_rascunho_metadados_e_restauracao(self):
        def arquivo_mbtiles(nome, cor, formato="png"):
            caminho = self.directory / nome
            imagem = io.BytesIO()
            Image.new("RGB", (256, 256), cor).save(imagem, format="JPEG" if formato == "jpg" else "PNG")
            with closing(sqlite3.connect(caminho)) as conn, conn:
                conn.executescript("""
                    CREATE TABLE metadata(name text PRIMARY KEY, value text);
                    CREATE TABLE tiles(zoom_level integer,tile_column integer,tile_row integer,tile_data blob,
                                       PRIMARY KEY(zoom_level,tile_column,tile_row));
                """)
                conn.execute("INSERT INTO metadata VALUES ('format',?)", (formato,))
                conn.execute("INSERT INTO tiles VALUES (15,11896,13998,?)", (imagem.getvalue(),))
            return caminho.read_bytes(), imagem.getvalue()

        admin = self.client()
        comum = self.client(uid=2)
        ambiental = self.client(uid=3)
        importa = "/geovsatt/admin/ortofotos/importar"
        gestor = "/geovsatt/admin/camadas/ortofoto-ensaio"
        publico = "/api/geovsatt/ortofotos/ortofoto-ensaio"
        painel = "/geovsatt/admin/ortofotos/ortofoto-ensaio/"
        download = "/geovsatt/camadas/ortofoto-ensaio/exportar/mbtiles"
        catalogo = "/api/geovsatt/catalogo"
        campos = {"nome": "Ortofoto de ensaio", "codigo": "ortofoto-ensaio", "grupo": "Imagens e bases",
                  "fonte": "Fonte de ensaio", "data_referencia": "2025-05-10", "licenca": "Uso de ensaio"}
        bruto1, png1 = arquivo_mbtiles("primeiro.mbtiles", "#11686e")
        bruto2, jpeg2 = arquivo_mbtiles("segundo.mbtiles", "#8a452d", "jpg")
        invalido, _ = arquivo_mbtiles("vetorial.mbtiles", "#222222", "pbf")
        self.assertIn(b'Nova ortofoto MBTiles', admin.get("/geovsatt/admin/camadas").data)
        self.assertIn(b'name="mbtiles"', admin.get(importa).data)
        self.assertEqual(comum.get(importa).status_code, 403)
        self.assertEqual(admin.post(importa, data=campos | {"mbtiles": (io.BytesIO(invalido), "vetorial.mbtiles")}).status_code, 400)
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM geovsatt_camadas"), 0)
        enviada = admin.post(importa, data=campos | {"mbtiles": (io.BytesIO(bruto1), "primeiro.mbtiles")})
        self.assertEqual(enviada.status_code, 303, enviada.data[:500])
        self.assertEqual(admin.get(catalogo).json["ortofotos"], [])
        self.assertIn(b'Mosaico de amostra da', admin.get(gestor).data)
        self.assertEqual(admin.get(painel + "versoes/1/amostra").data, png1)
        self.assertEqual(admin.get(gestor + "/versoes/1/geojson").status_code, 404)
        rota1 = f"{publico}/1/15/11896/18769"
        rota2 = f"{publico}/2/15/11896/18769"
        self.assertEqual(admin.get(rota1).status_code, 404)
        self.assertEqual(comum.get(painel + "versoes/1/amostra").status_code, 403)
        admin.post(gestor + "/versoes/1/metadados", data=campos | {"fonte": "Fonte revisada"})
        self.assertEqual(admin.post(gestor + "/versoes/1/publicar").status_code, 303)
        dados, = admin.get(catalogo).json["ortofotos"]
        self.assertEqual((dados["versao"], dados["fonte"], dados["zoom_max"]), (1, "Fonte revisada", 15))
        self.assertEqual(admin.get("/api/geovsatt/camadas/ortofoto-ensaio").status_code, 404)
        imagem = admin.get(rota1)
        self.assertEqual((imagem.mimetype, imagem.data), ("image/png", png1))
        self.assertEqual(imagem.headers["Cache-Control"], "private, no-store")
        vazia = admin.get(f"{publico}/1/15/11897/18769")
        with Image.open(io.BytesIO(vazia.data)) as transparente:
            self.assertEqual(transparente.convert("RGBA").getpixel((0, 0))[3], 0)
        self.assertEqual(comum.get(rota1).status_code, 404)
        admin.post(gestor, data=campos | {"usuarios": ["2"]})
        self.assertEqual(comum.get(rota1).data, png1)
        self.assertIn(b'value="ortofoto:ortofoto-ensaio"', comum.get("/geovsatt").data)
        self.assertNotIn(b'value="ortofoto:ortofoto-ensaio"', ambiental.get("/geovsatt").data)
        self.assertEqual(comum.get(download).status_code, 403)
        rota_offline = "/api/geovsatt/pacote-offline"
        apenas_imagem = {"camadas": [], "ortofotos": ["ortofoto-ensaio"]}
        self.assertEqual(comum.post(rota_offline, json=apenas_imagem).status_code, 403)
        admin.post(gestor, data=campos | {"usuarios": ["2"], "usuarios_exportacao": ["2"]})
        exportada = comum.get(download)
        self.addCleanup(exportada.close)
        self.assertEqual(exportada.data, bruto1)
        self.assertIn('v1.mbtiles', exportada.headers["Content-Disposition"])
        oeste, sul, leste, norte = dados["limites"]
        recorte = [oeste + (leste - oeste) / 4, sul + (norte - sul) / 4,
                   leste - (leste - oeste) / 4, norte - (norte - sul) / 4]
        copiada = comum.post(rota_offline, json=apenas_imagem | {"recorte": recorte})
        self.assertEqual(copiada.status_code, 200)
        orto, = copiada.json["ortofotos"]
        self.assertEqual(orto["limites"], recorte)
        self.assertEqual(orto["mime"], "image/png")
        self.assertEqual(set(orto["mosaicos"]), {"15/11896/18769"})
        self.assertEqual(b64decode(orto["mosaicos"]["15/11896/18769"]), png1)
        self.assertEqual(comum.post(rota_offline, json=apenas_imagem | {"recorte": [0, 0, 1, 1]}).status_code, 400)
        self.assertEqual(comum.get(rota_offline + "/estado").json["ortofotos"], {"ortofoto-ensaio": 1})
        composicao = {"titulo": "Ensaio", "orientacao": "paisagem", "layout": "inferior",
                      "base": dados["base"], "legenda": True, "centro": [-25.3, -49.3], "zoom": 16, "camadas": []}
        salvas = "/api/geovsatt/composicoes"
        criada = comum.post(salvas, json=composicao)
        self.assertEqual(criada.status_code, 201)
        salva = f"{salvas}/{criada.json['id_composicao']}"
        self.assertEqual(ambiental.post(salvas, json=composicao).status_code, 400)
        self.assertEqual(admin.post(painel + "importar", data=campos | {
            "mbtiles": (io.BytesIO(bruto2), "segundo.mbtiles"),
        }).status_code, 303)
        admin.post(gestor + "/versoes/2/publicar")
        imagem2 = comum.get(rota2)
        self.assertEqual((imagem2.mimetype, imagem2.data), ("image/jpeg", jpeg2))
        self.assertEqual(comum.get(rota_offline + "/estado").json["ortofotos"], {"ortofoto-ensaio": 2})
        self.assertEqual(comum.get(rota1).status_code, 404)
        self.assertEqual(comum.get(salva).json["configuracao"]["base"], dados["base"])
        admin.post(gestor + "/versoes/1/publicar")
        self.assertEqual(comum.get(rota1).data, png1)
        self.assertEqual(comum.get(rota2).status_code, 404)
        admin.post(gestor, data=campos)
        self.assertEqual(comum.get(rota1).status_code, 404)
        self.assertEqual(comum.get(download).status_code, 404)
        self.assertTrue(comum.get(salva).json["base_indisponivel"])

    def test_simbologia_por_faixa_e_etiqueta_composta_preservam_regras_validas(self):
        admin = self.client()
        comum = self.client(uid=2)
        codigo = "profundidade-ensaio"
        gestor = f"/geovsatt/admin/camadas/{codigo}"
        geometria = mapping(box(-49.31, -25.31, -49.30, -25.30))
        dados = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": geometria, "properties": {"nome": "Setor", "profundidade": 10.5}}
        ]}
        campos = {"nome": "Profundidade de ensaio", "codigo": codigo, "grupo": "Território", "fonte": "QGIS de ensaio"}
        self.assertEqual(admin.post("/geovsatt/admin/importar", data=campos | {
            "geojson": (io.BytesIO(json.dumps(dados).encode()), "profundidade.geojson"),
        }).status_code, 303)
        admin.post(gestor + "/versoes/1/publicar")
        consulta = "/api/geovsatt/catalogo"

        def estilo():
            return next(camada["estilo"] for camada in admin.get(consulta).json["camadas"] if camada["id"] == codigo)

        self.assertEqual(estilo()["modo_cor"], "")
        base = campos | {
            "modo_cor": "faixas", "atributo_cor": "profundidade", "usuarios": ["2"], "cor": "#c0ccdd",
            "faixa_de": ["10,5", ""], "faixa_ate": ["", "10,5"], "faixa_cor": ["#82223c", "#328B7C"],
            "faixa_legenda": ["Classe alta", "Classe baixa"], "rotulo": "nome", "rotulo_complemento": "profundidade",
            "rotulo_prefixo": "Área", "rotulo_sufixo": "m", "rotulo_zoom": "14", "rotulo_zoom_max": "19",
            "rotulo_halo": "1.5", "rotulo_halo_cor": "#FFEEDD",
        }
        salva = admin.post(gestor, data=base, follow_redirects=True)
        self.assertIn("Configuração salva.", salva.get_data(as_text=True))
        estilos = estilo()
        self.assertEqual(estilos["faixas_cor"], [
            {"de": None, "ate": 10.5, "cor": "#328b7c", "legenda": "Classe baixa"},
            {"de": 10.5, "ate": None, "cor": "#82223c", "legenda": "Classe alta"},
        ])
        self.assertEqual((estilos["rotulo_complemento"], estilos["rotulo_prefixo"], estilos["rotulo_sufixo"]),
                         ("profundidade", "Área", "m"))
        self.assertEqual((estilos["rotulo_zoom_max"], estilos["rotulo_halo"], estilos["rotulo_halo_cor"]),
                         (19, 1.5, "#FFEEDD"))
        self.assertIn("Prévia do estilo".encode("utf-8"), salva.data)
        self.assertIn(b'name="faixa_de"', salva.data)
        self.assertIn(b'geovsatt_estilos.js', comum.get("/geovsatt").data)
        self.assertEqual(comum.post(gestor, data=base).status_code, 403)
        for alteracao, mensagem in [
            ({"faixa_ate": ["", "12"]}, "sobrepor"),
            ({"faixa_de": ["nan", ""]}, "limites numéricos"),
            ({"faixa_cor": ["#82223c"]}, "faixas de cor"),
            ({"rotulo_zoom_max": "12"}, "zoom máximo"),
        ]:
            resposta = admin.post(gestor, data=base | alteracao, follow_redirects=True)
            self.assertIn(mensagem, resposta.get_data(as_text=True))
            self.assertEqual(estilo(), estilos)
        admin.post(gestor, data=campos | {"modo_cor": "unico", "cor": "#225566"})
        self.assertEqual(estilo()["faixas_cor"], [])
        self.assertEqual(estilo()["modo_cor"], "unico")

    def test_estimativa_area_parcial_usa_cadastro_rg_sem_duplicar_blocos(self):
        def poligono(x1, x2, chave=None):
            vertices = [[x1, -25.4], [x2, -25.4], [x2, -25.3], [x1, -25.3]]
            return {"geometry": {"type": "Polygon", "coordinates": [vertices + [vertices[0]]]},
                    "properties": {"chave": chave}}

        dados = {"features": [poligono(-49.4, -49.3, "1:1"), poligono(-49.4, -49.3, "1:1"),
                              poligono(-49.4, -49.3), poligono(-49.3, -49.2)],
                 "metadata": {"origem": "QGIS de ensaio"}}
        forma = [[-49.35, -25.4], [-49.3, -25.4], [-49.3, -25.3], [-49.35, -25.3]]
        rota = "/api/geovsatt/populacao"
        client = self.client()
        with patch("app_core.geovsatt.quarteiroes", return_value=dados):
            res = client.post(rota, json={"pontos": forma}).json
            self.assertEqual(res["populacao_estimada"], 6)
            self.assertEqual(res["residencias_equivalentes"], 2)
            self.assertEqual(res["quarteiroes_com_cadastro"], 1)
            self.assertEqual(res["quarteiroes_sem_cadastro"], 1)
            self.assertEqual(res["quarteiroes_parciais"], 1)
            sem_condominios = client.post(rota, json={"pontos": forma, "incluir_condominios": False}).json
            self.assertEqual(sem_condominios["populacao_estimada"], 0)
            vazia = client.post(rota, json={"pontos": poligono(-49.5, -49.45)["geometry"]["coordinates"][0]}).json
            self.assertIsNone(vazia["populacao_estimada"])
        self.assertEqual(client.post(rota, json={"pontos": [forma[i] for i in (0, 2, 1, 3)]}).status_code, 400)
        self.assertEqual(client.post(rota, json={"pontos": forma, "incluir_condominios": "false"}).status_code, 400)
        ambient = self.client(uid=3)
        self.assertEqual(ambient.post(rota, json={"pontos": forma}).status_code, 403)
        self.assertNotIn(b'data-medida="populacao"', ambient.get("/geovsatt").data)

    def test_trabalhos_agregam_visitas_e_liraa_na_malha_e_preservam_o_recorte(self):
        ciclo = liraa.criar_ciclo(str(self.path), {"ano": 2025, "nome": "Geo de ensaio",
                                                  "inicio": "2025-02-01", "fim": "2025-02-28"})
        with closing(db.connect(str(self.path))) as conn, conn:
            liraa_kobo.ensure_schema(conn)
            outra_localidade = conn.execute("INSERT INTO localidades(nome) VALUES('Outra localidade de ensaio')").lastrowid
            conn.executemany("""
                INSERT INTO visitas(id_visita,kobo_uuid,tipo,data,id_localidade,quarteirao,visita,morador,processado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Pessoa fictícia', '2026-11-26')
            """, [
                ("geo-1", "geo-1", "TB", "2025-02-01", 1, 1, "Normal"),
                ("geo-2", "geo-2", "TB", "2025-02-03", 1, 1, "Fechado"),
                ("geo-3", "geo-3", "PE", "2025-02-14", 1, 1, "Recuperado"),
                ("geo-4", "geo-4", "TB", "2025-02-16", 1, 999, "Normal"),
                ("geo-5", "geo-5", "TB", "2025-01-31", 1, 1, "Normal"),
                ("geo-6", "geo-6", "PVE", "2025-02-20", outra_localidade, 1, "Normal"),
            ])
            conn.execute("""
                INSERT INTO liraa_visitas(id_ciclo,kobo_uuid,data_visita,id_localidade,localidade_informada,
                    quarteirao,situacao_vinculo,morador,criado_em)
                VALUES (?, 'geo-liraa', '2025-02-28', 1, 'Localidade Ficticia', '0001', 'vinculado',
                    'Pessoa fictícia do LIRAa', '2026-11-26')
            """, (ciclo,))
        superadmin = self.client()
        comum = self.client(uid=2)
        ambiental = self.client(uid=3)
        geometria = box(-49.3012, -25.3012, -49.3008, -25.3008)
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"Localidade": "Localidade Ficticia", "id_Q": "0001"},
             "geometry": mapping(geometria)}] * 2}
        self.assertEqual(superadmin.post("/geovsatt/admin/importar", data={
            "nome": "Quarteirões QGIS", "codigo": "quarteiroes-qgis", "grupo": "Território", "fonte": "QGIS de ensaio",
            "geojson": (io.BytesIO(json.dumps(geojson).encode()), "blocos.geojson"),
        }).status_code, 303)
        superadmin.post("/geovsatt/admin/camadas/quarteiroes-qgis", data={
            "nome": "Quarteirões QGIS", "grupo": "Território", "usuarios": ["2"],
        })
        superadmin.post("/geovsatt/admin/camadas/quarteiroes-qgis/versoes/1/publicar")
        codigo = "quarteiroes_trabalhados"
        rota = f"/api/geovsatt/camadas/{codigo}"
        exportar = f"/geovsatt/camadas/{codigo}/exportar"
        periodo = {"inicio": "2025-02-01", "fim": "2025-02-28", "localidade": "1"}
        self.assertEqual(comum.get(rota, query_string=periodo).status_code, 404)
        superadmin.post(f"/geovsatt/admin/camadas/{codigo}", data={
            "nome": "Quarteirões trabalhados", "grupo": "Vigilância", "usuarios": ["2", "3"],
        })
        resposta = comum.get(rota, query_string=periodo)
        self.assertEqual(resposta.status_code, 200, resposta.json)
        self.assertNotIn("Pessoa fictícia", resposta.get_data(as_text=True))
        recorte = resposta.json
        feature, = recorte["features"]
        self.assertTrue(shape(feature["geometry"]).equals(geometria))
        self.assertEqual(recorte["metadata"]["origem_malha"], "Malha cartográfica QGIS")
        self.assertEqual(recorte["metadata"]["registros_no_recorte"], 5)
        self.assertEqual(recorte["metadata"]["registros_sem_malha"], 1)
        props = feature["properties"]
        self.assertEqual((props["chave"], props["atividade"], props["total_registros"]), ("1:1", "Mais de um tipo", 4))
        self.assertEqual((props["visitas_normais"], props["visitas_fechadas"], props["visitas_recuperadas"],
                          props["visitas_outras_situacoes"]), (1, 1, 1, 1))
        self.assertEqual(props["ultimo_registro"], "2025-02-28")
        self.assertIn("LIRAa (1)", props["tipos_registrados"])
        tb = periodo | {"tipo": "TB"}
        self.assertEqual(comum.get(rota, query_string=tb).json["features"][0]["properties"]["total_registros"], 2)
        self.assertEqual(comum.get(rota, query_string=periodo | {"inicio": "2025-02-30"}).status_code, 400)
        self.assertEqual(comum.get(rota, query_string=periodo | {"fim": "2025-01-30"}).status_code, 400)
        self.assertEqual(ambiental.get(rota, query_string=periodo).status_code, 404)
        self.assertEqual(comum.get(f"{exportar}/csv", query_string=tb).status_code, 403)
        superadmin.post(f"/geovsatt/admin/camadas/{codigo}", data={
            "nome": "Quarteirões trabalhados", "grupo": "Vigilância", "usuarios": ["2", "3"],
            "usuarios_exportacao": ["2", "3"],
        })
        for formato in ("csv", "geojson", "kml"):
            download = comum.get(f"{exportar}/{formato}", query_string=tb)
            self.assertEqual(download.status_code, 200)
            self.assertIn("-2025-02-01-2025-02-28", download.headers["Content-Disposition"])
            self.assertNotIn("LIRAa (1)", download.get_data(as_text=True))
            self.assertEqual(ambiental.get(f"{exportar}/{formato}", query_string=tb).status_code, 404)
        download = comum.get(f"{exportar}/geojson", query_string=tb)
        self.assertEqual(download.get_json()["metadata"]["consulta"], tb)
        regras = [{"field": "data_visita", "match": "gte", "value": periodo["inicio"]},
                  {"field": "data_visita", "match": "lte", "value": periodo["fim"]},
                  {"field": "tipo_trabalho", "match": "exact", "value": "TB"},
                  {"field": "localidade_id", "match": "exact", "value": "1"}]
        dados = {"titulo": "Recorte do trabalho", "orientacao": "paisagem", "layout": "inferior",
                 "base": "none", "legenda": True, "centro": [-25.31, -49.30], "zoom": 16,
                 "camadas": [codigo], "filtros": {codigo: regras}}
        composicoes = "/api/geovsatt/composicoes"
        criada = comum.post(composicoes, json=dados)
        self.assertEqual(criada.status_code, 201, criada.json)
        item = f"{composicoes}/{criada.json['id_composicao']}"
        self.assertEqual(comum.get(item).json["configuracao"]["filtros"][codigo], regras)
        self.assertEqual(comum.post(composicoes, json=dados | {"filtros": {codigo: [regras[0], regras[0]]}}).status_code, 400)
        superadmin.post("/geovsatt/admin/camadas/quarteiroes", data={"nome": "Quarteirões", "grupo": "Território"})
        self.assertEqual(comum.get(rota).status_code, 404)
        self.assertEqual(comum.get(item).json["configuracao"]["filtros"], {})

    def test_exportacao_exige_permissao_propria_e_entrega_tres_formatos(self):
        admin = self.client()
        autorizado = self.client(uid=2)
        ambiental = self.client(uid=3)
        registro = {"type": "Feature", "properties": {"nome": "Ponto <QGIS>", "valor": "=HYPERLINK(1)"},
                    "geometry": {"type": "Point", "coordinates": [-49.31, -25.31]}}
        dados = {"type": "FeatureCollection", "features": [registro]}
        pagina = "/geovsatt/admin/camadas/teste-exportacao"
        rota = "/geovsatt/camadas/teste-exportacao/exportar/"
        config = {"nome": "Camada de ensaio", "grupo": "Território", "niveis": "visualizador", "setores": "endemias"}
        self.assertEqual(admin.post("/geovsatt/admin/importar", data={**config, "codigo": "teste-exportacao",
            "fonte": "Cartografia de ensaio", "geojson": (io.BytesIO(json.dumps(dados).encode()), "dados.geojson")}).status_code, 303)
        self.assertEqual(admin.post(pagina + "/versoes/1/publicar").status_code, 303)
        admin.post(pagina, data=config)
        self.assertEqual(autorizado.get("/api/geovsatt/camadas/teste-exportacao").status_code, 200)
        self.assertEqual(autorizado.get(rota + "csv").status_code, 403)
        self.assertNotIn(rota.encode(), autorizado.get("/geovsatt").data)
        admin.post(pagina, data={**config, "usuarios_exportacao": ["2", "3"]})
        self.assertIn(rota.encode(), autorizado.get("/geovsatt").data)
        self.assertEqual(ambiental.get(rota + "geojson").status_code, 404)
        csv = autorizado.get(rota + "csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("geovsatt-teste-exportacao.csv", csv.headers["Content-Disposition"])
        self.assertIn("no-store", csv.headers["Cache-Control"])
        self.assertIn("'=HYPERLINK(1);POINT (-49.31 -25.31)", csv.data.decode("utf-8-sig"))
        geojson = autorizado.get(rota + "geojson")
        self.assertEqual(geojson.mimetype, "application/geo+json")
        self.assertEqual(geojson.json["features"], [registro])
        self.assertEqual(geojson.json["metadata"]["fonte"], "Cartografia de ensaio")
        kml = autorizado.get(rota + "kml")
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        raiz = ET.fromstring(kml.data)
        self.assertEqual(raiz.findtext(".//k:Placemark/k:name", namespaces=ns), "Ponto <QGIS>")
        self.assertEqual(raiz.findtext(".//k:Point/k:coordinates", namespaces=ns), "-49.31,-25.31")
        self.assertEqual(admin.get(rota + "shp").status_code, 404)
        admin.post(pagina, data=config)
        self.assertEqual(autorizado.get(rota + "kml").status_code, 403)
        self.assertEqual(db.scalar(str(self.path), "SELECT COUNT(*) FROM auditoria_eventos WHERE acao='geovsatt_camada_exportada'"), 3)

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

    def test_raios_e_abrangencia_usam_a_malha_qgis_e_permissoes_da_origem(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.executemany("""
                INSERT INTO esporotricose_doentes_animais
                       (chave,nome,tutor,latitude,longitude,bloqueio,data_bloqueio,criado_em,atualizado_em)
                VALUES (?, 'Animal de ensaio', 'Tutor de ensaio', -25.301, ?, ?, ?, '2026-11-26', '2026-11-26')
            """, [("feito", -49.301, "Realizado", "2026-11-26"), ("pendente", -49.301, "Não realizado", None),
                  ("sem-coordenada", None, "Não necessário", None)])
            conn.execute("UPDATE usuarios SET nivel='admin',setor='ambiental' WHERE id_usuario=2")
        superadmin = self.client()
        admin = self.client(uid=2)
        ambiental = self.client(uid=3)
        nome = db.scalar(str(self.path), "SELECT nome FROM localidades WHERE id_localidade=1")
        shapes = (
            (1, box(-49.3012, -25.3012, -49.3008, -25.3008)),
            (1, box(-49.3012, -25.3012, -49.3008, -25.3008)),
            (2, box(-49.3000, -25.3012, -49.2988, -25.3008)),
            (3, box(-49.31, -25.31, -49.309, -25.309)),
        )
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"Localidade": nome, "id_Q": str(numero)}, "geometry": mapping(poligono)}
            for numero, poligono in shapes]}
        superadmin.post("/geovsatt/admin/importar", data={
            "nome": "Quarteirões QGIS", "codigo": "quarteiroes-qgis", "grupo": "Território", "fonte": "QGIS de ensaio",
            "geojson": (io.BytesIO(json.dumps(geojson).encode()), "blocos.geojson"),
        })
        superadmin.post("/geovsatt/admin/camadas/quarteiroes-qgis", data={
            "nome": "Quarteirões QGIS", "grupo": "Território", "niveis": ["admin"], "setores": ["ambiental"],
        })
        self.assertEqual(superadmin.post("/geovsatt/admin/camadas/quarteiroes-qgis/versoes/1/publicar").status_code, 303)
        raio = "esporotricose_bloqueios"
        zona = "esporotricose_quarteiroes"
        rota = "/api/geovsatt/camadas/"
        download = f"/geovsatt/camadas/{raio}/exportar/"
        fontes = admin.get(rota + raio)
        self.assertEqual(fontes.status_code, 200)
        self.assertNotIn(b"Tutor de ensaio", fontes.data)
        self.assertEqual(fontes.json["metadata"]["origem_malha"], "Malha cartográfica QGIS")
        realizado, nao_realizado = fontes.json["features"]
        props = realizado["properties"]
        self.assertEqual((props["situacao_bloqueio"], props["data_bloqueio"]), ("Realizado", "2026-11-26"))
        self.assertEqual(nao_realizado["properties"]["situacao_bloqueio"], "Não realizado")
        self.assertIsNone(nao_realizado["properties"]["data_bloqueio"])
        self.assertEqual((props["raio_metros"], props["quarteiroes_abrangidos"], props["quarteiroes_integrais"]),
                         (150, 2, 1))
        centro = shape(realizado["geometry"]).centroid
        self.assertAlmostEqual(centro.x, -49.301, places=6)
        self.assertAlmostEqual(centro.y, -25.301, places=6)
        self.assertAlmostEqual((shape(realizado["geometry"]).bounds[3] - centro.y) * 111_195, 150, places=1)
        blocos = {f["properties"]["id_quart"]: f["properties"] for f in admin.get(rota + zona).json["features"]}
        self.assertEqual(set(blocos), {"1", "2"})
        self.assertEqual((blocos["1"]["cobertura"], blocos["1"]["percentual_no_raio"]), ("Integral", 100.0))
        self.assertEqual(blocos["2"]["cobertura"], "Parcial")
        self.assertLess(blocos["2"]["percentual_no_raio"], 100)
        self.assertEqual(blocos["2"]["casos_com_bloqueio_realizado"], 1)
        self.assertEqual(blocos["2"]["casos_com_bloqueio_nao_realizado"], 1)
        self.assertEqual(admin.get(download + "geojson").status_code, 403)
        config = {"nome": "Raios de bloqueio", "grupo": "Vigilância", "niveis": ["admin"],
                  "setores": ["ambiental"], "usuarios": ["3"], "usuarios_exportacao": ["2", "3"]}
        superadmin.post(f"/geovsatt/admin/camadas/{raio}", data=config)
        for formato in ("csv", "geojson", "kml"):
            exportada = admin.get(download + formato)
            self.assertEqual(exportada.status_code, 200)
            self.assertNotIn(b"Tutor de ensaio", exportada.data)
            self.assertEqual(ambiental.get(download + formato).status_code, 404)
        self.assertEqual(ambiental.get(rota + raio).status_code, 404)
        self.assertNotIn(raio, [c["id"] for c in ambiental.get("/api/geovsatt/catalogo").json["camadas"]])
        superadmin.post("/geovsatt/admin/camadas/quarteiroes", data={"nome": "Quarteirões", "grupo": "Território"})
        self.assertEqual(admin.get(rota + zona).status_code, 404)
        sem_malha = admin.get(rota + raio).json
        self.assertIsNone(sem_malha["metadata"]["origem_malha"])
        self.assertNotIn("quarteiroes_abrangidos", sem_malha["features"][0]["properties"])
        superadmin.post("/geovsatt/admin/camadas/esporotricose", data={"nome": "Esporotricose", "grupo": "Vigilância"})
        self.assertEqual(admin.get(rota + raio).status_code, 404)
        self.assertEqual(admin.get(download + "geojson").status_code, 404)

    def test_seletor_cep_e_base_de_satelite_no_mapa(self):
        client = self.client()
        mapa = client.get("/geovsatt")
        self.assertIn(b"CEP / BrasilAPI", mapa.data)
        self.assertIn(b'value="logradouro"', mapa.data)
        self.assertIn(b'value="sentinel"', mapa.data)
        self.assertIn(b'value="openfreemap"', mapa.data)
        self.assertIn(b'value="esri"', mapa.data)
        self.assertLess(mapa.data.index(b'value="none"'), mapa.data.index(b'value="esri"'))
        with patch.dict(self.geo.config, {"GEOVSATT_ESRI_LICENSED": False}):
            self.assertNotIn(b'value="esri"', client.get("/geovsatt").data)
        csp = mapa.headers.get("Content-Security-Policy") or mapa.headers["Content-Security-Policy-Report-Only"]
        self.assertIn("https://tiles.maps.eox.at", csp)
        self.assertIn("connect-src 'self' https://tiles.openfreemap.org;", csp)
        self.assertIn("worker-src 'self';", csp)
        worker = client.get("/static/vendor/maplibre/maplibre-gl-worker.mjs")
        self.addCleanup(worker.close)
        self.assertEqual(worker.status_code, 200)
        self.assertIn("javascript", worker.mimetype)
        csp_worker = worker.headers.get("Content-Security-Policy") or worker.headers["Content-Security-Policy-Report-Only"]
        self.assertIn("connect-src 'self' https://tiles.openfreemap.org;", csp_worker)

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
        prefixo = permitido.post(url, json={"q": "João de Souza, 1", "sugestao": True}).json["resultados"]
        self.assertEqual(prefixo[0]["titulo"], "Rua Doutor João de Souza, 10")
        self.assertEqual(permitido.post(url, json={"q": "João de Souza, 1"}).json["resultados"], [])
        self.assertEqual(self.client(uid=3).post(url, json={"q": "João de Sou", "sugestao": True}).json["resultados"], [])
        self.client().post("/geovsatt/admin/camadas/quarteiroes", data={"nome": "Quarteirões", "grupo": "Território"})
        self.assertEqual(permitido.post(url, json={"q": consulta}).json["resultados"], [])

    def test_nominatim_instancia_configurada_cache_limite_e_resultados(self):
        rota = "/api/geovsatt/nominatim"
        cliente = self.client()
        self.assertEqual(cliente.post(rota, json={"q": "Parque Municipal"}).status_code, 503)
        self.assertNotIn(b'value="nominatim"', cliente.get("/geovsatt").data)
        self.assertIsNone(geovsatt_busca.endpoint_nominatim("https://nominatim.openstreetmap.org"))
        self.assertIsNone(geovsatt_busca.endpoint_nominatim("http://osm.exemplo.invalid"))
        dados = [
            {"lat": "-25.32", "lon": "-49.30", "display_name": "Parque Municipal de Ensaio"},
            {"lat": "-10", "lon": "-40", "display_name": "Fora da região"},
            {"lat": "NaN", "lon": "-49.30", "display_name": "Inválido"},
        ]
        with (
            patch.dict(self.geo.config, {"GEOVSATT_NOMINATIM_URL": "https://geo.exemplo.invalid/nominatim"}),
            patch.object(geovsatt_busca, "_NOMINATIM_CACHE", OrderedDict()),
            patch.object(geovsatt_busca, "_NOMINATIM_PROXIMA", 0.0),
            patch.object(geovsatt_busca, "monotonic", return_value=100.0),
            patch.object(geovsatt_busca, "_consulta_postal", return_value=dados) as consultar,
        ):
            self.assertIn(b'value="nominatim"', cliente.get("/geovsatt").data)
            self.assertNotEqual(self.geo.test_client().post(rota, json={"q": "Parque Municipal"}).status_code, 200)
            self.assertEqual(cliente.post(rota, json={"q": "123.456.789-00"}).status_code, 400)
            ok = cliente.post(rota, json={"q": "Parque Municipal"})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json["resultados"], [{
                "tipo": "nominatim", "titulo": "Parque Municipal de Ensaio", "latitude": -25.32,
                "longitude": -49.30, "subtitulo": "OpenStreetMap · posição de referência",
            }])
            self.assertEqual(cliente.post(rota, json={"q": " parque   municipal "}).json, ok.json)
            self.assertEqual(cliente.post(rota, json={"q": "Biblioteca Municipal"}).status_code, 429)
            consultar.assert_called_once()
            url = urlsplit(consultar.call_args.args[0])
            self.assertEqual((url.netloc, url.path), ("geo.exemplo.invalid", "/nominatim/search"))
            self.assertEqual(parse_qs(url.query)["q"], ["Parque Municipal"])
            self.assertEqual(parse_qs(url.query)["bounded"], ["1"])

    def test_nominatim_provedor_com_token_nao_expoe_a_credencial(self):
        cliente = self.client()
        rota = "/api/geovsatt/nominatim"
        provedor = "https://geocode.maps.co"
        self.assertIsNone(geovsatt_busca.endpoint_nominatim(provedor))
        self.assertIsNone(geovsatt_busca.endpoint_nominatim("http://localhost:8000", "token"))
        self.assertIsNone(geovsatt_busca.endpoint_nominatim(provedor, "token\r\n"))
        config = {"GEOVSATT_NOMINATIM_URL": provedor, "GEOVSATT_NOMINATIM_TOKEN": "chave-de-ensaio"}
        with (
            patch.dict(self.geo.config, config),
            patch.object(geovsatt_busca, "_NOMINATIM_CACHE", OrderedDict()),
            patch.object(geovsatt_busca, "_NOMINATIM_PROXIMA", 0.0),
            patch.object(geovsatt_busca._CEP_HTTP, "open") as abrir,
        ):
            resposta = abrir.return_value.__enter__.return_value
            resposta.status, resposta.read.return_value = 200, b"[]"
            consulta = cliente.post(rota, json={"q": "Praça de ensaio"})
            self.assertEqual(consulta.status_code, 200)
            requisicao = abrir.call_args.args[0]
            self.assertEqual(requisicao.get_header("Authorization"), "Bearer chave-de-ensaio")
            self.assertNotIn("chave-de-ensaio", requisicao.full_url)
            self.assertNotIn(b"chave-de-ensaio", consulta.data)
            self.assertNotIn(b"chave-de-ensaio", cliente.get("/geovsatt").data)

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

    def test_ceps_por_logradouro_preserva_bairros_e_trechos(self):
        url = "/api/geovsatt/ceps-por-logradouro"
        rua = {"logradouro": "Rua da Praça", "localidade": "Almirante Tamandaré", "uf": "PR"}
        postal = [
            rua | {"cep": "83501-020", "bairro": "Jardim 1", "complemento": "lado par", "unidade": "Ignorar"},
            rua | {"cep": "83501020"},
            rua | {"cep": "83501-021", "bairro": "Jardim 2"},
            rua | {"cep": "99999-999", "localidade": "Outro município"},
        ]
        client = self.client(uid=3)
        with patch.object(geovsatt_busca._CEP_HTTP, "open") as pedir:
            resposta = MagicMock(status=200)
            resposta.read.return_value = json.dumps(postal).encode()
            pedir.return_value.__enter__.return_value = resposta
            self.assertEqual(client.post(url, json={"logradouro": "R."}).status_code, 400)
            self.assertEqual(client.post(url, json={"logradouro": "https://example.com"}).status_code, 400)
            self.assertEqual(client.post(url, json={"logradouro": []}).status_code, 400)
            self.assertEqual(self.geo.test_client().post(url, json={"logradouro": "Rua da Praça"}).status_code, 302)
            pedir.assert_not_called()
            obtidos = client.post(url, json={"logradouro": "  Rua da Praça, 150, Bairro  "}).json["resultados"]
            self.assertEqual(obtidos, [
                {"cep": "83501-020", "bairro": "Jardim 1", "complemento": "lado par", "logradouro": "Rua da Praça"},
                {"cep": "83501-021", "bairro": "Jardim 2", "complemento": "", "logradouro": "Rua da Praça"},
            ])
            self.assertEqual(pedir.call_args.args[0].full_url,
                             "https://viacep.com.br/ws/PR/Almirante%20Tamandar%C3%A9/Rua%20da%20Pra%C3%A7a/json/")
            resposta.read.return_value = b"[]"
            self.assertEqual(client.post(url, json={"logradouro": "Sem resultado"}).json["resultados"], [])
            resposta.read.return_value = b'{"erro":true}'
            self.assertEqual(client.post(url, json={"logradouro": "Rua da Praça"}).status_code, 502)


if __name__ == "__main__":
    unittest.main()
