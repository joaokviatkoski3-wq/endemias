"""Ativação controlada da conferência do estoque e dispensa municipal ZooMed."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ativar_interface_setores_windows import main

if __name__=='__main__':
    raise SystemExit(main(origin='2.9.0',target='2.9.1',marker='ativacao-estoque291'))
