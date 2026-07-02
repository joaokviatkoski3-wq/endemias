import json
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app_core import backup as backup_core


DEFAULT_DESTINO = Path("D:/BackupsEndemias")
ZIP_PREFIXO = "endemias_completo"
IGNORAR_PARTES = {"__pycache__", ".git"}
IGNORAR_SUFIXOS = {".pyc", ".pyo"}


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _zip_name():
    return f"{ZIP_PREFIXO}_{_timestamp()}.zip"


def _iso_mtime(path):
    return datetime.fromtimestamp(Path(path).stat().st_mtime).isoformat(timespec="seconds")


def _zip_write_file(zf, origem, destino):
    origem = Path(origem)
    if origem.is_file():
        zf.write(origem, destino)
        return origem.stat().st_size
    return 0


def _zip_write_tree(zf, origem, destino_base):
    origem = Path(origem)
    total = 0
    arquivos = 0
    if not origem.exists():
        return {"arquivos": 0, "bytes": 0}

    for item in origem.rglob("*"):
        if any(parte in IGNORAR_PARTES for parte in item.parts):
            continue
        if item.suffix.lower() in IGNORAR_SUFIXOS:
            continue
        if not item.is_file():
            continue
        rel = item.relative_to(origem).as_posix()
        total += _zip_write_file(zf, item, f"{destino_base}/{rel}")
        arquivos += 1
    return {"arquivos": arquivos, "bytes": total}


def _limpar_zips_antigos(destino, manter):
    if manter is None:
        return []
    manter = int(manter)
    if manter < 1:
        return []
    arquivos = sorted(
        destino.glob(f"{ZIP_PREFIXO}_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removidos = []
    for antigo in arquivos[manter:]:
        antigo.unlink()
        removidos.append(str(antigo))
    return removidos


def _ler_manifesto_zip(zip_path):
    try:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open("manifesto_backup.json") as f:
                return json.loads(f.read().decode("utf-8"))
    except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile):
        return {}


def listar_backups_completos(destino_dir=DEFAULT_DESTINO, limite=20):
    destino = Path(destino_dir)
    if not destino.exists():
        return []
    arquivos = sorted(
        (p for p in destino.glob(f"{ZIP_PREFIXO}_*.zip") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if limite is not None:
        arquivos = arquivos[: max(1, int(limite or 20))]

    backups = []
    for arquivo in arquivos:
        manifesto = _ler_manifesto_zip(arquivo)
        stat = arquivo.stat()
        backups.append({
            "nome": arquivo.name,
            "arquivo": str(arquivo),
            "tamanho_bytes": stat.st_size,
            "modificado_em": _iso_mtime(arquivo),
            "integridade_banco": manifesto.get("integridade_banco", "nao verificado"),
            "incluidos": manifesto.get("incluidos", []),
            "ausentes": manifesto.get("ausentes", []),
        })
    return backups


def resolver_backup_completo(destino_dir, nome_arquivo):
    destino = Path(destino_dir).resolve()
    nome = Path(nome_arquivo or "").name
    if (
        not nome
        or nome != nome_arquivo
        or not nome.startswith(f"{ZIP_PREFIXO}_")
        or not nome.endswith(".zip")
    ):
        raise ValueError("Backup completo invalido.")

    backup_path = (destino / nome).resolve()
    if os.path.commonpath([str(destino), str(backup_path)]) != str(destino):
        raise ValueError("Backup completo fora da pasta permitida.")
    if not backup_path.exists() or not backup_path.is_file():
        raise FileNotFoundError("Backup completo nao encontrado.")
    return backup_path


def excluir_backup_completo(backup_path):
    arquivo = Path(backup_path)
    if not arquivo.exists() or not arquivo.is_file():
        raise FileNotFoundError("Backup completo nao encontrado.")
    arquivo.unlink()
    return {"arquivo": str(arquivo)}


def criar_backup_completo(
    destino_dir=DEFAULT_DESTINO,
    manter=10,
    db_path=None,
    raiz=None,
    anexos_dir=None,
    kobo_config_path=None,
    secret_key_path=None,
):
    destino = Path(destino_dir)
    destino.mkdir(parents=True, exist_ok=True)
    raiz = Path(raiz or Path.cwd())
    db_path = Path(db_path or raiz / "endemias.db")
    zip_path = destino / _zip_name()

    arquivos_locais = [
        (Path(secret_key_path or raiz / "secret.key"), "configuracao/secret.key"),
        (Path(kobo_config_path or raiz / "kobo_config.json"), "configuracao/kobo_config.json"),
        (raiz / "queries.sql", "configuracao/queries.sql"),
    ]
    pastas_locais = [
        (Path(anexos_dir or raiz / "anexos"), "anexos"),
        (raiz / "notificacoes_geradas", "notificacoes_geradas"),
        (raiz / "saida", "saida"),
    ]

    manifesto = {
        "tipo": "backup_completo_endemias",
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "origem": str(raiz),
        "banco_origem": str(db_path),
        "destino": str(zip_path),
        "incluidos": [],
        "ausentes": [],
        "integridade_banco": "nao verificado",
    }

    with tempfile.TemporaryDirectory(prefix="endemias_backup_") as tmp:
        tmp_dir = Path(tmp)
        banco_info = backup_core.criar_backup_sqlite(
            db_path,
            destino_dir=tmp_dir,
            prefixo="endemias",
            manter=None,
            validar=True,
        )
        banco_backup = Path(banco_info["arquivo"])
        banco_meta = banco_backup.with_suffix(banco_backup.suffix + ".json")
        manifesto["integridade_banco"] = banco_info.get("integridade")

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            tamanho = _zip_write_file(zf, banco_backup, f"banco/{banco_backup.name}")
            manifesto["incluidos"].append({
                "tipo": "arquivo",
                "origem": str(db_path),
                "destino_zip": f"banco/{banco_backup.name}",
                "bytes": tamanho,
                "observacao": "Backup SQLite consistente e validado",
            })
            if banco_meta.exists():
                _zip_write_file(zf, banco_meta, f"banco/{banco_meta.name}")

            for origem, destino_zip in arquivos_locais:
                if origem.exists():
                    tamanho = _zip_write_file(zf, origem, destino_zip)
                    manifesto["incluidos"].append({
                        "tipo": "arquivo",
                        "origem": str(origem),
                        "destino_zip": destino_zip,
                        "bytes": tamanho,
                    })
                else:
                    manifesto["ausentes"].append(str(origem))

            for origem, destino_zip in pastas_locais:
                if origem.exists():
                    info = _zip_write_tree(zf, origem, destino_zip)
                    manifesto["incluidos"].append({
                        "tipo": "pasta",
                        "origem": str(origem),
                        "destino_zip": destino_zip,
                        **info,
                    })
                else:
                    manifesto["ausentes"].append(str(origem))

            restauracao = (
                "Backup completo do Sistema Endemias\n\n"
                "Conteudo principal:\n"
                "- banco/: copia consistente e validada do endemias.db\n"
                "- anexos/: arquivos anexados no sistema\n"
                "- configuracao/: chaves e configuracoes locais sensiveis\n"
                "- notificacoes_geradas/ e saida/: arquivos gerados/exportados\n\n"
                "Para restaurar, procure suporte tecnico antes de substituir arquivos em uso.\n"
                "Nunca envie este ZIP para repositorios publicos, pois ele contem dados reais e segredos locais.\n"
            )
            zf.writestr("LEIA_RESTAURACAO.txt", restauracao)
            zf.writestr("manifesto_backup.json", json.dumps(manifesto, ensure_ascii=False, indent=2))

    removidos = _limpar_zips_antigos(destino, manter)
    return {
        "arquivo": str(zip_path),
        "nome": zip_path.name,
        "tamanho_bytes": zip_path.stat().st_size,
        "integridade_banco": manifesto["integridade_banco"],
        "removidos": removidos,
        "manifesto": manifesto,
    }
