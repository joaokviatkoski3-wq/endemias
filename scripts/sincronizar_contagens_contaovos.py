"""Executa consulta/sincronizacao supervisionada das contagens Conta Ovos."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_client  # noqa: E402
from app_core import contaovos_credencial  # noqa: E402
from app_core import contaovos_sync  # noqa: E402
from app_core import db as db_core  # noqa: E402


READ_CONFIRMATION = "CONSULTAR CONTAGENS CONTA OVOS SOMENTE LEITURA"
APPLY_CONFIRMATION = "ATUALIZAR HISTORICO LOCAL CONTA OVOS"
SAFE_DATABASE = "endemias_teste"


def _parser():
    parser = argparse.ArgumentParser(
        description="Sincroniza no banco local as contagens lidas da API Conta Ovos."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--data-inicial")
    parser.add_argument("--data-final")
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
            "[ERRO] Confirme a consulta privada com "
            f'--confirmar-leitura "{READ_CONFIRMATION}"'
        )
        return 2
    if args.aplicar and args.autorizar_atualizacao_local != APPLY_CONFIRMATION:
        print(
            "[ERRO] Confirme a atualizacao do historico local com "
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
        key = contaovos_credencial.read_key()
        if not args.aplicar:
            result = contaovos_sync.fetch_countings(
                key,
                date_start=args.data_inicial,
                date_end=args.data_final,
                max_pages=args.max_paginas,
            )
            remote_ids = [
                int(item["id_contagem"]) for item in result["records"]
            ]
            print(
                "[OK] Consulta concluida sem atualizar o banco local: "
                f"{len(result['records'])} registro(s), "
                f"{result['pages']} pagina(s)."
            )
            if remote_ids:
                print(f"[OK] Maior counting_id observado: {max(remote_ids)}")
            return 0

        target = db_core.DatabaseTarget("postgresql", args.database)
        result = contaovos_sync.synchronize_countings(
            target,
            key=key,
            date_start=args.data_inicial,
            date_end=args.data_final,
            max_pages=args.max_paginas,
        )
        print(
            "[OK] Historico local atualizado: "
            f"{result['inseridos']} inserido(s), "
            f"{result['atualizados']} atualizado(s), "
            f"{result['sem_alteracao']} sem alteracao."
        )
        print(
            f"[OK] Cursor: {result['cursor_atual'] or '-'}; "
            f"execucao {result['id_execucao']}."
        )
        if result["ovitrampas_nao_cadastradas"]:
            print(
                "[AVISO] "
                f"{result['ovitrampas_nao_cadastradas']} ovitrampa(s) remota(s) "
                "nao possuem cadastro local correspondente."
            )
        return 0
    except Exception as exc:
        print(f"[ERRO] {contaovos_client.sanitize_message(exc, locals().get('key'))}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
