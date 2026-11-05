"""Entrada nativa da tarefa limitada; configuracao privada, sem PowerShell.

Nao cria contas, altera permissoes ou migra bancos. O instalador copia este
arquivo para um diretorio protegido antes de registrar a tarefa.
"""

import argparse
import csv
import ctypes
import json
import logging
import logging.handlers
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import traceback


def identity_sid():
    result = subprocess.run(
        [str(Path(os.environ["SystemRoot"]) / "System32/whoami.exe"), "/user", "/fo", "csv", "/nh"],
        capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return next(csv.reader([result.stdout.decode("mbcs").strip()]))[-1]


def configure(config):
    if identity_sid() != config["sid"] or ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Identidade do servidor diferente da conta limitada configurada.")
    root = Path(config["root"])
    if root.resolve() != Path(r"C:\endemias") or not (root / "secret.key").is_file():
        raise RuntimeError("Diretorio oficial ou chave existente nao conferem.")
    for name in list(os.environ):
        if name.startswith(("ENDEMIAS_", "PG", "PYTHON")):
            os.environ.pop(name, None)
    os.environ.update(config["env"])
    os.chdir(root)
    sys.path.insert(0, str(root))
    sys.dont_write_bytecode = True
    return root


def start_application(config, root):
    server = config.get("server", "werkzeug")
    if server not in {"werkzeug", "waitress"}:
        raise ValueError("Servidor nao reconhecido.")
    if config["env"].get("ENDEMIAS_ACESSO_EXTERNO") == "1" and server != "waitress":
        raise ValueError("Perfil externo exige Waitress.")
    entry = root / ("servir.py" if server == "waitress" else "app.py")
    # O argparse do servir.py nao deve receber --config do wrapper nativo.
    sys.argv = [str(entry)]
    runpy.run_path(str(entry), run_name="__main__")


def probe(config, root):
    """Verifica a identidade real sem enviar dados de teste ao banco oficial."""
    import psycopg2
    from openpyxl import Workbook, load_workbook
    import pandas
    import pymupdf
    import PIL.Image
    import shapely
    import docx
    from reportlab.pdfgen.canvas import Canvas

    checks = {"identidade_limitada": True}
    for name in ("app.py", "secret.key", "scripts/iniciar_servidor.ps1"):
        try:
            with (root / name).open("r+b"):
                pass
        except PermissionError:
            checks["sem_escrita_" + name] = True
        else:
            raise RuntimeError("A conta consegue modificar arquivo protegido.")
    for directory in (root, root / "app_core", root / "templates", Path(sys.prefix)):
        target = directory / "__endemias_negacao_teste__.tmp"
        try:
            with target.open("xb"):
                pass
        except PermissionError:
            continue
        else:
            target.unlink()
            raise RuntimeError("A conta consegue criar arquivos no codigo/Python.")
    checks["codigo_python_sem_criacao"] = True
    for path in config["read_files"]:
        with Path(path).open("rb"):
            pass
    checks["leitura_credenciais"] = True
    # Abrir para gravacao sem escrever nem truncar valida o Kobo sem alterar token.
    with (root / "kobo_config.json").open("r+b"):
        pass
    checks["configuracao_kobo_gravavel"] = True
    for path in config["write_dirs"]:
        target = Path(path) / "__endemias_escrita_teste__.tmp"
        with target.open("xb") as stream:
            stream.write(b"ensaio sem dados reais")
        target.unlink()
    checks["diretorios_operacionais"] = True
    # A identidade web nao deve abrir o arquivo que guarda a definicao/ACL antigas.
    try:
        with Path(config["rollback_guard"]).open("rb"):
            pass
    except PermissionError:
        checks["retorno_privado"] = True
    else:
        raise RuntimeError("A conta web consegue ler a area privada de retorno.")
    # Nenhuma consulta altera usuarios, aceita termos ou executa migracoes.
    with psycopg2.connect(
        host=config["env"]["ENDEMIAS_PG_HOST"], port=config["env"]["ENDEMIAS_PG_PORT"],
        user=config["env"]["ENDEMIAS_PG_USER"], dbname=config["env"]["ENDEMIAS_PG_DATABASE"],
        sslmode=config["env"]["ENDEMIAS_PG_SSLMODE"], connect_timeout=10,
        application_name="endemias_web_probe_readonly",
    ) as connection:
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname=current_user")
            privileges = cursor.fetchone()
            if not privileges or any(privileges):
                raise RuntimeError("Papel SQL possui privilegios administrativos; revisar antes da troca.")
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            cursor.fetchone()
    checks["postgresql_leitura_sem_admin"] = True
    runtime = Path(config["runtime"])
    xlsx = runtime / "ensaio-bibliotecas.xlsx"
    workbook = Workbook()
    workbook.active.append(["Dado ficticio", 1])
    workbook.save(xlsx)
    workbook.close()
    restored = load_workbook(xlsx)
    assert restored.active["B1"].value == 1
    restored.close()
    xlsx.unlink()
    pdf = runtime / "ensaio-bibliotecas.pdf"
    canvas = Canvas(str(pdf))
    canvas.drawString(20, 20, "Ensaio ficticio")
    canvas.save()
    with pymupdf.open(pdf) as document:
        assert len(document) == 1
    pdf.unlink()
    rotation = runtime / "ensaio-rotacao.log"
    handler = logging.handlers.RotatingFileHandler(rotation, maxBytes=30, backupCount=1)
    try:
        for _ in range(3):
            handler.emit(logging.LogRecord("ensaio", logging.WARNING, "", 0, "x" * 40, (), None))
    finally:
        handler.close()
    assert rotation.with_suffix(".log.1").exists()
    rotation.unlink()
    rotation.with_suffix(".log.1").unlink()
    checks["xlsx_pdf_rotacao"] = True
    from app import app
    if config["env"].get("ENDEMIAS_ACESSO_EXTERNO") == "1":
        hostname = config["env"]["ENDEMIAS_ALLOWED_HOSTS"]
        response = app.test_client().get("/login", base_url="https://" + hostname,
            headers={"CF-Connecting-IP": "203.0.113.21", "X-Forwarded-Proto": "https"})
    else:
        response = app.test_client().get("/login")
    if response.status_code != 200 or config["version"].encode() not in response.data:
        raise RuntimeError("A pagina de login nao corresponde a versao esperada.")
    checks["login_versao_atual"] = True
    if config['env'].get('ENDEMIAS_SETORES_ENABLED') == '1':
        from scripts.provar_setores_windows import verificar
        checks.update(verificar(config, root, app))
    from app_core import postgresql_backup
    backup = postgresql_backup.criar_backup_postgresql(
        database="endemias", destino_dir=config["env"]["ENDEMIAS_BACKUP_DIR"],
        prefixo="validacao_conta_limitada", manter=1,
    )
    if not backup.get("validado"):
        raise RuntimeError("Backup da identidade limitada nao foi validado.")
    checks["backup_postgresql_conta_limitada"] = True
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    root = configure(config)
    if args.probe or config.get("probe_only"):
        result = {"ok": False}
        try:
            result.update(checks=probe(config, root), ok=True)
        except Exception as error:
            # Nao exportar detalhes de conexao, tokens, comandos ou configuracoes.
            result.update(error_type=type(error).__name__,
                          trace=[{"file": Path(frame.filename).name, "line": frame.lineno,
                                  "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)])
        Path(config["runtime"], "probe.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0 if result["ok"] else 1
    log = Path(config["runtime"], "processo.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print(time.strftime("%Y-%m-%d %H:%M:%S") + " iniciando servidor com conta limitada", flush=True)
    start_application(config, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
