import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import esporotricose


class EsporotricoseClinicaDualTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = str(Path(self.tempdir.name) / "esporotricose.db")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE localidades (
                   id_localidade INTEGER PRIMARY KEY AUTOINCREMENT,
                   nome TEXT NOT NULL UNIQUE,
                   cod_localidade INTEGER
               )"""
        )
        esporotricose.ensure_schema(conn)
        conn.close()

    def _criar_doente(self):
        return esporotricose.salvar_doente(
            self.db_path,
            {
                "tutor": "Maria Silva",
                "nome": "Tilapia",
                "especie": "Gato",
                "sexo": "Fêmea",
                "telefone": "41999990000",
                "cpf": "12345678900",
                "localidade": "Tamboara",
                "quarteirao": "1405",
                "endereco": "Rua das Flores, 25",
                "status": "Em tratamento",
                "data_notificacao": "2026-07-29",
            },
        )

    def test_fluxo_clinico_calcula_receita_entrega_e_estoque(self):
        id_animal = self._criar_doente()
        id_receita = esporotricose.salvar_receita_doente(
            self.db_path,
            id_animal,
            {
                "data_receita": "2026-07-29",
                "capsulas_total": 90,
                "capsulas_por_dia": 1,
                "status": "Em tratamento",
            },
        )
        id_entrega = esporotricose.salvar_entrega_doente(
            self.db_path,
            id_receita,
            {
                "quantidade": 30,
                "data_entrega": "2026-07-29",
                "baixa_zoomed": "Sim",
            },
        )
        id_movimento = esporotricose.salvar_estoque_medicacao(
            self.db_path,
            {
                "data": "2026-07-29",
                "tipo": "Entrada",
                "quantidade": 180,
                "descricao": "Carga controlada",
            },
        )

        lista = esporotricose.listar_doentes(
            self.db_path, {"busca": "MARIA"}
        )
        detalhe = esporotricose.obter_doente(self.db_path, id_animal)
        estoque = esporotricose.estoque_medicacao(self.db_path)

        self.assertEqual(lista["total"], 1)
        self.assertEqual(lista["registros"][0]["capsulas_receitadas"], 90)
        self.assertEqual(lista["registros"][0]["capsulas_entregues"], 30)
        self.assertEqual(lista["registros"][0]["capsulas_restantes"], 60)
        self.assertEqual(lista["registros"][0]["proxima_entrega"], "2026-08-28")
        self.assertEqual(detalhe["receitas"][0]["entregas"][0]["id_entrega"], id_entrega)
        self.assertEqual(estoque["totais"]["saldo_setor"], 150)
        self.assertEqual(estoque["movimentos"][0]["id_movimento"], id_movimento)

    def test_edita_exporta_e_exclui_cadastro_relacionado(self):
        id_animal = self._criar_doente()
        id_receita = esporotricose.salvar_receita_doente(
            self.db_path,
            id_animal,
            {"data_receita": "2026-07-29", "capsulas_total": 60},
        )
        id_entrega = esporotricose.salvar_entrega_doente(
            self.db_path,
            id_receita,
            {"quantidade": 30, "data_entrega": "2026-07-29"},
        )
        ids_anexos = esporotricose.salvar_anexos_doente(
            self.db_path,
            id_animal,
            [
                {
                    "nome_original": "receita.pdf",
                    "nome_arquivo": "receita.pdf",
                    "caminho_rel": "esporotricose_doentes/000001/receita.pdf",
                    "mime_type": "application/pdf",
                    "tamanho": 120,
                }
            ],
            "João",
        )

        esporotricose.salvar_doente(
            self.db_path,
            {
                "id_animal_doente": id_animal,
                "tutor": "Maria Silva",
                "nome": "Tilapia",
                "status": "Em tratamento",
                "observacoes_entomologica": "Cadastro revisado",
            },
        )
        esporotricose.atualizar_receita_doente(
            self.db_path,
            id_receita,
            {"data_receita": "2026-07-29", "capsulas_total": 90},
        )
        esporotricose.atualizar_entrega_doente(
            self.db_path,
            id_entrega,
            {
                "quantidade": 20,
                "data_entrega": "2026-07-30",
                "baixa_zoomed": "Não",
            },
        )

        csv_rows = esporotricose.listar_doentes_csv(
            self.db_path, {"baixa_zoomed": "Pendente"}
        )
        anexo = esporotricose.obter_anexo_doente(
            self.db_path, ids_anexos[0]
        )

        self.assertEqual(len(csv_rows), 1)
        self.assertEqual(csv_rows[0]["capsulas_receitadas"], 90)
        self.assertEqual(csv_rows[0]["capsulas_entregues"], 20)
        self.assertEqual(anexo["nome_original"], "receita.pdf")

        removido = esporotricose.excluir_anexo_doente(
            self.db_path, ids_anexos[0]
        )
        self.assertEqual(removido["id_anexo"], ids_anexos[0])
        esporotricose.excluir_entrega_doente(self.db_path, id_entrega)
        esporotricose.excluir_receita_doente(self.db_path, id_receita)
        esporotricose.excluir_doente(self.db_path, id_animal)
        self.assertIsNone(esporotricose.obter_doente(self.db_path, id_animal))


if __name__ == "__main__":
    unittest.main()
