import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app_core import db as db_core
from app_core import logradouros


class LogradourosTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _csv(rows):
        return ("nome,localidade,id_logr\n" + "\n".join(rows) + "\n").encode("utf-8")

    def test_importa_trechos_repetidos_e_atualiza_por_id_estavel(self):
        first = self._csv((
            "Rua Sao Joao,Sede,uuid-a",
            "Rua Sao Joao,Roma,uuid-b",
            "Avenida Central,Sede,uuid-c",
        ))
        result = logradouros.importar_csv(self.path, first)
        self.assertEqual((3, 0, 0), (result["inseridos"], result["atualizados"], result["sem_alteracao"]))
        summary = logradouros.resumo(self.path)
        self.assertEqual(3, summary["trechos"])
        self.assertEqual(2, summary["nomes_normalizados"])

        second = self._csv((
            "Rua São João,Sede,uuid-a",
            "Rua Sao Joao,Roma,uuid-b",
            "Avenida Central,Sede,uuid-c",
        ))
        result = logradouros.importar_csv(self.path, second)
        self.assertEqual((0, 1, 2), (result["inseridos"], result["atualizados"], result["sem_alteracao"]))
        rows = logradouros.listar(self.path, "São João")["registros"]
        self.assertEqual(2, len(rows))
        self.assertEqual({"uuid-a", "uuid-b"}, {row["id_logradouro"] for row in rows})

    def test_recusa_coluna_ou_id_repetido(self):
        with self.assertRaisesRegex(ValueError, "obrigatoria"):
            logradouros.importar_csv(self.path, b"nome,id_logr\nRua A,1\n")
        with self.assertRaisesRegex(ValueError, "repetido"):
            logradouros.importar_csv(
                self.path,
                self._csv(("Rua A,Sede,1", "Rua B,Sede,1")),
            )

    def test_importacao_nao_remove_trecho_ausente(self):
        logradouros.importar_csv(self.path, self._csv(("Rua A,Sede,1", "Rua B,Sede,2")))
        logradouros.importar_csv(self.path, self._csv(("Rua A,Sede,1",)))
        conn = db_core.connect(self.path)
        try:
            self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM logradouros_oficiais").fetchone()[0])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
