"""Backup e restauracao PostgreSQL por ferramentas oficiais do servidor."""

import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from app_core import backup as backup_core
from app_core import postgresql


BACKUP_SUFFIX = ".dump"
DEFAULT_TIMEOUT_SECONDS = 1800


def _timestamp(agora=None):
    return (agora or datetime.now()).strftime("%Y%m%d_%H%M%S")


def _prefixo_seguro(prefixo):
    return "".join(
        char if char.isalnum() or char in ("-", "_") else "_"
        for char in str(prefixo or "")
    ).strip("_")


def _nome_backup(prefixo, agora=None):
    return f"{_prefixo_seguro(prefixo) or 'endemias'}_{_timestamp(agora)}{BACKUP_SUFFIX}"


def _caminho_disponivel(destino, nome):
    caminho = Path(destino) / nome
    if not caminho.exists():
        return caminho
    for numero in range(1, 1000):
        candidato = caminho.with_name(
            f"{caminho.stem}_{numero:02d}{caminho.suffix}"
        )
        if not candidato.exists():
            return candidato
    raise RuntimeError("Nao foi possivel reservar um nome para o backup PostgreSQL.")


def _executavel(nome, env=None):
    env = os.environ if env is None else env
    variavel = {
        "pg_dump": "ENDEMIAS_PG_DUMP",
        "pg_restore": "ENDEMIAS_PG_RESTORE",
    }[nome]
    explicito = env.get(variavel)
    if explicito:
        caminho = Path(explicito).expanduser()
        if caminho.is_file():
            return str(caminho.resolve())
        raise FileNotFoundError(
            f"Executavel configurado em {variavel} nao foi encontrado."
        )

    pg_bin = env.get("ENDEMIAS_PG_BIN")
    if pg_bin:
        caminho = Path(pg_bin) / f"{nome}.exe"
        if caminho.is_file():
            return str(caminho.resolve())
        raise FileNotFoundError(
            f"{nome}.exe nao foi encontrado em ENDEMIAS_PG_BIN."
        )

    encontrado = shutil.which(nome, path=env.get("PATH"))
    if encontrado:
        return str(Path(encontrado).resolve())

    program_files = Path(env.get("ProgramFiles", r"C:\Program Files"))
    postgres_root = program_files / "PostgreSQL"
    def versao_instalada(caminho):
        partes = caminho.parents[1].name.split(".")
        return tuple(int(parte) if parte.isdigit() else 0 for parte in partes)

    candidatos = sorted(
        postgres_root.glob(f"*/bin/{nome}.exe"),
        key=versao_instalada,
        reverse=True,
    ) if postgres_root.exists() else []
    if candidatos:
        return str(candidatos[0].resolve())
    raise FileNotFoundError(
        f"{nome} nao foi encontrado. Configure ENDEMIAS_PG_BIN."
    )


def _comando_conexao(executavel, database, env=None):
    params = postgresql.connection_parameters(database=database, env=env)
    return [
        executavel,
        "--no-password",
        "--host",
        str(params["host"]),
        "--port",
        str(params["port"]),
        "--username",
        str(params["user"]),
        "--dbname",
        str(params["dbname"]),
    ]


def _ambiente_libpq(database, env=None):
    source = os.environ if env is None else env
    process_env = dict(os.environ)
    process_env.update(source)
    params = postgresql.connection_parameters(database=database, env=source)
    process_env.update({
        "PGHOST": str(params["host"]),
        "PGPORT": str(params["port"]),
        "PGUSER": str(params["user"]),
        "PGDATABASE": str(params["dbname"]),
        "PGSSLMODE": str(params["sslmode"]),
        "PGAPPNAME": str(params["application_name"]),
    })
    return process_env


def _executar(args, env=None, timeout=DEFAULT_TIMEOUT_SECONDS):
    process_env = dict(os.environ)
    if env is not None:
        process_env.update(env)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=process_env,
            timeout=timeout,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("A operacao PostgreSQL excedeu o tempo limite.") from exc
    except subprocess.CalledProcessError as exc:
        detalhe = (exc.stderr or exc.stdout or "falha sem detalhe").strip()
        if len(detalhe) > 1200:
            detalhe = detalhe[-1200:]
        raise RuntimeError(f"A ferramenta PostgreSQL falhou: {detalhe}") from exc


def _validar_catalogo(arquivo, env=None):
    arquivo = Path(arquivo)
    if not arquivo.is_file():
        raise FileNotFoundError("Backup PostgreSQL nao encontrado.")
    if arquivo.stat().st_size <= 0:
        raise RuntimeError("Backup PostgreSQL vazio.")
    restore = _executavel("pg_restore", env=env)
    resultado = _executar([restore, "--list", str(arquivo)], env=env)
    if not (resultado.stdout or "").strip():
        raise RuntimeError("pg_restore nao encontrou objetos no backup.")
    return True, "catalogo validado"


def validar_backup(backup_path, env=None):
    arquivo = Path(backup_path)
    if arquivo.suffix.lower() != BACKUP_SUFFIX:
        raise ValueError("Backup PostgreSQL invalido.")
    return _validar_catalogo(arquivo, env=env)


def _escrever_metadados(backup_path, info):
    meta_path = Path(backup_path).with_suffix(Path(backup_path).suffix + ".json")
    temporario = meta_path.with_name(f".{meta_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporario.write_text(
            json.dumps(info, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporario, meta_path)
    finally:
        temporario.unlink(missing_ok=True)


def _ler_metadados(backup_path):
    meta_path = Path(backup_path).with_suffix(Path(backup_path).suffix + ".json")
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def limpar_backups_antigos(destino_dir, manter=20, prefixo="endemias"):
    if manter is None or int(manter) < 1:
        return []
    arquivos = sorted(
        Path(destino_dir).glob(
            f"{_prefixo_seguro(prefixo) or 'endemias'}_*{BACKUP_SUFFIX}"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removidos = []
    for antigo in arquivos[int(manter):]:
        backup_core.excluir_backup(antigo)
        removidos.append(antigo)
    return removidos


def criar_backup_postgresql(
    database,
    destino_dir,
    prefixo="endemias",
    manter=20,
    agora=None,
    env=None,
):
    destino = Path(destino_dir)
    destino.mkdir(parents=True, exist_ok=True)
    backup_path = _caminho_disponivel(destino, _nome_backup(prefixo, agora))
    temporario = destino / f".{backup_path.name}.{uuid.uuid4().hex}.tmp"
    process_env = _ambiente_libpq(database, env=env)
    dump = _executavel("pg_dump", env=process_env)
    comando = _comando_conexao(dump, database, env=env)
    comando.extend([
        "--format=custom",
        "--compress=6",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(temporario),
    ])
    try:
        _executar(comando, env=process_env)
        _validar_catalogo(temporario, env=process_env)
        tamanho = temporario.stat().st_size
        sha256 = backup_core.calcular_sha256(temporario)
        os.replace(temporario, backup_path)
        info = {
            "arquivo": str(backup_path),
            "origem": postgresql.connection_summary(database=database, env=env),
            "backend": "postgresql",
            "tamanho_bytes": tamanho,
            "integridade": "catalogo validado",
            "validado": True,
            "sha256": sha256,
            "criado_em": datetime.now().isoformat(timespec="seconds"),
        }
        _escrever_metadados(backup_path, info)
        removidos = limpar_backups_antigos(
            destino,
            manter=manter,
            prefixo=prefixo,
        )
        info["removidos"] = [str(path) for path in removidos]
        return info
    finally:
        temporario.unlink(missing_ok=True)


def listar_backups(destino_dir, limite=20):
    destino = Path(destino_dir)
    if not destino.exists():
        return []
    arquivos = sorted(
        (path for path in destino.glob(f"*{BACKUP_SUFFIX}") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if limite is not None:
        arquivos = arquivos[:max(1, int(limite or 20))]
    resultado = []
    for arquivo in arquivos:
        meta = _ler_metadados(arquivo)
        resultado.append({
            "arquivo": str(arquivo),
            "nome": arquivo.name,
            "tamanho_bytes": arquivo.stat().st_size,
            "modificado_em": datetime.fromtimestamp(
                arquivo.stat().st_mtime
            ).isoformat(),
            "integridade": meta.get("integridade", "nao verificado"),
            "validado": meta.get("validado"),
            "sha256": meta.get("sha256"),
            "backend": "postgresql",
        })
    return resultado


def resolver_backup(destino_dir, nome_arquivo):
    destino = Path(destino_dir).resolve()
    nome = Path(nome_arquivo or "").name
    if not nome or nome != nome_arquivo or not nome.endswith(BACKUP_SUFFIX):
        raise ValueError("Backup PostgreSQL invalido.")
    caminho = (destino / nome).resolve()
    if os.path.commonpath([str(destino), str(caminho)]) != str(destino):
        raise ValueError("Backup fora da pasta permitida.")
    if not caminho.is_file():
        raise FileNotFoundError("Backup PostgreSQL nao encontrado.")
    return caminho


def restaurar_backup_postgresql(
    database,
    backup_path,
    confirmacao,
    backup_dir,
    manter=20,
    env=None,
):
    if str(confirmacao or "").strip() != str(database):
        raise ValueError(
            "Confirme o nome exato do banco PostgreSQL antes de restaurar."
        )
    arquivo = Path(backup_path)
    validar_backup(arquivo, env=env)
    meta = _ler_metadados(arquivo)
    origem = meta.get("origem") or {}
    banco_origem = origem.get("database") if isinstance(origem, dict) else None
    if banco_origem and banco_origem != str(database):
        raise ValueError(
            "O backup pertence a outro banco PostgreSQL e nao pode ser "
            "restaurado pela Central."
        )
    hash_esperado = meta.get("sha256")
    hash_atual = backup_core.calcular_sha256(arquivo)
    if hash_esperado and hash_atual != hash_esperado:
        raise RuntimeError("Backup alterado ou corrompido: hash SHA-256 divergente.")

    seguranca = criar_backup_postgresql(
        database,
        backup_dir,
        prefixo="pre_restore",
        manter=manter,
        env=env,
    )
    process_env = _ambiente_libpq(database, env=env)
    restore = _executavel("pg_restore", env=process_env)
    comando = _comando_conexao(restore, database, env=env)
    comando.extend([
        "--clean",
        "--if-exists",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-privileges",
        str(arquivo),
    ])
    _executar(comando, env=process_env)
    postgresql.probe(database=database, env=env, write_test=False)
    return {
        "arquivo": str(arquivo),
        "destino": str(database),
        "integridade": "catalogo validado",
        "sha256": hash_atual,
        "backup_seguranca": Path(seguranca["arquivo"]).name,
        "restaurado_em": datetime.now().isoformat(timespec="seconds"),
    }
