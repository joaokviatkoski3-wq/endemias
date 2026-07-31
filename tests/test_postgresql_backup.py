import json
import subprocess
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from app_core import backup as backup_core
from app_core import backup_completo
from app_core import db as db_core
from app_core import postgresql_backup


class PostgreSQLBackupTests(unittest.TestCase):
    def _env_e_executaveis(self, raiz):
        dump = raiz / "pg_dump.exe"
        restore = raiz / "pg_restore.exe"
        dump.write_bytes(b"exe")
        restore.write_bytes(b"exe")
        return {
            "ENDEMIAS_PG_DUMP": str(dump),
            "ENDEMIAS_PG_RESTORE": str(restore),
            "ENDEMIAS_PG_HOST": "127.0.0.1",
            "ENDEMIAS_PG_PORT": "5432",
            "ENDEMIAS_PG_USER": "endemias_app",
            "ENDEMIAS_PG_SSLMODE": "require",
            "PGPASSWORD": "segredo-que-nao-pode-aparecer",
        }

    def test_cria_dump_custom_validado_sem_senha_no_comando_ou_metadados(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            env = self._env_e_executaveis(raiz)
            comandos = []

            def executar(args, env=None, timeout=1800):
                comandos.append((list(args), dict(env or {})))
                if "--file" in args:
                    Path(args[args.index("--file") + 1]).write_bytes(b"PGDMP teste")
                    return subprocess.CompletedProcess(args, 0, "", "")
                return subprocess.CompletedProcess(args, 0, "catalogo", "")

            with mock.patch.object(
                postgresql_backup,
                "_executar",
                side_effect=executar,
            ):
                info = postgresql_backup.criar_backup_postgresql(
                    "endemias_teste",
                    raiz / "backups",
                    agora=datetime(2026, 7, 31, 12, 0, 0),
                    env=env,
                )

            arquivo = Path(info["arquivo"])
            self.assertTrue(arquivo.is_file())
            self.assertEqual(arquivo.suffix, ".dump")
            self.assertIn("--format=custom", comandos[0][0])
            self.assertEqual(comandos[1][0][1], "--list")
            self.assertNotIn(env["PGPASSWORD"], " ".join(comandos[0][0]))
            self.assertEqual(comandos[0][1]["PGSSLMODE"], "require")
            meta = json.loads(
                arquivo.with_suffix(".dump.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("segredo", json.dumps(meta))
            self.assertEqual(meta["sha256"], backup_core.calcular_sha256(arquivo))

    def test_falha_de_validacao_nao_publica_dump_parcial(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            env = self._env_e_executaveis(raiz)

            def executar(args, env=None, timeout=1800):
                if "--file" in args:
                    Path(args[args.index("--file") + 1]).write_bytes(b"parcial")
                    return subprocess.CompletedProcess(args, 0, "", "")
                raise RuntimeError("catalogo invalido")

            with (
                mock.patch.object(
                    postgresql_backup,
                    "_executar",
                    side_effect=executar,
                ),
                self.assertRaisesRegex(RuntimeError, "catalogo invalido"),
            ):
                postgresql_backup.criar_backup_postgresql(
                    "endemias_teste",
                    raiz / "backups",
                    env=env,
                )

            self.assertEqual(list((raiz / "backups").iterdir()), [])

    def test_restauracao_exige_confirmacao_exata_antes_de_validar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup = Path(tmpdir) / "teste.dump"
            backup.write_bytes(b"PGDMP")
            with (
                mock.patch.object(postgresql_backup, "validar_backup") as validar,
                self.assertRaisesRegex(ValueError, "nome exato"),
            ):
                postgresql_backup.restaurar_backup_postgresql(
                    "endemias_teste",
                    backup,
                    confirmacao="endemias",
                    backup_dir=tmpdir,
                )
            validar.assert_not_called()

    def test_restauracao_rejeita_metadados_de_outro_banco(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup = Path(tmpdir) / "teste.dump"
            backup.write_bytes(b"PGDMP")
            backup.with_suffix(".dump.json").write_text(
                json.dumps({"origem": {"database": "outro_banco"}}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    postgresql_backup,
                    "validar_backup",
                    return_value=(True, "catalogo validado"),
                ),
                mock.patch.object(
                    postgresql_backup,
                    "criar_backup_postgresql",
                ) as criar_seguranca,
                self.assertRaisesRegex(ValueError, "outro banco"),
            ):
                postgresql_backup.restaurar_backup_postgresql(
                    "endemias_teste",
                    backup,
                    confirmacao="endemias_teste",
                    backup_dir=tmpdir,
                )
            criar_seguranca.assert_not_called()

    def test_restauracao_usa_transacao_unica_e_backup_previo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            env = self._env_e_executaveis(raiz)
            arquivo = raiz / "origem.dump"
            arquivo.write_bytes(b"PGDMP restauracao")
            seguranca = raiz / "pre_restore.dump"
            seguranca.write_bytes(b"PGDMP seguranca")

            with (
                mock.patch.object(
                    postgresql_backup,
                    "validar_backup",
                    return_value=(True, "catalogo validado"),
                ),
                mock.patch.object(
                    postgresql_backup,
                    "criar_backup_postgresql",
                    return_value={"arquivo": str(seguranca)},
                ) as criar_seguranca,
                mock.patch.object(
                    postgresql_backup,
                    "_executar",
                    return_value=subprocess.CompletedProcess([], 0, "", ""),
                ) as executar,
                mock.patch.object(postgresql_backup.postgresql, "probe") as probe,
            ):
                info = postgresql_backup.restaurar_backup_postgresql(
                    "endemias_teste",
                    arquivo,
                    confirmacao="endemias_teste",
                    backup_dir=raiz,
                    env=env,
                )

            criar_seguranca.assert_called_once()
            comando = executar.call_args.args[0]
            self.assertIn("--single-transaction", comando)
            self.assertIn("--clean", comando)
            self.assertIn("--exit-on-error", comando)
            self.assertNotIn(env["PGPASSWORD"], " ".join(comando))
            probe.assert_called_once_with(
                database="endemias_teste",
                env=env,
                write_test=False,
            )
            self.assertEqual(info["backup_seguranca"], seguranca.name)

    def test_backup_completo_inclui_dump_postgresql(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)

            def criar(database, destino_dir, prefixo, manter):
                dump = Path(destino_dir) / "endemias_20260731.dump"
                dump.write_bytes(b"PGDMP completo")
                meta = dump.with_suffix(".dump.json")
                meta.write_text("{}", encoding="utf-8")
                return {
                    "arquivo": str(dump),
                    "integridade": "catalogo validado",
                    "sha256": backup_core.calcular_sha256(dump),
                }

            with mock.patch.object(
                backup_completo.postgresql_backup,
                "criar_backup_postgresql",
                side_effect=criar,
            ):
                info = backup_completo.criar_backup_completo(
                    destino_dir=raiz / "completos",
                    raiz=raiz,
                    db_target=db_core.DatabaseTarget(
                        "postgresql",
                        "endemias_teste",
                    ),
                )

            with zipfile.ZipFile(info["arquivo"]) as zf:
                nomes = zf.namelist()
                manifesto = json.loads(
                    zf.read("manifesto_backup.json").decode("utf-8")
                )
            self.assertIn("banco/endemias_20260731.dump", nomes)
            self.assertEqual(manifesto["backend_banco"], "postgresql")
            self.assertEqual(manifesto["integridade_banco"], "catalogo validado")


if __name__ == "__main__":
    unittest.main()
