"""Ativa identidade dos setores, rastreabilidade e ajuda contextual, sem DDL."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ativar_interface_setores_windows import main


if __name__ == '__main__':
    raise SystemExit(main(origin='2.0.2', target='2.1.0', marker='ativacao-identidade210'))
