import unittest

from app_core import utils


class VisitFiltersTests(unittest.TestCase):
    def test_filtra_agua_sanepar_e_observacoes(self):
        where, params = utils.build_visit_where({
            "d_ini": "2026-07-01",
            "d_fim": "2026-07-31",
            "tipo": ["PE", "PVE", "TB", "TBO"],
            "agua_sanepar": "0",
            "observacoes": "caixa destampada",
        })

        self.assertIn("v.agua_sanepar=0", where)
        self.assertIn(
            "LOWER(COALESCE(v.observacoes,'')) LIKE LOWER(?)",
            where,
        )
        self.assertEqual(params[-1], "%caixa destampada%")

    def test_filtra_agua_sanepar_sem_informacao(self):
        where, _ = utils.build_visit_where({"agua_sanepar": "sem_info"})

        self.assertIn("v.agua_sanepar IS NULL", where)


if __name__ == "__main__":
    unittest.main()
