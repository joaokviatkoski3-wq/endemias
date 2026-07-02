import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as endemias_app
from app_core import backup_completo as backup_completo_core


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gera backup completo local do Sistema Endemias.")
    parser.add_argument(
        "--destino",
        default=endemias_app.BACKUP_COMPLETO_DIR,
        help="Pasta de destino dos ZIPs.",
    )
    parser.add_argument("--manter", type=int, default=10, help="Quantidade de backups completos a manter.")
    parser.add_argument("--db", default=endemias_app.DB_PATH, help="Caminho do banco de origem.")
    args = parser.parse_args(argv)

    info = backup_completo_core.criar_backup_completo(
        destino_dir=args.destino,
        manter=args.manter,
        db_path=args.db,
        raiz=ROOT,
        anexos_dir=endemias_app.ANEXOS_DIR,
        kobo_config_path=endemias_app.KOBO_CONFIG_PATH,
        secret_key_path=endemias_app.SECRET_KEY_PATH,
    )
    print(f"Backup completo criado: {info['arquivo']}")
    print(f"Tamanho: {info['tamanho_bytes']} bytes")
    print(f"Integridade do banco: {info['integridade_banco']}")
    if info["removidos"]:
        print(f"Backups completos antigos removidos: {len(info['removidos'])}")
    print("Destino pronto para copiar para HD externo, nuvem ou outro local seguro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
