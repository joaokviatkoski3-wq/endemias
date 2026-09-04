"""Diagnostico somente-leitura do espelho de contagens do Conta Ovos.

Mostra a distribuicao de ovitrampas_ocorrencias_conta_ovos por ano/semana e por
data de coleta, para entender onde estao as contagens e por que um filtro
(ano/semana) pode nao bater com o total do Conta Ovos. NAO altera nada.

Uso (Administrador):
  python scripts/diagnosticar_espelho_contagens.py
  python scripts/diagnosticar_espelho_contagens.py --database endemias --confirmar-banco endemias
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
TABELA = "ovitrampas_ocorrencias_conta_ovos"


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
    return p


def _dump(cur, rotulo, sql):
    print(f"\n== {rotulo} ==")
    try:
        cur.execute(sql)
    except Exception as exc:
        print("  [erro]", exc)
        return
    for linha in cur.fetchall():
        print("  ", " | ".join(str(x) for x in linha))


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print(f"[ERRO] Banco {args.database} nao autorizado. "
              f"Informe --confirmar-banco {args.database}")
        return 2
    _apontar_pgpass()
    print(f"Diagnostico somente-leitura em {args.database} ({TABELA})")
    conn = postgresql.connect(database=args.database)
    cur = conn.cursor()
    try:
        _dump(cur, "Total geral e por ano", f"""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT id_contagem) AS distintos
              FROM {TABELA}""")
        _dump(cur, "Por ano", f"""
            SELECT ano, COUNT(*) FROM {TABELA} GROUP BY ano ORDER BY ano""")
        _dump(cur, "Por ano/semana (limite 60)", f"""
            SELECT ano, semana, COUNT(*) FROM {TABELA}
             GROUP BY ano, semana ORDER BY ano, semana LIMIT 60""")
        _dump(cur, "Por mes da coleta (data, ano)", f"""
            SELECT EXTRACT(YEAR FROM data) AS ano, EXTRACT(MONTH FROM data) AS mes,
                   COUNT(*)
              FROM {TABELA}
             GROUP BY 1, 2 ORDER BY 1, 2""")
        _dump(cur, "Min/Max data e semana (2026)", f"""
            SELECT MIN(data), MAX(data), MIN(semana), MAX(semana)
              FROM {TABELA} WHERE ano=2026""")
        _dump(cur, "Contagens 2026 com semana>=24 (exemplo)", f"""
            SELECT ovitrampa_id, ano, semana, data, ovos
              FROM {TABELA}
             WHERE ano=2026 AND semana>=24
             ORDER BY semana, ovitrampa_id LIMIT 15""")
    finally:
        cur.close()
        conn.close()
    print("\n[FIM] Somente leitura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
