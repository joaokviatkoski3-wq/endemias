"""Corrige valores sim/nao ja gravados em `amostras_animais`.

Normaliza `houve_acidente` e `houve_captura` que vieram como codigo do Kobo
(ex.: ``n_o`` -> "Não", ``sim`` -> "Sim"), reutilizando a mesma regra da
importacao (app_core.amostras_animais._normalizar_sim_nao). Registros vazios
nao sao alterados (nao ha como inferir a resposta).

Por padrao apenas mostra o que seria alterado (dry-run). Para gravar, use
--aplicar. Fora de endemias_teste exige --confirmar-banco com o nome exato.
"""

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import amostras_animais  # noqa: E402
from app_core import postgresql  # noqa: E402


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--confirmar-banco", default="")
    parser.add_argument("--aplicar", action="store_true",
                        help="Grava as correcoes (sem este flag, so mostra).")
    return parser


def _colunas_afetadas(novo):
    return (novo.get("houve_acidente"), novo.get("houve_captura"))


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print(f"[ERRO] Banco {args.database} nao autorizado.")
        print(f"Informe --confirmar-banco {args.database} para autorizar.")
        return 2

    _apontar_pgpass()
    summary = postgresql.connection_summary(database=args.database)
    print(f"Alvo: {summary['user']}@{summary['host']}:{summary['port']}/"
          f"{summary['database']}  |  tabela amostras_animais")

    conn = postgresql.connect(database=args.database)
    cur = conn.cursor()
    cur.execute("""
        SELECT id_amostra, origem_estrutura, houve_acidente, houve_captura
          FROM amostras_animais
    """)
    linhas = cur.fetchall()

    mudancas = []
    for id_amostra, origem, acidente, captura in linhas:
        novo = {
            "houve_acidente": amostras_animais._normalizar_sim_nao(acidente),
            "houve_captura": amostras_animais._normalizar_sim_nao(captura),
        }
        antes = {"houve_acidente": acidente, "houve_captura": captura}
        if (novo["houve_acidente"], novo["houve_captura"]) != (antes["houve_acidente"], antes["houve_captura"]):
            mudancas.append({
                "id_amostra": id_amostra,
                "origem": origem,
                "acidente": (antes["houve_acidente"], novo["houve_acidente"]),
                "captura": (antes["houve_captura"], novo["houve_captura"]),
            })

    print(f"\nRegistros a corrigir: {len(mudancas)}")
    if not mudancas:
        print("Nenhuma correcao necessaria.")
        cur.close(); conn.close()
        return 0

    for m in mudancas:
        print("  id=", m["id_amostra"],
              "| origem=", m["origem"],
              "| acidente:", repr(m["acidente"][0]), "->", repr(m["acidente"][1]),
              "| captura:", repr(m["captura"][0]), "->", repr(m["captura"][1]))

    if not args.aplicar:
        print("\n[Dry-run] Nenhum dado foi alterado. Rode com --aplicar para gravar.")
        cur.close(); conn.close()
        return 0

    confirmado = input(
        f"\nConfirmar a gravacao de {len(mudancas)} correcao(oes) em "
        f"{args.database}? Digite SIM: "
    ).strip().upper()
    if confirmado != "SIM":
        print("Cancelado. Nenhum dado alterado.")
        cur.close(); conn.close()
        return 3

    try:
        for m in mudancas:
            cur.execute(
                """UPDATE amostras_animais
                      SET houve_acidente = %s, houve_captura = %s
                    WHERE id_amostra = %s""",
                (m["acidente"][1], m["captura"][1], m["id_amostra"]),
            )
        conn.commit()
        print(f"OK: {len(mudancas)} registro(s) corrigido(s) em {args.database}.")
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
