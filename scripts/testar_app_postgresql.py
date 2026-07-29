"""Executa um teste de leitura da infraestrutura Flask no PostgreSQL."""

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402


SAFE_DATABASE = "endemias_teste"


def _parser():
    parser = argparse.ArgumentParser(
        description="Testa a camada comum e a tela de login no PostgreSQL."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio para qualquer banco diferente de endemias_teste.",
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if (
        args.database != SAFE_DATABASE
        and args.confirmar_banco != args.database
    ):
        print(
            "[ERRO] Para testar outro banco, informe "
            f"--confirmar-banco {args.database}"
        )
        return 2

    target = db_core.DatabaseTarget("postgresql", args.database)
    try:
        tables = db_core.scalar(
            target,
            """
            SELECT COUNT(*)
              FROM information_schema.tables
             WHERE table_schema='public'
            """,
        )
        user = db_core.query_one(
            target,
            "SELECT id_usuario, usuario FROM usuarios "
            "WHERE ativo=? ORDER BY id_usuario LIMIT ?",
            (1, 1),
        )
        locations = db_core.query(
            target,
            "SELECT id_localidade, nome FROM localidades "
            "WHERE nome IS NOT NULL ORDER BY nome LIMIT ?",
            (3,),
        )

        with tempfile.TemporaryDirectory(prefix="endemias-pg-app-") as tmpdir:
            from app import create_app

            log_path = str(Path(tmpdir) / "teste.log")
            try:
                flask_app = create_app(
                    {
                        "DB_BACKEND": "postgresql",
                        "PG_DATABASE": args.database,
                        "TESTING": True,
                        "WTF_CSRF_ENABLED": False,
                        "LOG_PATH": log_path,
                        "SECRET_KEY_PATH": str(Path(tmpdir) / "secret.key"),
                    }
                )
                response = flask_app.test_client().get("/login")
                if response.status_code != 200:
                    raise RuntimeError(
                        "A tela de login respondeu "
                        f"HTTP {response.status_code}."
                    )
            finally:
                for handler in list(logging.getLogger().handlers):
                    if (
                        getattr(handler, "baseFilename", None)
                        == os.path.abspath(log_path)
                    ):
                        logging.getLogger().removeHandler(handler)
                        handler.close()
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1

    print("Teste da aplicacao no PostgreSQL")
    print("=" * 38)
    print(f"Banco: {args.database}")
    print(f"Tabelas publicas: {tables}")
    print(f"Consulta parametrizada: {'OK' if user else 'sem usuario ativo'}")
    print(f"Linhas por nome: {len(locations)}")
    print("Tela de login Flask: HTTP 200")
    print("\n[OK] Camada comum operando em modo somente leitura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
