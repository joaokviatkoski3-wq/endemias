"""Valida a carga recente destinada ao ensaio integrado PostgreSQL."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402
from app_core import postgresql_readiness  # noqa: E402
from app_core import postgresql_schema_compare  # noqa: E402
from app_core import sqlite_inventory  # noqa: E402
from app_core.postgresql_data_migration import sqlite_snapshot  # noqa: E402


SAFE_DATABASE = "endemias_migracao"


def _parser():
    parser = argparse.ArgumentParser(
        description="Valida dados, constraints e identidades da migracao."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--db", default=str(ROOT / "endemias.db"))
    parser.add_argument(
        "--report",
        default=str(
            ROOT / "saida" / "migracao" / "carga_postgresql_migracao.json"
        ),
    )
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio e deve repetir o banco validado.",
    )
    return parser


def _progress(position, total, table, rows):
    print(f"[{position:02d}/{total:02d}] {table}: {rows}")


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.confirmar_banco != args.database:
        print(
            "[ERRO] Informe --confirmar-banco com o nome exato do banco "
            "validado."
        )
        return 2
    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"[ERRO] Relatorio de carga nao encontrado: {report_path}")
        return 1
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_status = postgresql_readiness.validate_migration_report(
            report,
            args.database,
        )
        with sqlite_snapshot(args.db) as snapshot:
            inventory = sqlite_inventory.build_inventory(snapshot)
        conn = postgresql.connect(database=args.database)
        try:
            schema = postgresql_schema_compare.compare(conn, inventory)
            if not schema["ok"]:
                raise postgresql_readiness.PostgreSQLReadinessError(
                    "Esquema divergente: " + "; ".join(schema["differences"])
                )
            constraints = postgresql_readiness.validate_constraints(conn)
            identities = postgresql_readiness.validate_identities(conn)
            current = postgresql_readiness.validate_current_data(
                conn,
                inventory,
                report_status["target"],
                progress=_progress,
            )
            conn.rollback()
        finally:
            conn.close()
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1

    print("\n[OK] Migracao integrada consistente.")
    print(f"Banco: {args.database}")
    print(f"Tabelas/registros: {current['tables']}/{current['rows']}")
    print(f"Constraints nao validadas: {constraints['unvalidated']}")
    print(f"Identidades alinhadas: {identities['identities']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
