"""Promove rc.3 para 2.0.0 aprovada pelo usuário, sem alterações funcionais/DDL."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ativar_interface_setores_windows import main


if __name__=='__main__':
    raise SystemExit(main(origin='2.0.0-rc.3',target='2.0.0',marker='ativacao200estavel'))
