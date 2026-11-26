"""Ativa o GeoVSATT na instalação oficial, com as migrações aditivas."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ativar_interface_setores_windows import main


if __name__ == "__main__":
    raise SystemExit(main(
        origin="2.15.2",
        target="2.16.0",
        marker="ativacao-geovsatt2160",
        migration=("0046_geovsatt_setor.sql", "0047_geovsatt_catalogo.sql"),
        geo=True,
    ))
