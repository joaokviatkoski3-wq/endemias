"""Ativa piloto de Campo RG 2.2.0, sem DDL e sem alterar contas/setores/Kobo."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ativar_interface_setores_windows import main


if __name__ == '__main__':
    raise SystemExit(main(origin='2.1.1', target='2.2.0', marker='ativacao-pwarg220'))
