"""Valida a credencial privada Conta Ovos com uma unica consulta GET."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_client  # noqa: E402
from app_core import contaovos_credencial  # noqa: E402
from app_core import contaovos_health  # noqa: E402


CONFIRMATION = "CONSULTAR API CONTA OVOS SEM ALTERAR DADOS"


def _parser():
    parser = argparse.ArgumentParser(
        description="Valida autenticacao e escopo da API privada Conta Ovos."
    )
    parser.add_argument("--confirmar-leitura", required=True)
    parser.add_argument(
        "--municipality-code",
        default=contaovos_client.EXPECTED_MUNICIPALITY_CODE,
    )
    parser.add_argument(
        "--state-code", default=contaovos_client.EXPECTED_STATE_CODE
    )
    parser.add_argument("--status-file", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def _safe_error(exc):
    return {
        "ok": False,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "page_items": None,
        "scopes": [],
        "credential_format": None,
        "error": str(exc),
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.confirmar_leitura != CONFIRMATION:
        print("[ERRO] Confirmacao de consulta somente leitura invalida.")
        return 2

    env = None
    if args.status_file:
        import os

        env = dict(os.environ)
        env["ENDEMIAS_CONTAOVOS_STATUS_FILE"] = args.status_file

    try:
        key = contaovos_credencial.read_key()
        result = contaovos_client.validate_private_access(
            key,
            expected_municipality_code=args.municipality_code,
            expected_state_code=args.state_code,
        )
        result["checked_at"] = datetime.now().isoformat(timespec="seconds")
        result["error"] = None
    except (contaovos_credencial.ContaOvosCredentialError, contaovos_client.ContaOvosError) as exc:
        result = _safe_error(exc)

    contaovos_health.write_status(result, env=env)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["ok"]:
        scope = result["scopes"][0]
        print("[OK] Credencial privada Conta Ovos validada somente em leitura.")
        print(
            "Escopo confirmado: "
            f"{scope['municipality']} / {scope['state_code']} "
            f"({scope['municipality_code']})."
        )
        print(f"Registros verificados na primeira pagina: {result['page_items']}.")
    else:
        print(f"[ERRO] {result['error']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
