"""Executa cinco sessoes concorrentes somente em endemias_migracao."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql_concurrency  # noqa: E402


SAFE_DATABASE = "endemias_migracao"


def _parser():
    parser = argparse.ArgumentParser(
        description="Testa locks e novas tentativas no PostgreSQL descartavel."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--confirmar-banco")
    parser.add_argument("--sessoes", type=int, default=5)
    parser.add_argument("--iteracoes", type=int, default=5)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE:
        print(f"[ERRO] Este ensaio so pode usar {SAFE_DATABASE}.")
        return 2
    if args.confirmar_banco != args.database:
        print(
            "[ERRO] Informe --confirmar-banco endemias_migracao para autorizar "
            "a tabela efemera."
        )
        return 2
    try:
        result = postgresql_concurrency.run_probe(
            args.database,
            sessions=args.sessoes,
            iterations=args.iteracoes,
        )
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1

    print("Ensaio de concorrencia PostgreSQL")
    print("=" * 38)
    print(f"Banco descartavel: {args.database}")
    print(f"Sessoes: {result['sessions']}")
    print(f"Operacoes confirmadas: {result['operations']}")
    print(f"Novas tentativas por lock: {result['retries']}")
    print("Tabela efemera removida: OK")
    print("\n[OK] Concorrencia validada sem alterar tabelas do sistema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
