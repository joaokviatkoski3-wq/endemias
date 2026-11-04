import copy
import unittest
from unittest.mock import patch

from scripts.ativar_superadmin_windows import RELEASE
from scripts.ativar_recuperacao_senha_windows import config_atualizada
from scripts import recuperar_superadmin_windows


class AtivacaoSuperadminTests(unittest.TestCase):
    def test_release_preserva_ambiente_e_define_somente_owner_confirmado(self):
        original = {'version': '1.78.0', 'server': 'waitress', 'probe_only': False,
                    'env': {'ENDEMIAS_DB_BACKEND': 'postgresql', 'TESTE': 'preservar'}, 'sid': 'sintetico'}
        before = copy.deepcopy(original)
        proposed = config_atualizada(original, RELEASE)
        self.assertEqual(original, before)
        self.assertEqual(proposed, {**before, 'version': '1.79.0'})
        self.assertEqual((RELEASE.owner_id, RELEASE.owner_login), (2, 'joao'))
        self.assertEqual(RELEASE.migration, '0033_superadmin.sql')

    def test_rejeita_origem_inesperada(self):
        with self.assertRaises(ValueError):
            config_atualizada({'version': '1.79.0', 'server': 'waitress'}, RELEASE)

    def test_recuperacao_recusa_execucao_fora_instalacao_oficial(self):
        with patch('sys.argv', ['recuperar_superadmin_windows.py', '--usuario', 'joao']), \
                patch('builtins.input', side_effect=AssertionError('Nao deve pedir senha')):
            # O teste e executado em worktree isolada: deve parar antes de ler config/banco.
            from pathlib import Path
            with patch.object(recuperar_superadmin_windows, 'ROOT', Path('C:/nao-oficial')):
                self.assertEqual(recuperar_superadmin_windows.main(), 1)
