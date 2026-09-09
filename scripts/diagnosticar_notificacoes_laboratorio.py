"""Lista, sem alterar dados, positivos laboratoriais divergentes da regra de notificacao."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import focos_positivos  # noqa: E402


SAFE_DATABASE = "endemias_teste"


def _parser():
    parser = argparse.ArgumentParser(
        description="Previa somente leitura das notificacoes laboratoriais."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio fora de endemias_teste: repita exatamente o nome do banco.",
    )
    parser.add_argument("--limite", type=int, default=100)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print(
            f'[ERRO] Para consultar fora de {SAFE_DATABASE}, informe '
            f'--confirmar-banco {args.database}'
        )
        return 2

    target = db_core.DatabaseTarget("postgresql", args.database)
    conn = db_core.connect(target)
    try:
        conn.execute("SET TRANSACTION READ ONLY")
        itens = focos_positivos.listar_divergencias(conn)
        print(f"[OK] {len(itens)} divergencia(s) encontrada(s).")
        for item in itens[: max(args.limite, 0)]:
            print(
                " | ".join(
                    str(item.get(campo) or "")
                    for campo in (
                        "motivo", "id_visita", "tipo", "data", "localidade",
                        "logradouro", "numero", "tipo_imovel", "id_foco",
                        "gera_notificacao", "status_notificacao",
                    )
                )
            )
        if len(itens) > max(args.limite, 0):
            print(f"[INFO] {len(itens) - max(args.limite, 0)} item(ns) nao exibido(s).")
        return 0
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
