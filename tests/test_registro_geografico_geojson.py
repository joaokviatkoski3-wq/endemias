import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import registro_geografico as rg_core


def _geojson(lng= -49.30):
    return json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"Localidade": "11", "id_quart": "0007", "origem": "QGIS"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[lng, -25.30], [lng + 0.001, -25.30], [lng + 0.001, -25.301], [lng, -25.30]]],
            },
        }],
    }, ensure_ascii=False).encode("utf-8")


class RegistroGeograficoGeojsonTests(unittest.TestCase):
    def _database(self, tmpdir):
        path = Path(tmpdir) / "rg.db"
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript("""
                CREATE TABLE localidades (
                    id_localidade INTEGER PRIMARY KEY,
                    nome TEXT NOT NULL,
                    cod_localidade TEXT
                );
                CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER);
                INSERT INTO localidades VALUES (1, 'Sede', '11');
            """)
            rg_core.ensure_schema(conn)
            conn.commit()
        finally:
            conn.close()
        return str(path)

    def test_previa_importa_versiona_e_expoe_geojson_ativo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._database(tmpdir)
            original = _geojson()
            previa = rg_core.preview_importacao_geojson(db_path, original, "qgis.geojson", tmpdir)
            self.assertEqual(previa["total"], 1)
            self.assertEqual(previa["novos"], 1)
            resultado = rg_core.importar_geojson(
                db_path, original, "qgis.geojson", previa["sha256"], tmpdir, 9, "Administrador"
            )
            self.assertEqual(resultado["total"], 1)
            ativo = rg_core.geojson_ativo(db_path, tmpdir)
            self.assertEqual(ativo["type"], "FeatureCollection")
            self.assertEqual(ativo["features"][0]["properties"]["Localidade"], 1)
            self.assertEqual(ativo["features"][0]["properties"]["Localidade_nome"], "Sede")
            self.assertEqual(ativo["features"][0]["properties"]["id_quart"], "0007")

            mesma = rg_core.preview_importacao_geojson(db_path, original, "qgis.geojson", tmpdir)
            self.assertEqual(mesma["iguais"], 1)
            alterada = rg_core.preview_importacao_geojson(db_path, _geojson(-49.31), "qgis-novo.geojson", tmpdir)
            self.assertEqual(alterada["alterados"], 1)

    def test_exige_mesmo_arquivo_da_previa(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._database(tmpdir)
            previa = rg_core.preview_importacao_geojson(db_path, _geojson(), "qgis.geojson", tmpdir)
            with self.assertRaisesRegex(ValueError, "alterado após a prévia"):
                rg_core.importar_geojson(db_path, _geojson(-49.31), "qgis.geojson", previa["sha256"], tmpdir)

    def test_rejeita_geometria_aberta_e_localidade_desconhecida(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._database(tmpdir)
            aberta = json.loads(_geojson().decode("utf-8"))
            aberta["features"][0]["geometry"]["coordinates"][0][-1] = [-49.29, -25.301]
            with self.assertRaisesRegex(ValueError, "fechado"):
                rg_core.preview_importacao_geojson(db_path, json.dumps(aberta).encode(), "aberto.geojson", tmpdir)
            desconhecida = json.loads(_geojson().decode("utf-8"))
            desconhecida["features"][0]["properties"]["Localidade"] = "999"
            with self.assertRaisesRegex(ValueError, "não existe no cadastro"):
                rg_core.preview_importacao_geojson(db_path, json.dumps(desconhecida).encode(), "desconhecido.geojson", tmpdir)

    def test_aceita_multipolygon_do_qgis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._database(tmpdir)
            multipolygon = json.loads(_geojson().decode("utf-8"))
            geometry = multipolygon["features"][0]["geometry"]
            geometry["type"] = "MultiPolygon"
            geometry["coordinates"] = [geometry["coordinates"]]
            previa = rg_core.preview_importacao_geojson(
                db_path, json.dumps(multipolygon).encode(), "qgis.geojson", tmpdir
            )
            self.assertEqual(previa["total"], 1)

    def test_aceita_id_q_e_nome_normalizado_da_localidade_do_qgis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._database(tmpdir)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "INSERT INTO localidades (id_localidade, nome, cod_localidade) VALUES (?, ?, ?)",
                    (2, "São Venâncio", "12"),
                )
                conn.commit()
            finally:
                conn.close()
            documento = json.loads(_geojson().decode("utf-8"))
            documento["features"][0]["properties"] = {
                "Localidade": "São Venâncio",
                "id_Q": "0655.1",
                "origem": "QGIS",
            }
            conteudo = json.dumps(documento, ensure_ascii=False).encode("utf-8")
            previa = rg_core.preview_importacao_geojson(db_path, conteudo, "qgis.geojson", tmpdir)
            self.assertEqual(previa["total"], 1)
            resultado = rg_core.importar_geojson(
                db_path, conteudo, "qgis.geojson", previa["sha256"], tmpdir
            )
            self.assertEqual(resultado["total"], 1)
            ativo = rg_core.geojson_ativo(db_path, tmpdir)
            propriedades = ativo["features"][0]["properties"]
            self.assertEqual(propriedades["Localidade"], 2)
            self.assertEqual(propriedades["Localidade_nome"], "São Venâncio")
            self.assertEqual(propriedades["Localidade_origem"], "São Venâncio")
            self.assertEqual(propriedades["id_Q"], "0655.1")
            self.assertEqual(propriedades["id_quart"], "0655.1")

    def test_valida_o_formato_do_geojson_territorial_atual(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "rg.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.executescript("""
                    CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT NOT NULL, cod_localidade TEXT);
                    CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER);
                """)
                conn.executemany(
                    "INSERT INTO localidades VALUES (?, ?, ?)",
                    [(indice, f"Localidade {indice}", str(indice)) for indice in range(1, 16)],
                )
                rg_core.ensure_schema(conn)
                conn.commit()
            finally:
                conn.close()
            raiz = Path(__file__).resolve().parents[1]
            conteudo = (raiz / "static" / "quarteiroes.geojson").read_bytes()
            previa = rg_core.preview_importacao_geojson(str(db_path), conteudo, "quarteiroes.geojson", raiz)
            self.assertEqual(previa["total"], 1413)
            self.assertEqual(previa["iguais"], 1413)


if __name__ == "__main__":
    unittest.main()
