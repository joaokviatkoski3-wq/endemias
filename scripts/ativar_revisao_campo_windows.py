"""Ativa a fila de revisão e a gravação de exúvias do LIRAa."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(origin="2.11.1", target="2.12.0", marker="ativacao-revisao-campo2120",
                          migration="0039_liraa_exuvias.sql"))
