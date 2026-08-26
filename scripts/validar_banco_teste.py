"""Recusa um banco de teste que seja o mesmo arquivo do rollback oficial."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def mesmo_arquivo(alvo: str, oficial: str) -> bool:
    """Compara identidade e caminho resolvido, inclusive aliases do Windows."""
    alvo_path = Path(alvo)
    oficial_path = Path(oficial)

    if alvo_path.exists() and oficial_path.exists():
        return os.path.samefile(alvo_path, oficial_path)

    return alvo_path.resolve(strict=False) == oficial_path.resolve(strict=False)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        return 1

    try:
        return 2 if mesmo_arquivo(args[0], args[1]) else 0
    except (OSError, RuntimeError, ValueError):
        # Falha fechada: o iniciador deve recusar se nao puder provar o isolamento.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
