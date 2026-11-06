import unittest
from scripts.provar_setores_windows import validar_assets


class ProvaKoboTests(unittest.TestCase):
    def test_tipos_vazios_de_outro_setor_sao_compativeis(self):
        validar_assets({'BRI':'uid-ficticio','AMOSTRA_ANIMAIS':''},{'BRI'})

    def test_tipo_ativo_de_outro_setor_permanece_bloqueado(self):
        with self.assertRaises(AssertionError):
            validar_assets({'BRI':'uid-ficticio','AMOSTRA_ANIMAIS':'outro-ficticio'},{'BRI'})
