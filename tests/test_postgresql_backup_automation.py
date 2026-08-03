import io
import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from app_core import backup as backup_core
from app_core import backup_completo as backup_completo_core
from app_core import db as db_core
from scripts import backup_banco
from scripts import backup_completo
from scripts import verificar_backups_postgresql


ROOT = Path(__file__).resolve().parents[1]


class PostgreSQLBackupAutomationTests(unittest.TestCase):
    def _info_backup(self, arquivo):
        return {
            "arquivo": str(arquivo),
            "tamanho_bytes": 123,
            "integridade": "catalogo validado",
            "removidos": [],
        }

    def test_cli_backup_banco_seleciona_postgresql_sem_importar_app(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            pgpass = raiz / "pgpass.conf"
            pgpass.write_text("protegido", encoding="utf-8")
            destino = raiz / "backups"
            dump = destino / "endemias.dump"
            with (
                mock.patch.object(
                    backup_banco.postgresql_backup,
                    "criar_backup_postgresql",
                    return_value=self._info_backup(dump),
                ) as criar,
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                resultado = backup_banco.main([
                    "--backend", "postgresql",
                    "--database", "endemias",
                    "--destino", str(destino),
                    "--pgpass-file", str(pgpass),
                ])

            self.assertEqual(resultado, 0)
            kwargs = criar.call_args.kwargs
            self.assertEqual(criar.call_args.args[0], "endemias")
            self.assertEqual(kwargs["env"]["PGPASSFILE"], str(pgpass.resolve()))
            self.assertEqual(kwargs["env"]["ENDEMIAS_PG_APPLICATION_NAME"], "endemias_backup")
            self.assertNotIn("app as endemias_app", (ROOT / "scripts" / "backup_banco.py").read_text(encoding="utf-8"))

    def test_cli_backup_banco_preserva_modo_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            db_path = raiz / "origem.db"
            destino = raiz / "backups"
            with (
                mock.patch.object(
                    backup_banco.backup_core,
                    "criar_backup_sqlite",
                    return_value=self._info_backup(destino / "endemias.db"),
                ) as criar,
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                backup_banco.main([
                    "--backend", "sqlite",
                    "--db", str(db_path),
                    "--destino", str(destino),
                ])
            criar.assert_called_once()
            self.assertEqual(criar.call_args.args[0], str(db_path))

    def test_cli_backup_completo_passa_destino_e_ambiente_postgresql(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            pgpass = raiz / "pgpass.conf"
            pgpass.write_text("protegido", encoding="utf-8")
            destino = raiz / "completos"
            retorno = {
                "arquivo": str(destino / "completo.zip"),
                "tamanho_bytes": 456,
                "integridade_banco": "catalogo validado",
                "removidos": [],
            }
            with (
                mock.patch.object(
                    backup_completo.backup_completo_core,
                    "criar_backup_completo",
                    return_value=retorno,
                ) as criar,
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                resultado = backup_completo.main([
                    "--backend", "postgresql",
                    "--database", "endemias",
                    "--destino", str(destino),
                    "--pgpass-file", str(pgpass),
                ])

            self.assertEqual(resultado, 0)
            kwargs = criar.call_args.kwargs
            self.assertEqual(
                kwargs["db_target"],
                db_core.DatabaseTarget("postgresql", "endemias"),
            )
            self.assertEqual(
                kwargs["postgresql_env"]["PGPASSFILE"],
                str(pgpass.resolve()),
            )
            self.assertNotIn("import app", (ROOT / "scripts" / "backup_completo.py").read_text(encoding="utf-8"))

    def test_core_backup_completo_repassa_ambiente_protegido(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            dump = raiz / "dump.dump"
            ambiente = {"PGPASSFILE": str(raiz / "pgpass.conf")}

            def criar(database, destino_dir, prefixo, manter, env):
                arquivo = Path(destino_dir) / dump.name
                arquivo.write_bytes(b"PGDMP")
                return {
                    "arquivo": str(arquivo),
                    "integridade": "catalogo validado",
                    "sha256": backup_core.calcular_sha256(arquivo),
                }

            with mock.patch.object(
                backup_completo_core.postgresql_backup,
                "criar_backup_postgresql",
                side_effect=criar,
            ) as criar_mock:
                backup_completo_core.criar_backup_completo(
                    destino_dir=raiz / "completos",
                    raiz=raiz,
                    db_target=db_core.DatabaseTarget("postgresql", "endemias"),
                    postgresql_env=ambiente,
                )

            self.assertEqual(criar_mock.call_args.kwargs["env"], ambiente)

    def test_verificador_confere_dump_e_zip_postgresql(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            backups = raiz / "backups"
            completos = raiz / "completos"
            backups.mkdir()
            completos.mkdir()

            dump = backups / "endemias_20260803_120000.dump"
            dump.write_bytes(b"PGDMP diario")
            dump.with_suffix(".dump.json").write_text(
                json.dumps({
                    "validado": True,
                    "sha256": backup_core.calcular_sha256(dump),
                    "integridade": "catalogo validado",
                    "origem": {"database": "endemias"},
                }),
                encoding="utf-8",
            )

            interno = b"PGDMP completo"
            interno_hash = hashlib.sha256(interno).hexdigest()
            zip_path = completos / "endemias_completo_20260803_120000.zip"
            manifesto = {
                "tipo": "backup_completo_endemias",
                "backend_banco": "postgresql",
                "banco_origem": "endemias",
                "integridade_banco": "catalogo validado",
                "incluidos": [{
                    "destino_zip": "banco/endemias_20260803.dump",
                    "sha256": interno_hash,
                }],
            }
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("banco/endemias_20260803.dump", interno)
                zf.writestr("manifesto_backup.json", json.dumps(manifesto))

            agora = datetime.fromtimestamp(max(dump.stat().st_mtime, zip_path.stat().st_mtime))
            with mock.patch.object(
                verificar_backups_postgresql.postgresql_backup,
                "validar_backup",
                return_value=(True, "catalogo validado"),
            ) as validar:
                resultado = verificar_backups_postgresql.verificar_tudo(
                    backups,
                    completos,
                    agora=agora,
                )

            validar.assert_called_once()
            self.assertEqual(resultado["dump"]["sha256"], backup_core.calcular_sha256(dump))
            self.assertIn("SHA-256 interno", resultado["completo"]["integridade"])

            dump.with_suffix(".dump.json").write_text(
                json.dumps({
                    "validado": True,
                    "sha256": backup_core.calcular_sha256(dump),
                    "origem": {"database": "endemias_teste"},
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "outro banco"):
                verificar_backups_postgresql.verificar_dump(
                    backups,
                    database="endemias",
                    agora=agora,
                )

    def test_verificador_rejeita_zip_sem_dump_postgresql_integro(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            completos = Path(tmpdir)
            zip_path = completos / "endemias_completo_20260803_120000.zip"
            manifesto = {
                "backend_banco": "postgresql",
                "banco_origem": "endemias",
                "integridade_banco": "catalogo validado",
                "incluidos": [{
                    "destino_zip": "banco/endemias.dump",
                    "sha256": "0" * 64,
                }],
            }
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("banco/endemias.dump", b"alterado")
                zf.writestr("manifesto_backup.json", json.dumps(manifesto))

            with self.assertRaisesRegex(RuntimeError, "diverge"):
                verificar_backups_postgresql.verificar_backup_completo(completos)

    def test_instalador_agenda_system_sem_senha_e_tem_modo_validacao(self):
        script = (
            ROOT / "scripts" / "configurar_backup_automatico_postgresql.ps1"
        ).read_text(encoding="utf-8")
        wrapper = (ROOT / "configurar_backup_postgresql.bat").read_text(encoding="utf-8")

        self.assertIn('$DailyTaskName = "Endemias - Backup PostgreSQL Diario"', script)
        self.assertIn('$CompleteTaskName = "Endemias - Backup Completo PostgreSQL"', script)
        self.assertIn('New-ScheduledTaskPrincipal `', script)
        self.assertIn('-UserId "SYSTEM"', script)
        self.assertIn('New-ScheduledTaskTrigger -Daily', script)
        self.assertIn('-Weekly `', script)
        self.assertIn('-StartWhenAvailable', script)
        self.assertIn('$PgPassFile', script)
        self.assertNotIn("PGPASSWORD", script)
        self.assertIn("function Set-SecureBackupDirectory", script)
        self.assertIn('"S-1-5-18"', script)
        self.assertIn('"S-1-5-32-544"', script)
        self.assertNotIn('"S-1-5-32-545"', script)
        self.assertIn("SetAccessRuleProtection($true, $false)", script)
        self.assertLess(
            script.index("if ($ValidarSomente)"),
            script.index("Set-SecureBackupDirectory -Path $BackupDir"),
        )
        self.assertIn("-Database endemias -ExecutarAgora", wrapper)
        self.assertIn("-Verb RunAs", wrapper)


if __name__ == "__main__":
    unittest.main()
