from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from scripts.endurecer_tunnel_windows import ACCOUNT, Tunnel, validate_command


class TunnelHardeningTests(unittest.TestCase):
    def test_recusa_token_literal_sem_exibi_lo_na_excecao(self):
        with self.assertRaises(ValueError) as result:
            validate_command('"C:\\Program Files\\cloudflared\\cloudflared.exe" tunnel run --token SEGREDO-FICTICIO')
        self.assertNotIn("SEGREDO", str(result.exception))

    def test_recusa_token_fora_do_escopo_ou_sem_caminho(self):
        for arguments in ('--token-file "C:\\Outro\\token"', '--token-file'):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                validate_command('"C:\\Program Files\\cloudflared\\cloudflared.exe" tunnel run ' + arguments)

    def test_reconhece_arquivo_sem_abrir_conteudo(self):
        with patch.object(Path, "is_file", return_value=True), patch.object(Path, "open", side_effect=AssertionError("Nao abrir token")):
            binary, token = validate_command('"C:\\Program Files (x86)\\cloudflared\\cloudflared.exe" --no-autoupdate tunnel run --token-file "C:\\ProgramData\\cloudflared\\token"')
        self.assertEqual(binary.name, "cloudflared.exe")
        self.assertEqual(token, Path(r"C:\ProgramData\cloudflared\token"))

    def test_troca_virtual_sem_senha_e_sem_alterar_executavel_argumentos(self):
        tunnel = object.__new__(Tunnel)
        tunnel.svc = MagicMock()
        tunnel.svc.SERVICE_NO_CHANGE = -1
        tunnel.handle = object()
        tunnel.set_identity(ACCOUNT, 1, ["SeChangeNotifyPrivilege"])
        args = tunnel.svc.ChangeServiceConfig.call_args.args
        self.assertEqual(args[1:4], (-1, -1, -1))
        self.assertIsNone(args[4])  # caminho/argumentos atuais preservados
        self.assertEqual(args[8], ACCOUNT)
        self.assertIsNone(args[9])  # conta virtual exige NULL, nunca senha nova


if __name__ == "__main__":
    unittest.main()
