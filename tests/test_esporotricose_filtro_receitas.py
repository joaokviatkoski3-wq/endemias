import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose as core


class FiltroReceitasDoentesTests(unittest.TestCase):
    def test_pendente_sem_pendencia_e_sem_receita(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = str(Path(pasta) / "receitas.db")
            sem_receita = core.salvar_doente(banco, {"nome": "Sem receita", "tutor": "Tutor", "status": "Em tratamento"})
            regular = core.salvar_doente(banco, {"nome": "Regular", "tutor": "Tutor", "status": "Em tratamento"})
            pendente = core.salvar_doente(banco, {"nome": "Pendente", "tutor": "Tutor", "status": "Em tratamento"})
            core.salvar_receita_doente(banco, regular, {"capsulas_total": 30})
            core.salvar_receita_doente(banco, pendente, {"capsulas_total": 30})
            core.salvar_receita_doente(banco, pendente, {"receita_pendente": True})

            def ids(situacao):
                dados = core.listar_doentes(banco, {"situacao_receita": situacao})
                self.assertEqual(dados["total"], len(dados["registros"]))
                return {item["id_animal_doente"] for item in dados["registros"]}

            self.assertEqual(ids("pendente"), {pendente})
            self.assertEqual(ids("regular"), {regular})
            self.assertEqual(ids("sem_receita"), {sem_receita})
            self.assertEqual(ids(""), {sem_receita, regular, pendente})

    def test_situacao_invalida(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = str(Path(pasta) / "receitas.db")
            with self.assertRaises(core.ValidationError):
                core.listar_doentes(banco, {"situacao_receita": "qualquer"})
