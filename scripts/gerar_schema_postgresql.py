"""Gera a migracao SQL inicial sem incluir dados do sistema."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql_schema  # noqa: E402


def _parser():
    parser = argparse.ArgumentParser(description="Gera o esquema PostgreSQL inicial.")
    parser.add_argument(
        "--inventory",
        default=str(ROOT / "saida" / "migracao" / "inventario_sqlite.json"),
    )
    parser.add_argument(
        "--output",
        default=str(
            ROOT
            / "migrations"
            / "postgresql"
            / "0001_schema_inicial.sql"
        ),
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    inventory_path = Path(args.inventory)
    if not inventory_path.is_file():
        print(f"[ERRO] Inventario nao encontrado: {inventory_path}")
        return 1

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    sql = postgresql_schema.generate_schema_sql(inventory)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sql, encoding="utf-8", newline="\n")

    summary = postgresql_schema.expected_summary(inventory)
    print(f"Esquema gerado: {output.resolve()}")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
