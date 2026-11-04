import copy
import unittest

from scripts.ativar_recuperacao_senha_windows import config_atualizada


class AtualizacaoRecuperacaoTests(unittest.TestCase):
    def test_altera_so_versao_preservando_ambiente_identidade_e_origem(self):
        original = {"version": "1.76.0", "server": "waitress", "probe_only": False,
            "sid": "SID-FICTICIO", "env": {"ENDEMIAS_DB_BACKEND": "postgresql", "PGPASSFILE": "ficticio"}}
        snapshot = copy.deepcopy(original)
        proposed = config_atualizada(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(proposed.pop("version"), "1.77.0")
        snapshot.pop("version")
        self.assertEqual(proposed, snapshot)
        self.assertIsNot(proposed["env"], original["env"])

    def test_recusa_origem_servidor_banco_e_ensaio_diferentes(self):
        original = {"version": "1.76.0", "server": "waitress", "probe_only": False,
                    "env": {"ENDEMIAS_DB_BACKEND": "postgresql"}}
        for change in ({"version": "1.77.0"}, {"server": "werkzeug"}, {"probe_only": True},
                       {"env": {"ENDEMIAS_DB_BACKEND": "sqlite"}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                config_atualizada({**original, **change})
