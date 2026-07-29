import sys
import unittest
from unittest import mock

from app_core import postgresql


class PostgreSQLConfigurationTests(unittest.TestCase):
    def test_connection_parameters_use_safe_local_defaults(self):
        params = postgresql.connection_parameters(env={})

        self.assertEqual(params["host"], "127.0.0.1")
        self.assertEqual(params["port"], 5432)
        self.assertEqual(params["dbname"], "endemias_teste")
        self.assertEqual(params["user"], "endemias_app")
        self.assertNotIn("password", params)

    def test_connection_parameters_accept_endemias_environment(self):
        params = postgresql.connection_parameters(
            env={
                "ENDEMIAS_PG_HOST": "db.interno",
                "ENDEMIAS_PG_PORT": "5544",
                "ENDEMIAS_PG_DATABASE": "endemias_migracao",
                "ENDEMIAS_PG_USER": "aplicacao",
                "ENDEMIAS_PG_CONNECT_TIMEOUT": "9",
                "ENDEMIAS_PG_SSLMODE": "require",
            }
        )

        self.assertEqual(
            params,
            {
                "host": "db.interno",
                "port": 5544,
                "dbname": "endemias_migracao",
                "user": "aplicacao",
                "connect_timeout": 9,
                "sslmode": "require",
                "application_name": "endemias_migracao",
            },
        )

    def test_invalid_port_is_rejected_before_connecting(self):
        with self.assertRaisesRegex(
            postgresql.PostgreSQLConfigurationError,
            "porta PostgreSQL",
        ):
            postgresql.connection_parameters(env={"ENDEMIAS_PG_PORT": "invalida"})

    def test_connect_passes_no_password_to_driver(self):
        driver = mock.Mock()
        connection = object()
        driver.connect.return_value = connection

        with mock.patch.dict(sys.modules, {"psycopg2": driver}):
            result = postgresql.connect(database="endemias_teste", env={})

        self.assertIs(result, connection)
        kwargs = driver.connect.call_args.kwargs
        self.assertEqual(kwargs["dbname"], "endemias_teste")
        self.assertNotIn("password", kwargs)


if __name__ == "__main__":
    unittest.main()
