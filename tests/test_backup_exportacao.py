import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from flask import Flask

import py7zr
from app_core import backup_exportacao


class BackupExportacaoTests(unittest.TestCase):
    def test_rede_local_http_nao_recebe_formulario_ou_frase(self):
        app=Flask('download-ficticio')
        for method in ('GET','POST'):
            with app.test_request_context('/baixar',method=method,environ_base={'REMOTE_ADDR':'192.168.1.10'},headers={'X-Forwarded-Proto':'https'}), patch.object(backup_exportacao,'render_template',return_value='Use HTTPS'):
                response=backup_exportacao.resposta_download('ficticio.zip')
                self.assertEqual(response,('Use HTTPS',403))

    def test_copia_protegida_nao_revela_nomes_ou_segredos_sem_frase(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'ficticio.zip'
            with zipfile.ZipFile(source,'w') as z:
                z.writestr('configuracao/secret.key','CHAVE_INTEIRAMENTE_FICTICIA')
                z.writestr('banco/ficticio.txt','CONTEUDO_FICTICIO')
            encrypted=Path(tmp)/'ficticio.zip.7z'
            password='Frase ficticia exclusiva para ensaio!'
            backup_exportacao.criptografar(source,encrypted,password)
            self.assertNotIn(b'CHAVE_INTEIRAMENTE_FICTICIA',encrypted.read_bytes())
            self.assertNotIn(b'ficticio.zip',encrypted.read_bytes())
            with self.assertRaises(Exception):
                with py7zr.SevenZipFile(encrypted,'r') as archive:
                    archive.getnames()
            with self.assertRaises(Exception):
                with py7zr.SevenZipFile(encrypted,'r',password='Outra frase completamente ficticia') as archive:
                    archive.extractall(Path(tmp)/'errado')
            # Restauracao isolada da copia transportada: bytes originais identicos.
            with py7zr.SevenZipFile(encrypted,'r',password=password) as archive:
                self.assertTrue(archive.needs_password())
                archive.extractall(Path(tmp)/'restaurado')
            restored=Path(tmp)/'restaurado/ficticio.zip'
            self.assertEqual(source.read_bytes(),restored.read_bytes())
            with zipfile.ZipFile(restored) as archive:
                self.assertEqual(archive.read('configuracao/secret.key'),b'CHAVE_INTEIRAMENTE_FICTICIA')

    def test_senha_curta_nao_produz_arquivo(self):
        output=io.BytesIO()
        with self.assertRaises(ValueError):
            backup_exportacao.criptografar('nao-existe',output,'1234567890')
        self.assertEqual(output.getvalue(),b'')
