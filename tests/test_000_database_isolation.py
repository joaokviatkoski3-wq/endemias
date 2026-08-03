import os
import unittest
from pathlib import Path

try:
    from tests._database_isolation import TEST_DB_PATH
except ImportError:
    from _database_isolation import TEST_DB_PATH


class DatabaseIsolationTests(unittest.TestCase):
    def test_bateria_usa_copia_sqlite_temporaria(self):
        banco_oficial = Path(__file__).resolve().parents[1] / "endemias.db"

        self.assertEqual(os.environ.get("ENDEMIAS_TEST_DB_ISOLATED"), "1")
        self.assertTrue(TEST_DB_PATH.is_file())
        self.assertNotEqual(TEST_DB_PATH.resolve(), banco_oficial.resolve())


if __name__ == "__main__":
    unittest.main()
