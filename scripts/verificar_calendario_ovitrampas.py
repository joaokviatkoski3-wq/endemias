"""Diagnostico somente-leitura do calendario e ciclo de ovitrampas.

Despeja schema e dados de ovitrampas_calendario_*, ovitrampas_diarios,
ovitrampas_diario_armadilhas, ovitrampas_laboratorio_lotes/itens,
ovitrampas_armadilhas e ovitrampas_leituras, para entender como uma leitura de
laboratorio se liga a sua data de instalacao no calendario. NAO altera nada.

Uso (console elevado que leia o pgpass):
  python scripts/verificar_calendario_ovitrampas.py
  python scripts/verificar_calendario_ovitrampas.py --database endemias --confirmar-banco endemias
  python scripts/verificar_calendario_ovitrampas.py --eventos-total 400 --linhas 25
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import postgresql  # noqa: E402

SAFE_DATABASE = "endemias_teste"
KNOWN_PGPASS = r"C:\ProgramData\Endemias\pgpass.conf"

TABELAS = [
    "ovitrampas_calendario_grupos",
    "ovitrampas_calendario_eventos",
    "ovitrampas_calendario_agentes",
    "ovitrampas_diarios",
    "ovitrampas_diario_armadilhas",
    "ovitrampas_armadilhas",
    "ovitrampas_laboratorio_lotes",
    "ovitrampas_laboratorio_itens",
    "ovitrampas_leituras",
]


def _apontar_pgpass():
    if not os.environ.get("PGPASSFILE") and os.path.exists(KNOWN_PGPASS):
        try:
            with open(KNOWN_PGPASS, "rb") as fh:
                fh.read(1)
            os.environ["PGPASSFILE"] = KNOWN_PGPASS
        except OSError:
            pass


def _parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", default=SAFE_DATABASE)
    p.add_argument("--confirmar-banco", default="")
    p.add_argument("--linhas", type=int, default=25,
                   help="Linhas por tabela de dados (padrao: 25).")
    p.add_argument("--eventos-total", type=int, default=400,
                   help="Max. eventos do calendario a listar cronologicamente.")
    return p


def _colunas(cur, tabela):
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
         WHERE table_schema = current_schema() AND table_name = %s
         ORDER BY ordinal_position
        """,
        (tabela,),
    )
    return [r[0] for r in cur.fetchall()]


def _contagem(cur, tabela):
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{tabela}"')
        return cur.fetchone()[0]
    except Exception:
        return None


def _despejar_tabela(cur, tabela, limite, order_by=None):
    colunas = _colunas(cur, tabela)
    if not colunas:
        print(f"  [tabela nao encontrada: {tabela}]")
        return
    total = _contagem(cur, tabela)
    print(f"\n===== {tabela}  ({total} linha(s)) | colunas: {', '.join(colunas)} =====")
    ordem = f" ORDER BY {order_by}" if order_by else ""
    sel = ", ".join(f'"{c}"' for c in colunas)
    try:
        cur.execute(
            f'SELECT {sel} FROM "{tabela}"{ordem} LIMIT %s', (int(limite),)
        )
    except Exception as exc:
        print(f"  [erro ao consultar: {exc}]")
        return
    for linha in cur.fetchall():
        print("  -")
        for nome, valor in zip(colunas, linha):
            print(f"      {nome} = {valor!r}")


def _eventos_cronologicos(cur, limite):
    print(f"\n===== ovitrampas_calendario_eventos cronologico (ate {limite}) =====")
    cur.execute(
        """
        SELECT e.id_evento, e.data, e.movimento, e.ciclo, e.titulo,
               COALESCE(g.nome, '<sem grupo>') AS grupo,
               g.localidades,
               (SELECT string_agg(a.nome, ', ' ORDER BY a.nome)
                  FROM ovitrampas_calendario_agentes ea
                  JOIN agentes a ON a.id_agente = ea.id_agente
                 WHERE ea.id_evento = e.id_evento) AS agentes
          FROM ovitrampas_calendario_eventos e
          LEFT JOIN ovitrampas_calendario_grupos g ON g.id_grupo = e.id_grupo
         ORDER BY e.data, e.id_evento
        """,
    )
    linhas = cur.fetchmany(int(limite))
    for r in linhas:
        print("  -", r[0], "|", r[1], "|", r[2], "| ciclo:", r[3],
              "| grupo:", r[4], "| localidades:", r[6], "| titulo:", r[5],
              "| agentes:", r[7])


def _lotes_recentes(cur, limite):
    print(f"\n===== ovitrampas_laboratorio_lotes (recentes, ate {limite}) =====")
    cur.execute(
        """
        SELECT l.id_lote, l.data_movimento, l.movimento, l.ciclo, l.status,
               l.diario_nome, l.id_evento, l.enviado_conta_ovos_em,
               l.enviado_por_nome,
               COUNT(i.id_item) AS itens,
               COALESCE(SUM(i.ovos),0) AS ovos
          FROM ovitrampas_laboratorio_lotes l
          LEFT JOIN ovitrampas_laboratorio_itens i ON i.id_lote=l.id_lote
         GROUP BY l.id_lote, l.data_movimento, l.movimento, l.ciclo, l.status,
                  l.diario_nome, l.id_evento, l.enviado_conta_ovos_em,
                  l.enviado_por_nome
         ORDER BY l.data_movimento DESC, l.id_lote DESC
         LIMIT %s
        """,
        (int(limite),),
    )
    for r in cur.fetchall():
        print("  - id_lote", r[0], "| data", r[1], "| mov", r[2],
              "| ciclo", r[3], "| status", r[4], "| diario", r[5],
              "| id_evento", r[6], "| enviado_em", r[7],
              "| por", r[8], "| itens", r[9], "| ovos", r[10])


def _itens_de_lote(cur, id_lote, limite=60):
    print(f"\n  -- itens do lote {id_lote} --")
    cur.execute(
        """
        SELECT i.id_item, i.ovitrampa_id, i.complemento, i.localidade,
               i.ovos, i.ocorrencia
          FROM ovitrampas_laboratorio_itens i
         WHERE i.id_lote=%s
         ORDER BY i.id_item
         LIMIT %s
        """,
        (int(id_lote), int(limite)),
    )
    for r in cur.fetchall():
        print("      id_item", r[0], "| ovitrampa", r[1], "| ovos", r[4],
              "| ocorrencia", r[5], "| local", r[3], "| comp", r[2])


def _leituras_recentes(cur, limite):
    print(f"\n===== ovitrampas_leituras recentes (ate {limite}) =====")
    cur.execute(
        """
        SELECT ovitrampa_id, ano, semana, data_instalacao, data_coleta, ovos,
               ocorrencia_codigo, data_leitura
          FROM ovitrampas_leituras
         ORDER BY data_coleta DESC NULLS LAST, ovitrampa_id
         LIMIT %s
        """,
        (int(limite),),
    )
    for r in cur.fetchall():
        print("  - ovitrampa", r[0], "| ano/sem", r[1], "/", r[2],
              "| inst", r[3], "| coleta", r[4], "| ovos", r[5],
              "| oc", r[6], "| leitura", r[7])


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print(f"[ERRO] Banco {args.database} nao autorizado. "
              f"Informe --confirmar-banco {args.database}")
        return 2
    _apontar_pgpass()
    print(f"Diagnostico somente-leitura em {args.database} ...")
    conn = postgresql.connect(database=args.database)
    cur = conn.cursor()
    try:
        _eventos_cronologicos(cur, args.eventos_total)
    except Exception as exc:
        print("[aviso eventos]", exc)
    try:
        _lotes_recentes(cur, args.linhas)
    except Exception as exc:
        print("[aviso lotes]", exc)
    try:
        cur.execute(
            """SELECT id_lote FROM ovitrampas_laboratorio_lotes
                ORDER BY data_movimento DESC, id_lote DESC LIMIT 3"""
        )
        for (id_lote,) in cur.fetchall():
            _itens_de_lote(cur, id_lote, args.linhas)
    except Exception as exc:
        print("[aviso itens]", exc)
    try:
        _leituras_recentes(cur, args.linhas)
    except Exception as exc:
        print("[aviso leituras]", exc)

    for tabela in TABELAS:
        colunas = _colunas(cur, tabela)
        order = "data DESC" if "data" in colunas else None
        _despejar_tabela(cur, tabela, args.linhas, order_by=order)

    conn.rollback()
    print("\n[FIM] Nenhum dado foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
