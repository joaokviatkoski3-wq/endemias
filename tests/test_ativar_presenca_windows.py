import copy
import unittest

from scripts.ativar_recuperacao_senha_windows import config_atualizada
from scripts.ativar_presenca_windows import RELEASE


class AtualizacaoPresencaTests(unittest.TestCase):
    def test_pacote_178_preserva_identidade_ambiente_e_objeto_original(self):
        original = {"version": "1.77.0", "server": "waitress", "probe_only": False,
                    "sid": "SID-FICTICIO", "env": {"ENDEMIAS_DB_BACKEND": "postgresql"}}
        expected = copy.deepcopy(original)
        expected["version"] = "1.78.0"
        proposed = config_atualizada(original, RELEASE)
        self.assertEqual(proposed, expected)
        self.assertEqual(original["version"], "1.77.0")
        self.assertIsNot(proposed["env"], original["env"])
        self.assertEqual(RELEASE.migration, "0032_presenca_usuarios.sql")
        self.assertEqual(RELEASE.marker, "ativacao178")

    def test_pacote_178_recusa_origem_176_ou_178(self):
        for version in ("1.76.0", "1.78.0"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                config_atualizada({"version": version, "server": "waitress"}, RELEASE)
