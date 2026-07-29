"""Copia um snapshot consistente do SQLite para o PostgreSQL de teste."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402
from app_core import postgresql_data_migration  # noqa: E402
from app_core import postgresql_schema_compare  # noqa: E402
from app_core import sqlite_inventory  # noqa: E402


SAFE_DATABASE = "endemias_teste"


def _parser():
    parser = argparse.ArgumentParser(
        description="Copia e valida os dados SQLite no PostgreSQL."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--db", default=str(ROOT / "endemias.db"))
    parser.add_argument(
        "--substituir",
        action="store_true",
        help="Limpa e recarrega as tabelas do destino.",
    )
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio para qualquer banco diferente de endemias_teste.",
    )
    parser.add_argument(
        "--output",
        default=str(
            ROOT
            / "saida"
            / "migracao"
            / "carga_postgresql_teste.json"
        ),
    )
    return parser


def _progress(position, total, table, rows):
    print(f"[{position:02d}/{total:02d}] {table}: {rows}")


def main(argv=None):
    args = _parser().parse_args(argv)
    if (
        args.database != SAFE_DATABASE
        and args.confirmar_banco != args.database
    ):
        print(
            "[ERRO] Para copiar fora de endemias_teste, informe "
            f"--confirmar-banco {args.database}"
        )
        return 2

    conn = None
    try:
        with postgresql_data_migration.sqlite_snapshot(args.db) as snapshot:
            inventory = sqlite_inventory.build_inventory(snapshot)
            conn = postgresql.connect(database=args.database)
            schema_report = postgresql_schema_compare.compare(conn, inventory)
            if not schema_report["ok"]:
                print("[ERRO] O esquema PostgreSQL diverge do snapshot SQLite.")
                for difference in schema_report["differences"]:
                    print(f"- {difference}")
                return 1

            report = postgresql_data_migration.migrate_snapshot(
                snapshot,
                conn,
                inventory,
                replace=args.substituir,
                progress=_progress,
            )
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1
    finally:
        if conn is not None:
            conn.close()

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": Path(args.db).name,
        "database": args.database,
        **report,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n[OK] Carga PostgreSQL validada e confirmada.")
    print(f"Tabelas: {report['tables']}")
    print(f"Registros: {report['rows']}")
    print(f"Identidades reajustadas: {report['identities_reset']}")
    print(f"Conversoes para NULL: {sum(report['cleanups'].values())}")
    print(f"Duracao: {report['duration_seconds']} s")
    print(f"Relatorio local: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
