"""Verifica a infraestrutura PostgreSQL sem alterar dados persistentes."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402


DEFAULT_DATABASES = ("endemias_teste", "endemias_migracao")


def _parser():
    parser = argparse.ArgumentParser(
        description="Confere conexao, configuracao e permissao nos bancos PostgreSQL."
    )
    parser.add_argument(
        "--database",
        action="append",
        dest="databases",
        help="Banco a verificar. Pode ser informado mais de uma vez.",
    )
    parser.add_argument(
        "--somente-leitura",
        action="store_true",
        help="Nao executa o teste transacional com tabela temporaria.",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    databases = args.databases or DEFAULT_DATABASES
    failures = 0

    print("Diagnostico PostgreSQL do Endemias")
    print("=" * 38)
    for database in databases:
        summary = postgresql.connection_summary(database=database)
        target = (
            f"{summary['user']}@{summary['host']}:{summary['port']}"
            f"/{summary['database']}"
        )
        print(f"\nBanco: {target}")
        try:
            result = postgresql.probe(
                database=database,
                write_test=not args.somente_leitura,
            )
        except Exception as exc:
            failures += 1
            print(f"[ERRO] {exc}")
            continue

        print("[OK] Conexao autenticada")
        print(f"     PostgreSQL: {result['server_version']}")
        print(f"     Codificacao: {result['encoding']}")
        print(f"     Fuso horario: {result['timezone']}")
        if result["write_test"]:
            print("     Escrita transacional: OK (nenhum dado persistido)")

    print()
    if failures:
        print(f"Resultado: {failures} banco(s) com falha.")
        return 1
    print("Resultado: infraestrutura PostgreSQL pronta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
