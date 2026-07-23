import json
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from app_core import backup as backup_core
from app_core import backup_completo as backup_completo_core


class BackupResilienceTests(unittest.TestCase):
    def _criar_banco(self, db_path):
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE dados (id INTEGER PRIMARY KEY, nome TEXT)")
            conn.execute("INSERT INTO dados(nome) VALUES ('original')")
            conn.commit()
        finally:
            conn.close()

    def test_backup_usa_nome_unico_e_registra_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            db_path = raiz / "origem.db"
            destino = raiz / "backups"
            agora = datetime(2026, 7, 23, 10, 30, 0)
            self._criar_banco(db_path)

            primeiro = backup_core.criar_backup_sqlite(
                db_path,
                destino_dir=destino,
                agora=agora,
            )
            segundo = backup_core.criar_backup_sqlite(
                db_path,
                destino_dir=destino,
                agora=agora,
            )

            self.assertNotEqual(primeiro["arquivo"], segundo["arquivo"])
            for info in (primeiro, segundo):
                arquivo = Path(info["arquivo"])
                meta = json.loads(
                    arquivo.with_suffix(".db.json").read_text(encoding="utf-8")
                )
                self.assertEqual(info["sha256"], backup_core.calcular_sha256(arquivo))
                self.assertEqual(meta["sha256"], info["sha256"])

    def test_restauracao_rejeita_backup_modificado_apos_validacao(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            db_path = raiz / "origem.db"
            self._criar_banco(db_path)
            info = backup_core.criar_backup_sqlite(
                db_path,
                destino_dir=raiz / "backups",
            )
            backup_path = Path(info["arquivo"])

            conn = sqlite3.connect(backup_path)
            try:
                conn.execute("UPDATE dados SET nome='alterado'")
                conn.commit()
            finally:
                conn.close()

            with self.assertRaisesRegex(RuntimeError, "SHA-256 divergente"):
                backup_core.restaurar_backup_sqlite(db_path, backup_path)

    def test_backup_invalido_nao_deixa_arquivo_parcial(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            db_path = raiz / "origem.db"
            destino = raiz / "backups"
            self._criar_banco(db_path)

            with (
                mock.patch.object(
                    backup_core,
                    "validar_backup",
                    return_value=(False, "simulado"),
                ),
                self.assertRaisesRegex(RuntimeError, "Backup invalido"),
            ):
                backup_core.criar_backup_sqlite(db_path, destino_dir=destino)

            self.assertEqual(list(destino.iterdir()), [])

    def test_backup_completo_e_publicado_somente_apos_validar_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino = raiz / "completos"
            db_path = raiz / "endemias.db"
            self._criar_banco(db_path)
            (raiz / "secret.key").write_bytes(b"segredo-local")
            (raiz / "kobo_config.json").write_text("{}", encoding="utf-8")

            info = backup_completo_core.criar_backup_completo(
                destino_dir=destino,
                db_path=db_path,
                raiz=raiz,
                manter=3,
            )

            zip_path = Path(info["arquivo"])
            self.assertEqual(info["sha256"], backup_core.calcular_sha256(zip_path))
            with zipfile.ZipFile(zip_path) as zf:
                self.assertIsNone(zf.testzip())
                manifesto = json.loads(
                    zf.read("manifesto_backup.json").decode("utf-8")
                )
            banco = next(
                item
                for item in manifesto["incluidos"]
                if item.get("destino_zip", "").startswith("banco/")
                and item.get("destino_zip", "").endswith(".db")
            )
            self.assertEqual(len(banco["sha256"]), 64)
            self.assertEqual(
                list(destino.glob(f".{backup_completo_core.ZIP_PREFIXO}_*.tmp")),
                [],
            )

    def test_backup_completo_invalido_nao_e_publicado(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino = raiz / "completos"
            db_path = raiz / "endemias.db"
            self._criar_banco(db_path)

            with (
                mock.patch.object(
                    zipfile.ZipFile,
                    "testzip",
                    return_value="arquivo-corrompido",
                ),
                self.assertRaisesRegex(RuntimeError, "arquivo-corrompido"),
            ):
                backup_completo_core.criar_backup_completo(
                    destino_dir=destino,
                    db_path=db_path,
                    raiz=raiz,
                )

            self.assertEqual(list(destino.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
