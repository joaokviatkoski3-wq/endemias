"""Filtros de pendencia de cadastro dos Pontos Estrategicos."""

import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import pontos_estrategicos as pe_core


class FiltrosPendenciaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.caminho = Path(self.temp.name) / "pe.db"
        self.conn = db_core.connect(self.caminho)
        self.conn.executescript(
            """
            CREATE TABLE localidades (
                id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL, cod_localidade TEXT
            );
            CREATE TABLE visitas (
                id_visita TEXT PRIMARY KEY, tipo TEXT, data DATE NOT NULL,
                id_localidade INTEGER, quarteirao INTEGER, id_pe INTEGER, codigo_pe TEXT
            );
            CREATE TABLE focos_positivos (
                id_foco INTEGER PRIMARY KEY AUTOINCREMENT, gera_notificacao INTEGER,
                id_localidade INTEGER, quarteirao INTEGER
            );
            """
        )
        pe_core.ensure_schema(self.conn)
        agora = "2026-08-01T10:00:00"
        # Completo, sem nenhuma pendencia.
        self._inserir("PE-0001", "Completo", agora, cnpj="11.111.111/0001-11",
                      razao_social="Empresa A", telefone="4199990000", tipo="Borracharia",
                      latitude=-25.3, longitude=-49.2, numero="100",
                      data_inclusao="2026-01-10", observacoes="ok")
        # So falta CNPJ e razao social.
        self._inserir("PE-0002", "Sem CNPJ", agora, telefone="4199990001",
                      tipo="Ferro velho", latitude=-25.3, longitude=-49.2,
                      numero="200", data_inclusao="2026-01-11", observacoes="ok")
        # So falta telefone.
        self._inserir("PE-0003", "Sem telefone", agora, cnpj="22.222.222/0001-22",
                      razao_social="Empresa C", tipo="Obra", latitude=-25.3,
                      longitude=-49.2, numero="300", data_inclusao="2026-01-12",
                      observacoes="ok")
        # Inativo e sem telefone.
        self._inserir("PE-0004", "Inativo", agora, situacao=0, cnpj="33.333.333/0001-33",
                      razao_social="Empresa D", tipo="Obra", latitude=-25.3,
                      longitude=-49.2, numero="400", data_inclusao="2026-01-13",
                      observacoes="ok")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def _inserir(self, codigo, nome, agora, situacao=1, **campos):
        colunas = ["codigo_pe", "nome", "situacao", "criado_em", "atualizado_em"]
        valores = [codigo, nome, situacao, agora, agora]
        for chave, valor in campos.items():
            colunas.append(chave)
            valores.append(valor)
        marcadores = ",".join("?" * len(valores))
        self.conn.execute(
            f"INSERT INTO pontos_estrategicos ({','.join(colunas)}) VALUES ({marcadores})",
            valores,
        )

    def _codigos(self, filtros):
        return sorted(r["codigo_pe"] for r in pe_core.listar(self.conn, filtros)["registros"])

    def test_sem_filtro_lista_todos(self):
        self.assertEqual(len(self._codigos({})), 4)

    def test_filtra_por_uma_pendencia(self):
        self.assertEqual(self._codigos({"pendencias_cadastro": ["sem_cnpj"]}), ["PE-0002"])

    def test_filtra_por_telefone_incluindo_inativo(self):
        # O recorte por situacao e responsabilidade do filtro Situacao.
        self.assertEqual(
            self._codigos({"pendencias_cadastro": ["sem_telefone"]}),
            ["PE-0003", "PE-0004"],
        )

    def test_duas_pendencias_combinam_com_ou(self):
        self.assertEqual(
            self._codigos({"pendencias_cadastro": ["sem_cnpj", "sem_telefone"]}),
            ["PE-0002", "PE-0003", "PE-0004"],
        )

    def test_pendencia_combina_com_situacao(self):
        self.assertEqual(
            self._codigos({"pendencias_cadastro": ["sem_telefone"], "situacao": "1"}),
            ["PE-0003"],
        )

    def test_codigo_desconhecido_e_ignorado(self):
        self.assertEqual(len(self._codigos({"pendencias_cadastro": ["sem_qualquer_coisa"]})), 4)

    def test_texto_unico_tambem_e_aceito(self):
        self.assertEqual(self._codigos({"pendencias_cadastro": "sem_cnpj"}), ["PE-0002"])

    def test_totais_acompanham_o_filtro(self):
        dados = pe_core.listar(self.conn, {"pendencias_cadastro": ["sem_cnpj"]})
        self.assertEqual(dados["totais"]["total"], 1)
        self.assertEqual(dados["totais"]["sem_cnpj"], 1)

    def test_totais_sem_filtro_contam_cada_pendencia(self):
        totais = pe_core.listar(self.conn, {})["totais"]
        self.assertEqual(totais["sem_cnpj"], 1)
        self.assertEqual(totais["sem_telefone"], 2)
        self.assertEqual(totais["sem_numero"], 0)

    def test_opcoes_expoem_as_pendencias(self):
        codigos = [p["codigo"] for p in pe_core.opcoes(self.conn)["pendencias"]]
        self.assertIn("sem_cnpj", codigos)
        self.assertIn("sem_coordenadas", codigos)
        self.assertEqual(len(codigos), len(pe_core.PENDENCIAS_CADASTRO))

    def test_nome_nao_e_pendencia(self):
        # nome e NOT NULL no schema e sempre vem preenchido; nao ha o que cobrar.
        self.assertNotIn("sem_nome", pe_core.PENDENCIAS_POR_CODIGO)

    def test_data_desativacao_nao_e_pendencia(self):
        # Num PE ativo o normal e estar vazia.
        self.assertNotIn("sem_data_desativacao", pe_core.PENDENCIAS_POR_CODIGO)


if __name__ == "__main__":
    unittest.main()
