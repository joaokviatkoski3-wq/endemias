from pathlib import Path
import os
import shutil
import sys
from datetime import datetime


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import esporotricose
from etl import Logger


def main():
    pasta = ROOT / "ESPOROTRICOSE_PLANILHAS_NOVA_PAGINA"
    banco = ROOT / "endemias.db"
    arquivos = sorted(pasta.glob("ESPOROTRICOSE_2025*.xlsx"))
    if not arquivos:
        raise SystemExit("Nenhuma planilha legada ESPOROTRICOSE_2025*.xlsx encontrada.")

    backups = Path(os.environ.get("ENDEMIAS_BACKUP_DIR", r"D:\BackupsEndemias\backups_banco"))
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backups / f"endemias_pre_esporotricose_historico_{stamp}.db"
    shutil.copy2(banco, backup)
    print(f"Backup criado: {backup}")

    logger = Logger(callback=lambda msg, tag="normal": print(msg))
    total = esporotricose.importar_historico(arquivos, str(banco), logger, dry_run=False)
    print(f"Importacao historica concluida: {total['visitas']} visita(s), {total['animais']} animal(is).")


if __name__ == "__main__":
    main()
