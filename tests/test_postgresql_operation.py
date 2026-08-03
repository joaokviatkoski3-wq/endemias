import unittest
from pathlib import Path
from unittest import mock

from scripts import testar_restore_real_postgresql


class PostgreSQLOperationTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_restore_real_recusa_outro_banco(self):
        with (
            mock.patch.object(
                testar_restore_real_postgresql,
                "_fingerprint",
            ) as fingerprint,
            mock.patch("builtins.print"),
        ):
            result = testar_restore_real_postgresql.main([
                "--database",
                "endemias_migracao",
                "--confirmar-banco",
                "endemias_migracao",
                "--autorizar-restore",
                testar_restore_real_postgresql.RESTORE_CONFIRMATION,
            ])
        self.assertEqual(result, 2)
        fingerprint.assert_not_called()

    def test_launcher_configura_postgresql_so_no_processo(self):
        content = (self.ROOT / "scripts" / "iniciar_servidor.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("$env:ENDEMIAS_DB_BACKEND = $Backend", content)
        self.assertIn("$env:PGPASSFILE = $PgPassFile", content)
        self.assertNotIn("PGPASSWORD", content)
        self.assertNotIn("SetEnvironmentVariable", content)

    def test_credencial_system_usa_prompt_seguro_e_acl_restrita(self):
        content = (
            self.ROOT
            / "scripts"
            / "configurar_credencial_postgresql_system.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("Read-Host", content)
        self.assertIn("-AsSecureString", content)
        self.assertIn('"S-1-5-18"', content)
        self.assertIn('"S-1-5-32-544"', content)
        self.assertNotIn("param([string]$Password", content)

    def test_instalador_tem_validacao_e_modo_sem_inicio(self):
        content = (
            self.ROOT / "scripts" / "configurar_inicializacao_automatica.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("[switch]$ValidarSomente", content)
        self.assertIn("[switch]$NaoIniciar", content)
        self.assertIn('New-ScheduledTaskPrincipal `', content)
        self.assertIn('-UserId "SYSTEM"', content)
        self.assertIn("iniciar_servidor.ps1", content)
        self.assertIn('"$($_.Name).0"', content)
        self.assertNotIn("[version]$_.Name", content)

    def test_credencial_e_validada_por_tarefa_system_temporaria(self):
        content = (
            self.ROOT / "scripts" / "testar_credencial_postgresql_system.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn('-UserId "SYSTEM"', content)
        self.assertIn("$env:PGPASSFILE = $PgPassFile", content)
        self.assertIn("[switch]$Worker", content)
        self.assertIn("Unregister-ScheduledTask", content)
        self.assertIn("[System.IO.File]::Move", content)
        self.assertIn("finally", content)
        self.assertNotIn("PGPASSWORD", content)

    def test_restore_real_exige_dupla_confirmacao(self):
        with (
            mock.patch.object(
                testar_restore_real_postgresql,
                "_fingerprint",
            ) as fingerprint,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(
                testar_restore_real_postgresql.main([
                    "--database",
                    "endemias_teste",
                    "--confirmar-banco",
                    "endemias_teste",
                ]),
                2,
            )
            self.assertEqual(
                testar_restore_real_postgresql.main([
                    "--database",
                    "endemias_teste",
                    "--confirmar-banco",
                    "outro",
                    "--autorizar-restore",
                    testar_restore_real_postgresql.RESTORE_CONFIRMATION,
                ]),
                2,
            )
        fingerprint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
