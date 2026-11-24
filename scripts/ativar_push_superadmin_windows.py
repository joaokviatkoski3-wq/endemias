"""Ativa o teste de Web Push para superadmin e ajusta o pop-up do app."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(origin="2.14.0", target="2.14.1", marker="ativacao-push-superadmin2141",
                          migration="0043_campo_push_superadmin.sql"))
