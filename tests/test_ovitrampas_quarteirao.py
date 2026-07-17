import tempfile
import unittest
from pathlib import Path

from app_core import db as db_core
from app_core import ovitrampas


class OvitrampasQuarteiraoTests(unittest.TestCase):
    def test_normaliza_apenas_numeros_com_menos_de_quatro_digitos(self):
        self.assertEqual(ovitrampas._normalizar_quarteirao("56"), "0056")
        self.assertEqual(ovitrampas._normalizar_quarteirao("756"), "0756")
        self.assertEqual(ovitrampas._normalizar_quarteirao("0756"), "0756")
        self.assertEqual(ovitrampas._normalizar_quarteirao("12345"), "12345")
        self.assertEqual(ovitrampas._normalizar_quarteirao("A-1"), "A-1")

    def test_migra_quarteirao_existente_e_registra_historico(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "teste.db"
            conn = db_core.connect(db_path)
            try:
                ovitrampas.ensure_schema(conn)
                conn.execute(
                    """INSERT INTO ovitrampas_armadilhas
                           (ovitrampa_id, quarteirao, atualizado_em)
                       VALUES ('7-A', '56', '2026-07-17T12:00:00')"""
                )

                ovitrampas.ensure_schema(conn)

                atual = conn.execute(
                    "SELECT quarteirao FROM ovitrampas_armadilhas WHERE ovitrampa_id='7-A'"
                ).fetchone()[0]
                historico = conn.execute(
                    """SELECT valor_anterior, valor_novo
                           FROM ovitrampas_armadilhas_historico
                          WHERE ovitrampa_id='7-A' AND campo='quarteirao'"""
                ).fetchone()
                self.assertEqual(atual, "0056")
                self.assertEqual(tuple(historico), ("56", "0056"))
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
