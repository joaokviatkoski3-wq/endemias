"""Ativa ajustes compatíveis do BRI após recomposição explícita dos históricos."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ativar_interface_setores_windows import main


if __name__ == '__main__':
    raise SystemExit(main(origin='2.0.1', target='2.0.2', marker='ativacao-bri202'))
