import unittest
from datetime import date, time

from app_core import postgresql_data_migration


class PostgreSQLDataMigrationTests(unittest.TestCase):
    def test_table_order_places_parents_before_children(self):
        inventory = {
            "tables": [
                {
                    "name": "child",
                    "foreign_keys": [
                        {
                            "target_table": "parent",
                        }
                    ],
                },
                {
                    "name": "parent",
                    "foreign_keys": [],
                },
                {
                    "name": "independent",
                    "foreign_keys": [],
                },
            ]
        }

        order = postgresql_data_migration.table_load_order(inventory)

        self.assertLess(order.index("parent"), order.index("child"))
        self.assertEqual(set(order), {"parent", "child", "independent"})

    def test_table_order_rejects_cycles(self):
        inventory = {
            "tables": [
                {
                    "name": "first",
                    "foreign_keys": [{"target_table": "second"}],
                },
                {
                    "name": "second",
                    "foreign_keys": [{"target_table": "first"}],
                },
            ]
        }

        with self.assertRaisesRegex(
            postgresql_data_migration.DataMigrationError,
            "Ciclo",
        ):
            postgresql_data_migration.table_load_order(inventory)

    def test_temporal_conversion_cleans_empty_and_nat(self):
        cleanups = {}
        date_column = {"name": "data", "declared_type": "DATE"}
        time_column = {"name": "hora", "declared_type": "TIME"}

        self.assertEqual(
            postgresql_data_migration.convert_value(
                "2026-07-29",
                "visitas",
                date_column,
                cleanups,
            ),
            date(2026, 7, 29),
        )
        self.assertEqual(
            postgresql_data_migration.convert_value(
                "08:30",
                "visitas",
                time_column,
                cleanups,
            ),
            time(8, 30),
        )
        self.assertIsNone(
            postgresql_data_migration.convert_value(
                "NaT",
                "visitas",
                date_column,
                cleanups,
            )
        )
        self.assertIsNone(
            postgresql_data_migration.convert_value(
                "",
                "visitas",
                date_column,
                cleanups,
            )
        )
        self.assertEqual(cleanups, {"visitas.data": 2})

    def test_invalid_date_stops_migration(self):
        with self.assertRaisesRegex(
            postgresql_data_migration.DataMigrationError,
            "Data invalida",
        ):
            postgresql_data_migration.convert_value(
                "29/07/2026",
                "visitas",
                {"name": "data", "declared_type": "DATE"},
                {},
            )

    def test_checksum_is_independent_from_row_order(self):
        rows_a = [(1, "A"), (2, "B"), (3, None)]
        rows_b = list(reversed(rows_a))

        checksum_a = postgresql_data_migration.table_checksum(
            postgresql_data_migration.row_digest(row) for row in rows_a
        )
        checksum_b = postgresql_data_migration.table_checksum(
            postgresql_data_migration.row_digest(row) for row in rows_b
        )

        self.assertEqual(checksum_a, checksum_b)


if __name__ == "__main__":
    unittest.main()
