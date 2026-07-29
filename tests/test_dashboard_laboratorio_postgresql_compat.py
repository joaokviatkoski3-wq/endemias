import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import dashboard
from app_core import laboratorio


class DashboardLaboratorioPostgresqlCompatTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "dados.db")
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE localidades (
                id_localidade INTEGER PRIMARY KEY,
                nome TEXT NOT NULL
            );
            CREATE TABLE agentes (
                id_agente INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                nome_completo TEXT
            );
            CREATE TABLE visitas (
                id_visita TEXT PRIMARY KEY,
                tipo TEXT NOT NULL,
                data TEXT NOT NULL,
                hora_inicio TEXT,
                hora_fim TEXT,
                localidade TEXT,
                id_localidade INTEGER,
                quarteirao INTEGER,
                logradouro TEXT,
                numero TEXT,
                visita TEXT,
                tipo_imovel TEXT
            );
            CREATE TABLE visita_agentes (
                id_visita TEXT NOT NULL,
                id_agente INTEGER NOT NULL
            );
            CREATE TABLE depositos_inspecionados (
                id INTEGER PRIMARY KEY,
                id_visita TEXT NOT NULL,
                tipo_deposito TEXT,
                inspecionado INTEGER,
                eliminado INTEGER,
                tratado INTEGER
            );
            CREATE TABLE tratamentos (
                id INTEGER PRIMARY KEY,
                id_visita TEXT NOT NULL,
                qtd_depositos_tratados INTEGER
            );
            CREATE TABLE coletas (
                id_coleta TEXT PRIMARY KEY,
                id_visita TEXT NOT NULL,
                num_tubo TEXT,
                tipo_deposito TEXT
            );
            CREATE TABLE resultados_laboratorio (
                id_resultado INTEGER PRIMARY KEY,
                id_coleta TEXT NOT NULL,
                data_leitura TEXT,
                laboratorista TEXT,
                aegypt_larvas INTEGER,
                aegypt_pupas INTEGER,
                aegypt_exuvias INTEGER,
                aegypt_adulto INTEGER,
                albopictus_larvas INTEGER,
                albopictus_pupas INTEGER,
                albopictus_exuvias INTEGER,
                albopictus_adulto INTEGER,
                outra_larvas INTEGER,
                outra_pupas INTEGER,
                outra_exuvias INTEGER,
                outra_adulto INTEGER
            );
            INSERT INTO localidades VALUES (1, 'Lamenha');
            INSERT INTO agentes VALUES (1, 'Agente A', 'Agente A');
            INSERT INTO agentes VALUES (2, 'Agente B', 'Agente B');
            INSERT INTO visitas (
                id_visita, tipo, data, hora_inicio, hora_fim,
                localidade, id_localidade, quarteirao, logradouro,
                numero, visita, tipo_imovel
            ) VALUES (
                'visita-1', 'PVE', '2026-07-28', '09:00', '09:20',
                'Lamenha', 1, 100, 'Rua Alfa', '10',
                'Normal', 'Residencia'
            );
            INSERT INTO visita_agentes VALUES ('visita-1', 1);
            INSERT INTO visita_agentes VALUES ('visita-1', 2);
            INSERT INTO depositos_inspecionados
            VALUES (1, 'visita-1', 'B', 3, 1, 1);
            INSERT INTO tratamentos VALUES (1, 'visita-1', 2);
            INSERT INTO coletas
            VALUES ('coleta-1', 'visita-1', 'T-100', 'B');
            INSERT INTO resultados_laboratorio VALUES (
                1, 'coleta-1', '2026-07-29', 'Azimir',
                2, 0, 0, 0,
                1, 0, 0, 0,
                0, 0, 0, 0
            );
            """
        )
        conn.commit()
        conn.close()
        self.filtros = {
            "d_ini": "2026-07-01",
            "d_fim": "2026-07-31",
        }

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_dashboard_nao_duplica_visita_com_dois_agentes(self):
        dados = dashboard.vetorial(self.db_path, self.filtros)

        self.assertEqual(dados["kpi"]["total"], 1)
        self.assertEqual(dados["por_status"][0]["total"], 1)
        self.assertEqual(dados["por_imovel"][0]["total"], 1)
        self.assertEqual(dados["depositos"]["inspecionados"], 3)
        self.assertEqual(dados["depositos"]["eliminados"], 1)
        self.assertEqual(dados["depositos"]["tratados"], 3)
        self.assertEqual(
            {row["nome"] for row in dados["por_agente"]},
            {"Agente A", "Agente B"},
        )

    def test_laboratorio_agrega_agentes_sem_duplicar_resultado(self):
        dados = laboratorio.listar(
            self.db_path,
            self.filtros,
            pagina=1,
            por_pagina=10,
        )

        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["totais"]["total_coletas"], 1)
        self.assertEqual(dados["totais"]["aegypti"], 2)
        self.assertEqual(dados["totais"]["albopictus"], 1)
        self.assertEqual(dados["totais"]["positivos_aeg"], 1)
        self.assertEqual(
            dados["registros"][0]["agentes"],
            "Agente A, Agente B",
        )


if __name__ == "__main__":
    unittest.main()
