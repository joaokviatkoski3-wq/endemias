"""Executa consulta/sincronizacao supervisionada das contagens Conta Ovos."""

import argparse
import os
import sys
from calendar import monthrange
from datetime import date, timedelta
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
KNOWN_PGPASS = r"C:\ProgramData\Endemias\pgpass.conf"


def _apontar_pgpass():
    if not os.environ.get("PGPASSFILE") and os.path.exists(KNOWN_PGPASS):
        try:
            with open(KNOWN_PGPASS, "rb") as fh:
                fh.read(1)
            os.environ["PGPASSFILE"] = KNOWN_PGPASS
        except OSError:
            pass


def _parser():
    parser = argparse.ArgumentParser(
        description="Sincroniza no banco local as contagens lidas da API Conta Ovos."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--data-inicial")
    parser.add_argument("--data-final")
    parser.add_argument("--max-paginas", type=int, default=100)
    parser.add_argument(
        "--dividir-por-mes",
        action="store_true",
        help="Divide o periodo em meses para respeitar o limite da API.",
    )
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--confirmar-leitura")
    parser.add_argument("--autorizar-atualizacao-local")
    parser.add_argument("--confirmar-banco")
    return parser


def _periods(date_start, date_end, split_monthly=False):
    if not split_monthly:
        return [(date_start, date_end)]
    try:
        start = date.fromisoformat(str(date_start))
        end = date.fromisoformat(str(date_end))
    except (TypeError, ValueError):
        raise ValueError(
            "Informe datas inicial e final validas para dividir por mes."
        ) from None
    if start > end:
        raise ValueError("A data inicial nao pode ser posterior a data final.")
    result = []
    current = start
    while current <= end:
        month_end = date(
            current.year,
            current.month,
            monthrange(current.year, current.month)[1],
        )
        period_end = min(month_end, end)
        result.append((current.isoformat(), period_end.isoformat()))
        current = period_end + timedelta(days=1)
    return result


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
        periods = _periods(
            args.data_inicial, args.data_final, args.dividir_por_mes
        )
        if not args.aplicar:
            total_records = 0
            total_pages = 0
            remote_ids = []
            for date_start, date_end in periods:
                result = contaovos_sync.fetch_countings(
                    key,
                    date_start=date_start,
                    date_end=date_end,
                    max_pages=args.max_paginas,
                )
                records = result["records"]
                total_records += len(records)
                total_pages += result["pages"]
                remote_ids.extend(int(item["id_contagem"]) for item in records)
                if args.dividir_por_mes:
                    print(
                        f"[OK] {date_start} a {date_end}: {len(records)} "
                        f"registro(s), {result['pages']} pagina(s)."
                    )
            print(
                "[OK] Consulta concluida sem atualizar o banco local: "
                f"{total_records} registro(s), "
                f"{total_pages} pagina(s) somadas."
            )
            if remote_ids:
                print(f"[OK] Maior counting_id observado: {max(remote_ids)}")
            return 0

        target = db_core.DatabaseTarget("postgresql", args.database)
        _apontar_pgpass()
        totals = {
            "inseridos": 0,
            "atualizados": 0,
            "sem_alteracao": 0,
            "ovitrampas_nao_cadastradas": 0,
        }
        result = None
        for date_start, date_end in periods:
            result = contaovos_sync.synchronize_countings(
                target,
                key=key,
                date_start=date_start,
                date_end=date_end,
                max_pages=args.max_paginas,
            )
            for field in totals:
                totals[field] += result[field]
            if args.dividir_por_mes:
                print(
                    f"[OK] {date_start} a {date_end}: "
                    f"{result['inseridos']} inserido(s), "
                    f"{result['atualizados']} atualizado(s), "
                    f"{result['sem_alteracao']} sem alteracao."
                )
        print(
            "[OK] Historico local atualizado: "
            f"{totals['inseridos']} inserido(s), "
            f"{totals['atualizados']} atualizado(s), "
            f"{totals['sem_alteracao']} sem alteracao."
        )
        print(
            f"[OK] Cursor: {result['cursor_atual'] or '-'}; "
            f"execucao {result['id_execucao']}."
        )
        if totals["ovitrampas_nao_cadastradas"]:
            print(
                "[AVISO] "
                f"{totals['ovitrampas_nao_cadastradas']} ocorrencia(s) de "
                "ovitrampa remota "
                "nao possuem cadastro local correspondente."
            )
        return 0
    except Exception as exc:
        print(f"[ERRO] {contaovos_client.sanitize_message(exc, locals().get('key'))}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
