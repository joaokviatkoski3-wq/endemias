"""Copia somente o runtime Python padrao para a instalacao web dedicada.

Nao copia site-packages do usuario, nao toca no Python compartilhado e nao
cria conta/tarefa. Executar antes de aplicar as permissoes do servidor web.
"""

from pathlib import Path
import shutil
import subprocess
import sys


HOME = Path(r"C:\ProgramData\EndemiasWeb")


def main():
    source = Path(sys.base_prefix)
    destination = HOME / "base-python"
    if destination.exists() or source == destination:
        raise ValueError("Runtime dedicado ja existe; nao sobrescrever uma instalacao ativa.")
    destination.mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file() and (path.suffix.lower() in {".exe", ".dll"} or path.name == "LICENSE.txt"):
            shutil.copy2(path, destination / path.name)
    shutil.copytree(source / "Lib", destination / "Lib", ignore=shutil.ignore_patterns("site-packages", "__pycache__"))
    shutil.copytree(source / "DLLs", destination / "DLLs")
    binary = destination / "python.exe"
    subprocess.run([str(binary), "-I", "-c", "import ssl,sqlite3,ctypes,venv; print('Runtime Python padrao conferido')"], check=True)
    subprocess.run([str(binary), "-I", "-m", "venv", "--upgrade", str(HOME / "python")], check=True)
    expected = subprocess.check_output([str(HOME / "python/Scripts/python.exe"), "-I", "-c", "import sys; print(sys.base_prefix)"], text=True).strip()
    if Path(expected).resolve() != destination:
        raise RuntimeError("Ambiente dedicado ainda aponta para outro Python.")
    print("Python web independente do perfil do usuario; nenhuma conta/tarefa alterada.")


if __name__ == "__main__":
    main()
