import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app_core import meteorologia


class MeteorologiaTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "meteorologia.db"

    def tearDown(self):
        self.tmpdir.cleanup()

    @staticmethod
    def _fake_fetch(url):
        if url.startswith("https://api.open-meteo.com/"):
            return {
                "latitude": -25.32,
                "longitude": -49.31,
                "timezone": "America/Sao_Paulo",
                "current": {
                    "time": "2026-07-15T14:15",
                    "interval": 900,
                    "temperature_2m": 16.4,
                    "relative_humidity_2m": 72,
                    "apparent_temperature": 15.8,
                    "is_day": 1,
                    "precipitation": 0.0,
                    "weather_code": 2,
                    "wind_speed_10m": 7.1,
                },
            }
        if url.endswith("/estacoes/T"):
            return [
                {
                    "CD_ESTACAO": "B806",
                    "DC_NOME": "COLOMBO",
                    "SG_ESTADO": "PR",
                    "CD_SITUACAO": "Operante",
                    "TP_ESTACAO": "Automatica",
                    "VL_LATITUDE": "-25.32249999",
                    "VL_LONGITUDE": "-49.15777777",
                    "VL_ALTITUDE": "950",
                },
                {
                    "CD_ESTACAO": "A807",
                    "DC_NOME": "CURITIBA",
                    "SG_ESTADO": "PR",
                    "CD_SITUACAO": "Operante",
                    "TP_ESTACAO": "Automatica",
                    "VL_LATITUDE": "-25.4486111",
                    "VL_LONGITUDE": "-49.23055554",
                    "VL_ALTITUDE": "922.91",
                },
                {
                    "CD_ESTACAO": "A701",
                    "DC_NOME": "BRASILIA",
                    "SG_ESTADO": "DF",
                    "VL_LATITUDE": "-15.79",
                    "VL_LONGITUDE": "-47.92",
                },
            ]
        return [
            {
                "CAPITAL": "CURITIBA",
                "TMIN18": "8,3*",
                "TMAX18": "17.9*",
                "UMIN18": "60*",
                "PMAX12": "2.5*",
            }
        ]

    def test_sync_is_idempotent_and_preserves_provenance(self):
        for _ in range(2):
            result = meteorologia.sincronizar(
                self.db_path,
                dias=2,
                hoje=date(2026, 7, 15),
                fetch_json=self._fake_fetch,
            )
            self.assertEqual(result["status"], "concluido")
            self.assertEqual(result["resumos"], 2)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM meteorologia_resumos_diarios").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM meteorologia_estacoes").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM meteorologia_condicoes_atuais").fetchone()[0], 1)
            row = conn.execute(
                "SELECT * FROM meteorologia_resumos_diarios WHERE data='2026-07-15'"
            ).fetchone()
            self.assertEqual(row["temperatura_min"], 8.3)
            self.assertEqual(row["precipitacao"], 2.5)
            self.assertEqual(row["provisorio"], 1)
            self.assertIn('"CAPITAL": "CURITIBA"', row["bruto_json"])
            current = conn.execute("SELECT * FROM meteorologia_condicoes_atuais").fetchone()
            self.assertEqual(current["temperatura"], 16.4)
            self.assertEqual(current["sensacao_termica"], 15.8)
        finally:
            conn.close()

    def test_reference_stations_have_roles_and_distance(self):
        meteorologia.sincronizar(
            self.db_path,
            dias=1,
            hoje=date(2026, 7, 15),
            fetch_json=self._fake_fetch,
        )
        panel = meteorologia.obter_painel(self.db_path)
        stations = {item["codigo"]: item for item in panel["estacoes"]}
        self.assertEqual(stations["B806"]["papel"], "principal")
        self.assertEqual(stations["A807"]["papel"], "apoio")
        self.assertLess(stations["B806"]["distancia_km"], stations["A807"]["distancia_km"])
        self.assertEqual(panel["condicao_atual"]["descricao"], "Parcialmente nublado")

    def test_failed_daily_calls_are_reported_as_partial(self):
        def fetch(url):
            if url.endswith("/estacoes/T"):
                return self._fake_fetch(url)
            if url.endswith("2026-07-14"):
                raise RuntimeError("indisponivel")
            return self._fake_fetch(url)

        result = meteorologia.sincronizar(
            self.db_path,
            dias=2,
            hoje=date(2026, 7, 15),
            fetch_json=fetch,
        )
        self.assertEqual(result["status"], "parcial")
        self.assertEqual(result["resumos"], 1)
        self.assertEqual(len(result["avisos"]), 1)


if __name__ == "__main__":
    unittest.main()
