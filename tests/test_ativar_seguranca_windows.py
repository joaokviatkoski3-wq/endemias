import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.ativar_seguranca_windows import RELEASE, conferir_wheels
from scripts.ativar_recuperacao_senha_windows import config_atualizada


class AtivacaoSegurancaTests(unittest.TestCase):
    def test_configuracao_muda_apenas_versao(self):
        original={'version':'1.79.0','server':'waitress','probe_only':False,'env':{'ENDEMIAS_DB_BACKEND':'postgresql','ENDEMIAS_LOCAL_PORT':'5000'}}
        before=copy.deepcopy(original)
        self.assertEqual(config_atualizada(original,RELEASE),{**before,'version':'1.80.0'})
        self.assertEqual(original,before)
        self.assertIsNone(RELEASE.owner_id)
        self.assertTrue(RELEASE.snapshot_completo)

    def test_recusa_pacote_alterado_ausente_ou_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p=root/'ficticio.whl';p.write_bytes(b'ficticio')
            manifest={p.name:hashlib.sha256(b'ficticio').hexdigest()}
            conferir_wheels(root,manifest)
            p.write_bytes(b'alterado')
            with self.assertRaises(ValueError):conferir_wheels(root,manifest)
            p.write_bytes(b'ficticio');(root/'extra.whl').write_bytes(b'extra')
            with self.assertRaises(ValueError):conferir_wheels(root,manifest)
