"""Opera uma unica contagem da fila Conta Ovos com confirmacao forte."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_client  # noqa: E402
from app_core import contaovos_credencial  # noqa: E402
from app_core import contaovos_envio  # noqa: E402
from app_core import db as db_core  # noqa: E402


OFFICIAL_DATABASE = "endemias"
WRITE_CONFIRMATION = "ENVIAR UMA CONTAGEM AO CONTA OVOS"
INTERACTIVE_CONFIRMATION = "ENVIAR ID_FILA {queue_id} AO CONTA OVOS"


def _parser():
    parser = argparse.ArgumentParser(
        description="Lista a fila ou envia uma unica contagem ao Conta Ovos."
    )
    parser.add_argument("--database", default=OFFICIAL_DATABASE)
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--interativo", action="store_true")
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument("--id-fila", type=int)
    parser.add_argument("--operador")
    parser.add_argument("--confirmar-banco")
    parser.add_argument("--confirmar-item")
    parser.add_argument("--autorizar-envio")
    parser.add_argument("--autorizar-mudanca-coordenadas")
    return parser


def _target(database):
    return db_core.DatabaseTarget("postgresql", database)


def _list(args):
    conn = db_core.connect(_target(args.database))
    try:
        rows = contaovos_envio.list_queue(conn, limit=args.limite)
    finally:
        conn.close()
    if not rows:
        print("[OK] Nenhum item pendente ou inconclusivo na fila.")
        return 0
    print("ID_FILA  ESTADO     LOTE  ITEM  OVITRAMPA  DATA        OVOS  TENTATIVAS")
    for row in rows:
        print(
            f"{row['id_fila']:<8} {row['status']:<10} {row['id_lote']:<5} "
            f"{row['id_item']:<5} {row['ovitrampa_id']:<9} "
            f"{str(row['data_movimento'])[:10]:<10} {row['ovos']:<5} "
            f"{row['tentativas']}"
        )
    print("\nItens 'enviando' sao apenas reconciliados; nunca sao reenviados.")
    return len(rows)


def _read_interactive(args):
    listed = _list(args)
    if listed == 0:
        return 0
    print("\nA operacao pode criar uma leitura irreversivel no Conta Ovos.")
    queue_text = input("Digite o ID_FILA exato do item piloto: ").strip()
    if not queue_text.isdigit() or int(queue_text) < 1:
        print("[ERRO] ID_FILA invalido. Nenhum envio foi autorizado.")
        return 2
    operator_name = input("Digite seu nome para a auditoria: ").strip()
    if not operator_name or len(operator_name) > 120:
        print("[ERRO] Nome do operador invalido. Nenhum envio foi autorizado.")
        return 2
    expected = INTERACTIVE_CONFIRMATION.format(queue_id=int(queue_text))
    print("\nSera feita reconciliacao GET antes e depois de uma unica tentativa.")
    confirmation = input(f'Digite exatamente "{expected}": ').strip()
    if confirmation != expected:
        print("[ERRO] Confirmacao incorreta. Nenhum envio foi autorizado.")
        return 2
    args.id_fila = int(queue_text)
    args.operador = operator_name
    args.confirmar_banco = OFFICIAL_DATABASE
    args.confirmar_item = queue_text
    args.autorizar_envio = WRITE_CONFIRMATION
    return None


def _send(args, key):
    try:
        return contaovos_envio.send_one(
            _target(args.database),
            queue_id=args.id_fila,
            operator_name=args.operador,
            key=key,
            allow_remote_write=True,
            coordinate_authorization=args.autorizar_mudanca_coordenadas,
        )
    except contaovos_envio.ContaOvosSendError as exc:
        if (
            not args.interativo
            or exc.kind != "coordinate_change_confirmation_required"
        ):
            raise
        details = exc.details
        print("\n[ATENCAO] O POST alterara a posicao cadastrada da ovitrampa:")
        print(
            "  Conta Ovos: "
            f"{details['remote_lat']:.6f}, {details['remote_lng']:.6f}"
        )
        print(
            "  Cadastro local: "
            f"{details['local_lat']:.6f}, {details['local_lng']:.6f}"
        )
        typed = input(
            "Para autorizar conscientemente a mudanca, digite exatamente:\n"
            f'"{exc.required_confirmation}"\n> '
        ).strip()
        if typed != exc.required_confirmation:
            raise contaovos_envio.ContaOvosSendError(
                "Mudanca de coordenadas nao autorizada; nenhum POST foi enviado.",
                kind="coordinate_change_not_authorized",
            ) from None
        args.autorizar_mudanca_coordenadas = typed
        return contaovos_envio.send_one(
            _target(args.database),
            queue_id=args.id_fila,
            operator_name=args.operador,
            key=key,
            allow_remote_write=True,
            coordinate_authorization=typed,
        )


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != OFFICIAL_DATABASE:
        print(f"[ERRO] Este operador aceita somente o banco {OFFICIAL_DATABASE}.")
        return 2
    if args.interativo:
        try:
            interactive_result = _read_interactive(args)
        except (EOFError, KeyboardInterrupt):
            print("\n[ERRO] Operacao cancelada. Nenhum envio foi autorizado.")
            return 2
        except Exception as exc:
            print(f"[ERRO] {contaovos_client.sanitize_message(exc)}")
            return 1
        if interactive_result is not None:
            return interactive_result
    if args.listar:
        try:
            _list(args)
            return 0
        except Exception as exc:
            print(f"[ERRO] {contaovos_client.sanitize_message(exc)}")
            return 1
    if not args.id_fila or args.id_fila < 1:
        print("[ERRO] Informe um --id-fila positivo.")
        return 2
    if not str(args.operador or "").strip():
        print("[ERRO] Informe --operador para a auditoria.")
        return 2
    if args.confirmar_banco != OFFICIAL_DATABASE:
        print(f"[ERRO] Confirme o banco com --confirmar-banco {OFFICIAL_DATABASE}.")
        return 2
    if str(args.confirmar_item or "") != str(args.id_fila):
        print("[ERRO] --confirmar-item deve repetir exatamente o ID da fila.")
        return 2
    if args.autorizar_envio != WRITE_CONFIRMATION:
        print(
            "[ERRO] Confirme a escrita remota com "
            f'--autorizar-envio "{WRITE_CONFIRMATION}"'
        )
        return 2

    key = None
    try:
        key = contaovos_credencial.read_key()
        result = _send(args, key)
        if result["sent"]:
            print(
                "[OK] Uma contagem foi enviada e confirmada por GET. "
                f"ID remoto: {result['id_remoto']}."
            )
        else:
            print(
                "[OK] A contagem ja existia e foi reconciliada sem novo POST. "
                f"ID remoto: {result['id_remoto']}."
            )
        return 0
    except Exception as exc:
        message = contaovos_client.sanitize_message(exc, key)
        if getattr(exc, "outcome_uncertain", False):
            print("[ATENCAO] O resultado remoto e incerto. Nao tente enviar novamente.")
        print(f"[ERRO] {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
