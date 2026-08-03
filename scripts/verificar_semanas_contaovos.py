"""Compara por GET, sem escrever, a semana remota com a regra local."""

import argparse
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_client  # noqa: E402
from app_core import contaovos_credencial  # noqa: E402
from app_core import contaovos_fila  # noqa: E402
from scripts import sincronizar_contagens_contaovos  # noqa: E402


READ_CONFIRMATION = "COMPARAR SEMANAS CONTA OVOS SOMENTE LEITURA"


def _parser():
    parser = argparse.ArgumentParser(
        description="Compara date/year/week remotos sem alterar dados."
    )
    parser.add_argument("--data-inicial", default=f"{date.today().year}-01-01")
    parser.add_argument("--data-final", default=date.today().isoformat())
    parser.add_argument("--confirmar-leitura")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.confirmar_leitura != READ_CONFIRMATION:
        print(
            "[ERRO] Confirme a operacao somente leitura com "
            f'--confirmar-leitura "{READ_CONFIRMATION}"'
        )
        return 2
    key = None
    try:
        key = contaovos_credencial.read_key()
        periods = sincronizar_contagens_contaovos._periods(
            args.data_inicial, args.data_final, True
        )
        totals = {"comparados": 0, "divergencias": 0, "paginas": 0}
        examples = []
        for date_start, date_end in periods:
            result = contaovos_fila.check_remote_epidemiological_weeks(
                key, date_start=date_start, date_end=date_end
            )
            for field in totals:
                totals[field] += result[field]
            examples.extend(result["exemplos"][: max(0, 20 - len(examples))])
            label = "OK" if result["ok"] else "ALERTA"
            print(
                f"[{label}] {date_start} a {date_end}: "
                f"{result['comparados']} comparada(s), "
                f"{result['divergencias']} divergencia(s)."
            )
        label = "OK" if totals["divergencias"] == 0 else "ERRO"
        print(
            f"[{label}] {totals['comparados']} contagem(ns) comparada(s); "
            f"{totals['divergencias']} divergencia(s)."
        )
        for item in examples:
            print(
                "[DIVERGENCIA] "
                f"contagem={item['id_contagem']} ovitrampa={item['ovitrampa_id']} "
                f"data={item['data']} remoto={item['remoto']['ano']}/"
                f"{item['remoto']['semana']} local={item['local']['ano']}/"
                f"{item['local']['semana']}"
            )
        return 0 if totals["divergencias"] == 0 else 1
    except Exception as exc:
        print(f"[ERRO] {contaovos_client.sanitize_message(exc, key)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
