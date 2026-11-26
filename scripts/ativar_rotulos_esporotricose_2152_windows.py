"""Instala o ajuste de rótulos no mapa de bloqueio da Esporotricose."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(
        origin="2.15.1",
        target="2.15.2",
        marker="ativacao-rotulos-esporo2152",
    ))
