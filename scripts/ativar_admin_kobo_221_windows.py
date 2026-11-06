"""Corrige importação por admin, sem mudar permissões técnicas ou dados."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.ativar_interface_setores_windows import main

if __name__ == '__main__':
    raise SystemExit(main(origin='2.2.0',target='2.2.1',marker='ativacao-adminkobo221'))
