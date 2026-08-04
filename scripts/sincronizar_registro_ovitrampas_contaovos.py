"""Sincroniza no banco local o cadastro publico de ovitrampas do Conta Ovos.

Endpoint publico (getmunicipalityovitrapspublic), sem chave privada. Somente
GET. Nao ha botao na interface: esta e uma execucao supervisionada por linha
de comando, como os demais sincronizadores do projeto.
"""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_client  # noqa: E402
from app_core import contaovos_registro  # noqa: E402
from app_core import db as db_core  # noqa: E402


READ_CONFIRMATION = "CONSULTAR CADASTRO PUBLICO CONTA OVOS"
APPLY_CONFIRMATION = "ATUALIZAR ESPELHO LOCAL DE OVITRAMPAS"
SAFE_DATABASE = "endemias_teste"


def _parser():
    parser = argparse.ArgumentParser(
        description="Sincroniza o espelho local do cadastro publico de ovitrampas."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--max-paginas", type=int, default=100)
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--confirmar-leitura")
    parser.add_argument("--autorizar-atualizacao-local")
    parser.add_argument("--confirmar-banco")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.confirmar_leitura != READ_CONFIRMATION:
        print(
            "[ERRO] Confirme a consulta publica com "
            f'--confirmar-leitura "{READ_CONFIRMATION}"'
        )
        return 2
    if args.aplicar and args.autorizar_atualizacao_local != APPLY_CONFIRMATION:
        print(
            "[ERRO] Confirme a atualizacao do espelho local com "
            f'--autorizar-atualizacao-local "{APPLY_CONFIRMATION}"'
        )
        return 2
    if (
        args.aplicar
        and args.database != SAFE_DATABASE
        and args.confirmar_banco != args.database
    ):
        print(
            "[ERRO] Para atualizar fora de endemias_teste, informe "
            f"--confirmar-banco {args.database}"
        )
        return 2

    try:
        if not args.aplicar:
            result = contaovos_registro.fetch_registro(max_pages=args.max_paginas)
            print(
                "[OK] Consulta concluida sem atualizar o banco local: "
                f"{len(result['records'])} ovitrampa(s), {result['pages']} pagina(s)."
            )
            return 0

        target = db_core.DatabaseTarget("postgresql", args.database)
        result = contaovos_registro.synchronize(target, max_pages=args.max_paginas)
        print(
            "[OK] Espelho local atualizado: "
            f"{result['inseridos']} inserido(s), "
            f"{result['atualizados']} atualizado(s), "
            f"{result['sem_alteracao']} sem alteracao."
        )
        print(f"[OK] Execucao {result['id_execucao']}.")
        return 0
    except Exception as exc:
        print(f"[ERRO] {contaovos_client.sanitize_message(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
