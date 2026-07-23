import hashlib
import json
import os
import shutil
import sqlite3
import threading
import uuid
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
    seguro = _prefixo_seguro(prefixo)
    return f"{seguro or 'endemias'}_{_timestamp(agora)}.db"


def _prefixo_seguro(prefixo):
    return "".join(
        c if c.isalnum() or c in ("-", "_") else "_"
        for c in str(prefixo or "")
    ).strip("_")


def _caminho_disponivel(destino, nome):
    caminho = Path(destino) / nome
    if not caminho.exists():
        return caminho
    for numero in range(1, 1000):
        candidato = caminho.with_name(f"{caminho.stem}_{numero:02d}{caminho.suffix}")
        if not candidato.exists():
            return candidato
    raise RuntimeError("Nao foi possivel reservar um nome para o backup.")


def calcular_sha256(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(chunk_size), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _ler_metadados(backup_path):
    meta_path = Path(backup_path).with_suffix(Path(backup_path).suffix + ".json")
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


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
        meta = _ler_metadados(arquivo)
        backups.append({
            "arquivo": str(arquivo),
            "nome": arquivo.name,
            "tamanho_bytes": stat.st_size,
            "modificado_em": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "integridade": meta.get("integridade", "nao verificado"),
            "validado": meta.get("validado"),
            "sha256": meta.get("sha256"),
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
    backup_path = _caminho_disponivel(destino, _backup_name(prefixo, agora))
    temporario = destino / f".{backup_path.name}.{uuid.uuid4().hex}.tmp"

    try:
        origem_conn = sqlite3.connect(str(origem), timeout=30)
        try:
            origem_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            backup_conn = sqlite3.connect(str(temporario))
            try:
                origem_conn.backup(backup_conn)
            finally:
                backup_conn.close()
        finally:
            origem_conn.close()

        valido = True
        integridade = "nao verificado"
        if validar:
            valido, integridade = validar_backup(temporario)
            if not valido:
                raise RuntimeError(
                    f"Backup invalido: integrity_check retornou {integridade!r}"
                )

        tamanho_bytes = temporario.stat().st_size
        sha256 = calcular_sha256(temporario)
        os.replace(temporario, backup_path)
        removidos = limpar_backups_antigos(
            destino,
            manter=manter,
            padrao=f"{_prefixo_seguro(prefixo) or 'endemias'}_*.db",
        )
        info = {
            "arquivo": str(backup_path),
            "origem": str(origem),
            "tamanho_bytes": tamanho_bytes,
            "integridade": integridade,
            "validado": valido,
            "sha256": sha256,
            "removidos": [str(p) for p in removidos],
            "criado_em": datetime.now().isoformat(),
        }

        meta_path = backup_path.with_suffix(backup_path.suffix + ".json")
        meta_temp = meta_path.with_name(f".{meta_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            meta_temp.write_text(
                json.dumps(info, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(meta_temp, meta_path)
        finally:
            meta_temp.unlink(missing_ok=True)
        return info
    finally:
        temporario.unlink(missing_ok=True)


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

    meta = _ler_metadados(origem)
    hash_esperado = meta.get("sha256")
    hash_calculado = calcular_sha256(origem) if hash_esperado else None
    if hash_esperado and hash_calculado != hash_esperado:
        raise RuntimeError("Backup alterado ou corrompido: hash SHA-256 divergente.")

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
        "sha256": hash_calculado,
        "restaurado_em": datetime.now().isoformat(),
    }
