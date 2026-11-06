"""Ativa as melhorias de campo; preserva o catálogo Kobo privado já instalado."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ativar_interface_setores_windows import main

if __name__=='__main__':
    raise SystemExit(main(origin='2.3.0',target='2.4.0',marker='ativacao-formularios240'))
