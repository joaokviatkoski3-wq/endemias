"""Homologa pg_restore somente no banco local descartavel endemias_teste."""

import argparse
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402
from app_core import postgresql_backup  # noqa: E402
from app_core import postgresql_data_migration  # noqa: E402
from app_core import postgresql_schema_compare  # noqa: E402
from app_core import sqlite_inventory  # noqa: E402


SAFE_DATABASE = "endemias_teste"
RESTORE_CONFIRMATION = "RESTAURAR BANCO DESCARTAVEL"


def _parser():
    parser = argparse.ArgumentParser(
        description="Cria e restaura um dump real apenas em endemias_teste."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--db", default=str(ROOT / "endemias.db"))
    parser.add_argument("--confirmar-banco")
    parser.add_argument("--autorizar-restore")
    return parser


def _fingerprint(database, inventory):
    conn = postgresql.connect(database=database)
    try:
        schema = postgresql_schema_compare.compare(conn, inventory)
        if not schema["ok"]:
            raise RuntimeError(
                "Esquema divergente antes/depois do restore: "
                + "; ".join(schema["differences"])
            )
        result = postgresql_data_migration.postgres_snapshot_results(
            conn,
            inventory,
        )
        conn.rollback()
        return result
    finally:
        conn.close()


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE:
        print(f"[ERRO] Restore real permitido somente em {SAFE_DATABASE}.")
        return 2
    if args.confirmar_banco != args.database:
        print("[ERRO] Confirme o nome exato do banco descartavel.")
        return 2
    if args.autorizar_restore != RESTORE_CONFIRMATION:
        print(
            "[ERRO] Informe --autorizar-restore \""
            + RESTORE_CONFIRMATION
            + "\"."
        )
        return 2

    try:
        with postgresql_data_migration.sqlite_snapshot(args.db) as snapshot:
            inventory = sqlite_inventory.build_inventory(snapshot)
        before = _fingerprint(args.database, inventory)
        with tempfile.TemporaryDirectory(prefix="endemias-restore-real-") as tmp:
            backup = postgresql_backup.criar_backup_postgresql(
                args.database,
                destino_dir=tmp,
                prefixo="restore_homologacao",
                manter=None,
            )
            restored = postgresql_backup.restaurar_backup_postgresql(
                args.database,
                backup["arquivo"],
                confirmacao=args.database,
                backup_dir=tmp,
                manter=None,
            )
            safety_path = Path(tmp) / restored["backup_seguranca"]
            postgresql_backup.validar_backup(safety_path)
            after = _fingerprint(args.database, inventory)
            if before != after:
                changed = [
                    name
                    for name in sorted(set(before) | set(after))
                    if before.get(name) != after.get(name)
                ]
                raise RuntimeError(
                    "Restore alterou contagens/checksums: " + ", ".join(changed)
                )
            rows = sum(item["rows"] for item in after.values())
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1

    print("Homologacao de restore PostgreSQL")
    print("=" * 40)
    print(f"Banco descartavel: {args.database}")
    print(f"Tabelas/registros preservados: {len(after)}/{rows}")
    print("Dump, metadados e SHA-256: OK")
    print("Backup pre_restore: OK")
    print("pg_restore transacional: OK")
    print("\n[OK] Restore real homologado sem alterar o estado do banco de teste.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
