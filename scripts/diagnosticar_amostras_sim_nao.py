"""Diagnostico somente-leitura dos campos sim/nao de Amostra de Animais.

Lista como estao gravados `houve_acidente` e `houve_captura` em
`amostras_animais`: valores distintos + contagem (por origem) e os registros
recentes com valor fora de 'Sim'/'Nao' (vazio, codigo tipo n_o, etc.).

Nao altera nenhum dado. Nao imprime credenciais. Para rodar fora de
`endemias_teste`, exige --confirmar-banco com o nome exato do banco (o pgpass
precisa ser legivel pela sessao; normalmente console elevado/administrador).
"""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402


SAFE_DATABASE = "endemias_teste"
VALIDOS_SQL = "('Sim', 'Não', '')"


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=SAFE_DATABASE,
                        help=f"Banco a diagnosticar (padrao: {SAFE_DATABASE}).")
    parser.add_argument("--confirmar-banco", default="",
                        help="Obrigatorio para banco diferente de endemias_teste.")
    parser.add_argument("--limite", type=int, default=60,
                        help="Quantos registros afetados recentes listar (padrao: 60).")
    return parser


def _contagem_por_origem(cur, coluna):
    cur.execute(
        f"""
        SELECT origem_estrutura,
               COALESCE({coluna}, '') AS valor,
               COUNT(*) AS total
          FROM amostras_animais
         GROUP BY origem_estrutura, COALESCE({coluna}, '')
         ORDER BY origem_estrutura, total DESC
        """
    )
    return cur.fetchall()


def _total(cur):
    cur.execute("SELECT COUNT(*) FROM amostras_animais")
    return cur.fetchone()[0]


def _afetados(cur, limite):
    cur.execute(
        f"""
        SELECT id_amostra, data, origem_estrutura, arquivo_origem, kobo_uuid,
               houve_acidente, houve_captura
          FROM amostras_animais
         WHERE COALESCE(houve_acidente, '') NOT IN {VALIDOS_SQL}
            OR COALESCE(houve_captura, '') NOT IN {VALIDOS_SQL}
         ORDER BY data DESC, id_amostra
         LIMIT %s
        """,
        (int(limite),),
    )
    return cur.fetchall()


def _rotulo(valor):
    return "<vazio>" if valor == "" else str(valor)


def _imprime_coluna(titulo, rows):
    print(f"\n  {titulo}")
    if not rows:
        print("    (sem registros)")
        return
    for origem, valor, total in rows:
        print("    origem={:<12} valor={:<22} -> {}".format(
            str(origem or "-"), _rotulo(valor), total,
        ))


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print(f"[ERRO] Banco {args.database} nao autorizado.")
        print(f"Para rodar fora de {SAFE_DATABASE}, informe "
              f"--confirmar-banco {args.database}")
        return 2

    summary = postgresql.connection_summary(database=args.database)
    print(f"Diagnostico somente-leitura: "
          f"{summary['user']}@{summary['host']}:{summary['port']}/"
          f"{summary['database']}")
    print("Tabela: amostras_animais  |  colunas: houve_acidente, houve_captura")
    try:
        conn = postgresql.connect(database=args.database)
        cur = conn.cursor()
    except Exception as exc:
        print(f"[ERRO] Nao foi possivel conectar: {exc}")
        return 1

    try:
        total = _total(cur)
        print(f"\nTotal de registros em amostras_animais: {total}")

        print("\n== Valores de houve_acidente (por origem) ==")
        _imprime_coluna("houve_acidente", _contagem_por_origem(cur, "houve_acidente"))

        print("\n== Valores de houve_captura (por origem) ==")
        _imprime_coluna("houve_captura", _contagem_por_origem(cur, "houve_captura"))

        afetados = _afetados(cur, args.limite)
        print(f"\n== Registros recentes com acidente/captura fora de "
              f"Sim/Nao/vazio (limite {args.limite}) ==")
        if not afetados:
            print("  (nenhum registro afetado)")
        for row in afetados:
            print(
                "  id=", row[0],
                "| data=", row[1],
                "| origem=", row[2],
                "| arquivo=", row[3],
                "| acidente=", row[5] or "<vazio>",
                "| captura=", row[6] or "<vazio>",
            )
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.rollback()
        conn.close()

    print("\n[FIM] Nenhum dado foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
