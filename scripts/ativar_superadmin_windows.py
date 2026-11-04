"""Janela 1.78 -> 1.79; unica promocao pessoal explicitamente confirmada."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ativar_recuperacao_senha_windows import Release, main


RELEASE = Release("1.78.0", "1.79.0", "0033_superadmin.sql", "ativacao179", owner_id=2, owner_login="joao")


if __name__ == "__main__":
    raise SystemExit(main(RELEASE))
