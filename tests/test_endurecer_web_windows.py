import json
import importlib.util
from pathlib import Path
import tempfile
import unittest

from scripts import endurecer_web_windows as hardening


class HardeningWindowsTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("win32security"), "pywin32 somente no ambiente administrativo")
    def test_acl_real_em_arquivo_ficticio_e_retorno_sem_criar_conta(self):
        win = hardening.Windows()
        win.web = win.sec.ConvertStringSidToSid("S-1-5-21-1-2-3-1099")
        with tempfile.TemporaryDirectory(prefix="endemias-acl-ficticio-") as directory:
            target = Path(directory) / "ficticio.txt"
            target.write_text("sem dados reais", encoding="utf-8")
            original = win.sec.GetNamedSecurityInfo(str(target), win.sec.SE_FILE_OBJECT, win.sec.DACL_SECURITY_INFORMATION)
            try:
                win.protect(target, "read_file")
                sd = win.sec.GetNamedSecurityInfo(str(target), win.sec.SE_FILE_OBJECT, win.sec.DACL_SECURITY_INFORMATION)
                self.assertTrue(sd.GetSecurityDescriptorControl()[0] & win.sec.SE_DACL_PROTECTED)
                acl = sd.GetSecurityDescriptorDacl()
                entries = [acl.GetAce(index) for index in range(acl.GetAceCount())]
                web = [entry for entry in entries if entry[2] == win.web]
                self.assertEqual(len(web), 1)
                self.assertEqual(web[0][1], hardening.READ)
                self.assertFalse(web[0][1] & 0x2)  # FILE_WRITE_DATA
                self.assertFalse(web[0][1] & 0x10000)  # DELETE
            finally:
                self.assertEqual(win.restore_acls(), 0)
            restored = win.sec.GetNamedSecurityInfo(str(target), win.sec.SE_FILE_OBJECT, win.sec.DACL_SECURITY_INFORMATION)
            self.assertEqual(restored.GetSecurityDescriptorDacl().GetAceCount(), original.GetSecurityDescriptorDacl().GetAceCount())
            self.assertEqual(target.read_text(encoding="utf-8"), "sem dados reais")

    def test_permissoes_distinguem_codigo_dados_e_segredos(self):
        policies = {"app.py": "read", "templates/login.html": "read", "secret.key": "read_file",
                    "kobo_config.json": "write_file", "anexos/teste.txt": "modify",
                    "saida/relatorio.xlsx": "modify", ".git/config": "private",
                    "endemias.db": "private", "endemias.db.testes-antigos": "private"}
        for path, expected in policies.items():
            with self.subTest(path=path):
                self.assertEqual(hardening.policy_for(hardening.ROOT / path), expected)
        with self.assertRaises(ValueError):
            hardening.policy_for(Path(r"C:\Windows\system.ini"))

    def test_rejeita_opcao_imprevista_sem_exportar_credencial(self):
        with self.assertRaises(ValueError) as context:
            hardening.task_parameters('-File iniciar.ps1 -Password SEGREDO-FICTICIO')
        self.assertNotIn("SEGREDO", str(context.exception))

    def test_le_parametros_reais_sem_copiar_politica_de_execucao_para_config(self):
        arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\\endemias\\scripts\\iniciar_servidor.ps1" -Backend postgresql -Database endemias -HostName 127.0.0.1 -Port 5432 -UserName endemias_app -SslMode prefer -PgPassFile "C:\\ProgramData\\Endemias\\pgpass.conf" -PythonPath "C:\\Python\\python.exe"'
        parameters = hardening.task_parameters(arguments)
        config = hardening.make_config(parameters, "S-1-5-21-123", hardening.HOME / "rollback/teste")
        self.assertEqual(config["env"]["ENDEMIAS_DB_BACKEND"], "postgresql")
        self.assertNotIn("Bypass", json.dumps(config))
        self.assertNotIn("PASSWORD", json.dumps(config))
        self.assertNotEqual(config["env"]["ENDEMIAS_BACKUP_DIR"], r"D:\BackupsEndemias\backups_banco")

    def test_rejeita_banco_ou_credencial_fora_do_escopo(self):
        args = '-File "C:\\endemias\\scripts\\iniciar_servidor.ps1" -Backend postgresql -Database endemias -PgPassFile "C:\\ProgramData\\Endemias\\pgpass.conf"'
        for text in (args.replace('-Database endemias', '-Database outro'),
                     args.replace('Endemias\\pgpass.conf', 'Outro\\pgpass.conf'),
                     args + ' -HostName 10.0.0.1'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                hardening.task_parameters(text)

    def test_retorno_restabelece_protecao_e_heranca_por_objeto(self):
        from unittest.mock import MagicMock
        win = object.__new__(hardening.Windows)
        win.sec = MagicMock()
        win.sec.SE_DACL_PROTECTED = 4096
        win.sec.DACL_SECURITY_INFORMATION = 4
        win.sec.PROTECTED_DACL_SECURITY_INFORMATION = -2147483648
        win.sec.UNPROTECTED_DACL_SECURITY_INFORMATION = 536870912
        protected = MagicMock()
        protected.GetSecurityDescriptorControl.return_value = (4096, 1)
        inherited = MagicMock()
        inherited.GetSecurityDescriptorControl.return_value = (0, 1)
        win.sec.ConvertStringSecurityDescriptorToSecurityDescriptor.side_effect = [protected, inherited]
        win.journal = [{"path": "pai", "sddl": "D:P"}, {"path": "filho", "sddl": "D:AI"}]
        self.assertEqual(win.restore_acls(), 0)
        calls = win.sec.SetNamedSecurityInfo.call_args_list
        self.assertEqual(calls[0].args[2], 4 | -2147483648)
        self.assertEqual(calls[1].args[2], 4 | 536870912)


if __name__ == "__main__":
    unittest.main()
