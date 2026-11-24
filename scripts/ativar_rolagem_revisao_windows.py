"""Ativa a correção visual da fila de revisão de formulários."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(origin="2.12.0", target="2.12.1", marker="ativacao-rolagem-revisao2121"))
