import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose


class ControleEntregasMedicacaoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = str(Path(self.tmp.name) / "entregas.db")

    def _animal_receita(self, nome, localidade):
        animal = esporotricose.salvar_doente(self.db_path, {
            "nome": nome, "tutor": "Tutor " + nome, "localidade": localidade,
            "endereco": "Rua Teste, 12", "status": "Em tratamento",
        })
        receita = esporotricose.salvar_receita_doente(
            self.db_path, animal, {"capsulas_total": 100, "data_receita": "2026-09-01"},
        )
        return animal, receita

    def test_conta_animais_unicos_por_fonte_e_exibe_todas_as_entregas(self):
        animal, receita = self._animal_receita("Gato A", "Centro")
        outro, outra_receita = self._animal_receita("Gato B", "Outra")
        for quantidade, fonte, data in ((20, "SESA", "2026-09-02"),
                                       (10, "SESA", "2026-09-05"),
                                       (15, "Município", "2026-09-10")):
            esporotricose.salvar_entrega_doente(self.db_path, receita, {
                "quantidade": quantidade, "fonte_medicacao": fonte,
                "data_entrega": data, "baixa_zoomed": "Sim",
            })
        esporotricose.salvar_entrega_doente(self.db_path, outra_receita, {
            "quantidade": 8, "fonte_medicacao": "Município", "data_entrega": "2026-09-11",
            "baixa_zoomed": "Não", "observacoes": "Conferir baixa",
        })
        dados = esporotricose.controle_entregas_medicacao(self.db_path)
        self.assertEqual(dados["total"], 4)
        self.assertEqual((dados["por_fonte"]["SESA"]["animais"], dados["por_fonte"]["SESA"]["entregas"], dados["por_fonte"]["SESA"]["capsulas"]), (1, 2, 30))
        self.assertEqual((dados["por_fonte"]["Município"]["animais"], dados["por_fonte"]["Município"]["entregas"], dados["por_fonte"]["Município"]["capsulas"]), (2, 2, 23))
        self.assertEqual(dados["registros"][0]["id_animal_doente"], outro)
        self.assertEqual(dados["registros"][1]["id_animal_doente"], animal)
        self.assertEqual(dados["registros"][0]["observacoes_entrega"], "Conferir baixa")
        localidade_oficial = esporotricose.obter_doente(self.db_path, animal)["localidade"]
        filtrado = esporotricose.controle_entregas_medicacao(self.db_path, {
            "fonte": "Município", "inicio": "2026-09-10", "fim": "2026-09-10", "localidade": localidade_oficial,
        })
        self.assertEqual(filtrado["total"], 1)
        self.assertEqual(filtrado["registros"][0]["quantidade"], 15)
        self.assertEqual(filtrado["por_fonte"]["SESA"]["capsulas"], 0)
        self.assertEqual(esporotricose.controle_entregas_medicacao(
            self.db_path, {"baixa_zoomed": "Não", "busca": "Gato B"}
        )["total"], 1)

    def test_edicao_de_fonte_atualiza_o_controle_sem_cadastro_duplicado(self):
        _animal, receita = self._animal_receita("Gato A", "Centro")
        entrega = esporotricose.salvar_entrega_doente(self.db_path, receita, {
            "quantidade": 30, "data_entrega": "2026-09-10",
        })
        esporotricose.atualizar_entrega_doente(self.db_path, entrega, {
            "quantidade": 30, "data_entrega": "2026-09-10", "fonte_medicacao": "Município", "baixa_zoomed": "Sim",
        })
        dados = esporotricose.controle_entregas_medicacao(self.db_path)
        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["por_fonte"]["SESA"]["capsulas"], 0)
        self.assertEqual(dados["por_fonte"]["Município"]["capsulas"], 30)

    def test_rejeita_filtros_invalidos(self):
        for filtros in ({"fonte": "Outra"}, {"inicio": "2026-09-30", "fim": "2026-09-01"},
                        {"inicio": "invalido"}, {"baixa_zoomed": "talvez"}):
            with self.subTest(filtros=filtros), self.assertRaises(esporotricose.ValidationError):
                esporotricose.controle_entregas_medicacao(self.db_path, filtros)

    def test_paginacao_nao_altera_os_totais(self):
        _animal, receita = self._animal_receita("Gato A", "Centro")
        for _ in range(51):
            esporotricose.salvar_entrega_doente(self.db_path, receita, {
                "quantidade": 1, "fonte_medicacao": "SESA", "data_entrega": "2026-09-10",
            })
        segunda = esporotricose.controle_entregas_medicacao(self.db_path, {"pagina": "2"})
        self.assertEqual(segunda["total"], 51)
        self.assertEqual(len(segunda["registros"]), 1)
        self.assertEqual(segunda["por_fonte"]["SESA"]["animais"], 1)
        self.assertEqual(segunda["por_fonte"]["SESA"]["capsulas"], 51)


if __name__ == "__main__":
    unittest.main()
