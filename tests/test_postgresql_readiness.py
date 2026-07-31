import unittest
from unittest import mock

from app_core import postgresql_readiness
from scripts import testar_concorrencia_postgresql
from scripts import testar_smoke_integrado_postgresql


class PostgreSQLReadinessTests(unittest.TestCase):
    def _report(self):
        target = {
            "agentes": {"rows": 2, "checksum": "abc"},
            "visitas": {"rows": 3, "checksum": "def"},
        }
        return {
            "database": "endemias_migracao",
            "tables": 2,
            "rows": 5,
            "source": dict(target),
            "target": dict(target),
        }

    def test_relatorio_valido(self):
        status = postgresql_readiness.validate_migration_report(
            self._report(),
            "endemias_migracao",
        )
        self.assertEqual(status["tables"], 2)
        self.assertEqual(status["rows"], 5)

    def test_relatorio_de_outro_banco_e_rejeitado(self):
        with self.assertRaisesRegex(
            postgresql_readiness.PostgreSQLReadinessError,
            "outro banco",
        ):
            postgresql_readiness.validate_migration_report(
                self._report(),
                "endemias_teste",
            )

    def test_relatorio_com_checksum_divergente_e_rejeitado(self):
        report = self._report()
        report["target"]["visitas"] = {"rows": 3, "checksum": "outro"}
        with self.assertRaisesRegex(
            postgresql_readiness.PostgreSQLReadinessError,
            "checksums divergentes",
        ):
            postgresql_readiness.validate_migration_report(
                report,
                "endemias_migracao",
            )

    def test_estado_esperado_das_identidades(self):
        self.assertTrue(postgresql_readiness._identity_matches(None, 1, False))
        self.assertTrue(postgresql_readiness._identity_matches(42, 42, True))
        self.assertFalse(postgresql_readiness._identity_matches(42, 41, True))
        self.assertFalse(postgresql_readiness._identity_matches(None, 1, True))

    def test_concorrencia_exige_banco_e_confirmacao_exatos(self):
        with (
            mock.patch.object(
                testar_concorrencia_postgresql.postgresql_concurrency,
                "run_probe",
            ) as probe,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(
                testar_concorrencia_postgresql.main([
                    "--database",
                    "endemias_teste",
                    "--confirmar-banco",
                    "endemias_teste",
                ]),
                2,
            )
            self.assertEqual(
                testar_concorrencia_postgresql.main([
                    "--database",
                    "endemias_migracao",
                ]),
                2,
            )
        probe.assert_not_called()

    def test_smoke_integrado_exige_banco_e_confirmacao_exatos(self):
        with (
            mock.patch.object(
                testar_smoke_integrado_postgresql.subprocess,
                "run",
            ) as run,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(
                testar_smoke_integrado_postgresql.main([
                    "--database",
                    "endemias_teste",
                    "--confirmar-banco",
                    "endemias_teste",
                ]),
                2,
            )
            self.assertEqual(
                testar_smoke_integrado_postgresql.main([
                    "--database",
                    "endemias_migracao",
                ]),
                2,
            )
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
