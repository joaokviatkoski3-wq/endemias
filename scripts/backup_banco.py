import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as endemias_app
from app_core import backup as backup_core


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gera backup consistente do banco SQLite do Endemias.")
    parser.add_argument("--db", default=endemias_app.DB_PATH, help="Caminho do banco de origem.")
    parser.add_argument("--destino", default=None, help="Pasta de destino. Padrao: backups/ ao lado do banco.")
    parser.add_argument("--prefixo", default="endemias", help="Prefixo do arquivo de backup.")
    parser.add_argument("--manter", type=int, default=10, help="Quantidade de backups recentes a manter.")
    parser.add_argument("--sem-validar", action="store_true", help="Nao roda PRAGMA integrity_check no backup.")
    args = parser.parse_args(argv)

    info = backup_core.criar_backup_sqlite(
        args.db,
        destino_dir=args.destino,
        prefixo=args.prefixo,
        manter=args.manter,
        validar=not args.sem_validar,
    )
    print(f"Backup criado: {info['arquivo']}")
    print(f"Tamanho: {info['tamanho_bytes']} bytes")
    print(f"Integridade: {info['integridade']}")
    if info["removidos"]:
        print(f"Backups antigos removidos: {len(info['removidos'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
