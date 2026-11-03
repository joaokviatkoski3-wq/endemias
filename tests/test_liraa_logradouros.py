"""Logradouros RG no XLSForm e compatibilidade dos envios, em base sintética."""

from io import BytesIO
import sqlite3
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from app_core import liraa_kobo as kobo, liraa_logradouros as ruas
from app_core import liraa_operacional as op, liraa_xlsform as xls
from tests import test_liraa_operacao as fixtures


class LogradourosTests(unittest.TestCase):
    def setUp(self):
        self.env = fixtures.OperacaoTests()
        self.env.setUp()
        self.addCleanup(self.env.doCleanups)
        self.target = self.env.target

    def workbook(self):
        op.salvar_configuracao(self.target, self.env.ciclo, [], "asset123")
        book = load_workbook(BytesIO(xls.gerar(self.target, self.env.ciclo, self.env.base)))
        self.addCleanup(book.close)
        return book

    @staticmethod
    def rows(sheet):
        values = list(sheet.values)
        return [dict(zip(values[0], row)) for row in values[1:] if any(v is not None for v in row)]

    def test_codigo_unicode_contexto_canonico_e_compatibilidade(self):
        nome = "Rua São João d’Ávila / São José"
        valor = ruas.codigo("Sede", "0408.1", nome)
        self.assertEqual(ruas.nome_resposta(valor, "ignorar", "Sede", "408,1"), nome)
        self.assertEqual(ruas.nome_resposta("Rua antiga", None, "Sede", "1"), "Rua antiga")
        self.assertEqual(ruas.nome_resposta("outro", "  Rua Nova  ", "Sede", "1"), "Rua Nova")
        for loc, q in (("Sede", "409"), ("Tranqueira", "408.1")):
            with self.assertRaisesRegex(ValueError, "não corresponde"):
                ruas.nome_resposta(valor, None, loc, q)
        self.assertNotEqual(valor, ruas.codigo("Sede", "409", nome))

    def test_importacao_nome_snapshot_outro_e_texto_antigo(self):
        for numero, nome in enumerate(("Rua São João", "Rua nova", "Texto anterior")):
            registro = self.env.registro(str(numero), tubitos=0)
            dados = registro["Dados_visita"]
            if numero == 0:
                dados["Logradouro"] = ruas.codigo(dados["Localidade"], dados["Quarteir_o"], nome)
                dados["Logradouro_outro"] = "Complemento antigo ignorado"
            elif numero == 1:
                dados.update(Logradouro="outro", Logradouro_outro=nome)
            else:
                dados["Logradouro"] = nome
            self.assertEqual(kobo.importar(self.target, self.env.ciclo, [registro]), 1)
        self.assertEqual({r["logradouro"] for r in kobo.listar(self.target)}, {"Rua São João", "Rua nova", "Texto anterior"})

    def test_importacao_rejeita_outro_vazio_e_escolha_de_outro_quarteirao(self):
        registro = self.env.registro(tubitos=0)
        for valor in ("outro", "lg1_invalido", ruas.codigo("Sede", "9999", "Rua Teste")):
            registro["Dados_visita"]["Logradouro"] = valor
            with self.assertRaises(kobo.LiraaKoboError):
                kobo.importar(self.target, self.env.ciclo, [registro])
        self.assertEqual(kobo.listar(self.target), [])

    def test_catalogo_grafia_frequente_deduplicada_e_sem_cadastro(self):
        self.env.fixture.adicionar_rg((("R", 0), ("R", 0), ("R", 0), ("R", 0)))
        conn = sqlite3.connect(self.target)
        try:
            ids = [r[0] for r in conn.execute("SELECT id_imovel FROM registro_geografico_imoveis")]
            for ident, nome in zip(ids, ("RUA SÃO JOÃO", "RUA SÃO JOÃO", "Rua Sao Joao", "Sem logradouro")):
                conn.execute("UPDATE registro_geografico_imoveis SET logradouro=? WHERE id_imovel=?", (nome, ident))
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(ruas.catalogo(self.target), {("Sede", "1"): ["RUA SÃO JOÃO"]})

    def test_cascata_por_localidade_quarteirao_com_outro_e_sem_rg(self):
        self.env.fixture.adicionar_rg((("R", 0),))
        book = self.workbook()
        survey = {r["name"]: r for r in self.rows(book["survey"])}
        escolhas = [r for r in self.rows(book["choices"]) if r["list_name"] == ruas.LISTA]
        selecionadas = [r for r in escolhas if r["name"] != "outro"]
        self.assertEqual(len(selecionadas), 1)
        self.assertEqual((selecionadas[0]["localidade"], selecionadas[0]["quarteirao_rg"], selecionadas[0]["label"]), ("centro", "1", "Rua Teste"))
        self.assertIn("localidade=${Localidade}", survey["Logradouro"]["choice_filter"])
        self.assertIn("quarteirao_rg=string(number(", survey["Logradouro"]["choice_filter"])
        self.assertIn("or name='outro'", survey["Logradouro"]["choice_filter"])
        self.assertEqual(survey["Logradouro_outro"]["relevant"], "${Logradouro} = 'outro'")
        self.assertEqual(survey["Logradouro_outro"]["required"], "true")
        self.assertEqual(sum(r["name"] == "outro" for r in escolhas), 1)

    def test_reaplicar_idempotente_e_opcoes_unicas_para_rua_repetida(self):
        book = self.workbook()
        headers = [cell.value for cell in book["choices"][1]]
        for numero in ("2001", "2002"):
            opcao = {"list_name": "endemias_quarteiroes", "name": numero, "label": numero, "localidade": "centro"}
            book["choices"].append([opcao.get(h) for h in headers])
        quarters = [r for r in self.rows(book["choices"]) if r["list_name"] == "endemias_quarteiroes"]
        self.assertGreaterEqual(len(quarters), 2)
        catalogo = {("Sede", str(int(q["name"]))): ["Rua comum"] for q in quarters}
        with patch.object(ruas, "catalogo", return_value=catalogo):
            ruas.aplicar(book, self.target)
            antes = self.rows(book["choices"])
            ruas.aplicar(book, self.target)
        self.assertEqual(antes, self.rows(book["choices"]))
        values = [r["name"] for r in antes if r["list_name"] == ruas.LISTA]
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(sum(r["name"] == "Logradouro_outro" for r in self.rows(book["survey"])), 1)

