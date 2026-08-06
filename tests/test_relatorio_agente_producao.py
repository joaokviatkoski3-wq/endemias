"""Cobre a producao diaria do relatorio por agente.

O grafico "Producao diaria" vinha apenas da tabela ``visitas``, entao os dias em
que o agente fez somente esporotricose, recolhimento, amostra, BRI, acao ou
ovitrampa desapareciam do relatorio. A lista de servidores tambem escondia quem
foi inativado, deixando o historico inacessivel pela tela.
"""

import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import producao_operacional


def _criar_banco(caminho):
    conn = db_core.connect(caminho)
    conn.executescript(
        """
        CREATE TABLE agentes (
            id_agente INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            nome_completo TEXT,
            ativo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE localidades (
            id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL
        );
        CREATE TABLE visitas (
            id_visita TEXT PRIMARY KEY,
            tipo TEXT,
            data DATE NOT NULL,
            visita TEXT,
            localidade TEXT,
            id_localidade INTEGER
        );
        CREATE TABLE visita_agentes (
            id_visita TEXT NOT NULL,
            id_agente INTEGER NOT NULL,
            PRIMARY KEY (id_visita, id_agente)
        );
        CREATE TABLE acoes_setor (
            id_acao INTEGER PRIMARY KEY AUTOINCREMENT,
            data DATE NOT NULL,
            tipo TEXT,
            localidade TEXT,
            publico_aproximado INTEGER
        );
        CREATE TABLE acoes_setor_agentes (
            id_acao INTEGER NOT NULL,
            id_agente INTEGER NOT NULL,
            PRIMARY KEY (id_acao, id_agente)
        );
        CREATE TABLE registro_geografico_imoveis (
            id_imovel INTEGER PRIMARY KEY AUTOINCREMENT,
            localidade TEXT,
            data_atualizacao DATE
        );
        CREATE TABLE registro_geografico_imovel_agentes (
            id_imovel INTEGER NOT NULL,
            id_agente INTEGER NOT NULL,
            PRIMARY KEY (id_imovel, id_agente)
        );
        CREATE TABLE resultados_laboratorio (
            id_resultado INTEGER PRIMARY KEY AUTOINCREMENT,
            data_coleta DATE,
            data_leitura DATE,
            id_laboratorista INTEGER,
            laboratorista TEXT
        );
        CREATE TABLE ovitrampas_leituras (
            id_leitura TEXT PRIMARY KEY,
            distrito TEXT,
            ovos INTEGER,
            data_coleta DATE,
            data_leitura DATE,
            id_laboratorista INTEGER
        );
        CREATE TABLE ovitrampas_laboratorio_lotes (
            id_lote INTEGER PRIMARY KEY AUTOINCREMENT,
            data_movimento DATE,
            status TEXT,
            id_laboratorista INTEGER,
            laboratorista_nome TEXT
        );
        """
    )
    conn.execute("INSERT INTO agentes (nome, ativo) VALUES ('Marlon', 1)")
    conn.execute("INSERT INTO agentes (nome, ativo) VALUES ('Rafael', 0)")
    conn.execute("INSERT INTO localidades (nome) VALUES ('Sede')")

    # Marlon: dia 10 tem visita, dia 11 tem apenas acao do setor.
    conn.execute(
        "INSERT INTO visitas (id_visita,tipo,data,visita,localidade,id_localidade)"
        " VALUES ('v1','PE','2026-07-10','normal','Sede',1)"
    )
    conn.execute("INSERT INTO visita_agentes VALUES ('v1', 1)")
    conn.execute(
        "INSERT INTO acoes_setor (data,tipo,localidade,publico_aproximado)"
        " VALUES ('2026-07-11','educativa','Sede',30)"
    )
    conn.execute("INSERT INTO acoes_setor_agentes VALUES (1, 1)")

    # Rafael saiu da equipe, mas tem producao registrada no periodo.
    conn.execute(
        "INSERT INTO visitas (id_visita,tipo,data,visita,localidade,id_localidade)"
        " VALUES ('v2','PE','2026-07-12','normal','Sede',1)"
    )
    conn.execute("INSERT INTO visita_agentes VALUES ('v2', 2)")
    conn.commit()
    return conn


class ProducaoDiariaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.temp.name) / "relatorio.db"
        self.conn = _criar_banco(self.caminho)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def _resumo(self, agente):
        return producao_operacional.resumo(
            self.caminho,
            {"agente": [agente], "d_ini": "2026-07-01", "d_fim": "2026-07-31"},
        )

    def test_por_dia_soma_atividades_alem_das_visitas(self):
        resumo = self._resumo("Marlon")
        dias = [item["dia"] for item in resumo["por_dia"]]
        self.assertIn("2026-07-10", dias)  # visita
        self.assertIn("2026-07-11", dias)  # so acao do setor
        self.assertEqual(len(dias), 2)

    def test_por_dia_acompanha_o_total_de_dias(self):
        resumo = self._resumo("Marlon")
        self.assertEqual(len(resumo["por_dia"]), resumo["totais"]["dias"])

    def test_por_dia_vem_em_ordem_cronologica(self):
        resumo = self._resumo("Marlon")
        dias = [item["dia"] for item in resumo["por_dia"]]
        self.assertEqual(dias, sorted(dias))

    def test_agente_sem_visita_ainda_aparece_na_producao(self):
        # Antes da correcao o grafico ficava vazio para quem so fez outro
        # tipo de trabalho no periodo.
        self.conn.execute("INSERT INTO agentes (nome, ativo) VALUES ('Pedro', 1)")
        self.conn.execute(
            "INSERT INTO acoes_setor (data,tipo,localidade) VALUES ('2026-07-15','limpeza','Sede')"
        )
        self.conn.execute("INSERT INTO acoes_setor_agentes VALUES (2, 3)")
        self.conn.commit()
        resumo = self._resumo("Pedro")
        self.assertEqual([item["dia"] for item in resumo["por_dia"]], ["2026-07-15"])

    def test_dia_sem_producao_do_agente_nao_entra(self):
        resumo = self._resumo("Marlon")
        dias = [item["dia"] for item in resumo["por_dia"]]
        self.assertNotIn("2026-07-12", dias)  # dia do Rafael

    def test_dia_de_registro_geografico_conta_como_producao(self):
        self.conn.execute(
            "INSERT INTO registro_geografico_imoveis (localidade,data_atualizacao)"
            " VALUES ('Sede','2026-07-20')"
        )
        self.conn.execute("INSERT INTO registro_geografico_imovel_agentes VALUES (1, 1)")
        self.conn.commit()
        dias = [item["dia"] for item in self._resumo("Marlon")["por_dia"]]
        self.assertIn("2026-07-20", dias)

    def test_quantidade_de_imoveis_nao_muda_o_numero_de_dias(self):
        # Um dia de RG e um dia de producao, tenha ele 1 ou 300 imoveis.
        for _ in range(300):
            cur = self.conn.execute(
                "INSERT INTO registro_geografico_imoveis (localidade,data_atualizacao)"
                " VALUES ('Sede','2026-07-21')"
            )
            self.conn.execute(
                "INSERT INTO registro_geografico_imovel_agentes VALUES (?, 1)",
                (cur.lastrowid,),
            )
        self.conn.commit()
        resumo = self._resumo("Marlon")
        dias = [item["dia"] for item in resumo["por_dia"]]
        self.assertEqual(dias.count("2026-07-21"), 1)
        self.assertEqual(len(dias), resumo["totais"]["dias"])

    def test_leitura_de_laboratorio_conta_mesmo_sem_tabela_de_vinculo(self):
        # O laboratorista fica numa coluna da propria leitura.
        self.conn.execute(
            "INSERT INTO resultados_laboratorio (data_leitura,id_laboratorista)"
            " VALUES ('2026-07-22', 1)"
        )
        self.conn.commit()
        dias = [item["dia"] for item in self._resumo("Marlon")["por_dia"]]
        self.assertIn("2026-07-22", dias)

    def test_leitura_sem_data_de_leitura_usa_a_data_da_coleta(self):
        self.conn.execute(
            "INSERT INTO resultados_laboratorio (data_coleta,data_leitura,id_laboratorista)"
            " VALUES ('2026-07-23', NULL, 1)"
        )
        self.conn.commit()
        dias = [item["dia"] for item in self._resumo("Marlon")["por_dia"]]
        self.assertIn("2026-07-23", dias)

    def test_leitura_de_ovitrampa_conta_como_producao(self):
        self.conn.execute(
            "INSERT INTO ovitrampas_leituras (id_leitura,distrito,ovos,data_leitura,id_laboratorista)"
            " VALUES ('L1','Sede',12,'2026-07-24', 1)"
        )
        self.conn.commit()
        resumo = self._resumo("Marlon")
        self.assertIn("2026-07-24", [item["dia"] for item in resumo["por_dia"]])
        leitura = next(
            a for a in resumo["por_atividade"] if a["codigo"] == "OVITRAMPAS_LEITURA"
        )
        self.assertEqual(leitura["extras"]["ovos"], 12)

    def test_lote_credita_pelo_nome_e_nao_pelo_id_do_usuario(self):
        # O id_laboratorista do lote e o id do USUARIO logado. Marlon e o
        # agente 1; gravar id 2 (que em agentes e o Rafael) nao pode roubar
        # o credito dele, porque o nome no lote diz Marlon.
        self.conn.execute(
            "INSERT INTO ovitrampas_laboratorio_lotes"
            " (data_movimento,status,id_laboratorista,laboratorista_nome)"
            " VALUES ('2026-07-26','concluido', 2, 'Marlon')"
        )
        self.conn.commit()
        self.assertIn("2026-07-26", [i["dia"] for i in self._resumo("Marlon")["por_dia"]])
        self.assertNotIn("2026-07-26", [i["dia"] for i in self._resumo("Rafael")["por_dia"]])

    def test_nome_do_lote_ignora_caixa_e_espacos(self):
        self.conn.execute(
            "INSERT INTO ovitrampas_laboratorio_lotes"
            " (data_movimento,laboratorista_nome) VALUES ('2026-07-27', '  marlon ')"
        )
        self.conn.commit()
        self.assertIn("2026-07-27", [i["dia"] for i in self._resumo("Marlon")["por_dia"]])

    def test_lote_sem_nome_nao_credita_ninguem(self):
        self.conn.execute(
            "INSERT INTO ovitrampas_laboratorio_lotes"
            " (data_movimento,laboratorista_nome) VALUES ('2026-07-28', '')"
        )
        self.conn.commit()
        self.assertNotIn("2026-07-28", [i["dia"] for i in self._resumo("Marlon")["por_dia"]])

    def test_laboratorio_casa_pelo_nome_quando_o_id_esta_vazio(self):
        self.conn.execute(
            "INSERT INTO resultados_laboratorio (data_leitura,id_laboratorista,laboratorista)"
            " VALUES ('2026-07-29', NULL, 'marlon')"
        )
        self.conn.commit()
        self.assertIn("2026-07-29", [i["dia"] for i in self._resumo("Marlon")["por_dia"]])

    def test_agente_de_outro_laboratorio_nao_entra(self):
        self.conn.execute(
            "INSERT INTO resultados_laboratorio (data_leitura,id_laboratorista)"
            " VALUES ('2026-07-25', 2)"
        )
        self.conn.commit()
        dias = [item["dia"] for item in self._resumo("Marlon")["por_dia"]]
        self.assertNotIn("2026-07-25", dias)


class ServidoresDoRelatorioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.temp.name) / "servidores.db"
        self.conn = _criar_banco(self.caminho)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def _servidores(self, d_ini, d_fim):
        from unittest import mock

        from blueprints import relatorio_agente

        with mock.patch.object(relatorio_agente, "_get_db", return_value=self.conn):
            # A conexao e reaproveitada pelo teste, entao o close do modulo
            # nao pode derrubar o banco em memoria do proximo caso.
            with mock.patch.object(self.conn, "close"):
                return relatorio_agente._servidores_relatorio(d_ini, d_fim)

    def test_inativo_com_producao_no_periodo_aparece(self):
        nomes = [item["nome"] for item in self._servidores("2026-07-01", "2026-07-31")]
        self.assertIn("Rafael", nomes)

    def test_inativo_vem_marcado_na_exibicao(self):
        servidores = self._servidores("2026-07-01", "2026-07-31")
        rafael = next(item for item in servidores if item["nome"] == "Rafael")
        self.assertIn("inativo", rafael["nome_exibicao"].lower())
        self.assertEqual(rafael["ativo"], 0)

    def test_inativo_sem_producao_no_periodo_fica_de_fora(self):
        nomes = [item["nome"] for item in self._servidores("2026-09-01", "2026-09-30")]
        self.assertNotIn("Rafael", nomes)
        self.assertIn("Marlon", nomes)

    def test_sem_periodo_mantem_somente_ativos(self):
        nomes = [item["nome"] for item in self._servidores(None, None)]
        self.assertEqual(nomes, ["Marlon"])

    def test_inativo_reaparece_por_producao_de_laboratorio(self):
        # A busca precisa enxergar tambem as fontes ligadas por coluna direta.
        self.conn.execute(
            "INSERT INTO resultados_laboratorio (data_leitura,id_laboratorista)"
            " VALUES ('2026-08-05', 2)"
        )
        self.conn.commit()
        nomes = [item["nome"] for item in self._servidores("2026-08-01", "2026-08-31")]
        self.assertIn("Rafael", nomes)


if __name__ == "__main__":
    unittest.main()
