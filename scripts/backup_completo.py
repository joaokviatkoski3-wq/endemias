import argparse
import json
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as endemias_app
from app_core import backup as backup_core


DEFAULT_DESTINO = Path("D:/BackupsEndemias")
ZIP_PREFIXO = "endemias_completo"

ARQUIVOS_LOCAIS = [
    ("secret.key", "configuracao/secret.key"),
    ("kobo_config.json", "configuracao/kobo_config.json"),
    ("queries.sql", "configuracao/queries.sql"),
]

PASTAS_LOCAIS = [
    ("anexos", "anexos"),
    ("notificacoes_geradas", "notificacoes_geradas"),
    ("saida", "saida"),
]

IGNORAR_PARTES = {"__pycache__", ".git"}
IGNORAR_SUFIXOS = {".pyc", ".pyo"}


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _zip_name():
    return f"{ZIP_PREFIXO}_{_timestamp()}.zip"


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


def criar_backup_completo(destino_dir=DEFAULT_DESTINO, manter=10, db_path=None):
    destino = Path(destino_dir)
    destino.mkdir(parents=True, exist_ok=True)

    db_path = Path(db_path or endemias_app.DB_PATH)
    zip_path = destino / _zip_name()
    manifesto = {
        "tipo": "backup_completo_endemias",
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "origem": str(ROOT),
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

            for origem_rel, destino_zip in ARQUIVOS_LOCAIS:
                origem = ROOT / origem_rel
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

            for origem_rel, destino_zip in PASTAS_LOCAIS:
                origem = ROOT / origem_rel
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
    info_final = {
        "arquivo": str(zip_path),
        "tamanho_bytes": zip_path.stat().st_size,
        "integridade_banco": manifesto["integridade_banco"],
        "removidos": removidos,
        "manifesto": manifesto,
    }
    return info_final


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gera backup completo local do Sistema Endemias.")
    parser.add_argument("--destino", default=str(DEFAULT_DESTINO), help="Pasta de destino dos ZIPs.")
    parser.add_argument("--manter", type=int, default=10, help="Quantidade de backups completos a manter.")
    parser.add_argument("--db", default=endemias_app.DB_PATH, help="Caminho do banco de origem.")
    args = parser.parse_args(argv)

    info = criar_backup_completo(args.destino, manter=args.manter, db_path=args.db)
    print(f"Backup completo criado: {info['arquivo']}")
    print(f"Tamanho: {info['tamanho_bytes']} bytes")
    print(f"Integridade do banco: {info['integridade_banco']}")
    if info["removidos"]:
        print(f"Backups completos antigos removidos: {len(info['removidos'])}")
    print("Destino pronto para copiar para HD externo, nuvem ou outro local seguro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
