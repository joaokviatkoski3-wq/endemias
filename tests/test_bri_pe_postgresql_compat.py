import unittest

from app_core import bri
from app_core import pontos_estrategicos as pe


class BriPePostgreSQLCompatTests(unittest.TestCase):
    def test_schema_postgresql_fica_sob_responsabilidade_da_migracao(self):
        class PostgreSQLStub:
            backend = "postgresql"

            def execute(self, *_args, **_kwargs):
                raise AssertionError("DDL nao deve executar no PostgreSQL.")

            def executescript(self, *_args, **_kwargs):
                raise AssertionError("DDL nao deve executar no PostgreSQL.")

        conn = PostgreSQLStub()
        pe.ensure_schema(conn)
        bri.ensure_schema(conn)

    def test_expressao_de_atraso_respeita_o_backend(self):
        class ConnectionStub:
            def __init__(self, backend):
                self.backend = backend

        sqlite_sql = pe._atraso_sql(
            ConnectionStub("sqlite"), "MAX(v.data)"
        )
        postgresql_sql = pe._atraso_sql(
            ConnectionStub("postgresql"), "MAX(v.data)"
        )

        self.assertIn("julianday", sqlite_sql)
        self.assertIn("CURRENT_DATE", postgresql_sql)
        self.assertNotIn("julianday", postgresql_sql)

    def test_alias_normalizado_permanece_estavel(self):
        self.assertEqual(
            pe.normalizar_alias("  Rod. dos Minérios - Ferro Velho  "),
            "rodovia dos minerios - ferro velho",
        )


if __name__ == "__main__":
    unittest.main()
