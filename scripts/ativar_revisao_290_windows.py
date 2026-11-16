"""Ativação controlada da revisão; requer autorização e console administrativo."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ativar_interface_setores_windows import main


if __name__ == '__main__':
    raise SystemExit(main(origin='2.8.6', target='2.9.0', marker='ativacao-revisao290',
                          migration='0037_amostras_animais_anexos.sql'))
