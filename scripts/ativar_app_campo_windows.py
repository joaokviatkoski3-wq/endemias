"""Ativa o aplicativo de campo 2.13.0 e o controle de leitura dos avisos."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(origin="2.12.1", target="2.13.0", marker="ativacao-app-campo2130",
                          migration="0040_avisos_campo.sql"))
