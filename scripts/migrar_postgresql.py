"""Consulta ou aplica migracoes PostgreSQL versionadas."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402
from app_core import postgresql_migrations  # noqa: E402


MIGRATIONS_DIR = ROOT / "migrations" / "postgresql"
SAFE_DATABASE = "endemias_teste"


def _parser():
    parser = argparse.ArgumentParser(description="Gerencia migracoes PostgreSQL.")
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Aplica migracoes pendentes em uma unica transacao.",
    )
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio ao aplicar fora de endemias_teste.",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if (
        args.aplicar
        and args.database != SAFE_DATABASE
        and args.confirmar_banco != args.database
    ):
        print(
            "[ERRO] Para aplicar fora de endemias_teste, informe "
            f"--confirmar-banco {args.database}"
        )
        return 2

    conn = None
    try:
        conn = postgresql.connect(database=args.database)
        if args.aplicar:
            applied_now = postgresql_migrations.apply_pending(
                conn,
                MIGRATIONS_DIR,
            )
            if applied_now:
                for name in applied_now:
                    print(f"[OK] Aplicada: {name}")
            else:
                print("[OK] Nenhuma migracao pendente.")

        status = postgresql_migrations.status(conn, MIGRATIONS_DIR)
        for item in status:
            print(f"{item['version']} {item['state']:>18}  {item['name']}")
        if any(item["state"] == "checksum_mismatch" for item in status):
            return 1
        return 0
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
