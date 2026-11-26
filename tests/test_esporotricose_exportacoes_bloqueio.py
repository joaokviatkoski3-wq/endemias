
import json
import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook
import pymupdf
from shapely.geometry import shape

from app_core import esporotricose, esporotricose_bloqueio, esporotricose_exportacao, kobo_api
from scripts.completar_origem_esporotricose import completar


class ExportacaoEsporotricoseTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.base = Path(pasta.name)
        self.banco = self.base / "cadastro.db"
        with closing(sqlite3.connect(self.banco)) as conn, conn:
            conn.execute("CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT UNIQUE, cod_localidade INTEGER)")
            conn.execute("CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT UNIQUE)")
            esporotricose.ensure_schema(conn)

    def test_exporta_recorte_inteiro_com_animais_e_texto_literal(self):
        with closing(sqlite3.connect(self.banco)) as conn, conn:
            conn.executemany(
                """INSERT INTO esporotricose_visitas (id_visita,kobo_uuid,data,localidade,visita,processado_em)
                   VALUES (?,?,'2026-11-12','Lamenha','Normal','2026-11-13')""",
                [(str(i), f"uuid-{i}") for i in range(501)],
            )
            conn.execute(
                """INSERT INTO esporotricose_visitas (id_visita,kobo_uuid,data,localidade,visita,processado_em)
                   VALUES ('fora','uuid-fora','2026-11-12','Sede','Fechado','2026-11-13')"""
            )
            conn.execute(
                """INSERT INTO esporotricose_animais(id_animal,id_visita,nome,evolucao_caso,processado_em)
                   VALUES ('a','0','Gato de teste','_bito_eutan_sia','2026-11-13')"""
            )
            origem = {"kobo_uuid": "uuid-0", "dados_kobo": {
                "visita": {"Telefone_do_morador": "04100000000", "observacao": "=1+1"},
                "animais": [{"campo extra": "observação do animal"}],
            }}
            self.assertEqual(esporotricose.armazenar_dados_kobo(conn, origem), 1)

        filtros = {"localidade": "Lamenha", "d_ini": "2026-11-12", "d_fim": "2026-11-12"}
        self.assertEqual(len(esporotricose.listar_visitas(self.banco, filtros)["registros"]), 500)
        dados = esporotricose.listar_visitas(self.banco, filtros, todos=True)
        self.assertEqual(len(dados["registros"]), 501)
        caso = next(row for row in dados["registros"] if row["id_visita"] == "0")
        self.assertEqual(caso["telefone"], "04100000000")
        self.assertEqual(caso["animais_detalhes"][0]["evolucao_caso"], "Óbito/Eutanásia")
        wb = load_workbook(esporotricose_exportacao.xlsx(dados["registros"]))
        self.assertEqual(wb["Visitas"].max_row, 502)
        self.assertEqual(wb["Animais"].max_row, 2)
        celula = next(c for c in wb["Campos de origem"]["F"] if c.value == "=1+1")
        self.assertEqual(celula.data_type, "s")
        with pymupdf.open(stream=esporotricose_exportacao.pdf([caso]).read(), filetype="pdf") as doc:
            texto = "".join(pagina.get_text() for pagina in doc)
        self.assertIn("Gato de teste", texto)
        self.assertIn("04100000000", texto)
        self.assertIn("observação do animal", texto)
        locais = esporotricose.dashboard(self.banco, filtros)["localidades"]
        self.assertEqual([(r["localidade"], r["visitas"], r["animais"]) for r in locais], [("Lamenha", 501, 1)])

    def test_api_preserva_grupo_e_metadados_e_historico_so_preenche_lacuna(self):
        original = {
            "_id": 11, "_uuid": "a1234", "Dados do morador/Data": "2026-11-11",
            "Dados do morador/Hora Inicio": "07:00", "Dados do morador/Localidade": "Lamenha",
            "start": "2026-11-11T08:00:00", "end": "2026-11-11T08:01:00",
            "_attachments": [{"filename": "arquivo de teste.jpg"}],
            "Dados do animal": [{"Nome_do_animal": "Gato alfa", "campo_novo": "x" * 37000},
                                {"Nome_do_animal": "Gato beta", "so_na_origem": {"campo": "retido"}}],
        }
        config = self.base / "config.json"
        config.write_text("{}", encoding="utf-8")
        arquivo, = kobo_api.write_etl_workbooks({"ESPOROTRICOSE": [original]}, config, self.base)
        visitas, animais = esporotricose.parse_workbook(arquivo, estrutura="nova")
        self.assertEqual(len(animais), 2)
        self.assertEqual(visitas[0]["dados_kobo"]["envio_api"], original)

        with closing(sqlite3.connect(self.banco)) as conn, conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """INSERT INTO esporotricose_visitas (id_visita,kobo_uuid,kobo_id,data,telefone,processado_em)
                   VALUES ('v','a1234',11,'2026-11-10','04100000001','2026-11-10')"""
            )
            self.assertEqual(completar(conn, visitas)["origens localizadas"], 1)
            self.assertIsNone(conn.execute("SELECT dados_kobo_json FROM esporotricose_visitas").fetchone()[0])
            self.assertEqual(completar(conn, visitas, aplicar=True)["origens preenchidas"], 1)
            self.assertEqual(completar(conn, visitas, aplicar=True)["origens preenchidas"], 0)
            row = conn.execute("SELECT * FROM esporotricose_visitas").fetchone()
            self.assertEqual(row["telefone"], "04100000001")
            self.assertEqual(row["data"], "2026-11-10")
            self.assertEqual(json.loads(row["dados_kobo_json"])["envio_api"], original)

    def test_bloqueio_lista_quadra_parcial_e_recusa_coordenada_ausente(self):
        centro = (-25.34, -49.30)
        features = [{
            "type": "Feature", "properties": {"id_Q": "1045", "Localidade": "Lamenha"},
            "geometry": {"type": "Polygon", "coordinates": [[[-49.301,-25.341], [-49.298,-25.341], [-49.298,-25.339], [-49.301,-25.339], [-49.301,-25.341]]]},
        }]
        with patch("app_core.esporotricose_bloqueio.registro_geografico.geojson_ativo", return_value={"features": features}):
            dados = esporotricose_bloqueio.mapa(self.banco, self.base, centro)
        self.assertEqual(dados["raio_metros"], 150)
        self.assertTrue(shape(dados["circulo"]).is_valid)
        self.assertEqual(dados["atingidos"], [{"codigo": "1045", "localidade": "Lamenha", "parcial": True}])
        self.assertIsNone(esporotricose_bloqueio.coordenadas({"latitude": "NaN", "longitude": -49.30}))
