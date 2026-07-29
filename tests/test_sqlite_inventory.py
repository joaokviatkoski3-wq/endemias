import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app_core import sqlite_inventory


class SQLiteInventoryTests(unittest.TestCase):
    def _database(self, directory):
        path = Path(directory) / "inventory.db"
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE parent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_on DATE
            );
            CREATE UNIQUE INDEX idx_parent_name_duplicate ON parent(name);
            CREATE TABLE child (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL REFERENCES parent(id),
                amount REAL,
                note TEXT
            );
            CREATE INDEX idx_child_parent ON child(parent_id);
            INSERT INTO parent(name, created_on)
            VALUES ('SEGREDO-NAO-EXPORTAR', '2026-07-29');
            INSERT INTO child(id, parent_id, amount, note)
            VALUES (1, 1, 2.5, 'OUTRO-SEGREDO');
            """
        )
        conn.commit()
        conn.close()
        return path

    def test_inventory_contains_structure_without_stored_values(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory = sqlite_inventory.build_inventory(
                self._database(directory)
            )
            serialized = json.dumps(inventory, ensure_ascii=False)

        self.assertEqual(inventory["database"]["quick_check"], "ok")
        self.assertEqual(inventory["summary"]["tables"], 2)
        self.assertEqual(inventory["summary"]["rows"], 2)
        self.assertEqual(inventory["summary"]["foreign_keys"], 1)
        self.assertEqual(inventory["summary"]["duplicate_indexes"], 1)
        self.assertEqual(inventory["summary"]["invalid_temporal_columns"], 0)
        self.assertNotIn("SEGREDO-NAO-EXPORTAR", serialized)
        self.assertNotIn("OUTRO-SEGREDO", serialized)

    def test_inventory_detects_mixed_storage_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.db"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE mixed (
                    id INTEGER PRIMARY KEY,
                    value
                );
                INSERT INTO mixed(id, value) VALUES (1, 10);
                INSERT INTO mixed(id, value) VALUES (2, 'dez');
                """
            )
            conn.commit()
            conn.close()

            inventory = sqlite_inventory.build_inventory(path)

        self.assertEqual(inventory["summary"]["mixed_storage_columns"], 1)
        issue = inventory["issues"]["mixed_storage_columns"][0]
        self.assertEqual(issue["table"], "mixed")
        self.assertEqual(issue["column"], "value")
        self.assertEqual(issue["storage_classes"], ["integer", "text"])

    def test_write_inventory_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "inventory.json"
            sqlite_inventory.write_inventory({"ok": True}, output)

            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                {"ok": True},
            )


if __name__ == "__main__":
    unittest.main()
