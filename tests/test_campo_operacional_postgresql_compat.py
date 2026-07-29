import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import amostras_animais
from app_core import db as db_core
from app_core import recolhimentos


class CampoOperacionalCompatTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "campo.db"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE localidades (
                    id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    cod_localidade TEXT
                );
                CREATE TABLE agentes (
                    id_agente INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    nome_completo TEXT
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
        self.target = db_core.DatabaseTarget("sqlite", str(self.db_path))

    def tearDown(self):
        self.tempdir.cleanup()

    def test_recolhimento_portatil_deduplica_e_lista(self):
        conn = db_core.connect(self.target)
        try:
            recolhimentos.ensure_schema(conn)
            registro = {
                "id_recolhimento": "rec-1",
                "kobo_uuid": "uuid-rec-1",
                "data": "2026-07-29",
                "hora": "09:30",
                "localidade": "Tamboara",
                "agentes_texto": "Ana Beatriz",
                "pneu": 2,
                "louca_sanitaria": 1,
                "tv": 0,
                "parachoque": 0,
                "outros": 0,
                "total_materiais": 3,
            }
            self.assertTrue(
                recolhimentos._inserir_recolhimento(
                    conn, registro, "2026-07-29T10:00:00"
                )
            )
            self.assertFalse(
                recolhimentos._inserir_recolhimento(
                    conn, registro, "2026-07-29T10:00:00"
                )
            )
            self.assertEqual(
                recolhimentos._inserir_agentes(
                    conn, registro["id_recolhimento"], registro["agentes_texto"]
                ),
                1,
            )
            conn.commit()
        finally:
            conn.close()

        resumo = recolhimentos.resumo(
            self.target, {"d_ini": "2026-01-01", "d_fim": "2026-12-31"}
        )
        lista = recolhimentos.listar(self.target, {"busca": "tamboara"})

        self.assertEqual(resumo["totais"]["registros"], 1)
        self.assertEqual(resumo["totais"]["total_materiais"], 3)
        self.assertEqual(lista["total"], 1)
        self.assertEqual(lista["registros"][0]["agentes"], "Ana Beatriz")
        self.assertEqual(lista["registros"][0]["data"], "2026-07-29")

    def test_amostra_portatil_deduplica_e_lista(self):
        conn = db_core.connect(self.target)
        try:
            amostras_animais.ensure_schema(conn)
            registro = {
                "id_amostra": "amostra-1",
                "kobo_uuid": "uuid-amostra-1",
                "data": "2026-07-29",
                "hora": "11:15",
                "agentes_texto": "Fernando",
                "motivo_visita": "Investigacao",
                "animal_motivador": "Escorpiao",
                "localidade": "Lamenha",
                "logradouro": "Rua de Teste",
                "houve_acidente": "Sim",
                "houve_captura": "Sim",
                "tipo_animal": "Escorpiao",
                "especie_resumo": "Tityus",
                "quantidade": 2,
            }
            self.assertTrue(
                amostras_animais._inserir_amostra(
                    conn, registro, "2026-07-29T12:00:00"
                )
            )
            self.assertFalse(
                amostras_animais._inserir_amostra(
                    conn, registro, "2026-07-29T12:00:00"
                )
            )
            self.assertEqual(
                amostras_animais._inserir_agentes(
                    conn, registro["id_amostra"], registro["agentes_texto"]
                ),
                1,
            )
            conn.commit()
        finally:
            conn.close()

        resumo = amostras_animais.resumo(
            self.target, {"d_ini": "2026-01-01", "d_fim": "2026-12-31"}
        )
        lista = amostras_animais.listar(self.target, {"busca": "tityus"})

        self.assertEqual(resumo["totais"]["registros"], 1)
        self.assertEqual(resumo["totais"]["quantidade"], 2)
        self.assertEqual(resumo["totais"]["acidentes"], 1)
        self.assertEqual(lista["total"], 1)
        self.assertEqual(lista["registros"][0]["agentes"], "Fernando")
        self.assertEqual(lista["registros"][0]["hora"], "11:15")

    def test_schema_postgresql_fica_sob_responsabilidade_da_migracao(self):
        class PostgreSQLStub:
            backend = "postgresql"

            def execute(self, *_args, **_kwargs):
                raise AssertionError("DDL nao deve executar no PostgreSQL.")

            def executescript(self, *_args, **_kwargs):
                raise AssertionError("DDL nao deve executar no PostgreSQL.")

        conn = PostgreSQLStub()
        recolhimentos.ensure_schema(conn)
        amostras_animais.ensure_schema(conn)

    def test_agregacao_de_agentes_respeita_o_backend(self):
        class ConnectionStub:
            def __init__(self, backend):
                self.backend = backend

        sqlite_sql = recolhimentos._agentes_aggregate(
            ConnectionStub("sqlite"), "a.nome"
        )
        postgresql_sql = recolhimentos._agentes_aggregate(
            ConnectionStub("postgresql"), "a.nome"
        )

        self.assertIn("GROUP_CONCAT", sqlite_sql)
        self.assertIn("string_agg", postgresql_sql)
        self.assertIn(
            "substr",
            recolhimentos._month_expression(
                ConnectionStub("sqlite"), "data"
            ),
        )
        self.assertIn(
            "to_char",
            recolhimentos._month_expression(
                ConnectionStub("postgresql"), "data"
            ),
        )


if __name__ == "__main__":
    unittest.main()
