"""Ativação dos cards de entregas municipais, sem migração ou correção de dados."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ativar_interface_setores_windows import main

if __name__=='__main__':
    raise SystemExit(main(origin='2.9.1',target='2.9.2',marker='ativacao-estoque292'))
