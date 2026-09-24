import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose as esporotricose_core
from app_core import db as db_core


class EstoqueAutomaticoTests(unittest.TestCase):
    def test_saldos_por_fonte_e_correcao_de_entrega_antiga(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            animal = esporotricose_core.salvar_doente(db_path, {
                "nome": "Paciente", "tutor": "Tutor", "status": "Em tratamento",
            })
            receita = esporotricose_core.salvar_receita_doente(
                db_path, animal, {"capsulas_total": 60},
            )
            antiga = esporotricose_core.salvar_entrega_doente(
                db_path, receita, {"quantidade": 20, "baixa_zoomed": "Sim", "observacoes": "Entrega conferida"},
            )
            esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 100},
            )
            esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 50, "fonte_medicacao": "Município"},
            )
            self.assertEqual(esporotricose_core.estoque_medicacao(db_path)["totais"]["saldos_por_fonte"],
                             {"SESA": 80, "Município": 50})
            esporotricose_core.atualizar_entrega_doente(db_path, antiga, {
                "quantidade": 20, "baixa_zoomed": "Sim", "fonte_medicacao": "Município",
            })
            estoque = esporotricose_core.estoque_medicacao(db_path)
            self.assertEqual(estoque["totais"]["saldos_por_fonte"], {"SESA": 100, "Município": 30})
            self.assertEqual(estoque["totais"]["saldo_setor"], 130)
            self.assertEqual(esporotricose_core.listar_doentes(db_path)["totais"]["capsulas_baixa_zoomed"], 20)
            entrega = esporotricose_core.obter_doente(db_path, animal)["receitas"][0]["entregas"][0]
            self.assertEqual(entrega["baixa_zoomed"], "Sim")
            self.assertEqual(entrega["fonte_medicacao"], "Município")
            self.assertEqual(entrega["observacoes"], "Entrega conferida")
            self.assertEqual(esporotricose_core.listar_doentes(db_path)["registros"][0]["entregas_zoomed_pendentes"], 0)

            pendente = esporotricose_core.salvar_entrega_doente(db_path, receita, {
                "quantidade": 5, "fonte_medicacao": "Município", "baixa_zoomed": "Não",
            })
            self.assertEqual(esporotricose_core.listar_doentes(db_path)["registros"][0]["entregas_zoomed_pendentes"], 1)
            self.assertEqual(len(esporotricose_core.listar_doentes(db_path, {"baixa_zoomed": "Pendente"})["registros"]), 1)
            self.assertEqual(len(esporotricose_core.listar_doentes_csv(db_path, {"baixa_zoomed": "Pendente"})), 1)
            esporotricose_core.atualizar_entrega_doente(db_path, pendente, {
                "quantidade": 5, "fonte_medicacao": "Município", "baixa_zoomed": "Sim",
            })
            self.assertEqual(esporotricose_core.listar_doentes(db_path)["totais"]["capsulas_baixa_zoomed"], 25)
            self.assertEqual(esporotricose_core.listar_doentes(db_path, {"baixa_zoomed": "Pendente"})["registros"], [])
            self.assertEqual(esporotricose_core.listar_doentes_csv(db_path, {"baixa_zoomed": "Pendente"}), [])

    def test_edicao_do_movimento_reclassifica_saldo_sem_alterar_total(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            movimento = esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 40},
            )
            esporotricose_core.salvar_estoque_medicacao(
                db_path, {"id_movimento": movimento, "tipo": "Entrada", "quantidade": 40,
                          "fonte_medicacao": "Município"},
            )
            self.assertEqual(esporotricose_core.estoque_medicacao(db_path)["totais"]["saldos_por_fonte"],
                             {"SESA": 0, "Município": 40})

    def test_nome_legado_zoomed_e_convertido_em_sesa(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            movimento = esporotricose_core.salvar_estoque_medicacao(
                db_path, {"tipo": "Entrada", "quantidade": 10, "fonte_medicacao": "Zoomed"},
            )
            conn = db_core.connect(db_path)
            try:
                conn.execute("UPDATE esporotricose_estoque_medicacao SET fonte_medicacao='Zoomed' WHERE id_movimento=?", (movimento,))
                conn.commit()
            finally:
                conn.close()
            estoque = esporotricose_core.estoque_medicacao(db_path)
            self.assertEqual(estoque["movimentos"][0]["fonte_medicacao"], "SESA")
            self.assertEqual(estoque["totais"]["entradas_sesa"], 10)

    def test_rejeita_fonte_desconhecida(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "estoque.db")
            with self.assertRaises(esporotricose_core.ValidationError):
                esporotricose_core.salvar_estoque_medicacao(
                    db_path, {"tipo": "Entrada", "quantidade": 10, "fonte_medicacao": "Outra"},
                )

    def test_atualiza_apenas_observacao_da_saida_automatica(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "estoque.db"
            conn = db_core.connect(db_path)
            try:
                esporotricose_core.ensure_schema(conn)
            finally:
                conn.close()

            id_animal = esporotricose_core.salvar_doente(str(db_path), {
                "nome": "Paciente",
                "tutor": "Tutor de teste",
                "status": "Em tratamento",
            })
            id_receita = esporotricose_core.salvar_receita_doente(
                str(db_path), id_animal, {"capsulas_total": 30, "status": "Em tratamento"},
            )
            id_entrega = esporotricose_core.salvar_entrega_doente(
                str(db_path), id_receita, {"quantidade": 30, "observacoes": "Entrega inicial"},
            )

            esporotricose_core.salvar_observacao_movimento_automatico(
                str(db_path), id_entrega, "Paciente orientado sobre o retorno.",
            )
            estoque = esporotricose_core.estoque_medicacao(str(db_path))

        movimento = next(item for item in estoque["movimentos_automaticos"] if item["id_entrega"] == id_entrega)
        self.assertEqual(movimento["quantidade"], 30)
        self.assertEqual(movimento["observacoes"], "Paciente orientado sobre o retorno.")


if __name__ == "__main__":
    unittest.main()
