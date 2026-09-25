"""Executa uma importação Kobo de 7 dias; simulação é o padrão."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import db, kobo_auto  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="endemias_teste")
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--confirmar-banco")
    parser.add_argument("--confirmar-leitura")
    args = parser.parse_args(argv)
    if args.aplicar and args.confirmar_banco != args.database:
        parser.error("Para gravar, informe --confirmar-banco com o nome do banco.")
    if args.database == "endemias" and not args.aplicar and args.confirmar_leitura != "CONSULTAR KOBO E BANCO SOMENTE LEITURA":
        parser.error('Para simular no banco oficial, use --confirmar-leitura "CONSULTAR KOBO E BANCO SOMENTE LEITURA".')
    if args.aplicar and args.database != "endemias":
        parser.error("A rotina automática só grava no banco oficial endemias.")
    if args.aplicar and not os.environ.get("PGPASSFILE"):
        parser.error("PGPASSFILE precisa estar definido no processo agendado.")
    target = db.DatabaseTarget("postgresql", args.database)
    try:
        resultado = kobo_auto.executar(
            target=target,
            config_path=str(ROOT / "config.json"),
            kobo_config_path=str(ROOT / "kobo_config.json"),
            migracoes_dir=str(ROOT / "migrations" / "postgresql"),
            aplicar=args.aplicar,
        )
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1
    print(json.dumps(resultado, ensure_ascii=False))
    print("[OK] Lote gravado." if args.aplicar else "[OK] Simulação concluída; banco não alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
