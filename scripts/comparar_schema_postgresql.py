"""Compara o esquema de teste com o inventario estrutural SQLite."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402
from app_core import postgresql_schema_compare  # noqa: E402


def _parser():
    parser = argparse.ArgumentParser(description="Compara os esquemas SQLite/PostgreSQL.")
    parser.add_argument("--database", default="endemias_teste")
    parser.add_argument(
        "--inventory",
        default=str(ROOT / "saida" / "migracao" / "inventario_sqlite.json"),
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    inventory_path = Path(args.inventory)
    if not inventory_path.is_file():
        print(f"[ERRO] Inventario nao encontrado: {inventory_path}")
        return 1

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    conn = None
    try:
        conn = postgresql.connect(database=args.database)
        report = postgresql_schema_compare.compare(conn, inventory)
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1
    finally:
        if conn is not None:
            conn.close()

    print(f"Comparacao do esquema: {args.database}")
    print("=" * 38)
    for key, expected in report["expected"].items():
        actual = report["actual"].get(key)
        if actual is not None:
            print(f"{key}: {actual}/{expected}")
    print(
        "explicit_indexes: "
        f"{report['actual']['explicit_indexes_found']}/"
        f"{report['expected']['explicit_indexes']}"
    )
    if report["differences"]:
        print("\nDivergencias:")
        for difference in report["differences"]:
            print(f"- {difference}")
        return 1
    print("\n[OK] Esquema PostgreSQL compativel com o inventario.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
