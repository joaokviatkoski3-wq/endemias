"""Gera inventario estrutural local para planejar a migracao PostgreSQL."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import sqlite_inventory  # noqa: E402


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Inventaria estrutura, tipos e volumes do SQLite sem exportar "
            "valores armazenados."
        )
    )
    parser.add_argument(
        "--db",
        default=str(ROOT / "endemias.db"),
        help="Caminho do banco SQLite.",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "saida" / "migracao" / "inventario_sqlite.json"),
        help="Arquivo JSON local de saida.",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        inventory = sqlite_inventory.build_inventory(args.db)
        output = sqlite_inventory.write_inventory(inventory, args.output)
    except Exception as exc:
        print(f"[ERRO] Nao foi possivel gerar o inventario: {exc}")
        return 1

    print("Inventario SQLite do Endemias")
    print("=" * 31)
    for line in sqlite_inventory.summary_lines(inventory):
        print(line)
    print(f"\nRelatorio local: {output.resolve()}")
    print("Nenhum valor de negocio foi exportado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
