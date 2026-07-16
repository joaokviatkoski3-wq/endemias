import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose


class EsporotricoseBuscasFeridoTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = str(Path(self.tempdir.name) / "esporotricose.db")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE localidades (
                   id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
                   nome TEXT NOT NULL UNIQUE,
                   cod_localidade INTEGER
               )"""
        )
        esporotricose.ensure_schema(conn)
        conn.execute(
            """INSERT INTO esporotricose_visitas(
                   id_visita, kobo_uuid, data, agentes_texto, localidade, quarteirao,
                   logradouro, numero, morador, telefone, visita, origem_estrutura,
                   processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "visita-tilapia", "uuid-visita-tilapia", "2026-07-10", "Ana Beatriz",
                "Tamboara", 1405, "Rua das Flores", "25", "Maria", "41999990000",
                "Normal", "nova", "2026-07-10T10:00:00",
            ),
        )
        conn.execute(
            """INSERT INTO esporotricose_animais(
                   id_animal, id_visita, kobo_uuid, especie, nome, feridas,
                   busca_ferido_data, busca_ferido_agente, busca_ferido_observacoes,
                   processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                "animal-tilapia", "visita-tilapia", "uuid-animal-tilapia", "Gato",
                "Tilapia", "Sim", "2026-07-16", "Joao", "Primeira tentativa",
                "2026-07-10T10:00:00",
            ),
        )
        conn.commit()
        conn.close()

    def test_migra_busca_antiga_uma_unica_vez(self):
        primeiro = esporotricose.listar_animais(self.db_path)["registros"][0]
        segundo = esporotricose.listar_animais(self.db_path)["registros"][0]

        self.assertEqual(len(primeiro["buscas_ferido"]), 1)
        self.assertEqual(primeiro["buscas_ferido"][0]["data_busca"], "2026-07-16")
        self.assertEqual(primeiro["buscas_ferido"][0]["origem"], "legado")
        self.assertEqual(len(segundo["buscas_ferido"]), 1)

        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM esporotricose_buscas_ferido").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(total, 1)

    def test_adiciona_nova_busca_sem_substituir_anterior(self):
        busca = esporotricose.salvar_busca_ferido(
            self.db_path,
            "animal-tilapia",
            {"data_busca": "2026-07-20", "agente": "Azimir", "observacoes": "Nova busca"},
        )
        animal = esporotricose.listar_animais(self.db_path)["registros"][0]

        self.assertEqual(busca["origem"], "sistema")
        self.assertEqual(len(animal["buscas_ferido"]), 2)
        self.assertEqual(animal["buscas_ferido"][0]["data_busca"], "2026-07-20")
        self.assertEqual(animal["buscas_ferido"][1]["data_busca"], "2026-07-16")
        self.assertEqual(animal["busca_ferido_agente"], "Azimir")

    def test_lista_busca_para_agenda(self):
        esporotricose.salvar_busca_ferido(
            self.db_path,
            "animal-tilapia",
            {"data_busca": "2026-07-20", "agente": "Azimir", "observacoes": "Nova busca"},
        )

        eventos = esporotricose.eventos_agenda_buscas_ferido(
            self.db_path, "2026-07-20", "2026-07-20"
        )

        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["animal"], "Tilapia")
        self.assertEqual(eventos[0]["agente"], "Azimir")
        self.assertEqual(eventos[0]["localidade"], "Tamboara")

    def test_exige_data_e_agente(self):
        with self.assertRaises(esporotricose.ValidationError):
            esporotricose.salvar_busca_ferido(
                self.db_path, "animal-tilapia", {"data_busca": "", "agente": "Azimir"}
            )
        with self.assertRaises(esporotricose.ValidationError):
            esporotricose.salvar_busca_ferido(
                self.db_path, "animal-tilapia", {"data_busca": "2026-07-20", "agente": ""}
            )


if __name__ == "__main__":
    unittest.main()
