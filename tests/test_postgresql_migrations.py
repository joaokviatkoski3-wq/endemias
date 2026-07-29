import hashlib
import tempfile
import unittest
from pathlib import Path

from app_core import postgresql_migrations


class PostgreSQLMigrationDiscoveryTests(unittest.TestCase):
    def test_discover_orders_and_hashes_migrations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            second = root / "0002_segunda.sql"
            first = root / "0001_primeira.sql"
            second.write_text("SELECT 2;\n", encoding="utf-8")
            first.write_text("SELECT 1;\n", encoding="utf-8")

            migrations = postgresql_migrations.discover(root)

        self.assertEqual([item.version for item in migrations], ["0001", "0002"])
        self.assertEqual(
            migrations[0].checksum,
            hashlib.sha256(b"SELECT 1;\n").hexdigest(),
        )

    def test_discover_rejects_invalid_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.sql"
            path.write_text("SELECT 1;", encoding="utf-8")

            with self.assertRaisesRegex(
                postgresql_migrations.MigrationError,
                "Nome de migracao invalido",
            ):
                postgresql_migrations.discover(directory)

    def test_discover_rejects_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                postgresql_migrations.MigrationError,
                "Nenhuma migracao encontrada",
            ):
                postgresql_migrations.discover(directory)


if __name__ == "__main__":
    unittest.main()
