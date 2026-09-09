"""Confere e, sob confirmacao dupla, reconcilia focos/notificacoes laboratoriais."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import focos_positivos  # noqa: E402


SAFE_DATABASE = "endemias_teste"
CONFIRMACAO_APLICACAO = "RECONCILIAR NOTIFICACOES LABORATORIAIS"


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
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Cria/atualiza focos divergentes; exige confirmacao adicional.",
    )
    parser.add_argument(
        "--confirmar-aplicacao",
        help=f'Repita exatamente: "{CONFIRMACAO_APLICACAO}".',
    )
    return parser


def _exibir(itens, limite):
    for item in itens[: max(limite, 0)]:
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
    if len(itens) > max(limite, 0):
        print(f"[INFO] {len(itens) - max(limite, 0)} item(ns) nao exibido(s).")


def _auditar_reconciliacao(conn, database, antes, depois):
    detalhes = {
        "database": database,
        "divergencias_antes": len(antes),
        "divergencias_depois": len(depois),
        "por_motivo": {
            motivo: sum(1 for item in antes if item["motivo"] == motivo)
            for motivo in sorted({item["motivo"] for item in antes})
        },
        "origem": "script_controlado",
    }
    conn.execute(
        """INSERT INTO auditoria_eventos
               (acao, entidade, entidade_id, usuario_nome, detalhes_json, criado_em)
           VALUES (?,?,?,?,?,?)""",
        (
            "notificacoes_laboratorio_reconciliadas",
            "focos_positivos",
            None,
            "Sistema - reconciliacao autorizada",
            json.dumps(detalhes, ensure_ascii=False, sort_keys=True),
            datetime.now().isoformat(),
        ),
    )


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print(
            f'[ERRO] Para consultar fora de {SAFE_DATABASE}, informe '
            f'--confirmar-banco {args.database}'
        )
        return 2
    if args.aplicar and args.confirmar_aplicacao != CONFIRMACAO_APLICACAO:
        print(
            f'[ERRO] Para aplicar, informe --confirmar-aplicacao '
            f'"{CONFIRMACAO_APLICACAO}"'
        )
        return 2

    target = db_core.DatabaseTarget("postgresql", args.database)
    conn = db_core.connect(target)
    try:
        itens = focos_positivos.listar_divergencias(conn)
        print(f"[OK] {len(itens)} divergencia(s) encontrada(s).")
        _exibir(itens, args.limite)
        if not args.aplicar:
            conn.rollback()
            return 0

        agora = datetime.now().isoformat()
        for item in itens:
            focos_positivos.sincronizar_foco_visita(conn, item["id_visita"], agora)
        restantes = focos_positivos.listar_divergencias(conn)
        if restantes:
            conn.rollback()
            print(f"[ERRO] Restaram {len(restantes)} divergencia(s); nenhuma alteracao foi gravada.")
            _exibir(restantes, args.limite)
            return 1
        _auditar_reconciliacao(conn, args.database, itens, restantes)
        conn.commit()
        print(f"[OK] {len(itens)} divergencia(s) reconciliada(s).")
        return 0
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
