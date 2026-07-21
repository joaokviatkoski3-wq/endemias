import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose as esporotricose_core
from app_core import db as db_core


class EstoqueAutomaticoTests(unittest.TestCase):
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
