import sqlite3
import unittest

from app_core import visitas


class VisitasPostgresqlCompatTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
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
            CREATE TABLE visitas (
                id_visita TEXT PRIMARY KEY,
                kobo_uuid TEXT NOT NULL,
                tipo TEXT NOT NULL,
                data TEXT NOT NULL,
                hora_inicio TEXT,
                hora_fim TEXT,
                ciclo INTEGER,
                localidade TEXT,
                logradouro TEXT,
                numero TEXT,
                quarteirao INTEGER,
                sequencia TEXT,
                morador TEXT,
                tipo_imovel TEXT,
                visita TEXT,
                lado TEXT,
                agua_sanepar INTEGER,
                observacoes TEXT,
                processado_em TEXT NOT NULL,
                id_localidade INTEGER
            );
            CREATE TABLE visita_agentes (
                id_visita TEXT NOT NULL,
                id_agente INTEGER NOT NULL,
                UNIQUE(id_visita, id_agente)
            );
            CREATE TABLE depositos_inspecionados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_visita TEXT NOT NULL,
                tipo_deposito TEXT NOT NULL,
                inspecionado INTEGER,
                eliminado INTEGER,
                tratado INTEGER,
                tipo_tratamento TEXT,
                qtd_carga REAL
            );
            CREATE TABLE tratamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_visita TEXT NOT NULL,
                tipo TEXT,
                quantidade_carga REAL,
                qtd_depositos_tratados INTEGER
            );
            CREATE TABLE coletas (
                id_coleta TEXT PRIMARY KEY,
                id_visita TEXT NOT NULL,
                num_tubo TEXT,
                codigo_deposito TEXT,
                tipo_deposito TEXT,
                deposito_eliminado INTEGER
            );
            CREATE TABLE resultados_laboratorio (
                id_resultado INTEGER PRIMARY KEY AUTOINCREMENT,
                id_coleta TEXT NOT NULL,
                num_tubo TEXT NOT NULL,
                data_coleta TEXT NOT NULL,
                data_leitura TEXT,
                laboratorista TEXT,
                aegypt_larvas INTEGER DEFAULT 0,
                aegypt_pupas INTEGER DEFAULT 0,
                aegypt_exuvias INTEGER DEFAULT 0,
                aegypt_adulto INTEGER DEFAULT 0,
                albopictus_larvas INTEGER DEFAULT 0,
                albopictus_pupas INTEGER DEFAULT 0,
                albopictus_exuvias INTEGER DEFAULT 0,
                albopictus_adulto INTEGER DEFAULT 0,
                outra_larvas INTEGER DEFAULT 0,
                outra_pupas INTEGER DEFAULT 0,
                outra_exuvias INTEGER DEFAULT 0,
                outra_adulto INTEGER DEFAULT 0
            );
            CREATE TABLE focos_positivos (
                id_foco TEXT PRIMARY KEY,
                id_visita TEXT,
                id_coleta TEXT,
                num_tubo TEXT,
                tipo_trabalho TEXT,
                data TEXT,
                id_localidade INTEGER,
                localidade TEXT,
                quarteirao INTEGER,
                logradouro TEXT,
                numero TEXT,
                nome_morador TEXT,
                tipo_imovel TEXT,
                agentes TEXT,
                gera_notificacao INTEGER DEFAULT 1,
                status_notificacao TEXT,
                data_entrega TEXT,
                observacoes TEXT,
                codigo TEXT
            );
            INSERT INTO localidades(nome) VALUES ('Lamenha');
            INSERT INTO agentes(nome, nome_completo)
            VALUES ('Fernando', 'Fernando');
            INSERT INTO visitas (
                id_visita, kobo_uuid, tipo, data, hora_inicio,
                localidade, id_localidade, logradouro, numero,
                quarteirao, morador, tipo_imovel, visita,
                agua_sanepar, observacoes, processado_em
            ) VALUES (
                'visita-1', 'uuid-visita-1', 'PVE', '2026-07-28',
                '09:30', 'Lamenha', 1, 'Rua Alfa', '10', 123,
                'Maria', 'Residencia', 'Normal', 1,
                'Observacao inicial', '2026-07-28T10:00:00'
            );
            INSERT INTO visita_agentes VALUES ('visita-1', 1);
            INSERT INTO depositos_inspecionados (
                id_visita, tipo_deposito, inspecionado, eliminado,
                tratado, tipo_tratamento, qtd_carga
            ) VALUES ('visita-1', 'B', 3, 1, 2, 'Natular', 4);
            INSERT INTO tratamentos (
                id_visita, tipo, quantidade_carga,
                qtd_depositos_tratados
            ) VALUES ('visita-1', 'Natular', 4, 2);
            INSERT INTO coletas (
                id_coleta, id_visita, num_tubo, codigo_deposito,
                tipo_deposito, deposito_eliminado
            ) VALUES ('coleta-1', 'visita-1', 'T-100', 'B1', 'B', 0);
            INSERT INTO resultados_laboratorio (
                id_coleta, num_tubo, data_coleta, data_leitura,
                aegypt_larvas
            ) VALUES (
                'coleta-1', 'T-100', '2026-07-28', '2026-07-29', 2
            );
            INSERT INTO focos_positivos (
                id_foco, id_visita, id_coleta, num_tubo,
                gera_notificacao
            ) VALUES ('foco-1', 'visita-1', 'coleta-1', 'T-100', 1);
            """
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_lista_detalhe_e_edicao_compartilham_o_mesmo_nucleo(self):
        opcoes = visitas.filter_options(self.conn)
        self.assertIn("Lamenha", opcoes["localidades"])
        self.assertIn("Fernando", opcoes["agentes"])

        lista = visitas.listar(
            self.conn,
            {"busca": "RUA ALFA", "laboratorio": "positivo"},
            pagina=1,
            por_pagina=10,
        )
        self.assertEqual(lista["total"], 1)
        self.assertEqual(lista["registros"][0]["agentes"], "Fernando")
        self.assertEqual(lista["registros"][0]["laboratorio_status"], "positivo")

        detalhe = visitas.detalhar(self.conn, "visita-1")
        self.assertEqual(detalhe["depositos"][0]["inspecionado"], 3)
        self.assertEqual(detalhe["coletas"][0]["aegypt_larvas"], 2)

        auditoria = visitas.editar(
            self.conn,
            "visita-1",
            {
                "data": "2026-07-29",
                "localidade": "grasiela",
                "agentes": "viviane_1, cecon",
                "observacoes": "Revisada",
                "coletas": [
                    {
                        "id_coleta": "coleta-1",
                        "num_tubo": "T-101",
                        "codigo_deposito": "A2-1",
                        "tipo_deposito": "A2",
                        "deposito_eliminado": True,
                    }
                ],
            },
        )
        self.assertEqual(auditoria["depois"]["localidade"], "Graziela")
        self.assertEqual(auditoria["agentes"], ["Viviane", "Ceccon"])

        detalhe = visitas.detalhar(self.conn, "visita-1")
        self.assertEqual(detalhe["visita"]["data"], "2026-07-29")
        self.assertEqual(detalhe["visita"]["localidade_nome"], "Graziela")
        self.assertEqual(detalhe["coletas"][0]["num_tubo"], "T-101")
        self.assertEqual(detalhe["coletas"][0]["aegypt_larvas"], 2)

    def test_coleta_com_resultado_nao_pode_ser_removida(self):
        with self.assertRaises(visitas.ColetaComResultado):
            visitas.editar(
                self.conn,
                "visita-1",
                {"data": "2026-07-28", "coletas": []},
            )

        coleta = self.conn.execute(
            "SELECT num_tubo FROM coletas WHERE id_coleta='coleta-1'"
        ).fetchone()
        self.assertIsNotNone(coleta)
        self.assertEqual(coleta["num_tubo"], "T-100")


if __name__ == "__main__":
    unittest.main()
