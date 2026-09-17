import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import positividade


class PositividadeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "positividade.db")
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT);
            CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT);
            CREATE TABLE visitas (
                id_visita TEXT PRIMARY KEY, tipo TEXT, data TEXT, id_localidade INTEGER,
                localidade TEXT, quarteirao TEXT, logradouro TEXT, numero TEXT,
                morador TEXT, tipo_imovel TEXT
            );
            CREATE TABLE visita_agentes (id_visita TEXT, id_agente INTEGER);
            CREATE TABLE coletas (
                id_coleta TEXT PRIMARY KEY, id_visita TEXT, num_tubo TEXT, tipo_deposito TEXT
            );
            CREATE TABLE resultados_laboratorio (
                id_resultado INTEGER PRIMARY KEY, id_coleta TEXT,
                aegypt_larvas INTEGER, aegypt_pupas INTEGER,
                aegypt_exuvias INTEGER, aegypt_adulto INTEGER
            );
            CREATE TABLE focos_positivos (
                id_foco TEXT PRIMARY KEY, id_visita TEXT, id_coleta TEXT,
                id_resultado INTEGER, num_tubo TEXT, origem TEXT, tipo_trabalho TEXT,
                data TEXT, id_localidade INTEGER, localidade TEXT, quarteirao TEXT,
                logradouro TEXT, numero TEXT, complemento TEXT, nome_morador TEXT,
                tipo_imovel TEXT, depositos TEXT, agentes TEXT, gera_notificacao INTEGER
            );
            INSERT INTO localidades VALUES (1, 'Sede');
            INSERT INTO agentes VALUES (1, 'Ana');
            INSERT INTO visitas VALUES ('v-lab', 'PE', '2026-02-10', 1, 'Sede', '2', 'Rua Atual', '10', 'Maria', 'Ponto estratégico');
            INSERT INTO visita_agentes VALUES ('v-lab', 1);
            INSERT INTO coletas VALUES ('c-lab', 'v-lab', '18', 'Pneu');
            INSERT INTO resultados_laboratorio VALUES (1, 'c-lab', 2, 1, 0, 0);
            INSERT INTO visitas VALUES ('v-neg', 'PVE', '2026-02-11', 1, 'Sede', '3', 'Rua Negativa', '20', 'Joana', 'Residência');
            INSERT INTO coletas VALUES ('c-neg', 'v-neg', '19', 'Vaso');
            INSERT INTO resultados_laboratorio VALUES (2, 'c-neg', 0, 0, 0, 0);
            INSERT INTO focos_positivos VALUES (
                'f-hist', NULL, NULL, NULL, NULL, 'historico', 'LIRA', '2025-05-03',
                NULL, 'S. VENÂNCIO', '1', 'Rua Legada', '5', 'Fundos', 'José', 'R',
                'Caixa d''água', 'ANA / PEDRO', 1
            );
            INSERT INTO focos_positivos VALUES (
                'f-outro', NULL, NULL, NULL, NULL, 'kobo', 'PVE', '2026-02-10',
                1, 'Sede', '2', 'Rua Atual', '10', NULL, 'Maria', 'Residência',
                'Pneu', 'Ana', 1
            );
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_reune_historico_e_laboratorio_sem_duplicar_foco_atual(self):
        dados = positividade.listar(
            self.db_path,
            {"d_ini": "2025-01-01", "d_fim": "2026-12-31"},
            pagina=1,
            por_pagina=20,
        )

        self.assertEqual(dados["total"], 2)
        self.assertEqual(dados["totais"], {
            "total": 2,
            "historico": 1,
            "laboratorio": 1,
            "aegypti_quantificado": 3,
        })
        historico = next(item for item in dados["registros"] if item["origem"] == "historico")
        laboratorio = next(item for item in dados["registros"] if item["origem"] == "laboratorio")
        self.assertTrue(historico["legado_sem_detalhe"])
        self.assertIsNone(historico["aegypt_larvas"])
        self.assertEqual(laboratorio["num_tubo"], "18")
        self.assertEqual(laboratorio["aegypti_total"], 3)

    def test_filtros_respeitam_localidade_agente_e_fonte(self):
        dados = positividade.listar(
            self.db_path,
            {
                "d_ini": "2025-01-01", "d_fim": "2026-12-31",
                "localidade": ["São Venâncio"], "agente": ["Ana"], "fonte": "historico",
            },
            pagina=1,
            por_pagina=20,
        )

        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["registros"][0]["logradouro"], "Rua Legada")
        self.assertEqual(dados["registros"][0]["origem_rotulo"], "Histórico pré-sistema")

    def test_opcoes_incluem_tipo_exclusivo_do_historico(self):
        opcoes = positividade.opcoes(self.db_path)

        self.assertIn("LIRA", opcoes["tipos"])
        self.assertIn("Sede", opcoes["localidades"])
        self.assertEqual(opcoes["localidades"].count("São Venâncio"), 1)

    def test_normaliza_localidade_legada_e_filtra_suas_variantes(self):
        dados = positividade.listar(
            self.db_path,
            {
                "d_ini": "2025-01-01", "d_fim": "2026-12-31",
                "localidade": ["São Venâncio"],
            },
            pagina=1,
            por_pagina=20,
        )

        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["registros"][0]["localidade"], "São Venâncio")
        self.assertEqual(dados["por_localidade"], [{
            "localidade": "São Venâncio", "total": 1,
            "historico": 1, "laboratorio": 0,
        }])

    def test_consulta_postgresql_usa_agregacao_portavel(self):
        sql, _ = positividade._union_sql(
            positividade._consultas({"d_ini": "2026-01-01", "d_fim": "2026-12-31"}),
            "postgresql",
        )

        self.assertIn("string_agg(nomes.nome, ', ' ORDER BY nomes.nome)", sql)
        self.assertNotIn("GROUP_CONCAT", sql)
        self.assertIn("CAST(v.data AS TEXT) AS data", sql)
        self.assertIn("CAST(f.data AS TEXT) AS data", sql)


if __name__ == "__main__":
    unittest.main()
