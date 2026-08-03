"""Isola a bateria SQLite do banco operacional do repositorio."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path


_ISOLATION_FLAG = "ENDEMIAS_TEST_DB_ISOLATED"
_TEMP_DIR = None


def ensure_isolated_database():
    """Seleciona uma copia temporaria antes que ``app`` seja importado."""
    global _TEMP_DIR

    configured = os.environ.get("ENDEMIAS_DB_PATH")
    if os.environ.get(_ISOLATION_FLAG) == "1" and configured:
        return Path(configured)

    root = Path(__file__).resolve().parents[1]
    source = Path(configured) if configured else root / "endemias.db"
    source = source.resolve()
    if not source.is_file():
        raise RuntimeError(f"Banco SQLite de referencia nao encontrado: {source}")

    _TEMP_DIR = Path(tempfile.mkdtemp(prefix="endemias-testes-"))
    destination = _TEMP_DIR / "endemias_testes.db"
    shutil.copy2(source, destination)

    os.environ["ENDEMIAS_DB_PATH"] = str(destination)
    os.environ["ENDEMIAS_DB_BACKEND"] = "sqlite"
    os.environ[_ISOLATION_FLAG] = "1"

    def cleanup():
        if _TEMP_DIR is not None:
            shutil.rmtree(_TEMP_DIR, ignore_errors=True)

    atexit.register(cleanup)
    return destination


TEST_DB_PATH = ensure_isolated_database()
