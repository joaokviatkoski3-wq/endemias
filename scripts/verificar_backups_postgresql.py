"""Valida os backups PostgreSQL recentes sem conectar ao banco.

A regra de validacao vive em ``app_core.backup_health``, compartilhada com a
Central do Sistema e com o diagnostico administrativo. Este arquivo e apenas a
interface de linha de comando.
"""

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import backup as backup_core  # noqa: E402,F401
from app_core import backup_completo  # noqa: E402,F401
from app_core import backup_health  # noqa: E402
from app_core import postgresql_backup  # noqa: E402,F401


DEFAULT_BACKUP_DIR = Path(r"D:\BackupsEndemias\backups_banco")
DEFAULT_COMPLETE_DIR = Path(r"D:\BackupsEndemias\backups_completos")


def verificar_dump(
    destino,
    database="endemias",
    max_horas=backup_health.MAX_DUMP_HORAS_PADRAO,
    agora=None,
    env=None,
):
    return backup_health.verificar_dump(
        destino,
        database=database,
        max_horas=max_horas,
        agora=agora,
        env=env,
    )


def verificar_backup_completo(
    destino,
    database="endemias",
    max_dias=backup_health.MAX_COMPLETO_DIAS_PADRAO,
    agora=None,
):
    return backup_health.verificar_backup_completo(
        destino,
        database=database,
        max_dias=max_dias,
        agora=agora,
    )


def verificar_tudo(
    backup_dir=DEFAULT_BACKUP_DIR,
    complete_dir=DEFAULT_COMPLETE_DIR,
    database="endemias",
    max_dump_horas=backup_health.MAX_DUMP_HORAS_PADRAO,
    max_completo_dias=backup_health.MAX_COMPLETO_DIAS_PADRAO,
    agora=None,
    env=None,
):
    return backup_health.verificar_tudo(
        backup_dir,
        complete_dir,
        database=database,
        max_dump_horas=max_dump_horas,
        max_completo_dias=max_completo_dias,
        agora=agora,
        env=env,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Valida os backups PostgreSQL recentes sem conectar ao banco."
    )
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--completo-dir", default=str(DEFAULT_COMPLETE_DIR))
    parser.add_argument("--database", default="endemias")
    parser.add_argument(
        "--max-dump-horas",
        type=float,
        default=backup_health.MAX_DUMP_HORAS_PADRAO,
    )
    parser.add_argument(
        "--max-completo-dias",
        type=float,
        default=backup_health.MAX_COMPLETO_DIAS_PADRAO,
    )
    parser.add_argument("--pg-bin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.max_dump_horas <= 0 or args.max_completo_dias <= 0:
        parser.error("Os limites de idade devem ser maiores que zero.")

    env = dict(os.environ)
    if args.pg_bin:
        env["ENDEMIAS_PG_BIN"] = str(Path(args.pg_bin).resolve())
    try:
        resultado = verificar_tudo(
            backup_dir=args.backup_dir,
            complete_dir=args.completo_dir,
            database=args.database,
            max_dump_horas=args.max_dump_horas,
            max_completo_dias=args.max_completo_dias,
            env=env,
        )
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print("Backups PostgreSQL validados.")
        print(f"Dump: {resultado['dump']['arquivo']}")
        print(f"Backup completo: {resultado['completo']['arquivo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
