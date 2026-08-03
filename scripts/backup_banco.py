import argparse
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import backup as backup_core
from app_core import postgresql_backup


DEFAULT_DB_PATH = os.environ.get("ENDEMIAS_DB_PATH", str(ROOT / "endemias.db"))
DEFAULT_BACKUP_DIR = os.environ.get(
    "ENDEMIAS_BACKUP_DIR",
    r"D:\BackupsEndemias\backups_banco",
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_HOST_RE = re.compile(r"^[A-Za-z0-9.:-]+$")


def _postgresql_env(args, parser):
    if not args.database or not _IDENTIFIER_RE.fullmatch(args.database):
        parser.error("Informe --database com um nome PostgreSQL valido.")
    if not _HOST_RE.fullmatch(args.host):
        parser.error("O host PostgreSQL contem caracteres nao permitidos.")
    if not _IDENTIFIER_RE.fullmatch(args.usuario):
        parser.error("O usuario PostgreSQL contem caracteres nao permitidos.")
    if not 1 <= args.porta <= 65535:
        parser.error("A porta PostgreSQL deve estar entre 1 e 65535.")
    if args.pgpass_file and not Path(args.pgpass_file).is_file():
        parser.error("O arquivo pgpass informado nao foi encontrado.")
    if args.sem_validar:
        parser.error("Backups PostgreSQL sempre exigem validacao por pg_restore.")

    env = dict(os.environ)
    env.update({
        "ENDEMIAS_PG_HOST": args.host,
        "ENDEMIAS_PG_PORT": str(args.porta),
        "ENDEMIAS_PG_USER": args.usuario,
        "ENDEMIAS_PG_DATABASE": args.database,
        "ENDEMIAS_PG_SSLMODE": args.sslmode,
        "ENDEMIAS_PG_APPLICATION_NAME": "endemias_backup",
    })
    if args.pgpass_file:
        env["PGPASSFILE"] = str(Path(args.pgpass_file).resolve())
    if args.pg_bin:
        env["ENDEMIAS_PG_BIN"] = str(Path(args.pg_bin).resolve())
    return env


def _parser():
    parser = argparse.ArgumentParser(
        description="Gera backup consistente do banco do Sistema Endemias."
    )
    parser.add_argument(
        "--backend",
        choices=("sqlite", "postgresql"),
        default=os.environ.get("ENDEMIAS_DB_BACKEND", "sqlite"),
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Caminho SQLite de origem.")
    parser.add_argument("--database", help="Nome do banco PostgreSQL de origem.")
    parser.add_argument("--destino", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--prefixo", default="endemias")
    parser.add_argument("--manter", type=int, default=30)
    parser.add_argument("--sem-validar", action="store_true")
    parser.add_argument("--host", default=os.environ.get("ENDEMIAS_PG_HOST", "127.0.0.1"))
    parser.add_argument("--porta", type=int, default=int(os.environ.get("ENDEMIAS_PG_PORT", "5432")))
    parser.add_argument("--usuario", default=os.environ.get("ENDEMIAS_PG_USER", "endemias_app"))
    parser.add_argument(
        "--sslmode",
        choices=("disable", "allow", "prefer", "require", "verify-ca", "verify-full"),
        default=os.environ.get("ENDEMIAS_PG_SSLMODE", "prefer"),
    )
    parser.add_argument("--pgpass-file")
    parser.add_argument("--pg-bin")
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if args.manter < 1:
        parser.error("--manter deve ser maior que zero.")

    if args.backend == "postgresql":
        env = _postgresql_env(args, parser)
        info = postgresql_backup.criar_backup_postgresql(
            args.database,
            destino_dir=args.destino,
            prefixo=args.prefixo,
            manter=args.manter,
            env=env,
        )
    else:
        info = backup_core.criar_backup_sqlite(
            args.db,
            destino_dir=args.destino,
            prefixo=args.prefixo,
            manter=args.manter,
            validar=not args.sem_validar,
        )

    print(f"Backup criado: {info['arquivo']}")
    print(f"Backend: {args.backend}")
    print(f"Tamanho: {info['tamanho_bytes']} bytes")
    print(f"Integridade: {info['integridade']}")
    if info["removidos"]:
        print(f"Backups antigos removidos: {len(info['removidos'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
