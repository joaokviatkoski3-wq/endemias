"""Janela 1.77 -> 1.78, somente migracao aditiva 0032; mesma tarefa limitada."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ativar_recuperacao_senha_windows import Release, main


RELEASE = Release("1.77.0", "1.78.0", "0032_presenca_usuarios.sql", "ativacao178")


if __name__ == "__main__":
    raise SystemExit(main(RELEASE))
