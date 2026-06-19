# Limpeza Diária — Sistema Endemias
import argparse
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as endemias_app
from app_core import backup as backup_core


def limpar_uploads_temp(upload_dir, max_age_hours=24):
    """Remove pastas de upload temporárias com mais de X horas."""
    if not os.path.isdir(upload_dir):
        return 0
    cutoff = time.time() - (max_age_hours * 3600)
    removidos = 0
    for entry in os.scandir(upload_dir):
        if not entry.is_dir():
            continue
        if entry.stat().st_mtime < cutoff:
            try:
                import shutil
                shutil.rmtree(entry.path)
                removidos += 1
            except Exception:
                pass
    return removidos


def limpar_logs(log_path, max_size_mb=50):
    """Trunca log se ultrapassar tamanho máximo."""
    if not os.path.exists(log_path):
        return False
    size_mb = os.path.getsize(log_path) / (1024 * 1024)
    if size_mb > max_size_mb:
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"# Log truncado em {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            return True
        except Exception:
            pass
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Limpeza diária de arquivos temporários do Endemias.")
    parser.add_argument("--upload-dir", default=endemias_app.UPLOAD_TEMP, help="Pasta de uploads temporários.")
    parser.add_argument("--backup-dir", default=None, help="Pasta de backups (padrão: backups/ ao lado do banco).")
    parser.add_argument("--log-path", default=endemias_app.LOG_PATH, help="Caminho do log.")
    parser.add_argument("--manter-backups", type=int, default=20, help="Quantidade de backups a manter.")
    parser.add_argument("--upload-horas", type=int, default=24, help="Idade máxima de uploads temporários (horas).")
    parser.add_argument("--log-mb", type=int, default=50, help="Tamanho máximo do log (MB).")
    args = parser.parse_args(argv)

    backup_dir = args.backup_dir or os.path.join(os.path.dirname(endemias_app.DB_PATH), "backups")

    print("=== Limpeza Diária — Endemias ===")
    print(f"Iniciada em: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Limpar uploads temporários
    removidos = limpar_uploads_temp(args.upload_dir, args.upload_horas)
    print(f"Uploads temporários removidos: {removidos}")

    # Limpar backups antigos
    removidos_backups = backup_core.limpar_backups_antigos(backup_dir, manter=args.manter_backups, padrao="*.db")
    print(f"Backups antigos removidos: {len(removidos_backups)}")
    for b in removidos_backups:
        print(f"  - {b.name}")

    # Truncar log se muito grande
    truncado = limpar_logs(args.log_path, args.log_mb)
    if truncado:
        print(f"Log truncado (ultrapassava {args.log_mb} MB)")
    else:
        print("Log dentro do limite de tamanho.")

    print("Limpeza concluída.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
