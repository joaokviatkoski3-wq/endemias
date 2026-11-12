"""Ativa a separação entre tipo de depósito e resposta sobre eliminação."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ativar_interface_setores_windows import main

if __name__ == "__main__":
    raise SystemExit(main(origin="2.7.5", target="2.7.6", marker="ativacao-depositos-tubitos276"))
