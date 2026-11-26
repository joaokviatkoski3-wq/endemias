
"""Ativa a revisão de Esporotricose com migração aditiva e backup."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(
        origin="2.14.2",
        target="2.15.0",
        marker="ativacao-esporotricose2150",
        migration="0045_esporotricose_dados_kobo.sql",
    ))
