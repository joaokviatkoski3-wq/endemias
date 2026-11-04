from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from scripts.preparar_ativacao_externa import proposed_config
from scripts.servico_web_windows import start_application


class AtivacaoExternaTests(unittest.TestCase):
    def test_preserva_identidade_dados_e_separa_entradas(self):
        original = {"sid": "SID-FICTICIO", "env": {"ENDEMIAS_DB_BACKEND": "postgresql", "PGPASSFILE": "privado"}}
        proposed = proposed_config(original, "endemias.vsatt.com.br", "192.168.7.20")
        self.assertEqual(proposed["sid"], original["sid"])
        self.assertEqual(proposed["env"]["PGPASSFILE"], "privado")
        self.assertNotIn("server", original)
        self.assertNotEqual(proposed["env"]["ENDEMIAS_LOCAL_PORT"], proposed["env"]["ENDEMIAS_TUNNEL_PORT"])
        self.assertEqual(proposed["env"]["ENDEMIAS_BIND"], "127.0.0.1")

    def test_recusa_host_fora_do_dominio_e_bind_publico(self):
        for host, ip in (("outro.example", "192.168.7.20"), ("*.vsatt.com.br", "192.168.7.20"),
                         ("endemias.vsatt.com.br", "0.0.0.0"), ("endemias.vsatt.com.br", "8.8.8.8")):
            with self.subTest(host=host, ip=ip), self.assertRaises(ValueError):
                proposed_config({"env": {}}, host, ip)

    def test_waitress_nao_recebe_argumentos_do_wrapper(self):
        with patch("scripts.servico_web_windows.runpy.run_path") as run, patch.object(sys, "argv", ["wrapper", "--config", "privado"]):
            start_application({"server": "waitress", "env": {"ENDEMIAS_ACESSO_EXTERNO": "1"}}, Path(r"C:\endemias"))
            self.assertEqual(sys.argv, [str(Path(r"C:\endemias\servir.py"))])
            run.assert_called_once_with(str(Path(r"C:\endemias\servir.py")), run_name="__main__")

    def test_perfil_externo_recusa_werkzeug(self):
        with self.assertRaises(ValueError):
            start_application({"env": {"ENDEMIAS_ACESSO_EXTERNO": "1"}}, Path(r"C:\endemias"))
