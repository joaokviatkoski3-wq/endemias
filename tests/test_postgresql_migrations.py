import hashlib
import tempfile
import unittest
from pathlib import Path

from app_core import postgresql_migrations


class PostgreSQLMigrationDiscoveryTests(unittest.TestCase):
    def test_migracao_visitas_acs_e_aditiva_e_validada(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "postgresql"
            / "0009_visitas_acs.sql"
        )
        sql = path.read_text(encoding="utf-8").casefold()

        self.assertIn("add column acs_presente", sql)
        self.assertIn("add column acs_nome", sql)
        self.assertIn("check (acs_presente in (0, 1))", sql)

    def test_migracao_visita_acs_preserva_selecao_multipla(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "postgresql"
            / "0010_visita_acs.sql"
        )
        sql = path.read_text(encoding="utf-8").casefold()

        self.assertIn("create table visita_acs", sql)
        self.assertIn("references visitas(id_visita) on delete cascade", sql)
        self.assertIn("primary key (id_visita, acs_codigo)", sql)

    def test_migracao_catalogo_acs_separa_codigo_do_rotulo(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "postgresql"
            / "0015_acs_catalogo.sql"
        )
        sql = path.read_text(encoding="utf-8").casefold()

        self.assertIn("create table acs_catalogo", sql)
        self.assertIn("acs_codigo text primary key", sql)
        self.assertIn("nome text not null", sql)

    def test_migracao_vincula_usuario_a_agente(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "postgresql"
            / "0011_usuarios_agentes.sql"
        )
        sql = path.read_text(encoding="utf-8").casefold()

        self.assertIn("alter table usuarios", sql)
        self.assertIn("add column id_agente", sql)
        self.assertIn("references agentes(id_agente)", sql)

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
