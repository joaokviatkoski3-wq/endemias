import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose


class EsporotricoseVisitasDualTests(unittest.TestCase):
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
        conn.execute(
            """CREATE TABLE agentes (
                   id_agente INTEGER PRIMARY KEY AUTOINCREMENT,
                   nome TEXT NOT NULL UNIQUE
               )"""
        )
        esporotricose.ensure_schema(conn)
        conn.execute("INSERT INTO agentes(nome) VALUES (?)", ("Agente B",))
        agente_b = conn.execute(
            "SELECT id_agente FROM agentes WHERE nome=?", ("Agente B",)
        ).fetchone()[0]
        conn.execute("INSERT INTO agentes(nome) VALUES (?)", ("Agente A",))
        agente_a = conn.execute(
            "SELECT id_agente FROM agentes WHERE nome=?", ("Agente A",)
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO esporotricose_visitas(
                   id_visita, kobo_uuid, data, hora_inicio, agentes_texto,
                   localidade, quarteirao, logradouro, numero, morador,
                   telefone, visita, origem_estrutura, processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "visita-dual",
                "uuid-visita-dual",
                "2026-07-28",
                "09:00",
                "Agente A, Agente B",
                "Tamboara",
                1405,
                "Rua das Flores",
                "25",
                "Maria",
                "41999990000",
                "Normal",
                "nova",
                "2026-07-28T10:00:00",
            ),
        )
        conn.executemany(
            """INSERT INTO esporotricose_visita_agentes(id_visita, id_agente)
               VALUES (?,?)""",
            (("visita-dual", agente_b), ("visita-dual", agente_a)),
        )
        conn.executemany(
            """INSERT INTO esporotricose_animais(
                   id_animal, id_visita, kobo_uuid, especie, nome, feridas,
                   vacinado, castrado, ambiente, processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                (
                    "animal-dual-1",
                    "visita-dual",
                    "uuid-animal-dual-1",
                    "Gato",
                    "Tilapia",
                    "Sim",
                    "Sim",
                    "Não",
                    "Domiciliado",
                    "2026-07-28T10:00:00",
                ),
                (
                    "animal-dual-2",
                    "visita-dual",
                    "uuid-animal-dual-2",
                    "Cão",
                    "Lobo",
                    "Não",
                    "Desconhecido",
                    "Sim",
                    "Semidomiciliado",
                    "2026-07-28T10:00:00",
                ),
            ),
        )
        conn.commit()
        conn.close()

    def test_lista_visita_sem_duplicar_animais_ou_agentes(self):
        dados = esporotricose.listar_visitas(
            self.db_path, {"busca": "1405"}
        )

        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["registros"][0]["animais"], 2)
        self.assertEqual(
            dados["registros"][0]["agentes"],
            "Agente A, Agente B",
        )

    def test_busca_aceita_data_e_lista_animais_com_detalhes(self):
        visitas = esporotricose.listar_visitas(
            self.db_path, {"busca": "2026-07-28"}
        )
        animais = esporotricose.listar_animais(
            self.db_path,
            {
                "busca": "Tilapia",
                "especie": ["Gato"],
                "feridas": ["Sim"],
            },
        )

        self.assertEqual(visitas["total"], 1)
        self.assertEqual(animais["total"], 1)
        self.assertEqual(animais["registros"][0]["nome"], "Tilapia")
        self.assertEqual(
            animais["registros"][0]["motivo_atencao"],
            "Ferida informada",
        )

    def test_edita_visita_animal_e_resume_localidade(self):
        esporotricose.atualizar_visita(
            self.db_path,
            "visita-dual",
            {"observacoes": "Revisada", "quarteirao": 1406},
        )
        esporotricose.atualizar_animal(
            self.db_path,
            "animal-dual-1",
            {"evolucao_caso": "Em acompanhamento"},
        )
        localidades = esporotricose.resumo_localidades(self.db_path)
        visitas = esporotricose.listar_visitas(
            self.db_path, {"busca": "1406"}
        )
        animais = esporotricose.listar_animais(
            self.db_path, {"busca": "Tilapia"}
        )

        self.assertEqual(visitas["registros"][0]["observacoes"], "Revisada")
        self.assertEqual(
            animais["registros"][0]["evolucao_caso"],
            "Em acompanhamento",
        )
        self.assertEqual(localidades["registros"][0]["visitas"], 1)
        self.assertEqual(localidades["registros"][0]["animais"], 2)


if __name__ == "__main__":
    unittest.main()
