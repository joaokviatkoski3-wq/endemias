"""Ativa a opção de notificações no aparelho do piloto de campo."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(origin="2.13.1", target="2.14.0", marker="ativacao-web-push2140",
                          migration="0042_campo_push.sql", push=True))
