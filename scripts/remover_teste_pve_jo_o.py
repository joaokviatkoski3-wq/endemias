"""Remove, sob confirmacao explicita, a visita-teste PVE e o resultado do tubo 666.

O alvo e deliberadamente fixo. O script primeiro apresenta uma previa e, ao
aplicar, remove em uma unica transacao os dados derivados da visita e somente o
resultado de tubo 666 cuja assinatura ainda seja ``jo_o``. Auditorias antigas
nao sao apagadas; a remocao gera um novo evento de auditoria.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402


SAFE_DATABASE = "endemias_teste"
VISITA_ID = "1e6b83368ad724b12c7ffe085568e165"
TUBO = "666"
AGENTE_INVALIDO = "jo_o"
CONFIRMACAO = "REMOVER TESTE PVE JO_O TUBO 666"


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument(
        "--confirmar-banco",
        default="",
        help="Obrigatorio fora de endemias_teste: repita o nome do banco.",
    )
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument(
        "--confirmar-remocao",
        default="",
        help=f'Repita exatamente: "{CONFIRMACAO}".',
    )
    return parser


def _fetchone(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def _prever(cur):
    visita = _fetchone(
        cur,
        """SELECT id_visita, tipo, data, kobo_uuid
             FROM visitas WHERE id_visita=%s""",
        (VISITA_ID,),
    )
    if not visita:
        raise ValueError("A visita-teste informada nao foi encontrada.")
    if visita[1] != "PVE":
        raise ValueError("O identificador encontrado nao pertence a uma visita PVE.")

    cur.execute("SELECT id_coleta FROM coletas WHERE id_visita=%s", (VISITA_ID,))
    coletas = [row[0] for row in cur.fetchall()]
    cur.execute(
        """SELECT rl.id_resultado, rl.id_coleta, rl.num_tubo, rl.laboratorista
             FROM resultados_laboratorio rl
             JOIN coletas c ON c.id_coleta=rl.id_coleta
            WHERE c.id_visita=%s
               OR (rl.num_tubo=%s AND rl.laboratorista=%s)
            ORDER BY rl.id_resultado""",
        (VISITA_ID, TUBO, AGENTE_INVALIDO),
    )
    resultados = cur.fetchall()
    cur.execute(
        """SELECT a.id_agente,
                  (SELECT COUNT(*) FROM visita_agentes va
                    WHERE va.id_agente=a.id_agente) AS visitas,
                  (SELECT COUNT(*) FROM resultados_laboratorio rl
                    WHERE rl.id_laboratorista=a.id_agente) AS resultados
             FROM agentes a
            WHERE a.nome=%s""",
        (AGENTE_INVALIDO,),
    )
    agente = cur.fetchone()
    return visita, coletas, resultados, agente


def _delete(cur, coletas, resultados, agente):
    ids_resultados = [row[0] for row in resultados]
    cur.execute("DELETE FROM focos_positivos WHERE id_visita=%s", (VISITA_ID,))
    if ids_resultados:
        cur.execute("DELETE FROM focos_positivos WHERE id_resultado = ANY(%s)", (ids_resultados,))
    if coletas:
        cur.execute("DELETE FROM focos_positivos WHERE id_coleta = ANY(%s)", (coletas,))
        cur.execute("DELETE FROM laboratorio_coletas_status WHERE id_coleta = ANY(%s)", (coletas,))
    if ids_resultados:
        cur.execute("DELETE FROM resultados_laboratorio WHERE id_resultado = ANY(%s)", (ids_resultados,))
    cur.execute("DELETE FROM visita_acs WHERE id_visita=%s", (VISITA_ID,))
    cur.execute("DELETE FROM visita_agentes WHERE id_visita=%s", (VISITA_ID,))
    cur.execute("DELETE FROM depositos_inspecionados WHERE id_visita=%s", (VISITA_ID,))
    cur.execute("DELETE FROM tratamentos WHERE id_visita=%s", (VISITA_ID,))
    cur.execute("DELETE FROM coletas WHERE id_visita=%s", (VISITA_ID,))
    cur.execute("DELETE FROM visitas WHERE id_visita=%s", (VISITA_ID,))
    if agente:
        cur.execute(
            """DELETE FROM agentes a
                 WHERE a.id_agente=%s
                   AND NOT EXISTS (SELECT 1 FROM visita_agentes va WHERE va.id_agente=a.id_agente)
                   AND NOT EXISTS (SELECT 1 FROM resultados_laboratorio rl WHERE rl.id_laboratorista=a.id_agente)""",
            (agente[0],),
        )
        agente_removido = cur.rowcount == 1
    else:
        agente_removido = False
    cur.execute(
        """INSERT INTO auditoria_eventos
               (acao, entidade, entidade_id, usuario_nome, detalhes_json, criado_em)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (
            "visita_teste_pve_removida",
            "visitas",
            VISITA_ID,
            "Sistema - limpeza autorizada",
            json.dumps({
                "tubo": TUBO,
                "laboratorista_invalido": AGENTE_INVALIDO,
                "resultados_removidos": ids_resultados,
                "agente_removido": agente_removido,
            }, ensure_ascii=False, sort_keys=True),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    return agente_removido


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print("[ERRO] Confirme o banco fora de endemias_teste.")
        return 2
    if args.aplicar and args.confirmar_remocao != CONFIRMACAO:
        print(f'[ERRO] Para aplicar, informe --confirmar-remocao "{CONFIRMACAO}".')
        return 2

    conn = None
    try:
        conn = postgresql.connect(database=args.database)
        cur = conn.cursor()
        visita, coletas, resultados, agente = _prever(cur)
        print("Visita:", " | ".join(str(valor or "") for valor in visita))
        print("Coletas da visita:", len(coletas))
        print("Resultados a remover:", len(resultados))
        for resultado in resultados:
            print("  ", " | ".join(str(valor or "") for valor in resultado))
        print("Agente jo_o:", "presente" if agente else "nao encontrado")
        if not args.aplicar:
            conn.rollback()
            print("[FIM] Previa concluida; nenhum dado foi alterado.")
            return 0
        agente_removido = _delete(cur, coletas, resultados, agente)
        conn.commit()
        print("[OK] Visita-teste e dados derivados removidos em uma transacao.")
        print("[OK] Agente jo_o removido:", "sim" if agente_removido else "nao (ausente ou ainda referenciado)")
        return 0
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        print(f"[ERRO] Nenhum dado foi confirmado como removido: {exc}")
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
