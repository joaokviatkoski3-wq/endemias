"""Ativa a separação de sequências LIRAa sem reprocessar dados históricos."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ativar_interface_setores_windows import main

if __name__=='__main__':
    raise SystemExit(main(origin='2.5.0',target='2.6.0',marker='ativacao-liraa260'))
