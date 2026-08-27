"""Recusa um banco de teste que seja o mesmo arquivo do rollback oficial."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime


TABELAS_MINIMAS = frozenset({"usuarios", "localidades", "visitas"})


def mesmo_arquivo(alvo: str, oficial: str) -> bool:
    """Compara identidade e caminho resolvido, inclusive aliases do Windows."""
    alvo_path = Path(alvo)
    oficial_path = Path(oficial)

    if alvo_path.exists() and oficial_path.exists():
        return os.path.samefile(alvo_path, oficial_path)

    return alvo_path.resolve(strict=False) == oficial_path.resolve(strict=False)


def schema_minimo_valido(caminho: str) -> bool:
    """Confirma que um SQLite existente e um banco utilizavel pelo sistema."""
    banco = Path(caminho)
    if not banco.is_file():
        return False

    try:
        conn = sqlite3.connect(f"file:{banco.resolve()}?mode=ro", uri=True)
        try:
            tabelas = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return TABELAS_MINIMAS.issubset(tabelas)


def arquivar_invalido(caminho: str) -> Path:
    """Move um banco local incompleto para um nome recuperavel no mesmo local."""
    banco = Path(caminho)
    if not banco.is_file():
        raise FileNotFoundError(caminho)

    sufixo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    arquivado = banco.with_name(f"{banco.stem}.invalido-{sufixo}{banco.suffix}")
    banco.replace(arquivado)
    for extra in ("-wal", "-shm"):
        auxiliar = Path(f"{banco}{extra}")
        if auxiliar.exists():
            auxiliar.replace(Path(f"{arquivado}{extra}"))
    return arquivado


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "--schema":
        return 0 if schema_minimo_valido(args[1]) else 3
    if len(args) == 2 and args[0] == "--arquivar-invalido":
        try:
            print(arquivar_invalido(args[1]))
            return 0
        except OSError:
            return 1
    if len(args) != 2:
        return 1

    try:
        return 2 if mesmo_arquivo(args[0], args[1]) else 0
    except (OSError, RuntimeError, ValueError):
        # Falha fechada: o iniciador deve recusar se nao puder provar o isolamento.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
