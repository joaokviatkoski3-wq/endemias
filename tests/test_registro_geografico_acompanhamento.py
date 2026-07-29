import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_core import agentes as agentes_core
from app_core import registro_geografico as rg_core


class RegistroGeograficoAcompanhamentoTests(unittest.TestCase):
    def test_classifica_quarteiroes_e_filtra_agente(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "rg.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.executescript("""
                    CREATE TABLE localidades (id_localidade INTEGER PRIMARY KEY, nome TEXT);
                    CREATE TABLE agentes (id_agente INTEGER PRIMARY KEY, nome TEXT, ativo INTEGER);
                    INSERT INTO localidades VALUES (1, 'Centro');
                    INSERT INTO agentes VALUES (1, 'Agente RG', 1);
                """)
                rg_core.ensure_schema(conn)
                agora = "2026-07-21T10:00:00"
                quarteiroes = []
                for numero in ("0001", "0002", "0003", "0004"):
                    cur = conn.execute(
                        """INSERT INTO registro_geografico_quarteiroes
                           (id_localidade, localidade, quarteirao, criado_em, atualizado_em)
                           VALUES (1, 'Centro', ?, ?, ?)""",
                        (numero, agora, agora),
                    )
                    quarteiroes.append(cur.lastrowid)

                def inserir(id_quarteirao, ordem, data):
                    cur = conn.execute(
                        """INSERT INTO registro_geografico_imoveis
                           (id_quarteirao, ordem, id_localidade, localidade, quarteirao,
                            logradouro, numero, tipo, data_atualizacao, criado_em, atualizado_em)
                           VALUES (?, ?, 1, 'Centro', ?, 'Rua Teste', '1', 'R', ?, ?, ?)""",
                        (id_quarteirao, ordem, f"{id_quarteirao:04d}", data, agora, agora),
                    )
                    if data:
                        conn.execute(
                            "INSERT INTO registro_geografico_imovel_agentes (id_imovel, id_agente) VALUES (?, 1)",
                            (cur.lastrowid,),
                        )

                inserir(quarteiroes[0], 1, "2026-07-20")
                inserir(quarteiroes[1], 1, "2026-07-20")
                inserir(quarteiroes[1], 2, None)
                inserir(quarteiroes[2], 1, None)
                rg_core._marcar_atualizacao_sistema(conn, quarteiroes[0], 7, "Joao", agora)
                conn.commit()
            finally:
                conn.close()

            resultado = rg_core.acompanhamento_atualizacoes(str(db_path))
            por_quarteirao = {item["quarteirao_raw"]: item for item in resultado["registros"]}

            self.assertEqual(resultado["totais"], {
                "quarteiroes": 4,
                "atualizado": 1,
                "parcial": 1,
                "pendente": 1,
                "sem_cadastro": 1,
                "percentual_concluido": 33,
            })
            self.assertEqual(por_quarteirao["0001"]["situacao"], "atualizado")
            self.assertEqual(por_quarteirao["0002"]["situacao"], "parcial")
            self.assertEqual(por_quarteirao["0003"]["situacao"], "pendente")
            self.assertEqual(por_quarteirao["0004"]["situacao"], "sem_cadastro")
            self.assertEqual(por_quarteirao["0002"]["agentes"], "Agente RG")
            self.assertEqual(por_quarteirao["0001"]["atualizado_por_usuario"], "Joao")

            filtrado = rg_core.acompanhamento_atualizacoes(str(db_path), {"agente": "1"})
            self.assertEqual([item["quarteirao_raw"] for item in filtrado["registros"]], ["0001", "0002"])

    def test_inclusoes_no_mesmo_segundo_recebem_chaves_unicas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "rg.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript("""
                    CREATE TABLE localidades (
                        id_localidade INTEGER PRIMARY KEY,
                        nome TEXT,
                        cod_localidade TEXT
                    );
                    CREATE TABLE agentes (
                        id_agente INTEGER PRIMARY KEY,
                        nome TEXT,
                        ativo INTEGER
                    );
                    INSERT INTO localidades VALUES (1, 'Centro', 'CTR');
                """)
                conn.commit()
            finally:
                conn.close()

            payload = {
                "id_localidade": 1,
                "quarteirao": "0001",
                "logradouro": "Rua Teste",
                "numero": "1",
                "tipo": "R",
            }
            with mock.patch.object(
                rg_core, "_now", return_value="2026-07-29T10:00:00"
            ):
                rg_core.criar(str(db_path), payload)
                rg_core.criar(str(db_path), {**payload, "numero": "2"})

            conn = sqlite3.connect(db_path)
            try:
                total, chaves = conn.execute(
                    """SELECT COUNT(*), COUNT(DISTINCT chave_origem)
                         FROM registro_geografico_imoveis"""
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(total, 2)
            self.assertEqual(chaves, 2)


class ServidorDadosPessoaisTests(unittest.TestCase):
    def test_salva_cpf_e_data_nascimento(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "servidores.db"
            agentes_core.ensure_schema(str(db_path))
            servidor_id = agentes_core.criar(str(db_path), {
                "nome": "Maria Kobo",
                "nome_completo": "Maria da Silva",
                "cpf": "123.456.789-09",
                "data_nascimento": "1990-07-16",
            })
            servidor = agentes_core.obter(str(db_path), servidor_id)

        self.assertEqual(servidor["cpf"], "12345678909")
        self.assertEqual(servidor["data_nascimento"], "1990-07-16")


if __name__ == "__main__":
    unittest.main()
