"""Ativa a exclusão de rascunhos próprios nos formulários internos."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(origin="2.13.0", target="2.13.1", marker="ativacao-rascunhos2131",
                          migration="0041_formularios_rascunhos_descartados.sql"))
