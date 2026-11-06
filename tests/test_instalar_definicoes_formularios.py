import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app_core.formularios_kobo import TITULOS
from scripts.ativar_formularios_230_windows import instalar_definicoes


class InstalarDefinicoesTests(unittest.TestCase):
    def test_catalogo_privado_conferido_e_origem_errada_nao_sobrescreve(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);source=home/'consulta.json'
            (home/'config.json').write_text(json.dumps({'version':'2.2.1'}),encoding='utf-8')
            definition={'somente_definicoes':True,'respostas_consultadas':False,'errors':[],
                'forms':[{'tipo':tipo,'survey':[{'name':'Data','type':'date'}],'choices':[]} for tipo in TITULOS]}
            source.write_text(json.dumps(definition),encoding='utf-8')
            with patch('ctypes.windll.shell32.IsUserAnAdmin',return_value=True):
                instalar_definicoes(source,home)
                installed=(home/'formularios-kobo.json').read_bytes()
                self.assertEqual(installed,source.read_bytes())
                (home/'config.json').write_text(json.dumps({'version':'2.3.0'}),encoding='utf-8')
                source.write_text('conteudo diferente',encoding='utf-8')
                with self.assertRaises(ValueError):instalar_definicoes(source,home)
                self.assertEqual((home/'formularios-kobo.json').read_bytes(),installed)
