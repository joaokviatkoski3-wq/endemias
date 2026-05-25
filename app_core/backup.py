import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _timestamp(agora=None):
    agora = agora or datetime.now()
    return agora.strftime("%Y%m%d_%H%M%S")


def _backup_name(prefixo, agora=None):
    seguro = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in prefixo).strip("_")
    return f"{seguro or 'endemias'}_{_timestamp(agora)}.db"


def validar_backup(db_path):
    conn = sqlite3.connect(db_path)
    try:
        resultado = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    return resultado == "ok", resultado


def limpar_backups_antigos(destino_dir, manter=10, padrao="*.db"):
    if manter is None:
        return []
    manter = int(manter)
    if manter < 1:
        return []

    destino = Path(destino_dir)
    arquivos = sorted(
        (p for p in destino.glob(padrao) if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removidos = []
    for antigo in arquivos[manter:]:
        antigo.unlink()
        meta = antigo.with_suffix(antigo.suffix + ".json")
        if meta.exists():
            meta.unlink()
        removidos.append(antigo)
    return removidos


def criar_backup_sqlite(db_path, destino_dir=None, prefixo="endemias", manter=10, validar=True, agora=None):
    origem = Path(db_path)
    if not origem.exists():
        raise FileNotFoundError(f"Banco nao encontrado: {origem}")

    destino = Path(destino_dir) if destino_dir else origem.parent / "backups"
    destino.mkdir(parents=True, exist_ok=True)
    backup_path = destino / _backup_name(prefixo, agora)

    origem_conn = sqlite3.connect(str(origem))
    try:
        origem_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        backup_conn = sqlite3.connect(str(backup_path))
        try:
            origem_conn.backup(backup_conn)
        finally:
            backup_conn.close()
    finally:
        origem_conn.close()

    valido = True
    integridade = "nao verificado"
    if validar:
        valido, integridade = validar_backup(backup_path)
        if not valido:
            backup_path.unlink(missing_ok=True)
            raise RuntimeError(f"Backup invalido: integrity_check retornou {integridade!r}")

    removidos = limpar_backups_antigos(destino, manter=manter, padrao=f"{prefixo}_*.db")
    info = {
        "arquivo": str(backup_path),
        "origem": str(origem),
        "tamanho_bytes": backup_path.stat().st_size,
        "integridade": integridade,
        "validado": valido,
        "removidos": [str(p) for p in removidos],
        "criado_em": datetime.now().isoformat(),
    }

    meta_path = backup_path.with_suffix(backup_path.suffix + ".json")
    meta_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info
