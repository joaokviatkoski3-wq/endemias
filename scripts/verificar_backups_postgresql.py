import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import backup as backup_core
from app_core import backup_completo
from app_core import postgresql_backup


DEFAULT_BACKUP_DIR = Path(r"D:\BackupsEndemias\backups_banco")
DEFAULT_COMPLETE_DIR = Path(r"D:\BackupsEndemias\backups_completos")


def _idade_horas(path, agora):
    modificado = datetime.fromtimestamp(Path(path).stat().st_mtime)
    return max(0.0, (agora - modificado).total_seconds() / 3600)


def verificar_dump(
    destino,
    database="endemias",
    max_horas=36,
    agora=None,
    env=None,
):
    agora = agora or datetime.now()
    backups = postgresql_backup.listar_backups(destino, limite=1)
    if not backups:
        raise RuntimeError("Nenhum dump PostgreSQL foi encontrado.")

    info = backups[0]
    arquivo = Path(info["arquivo"])
    origem = info.get("origem") or {}
    if origem.get("database") != database:
        raise RuntimeError(
            "O dump mais recente pertence a outro banco PostgreSQL."
        )
    if info.get("validado") is not True or not info.get("sha256"):
        raise RuntimeError("O dump mais recente nao possui metadados validados.")
    hash_atual = backup_core.calcular_sha256(arquivo)
    if hash_atual != info["sha256"]:
        raise RuntimeError("O dump mais recente falhou na verificacao SHA-256.")
    postgresql_backup.validar_backup(arquivo, env=env)
    idade = _idade_horas(arquivo, agora)
    if idade > float(max_horas):
        raise RuntimeError(
            f"O dump PostgreSQL mais recente tem {idade:.1f} horas."
        )
    return {
        "arquivo": str(arquivo),
        "idade_horas": round(idade, 2),
        "tamanho_bytes": arquivo.stat().st_size,
        "sha256": hash_atual,
        "integridade": "catalogo e SHA-256 validados",
    }


def _manifesto_postgresql(zip_path, database):
    try:
        with zipfile.ZipFile(zip_path) as zf:
            corrompido = zf.testzip()
            if corrompido:
                raise RuntimeError(
                    f"O backup completo esta corrompido em {corrompido}."
                )
            manifesto = json.loads(
                zf.read("manifesto_backup.json").decode("utf-8")
            )
            if manifesto.get("backend_banco") != "postgresql":
                return None
            if manifesto.get("banco_origem") != database:
                return None
            if manifesto.get("integridade_banco") != "catalogo validado":
                raise RuntimeError(
                    "O backup completo PostgreSQL nao registra catalogo validado."
                )
            dumps = [
                item
                for item in manifesto.get("incluidos", [])
                if item.get("destino_zip", "").startswith("banco/")
                and item.get("destino_zip", "").endswith(".dump")
            ]
            if len(dumps) != 1 or not dumps[0].get("sha256"):
                raise RuntimeError(
                    "O backup completo nao possui um dump PostgreSQL identificavel."
                )
            item = dumps[0]
            digest = hashlib.sha256()
            with zf.open(item["destino_zip"]) as stream:
                for bloco in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(bloco)
            if digest.hexdigest() != item["sha256"]:
                raise RuntimeError(
                    "O dump interno do backup completo diverge do SHA-256."
                )
            return manifesto
    except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise RuntimeError("Backup completo PostgreSQL invalido.") from exc


def verificar_backup_completo(
    destino,
    database="endemias",
    max_dias=8,
    agora=None,
):
    agora = agora or datetime.now()
    candidatos = backup_completo.listar_backups_completos(destino, limite=None)
    for info in candidatos:
        arquivo = Path(info["arquivo"])
        manifesto = _manifesto_postgresql(arquivo, database)
        if manifesto is None:
            continue
        idade = _idade_horas(arquivo, agora)
        if idade > float(max_dias) * 24:
            raise RuntimeError(
                f"O backup completo PostgreSQL mais recente tem {idade / 24:.1f} dias."
            )
        return {
            "arquivo": str(arquivo),
            "idade_dias": round(idade / 24, 2),
            "tamanho_bytes": arquivo.stat().st_size,
            "integridade": "ZIP, manifesto e SHA-256 interno validados",
        }
    raise RuntimeError("Nenhum backup completo PostgreSQL foi encontrado.")


def verificar_tudo(
    backup_dir=DEFAULT_BACKUP_DIR,
    complete_dir=DEFAULT_COMPLETE_DIR,
    database="endemias",
    max_dump_horas=36,
    max_completo_dias=8,
    agora=None,
    env=None,
):
    return {
        "verificado_em": (agora or datetime.now()).isoformat(timespec="seconds"),
        "dump": verificar_dump(
            backup_dir,
            database=database,
            max_horas=max_dump_horas,
            agora=agora,
            env=env,
        ),
        "completo": verificar_backup_completo(
            complete_dir,
            database=database,
            max_dias=max_completo_dias,
            agora=agora,
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Valida os backups PostgreSQL recentes sem conectar ao banco."
    )
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--completo-dir", default=str(DEFAULT_COMPLETE_DIR))
    parser.add_argument("--database", default="endemias")
    parser.add_argument("--max-dump-horas", type=float, default=36)
    parser.add_argument("--max-completo-dias", type=float, default=8)
    parser.add_argument("--pg-bin")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.max_dump_horas <= 0 or args.max_completo_dias <= 0:
        parser.error("Os limites de idade devem ser maiores que zero.")

    env = dict(os.environ)
    if args.pg_bin:
        env["ENDEMIAS_PG_BIN"] = str(Path(args.pg_bin).resolve())
    try:
        resultado = verificar_tudo(
            backup_dir=args.backup_dir,
            complete_dir=args.completo_dir,
            database=args.database,
            max_dump_horas=args.max_dump_horas,
            max_completo_dias=args.max_completo_dias,
            env=env,
        )
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print("Backups PostgreSQL validados.")
        print(f"Dump: {resultado['dump']['arquivo']}")
        print(f"Backup completo: {resultado['completo']['arquivo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
