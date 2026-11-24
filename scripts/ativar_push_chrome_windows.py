"""Ativa a compatibilidade com o Web Push atual do Chrome."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(origin="2.14.1", target="2.14.2", marker="ativacao-push-chrome2142",
                          migration="0044_campo_push_teste_estado.sql"))
