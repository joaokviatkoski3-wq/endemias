import json
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


_operacao_lock = threading.Lock()


@contextmanager
def operacao_exclusiva():
    adquirido = _operacao_lock.acquire(blocking=False)
    if not adquirido:
        raise RuntimeError("Outra operacao de banco esta em andamento. Aguarde concluir e tente novamente.")
    try:
        yield
    finally:
        _operacao_lock.release()


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


def listar_backups(destino_dir, limite=5):
    destino = Path(destino_dir)
    if not destino.exists():
        return []

    arquivos = sorted(
        (p for p in destino.glob("*.db") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if limite is None:
        selecionados = arquivos
    else:
        selecionados = arquivos[: max(1, int(limite or 5))]
    backups = []
    for arquivo in selecionados:
        stat = arquivo.stat()
        meta = {}
        meta_path = arquivo.with_suffix(arquivo.suffix + ".json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        backups.append({
            "arquivo": str(arquivo),
            "nome": arquivo.name,
            "tamanho_bytes": stat.st_size,
            "modificado_em": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "integridade": meta.get("integridade", "nao verificado"),
            "validado": meta.get("validado"),
        })
    return backups


def resolver_backup(destino_dir, nome_arquivo):
    destino = Path(destino_dir).resolve()
    nome = Path(nome_arquivo or "").name
    if not nome or nome != nome_arquivo or not nome.endswith(".db"):
        raise ValueError("Backup invalido.")

    backup_path = (destino / nome).resolve()
    if os.path.commonpath([str(destino), str(backup_path)]) != str(destino):
        raise ValueError("Backup fora da pasta permitida.")
    if not backup_path.exists() or not backup_path.is_file():
        raise FileNotFoundError("Backup nao encontrado.")
    return backup_path


def excluir_backup(backup_path):
    arquivo = Path(backup_path)
    if not arquivo.exists() or not arquivo.is_file():
        raise FileNotFoundError("Backup nao encontrado.")
    meta = arquivo.with_suffix(arquivo.suffix + ".json")
    arquivo.unlink()
    if meta.exists():
        meta.unlink()
    return {"arquivo": str(arquivo), "meta_removido": not meta.exists()}


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


def restaurar_backup_sqlite(db_path, backup_path, validar=True):
    destino = Path(db_path)
    origem = Path(backup_path)
    if not origem.exists():
        raise FileNotFoundError(f"Backup nao encontrado: {origem}")

    if validar:
        valido, integridade = validar_backup(origem)
        if not valido:
            raise RuntimeError(f"Backup invalido: integrity_check retornou {integridade!r}")
    else:
        integridade = "nao verificado"

    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        conn = sqlite3.connect(str(destino))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()

    temporario = destino.with_name(f".{destino.name}.restore.tmp")
    shutil.copy2(origem, temporario)
    try:
        if validar:
            valido_tmp, integridade_tmp = validar_backup(temporario)
            if not valido_tmp:
                raise RuntimeError(f"Copia de restauracao invalida: {integridade_tmp!r}")
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)

    for sufixo in ("-wal", "-shm"):
        Path(str(destino) + sufixo).unlink(missing_ok=True)

    return {
        "arquivo": str(origem),
        "destino": str(destino),
        "integridade": integridade,
        "restaurado_em": datetime.now().isoformat(),
    }
