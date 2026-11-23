"""Instala a versão com os catálogos offline e valida a conta piloto."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--usuario-piloto", required=True)
    args, remaining = parser.parse_known_args()
    sys.argv[1:] = remaining
    raise SystemExit(main(origin="2.10.0", target="2.11.0", marker="ativacao-formularios-campo2110",
                          migration="0038_formularios_campo.sql", piloto=args.usuario_piloto.strip()))
