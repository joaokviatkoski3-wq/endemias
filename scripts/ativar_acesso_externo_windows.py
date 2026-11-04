"""Ativacao local 1.76.0; hostname publico e configurado depois no painel.

Usa a tarefa/identidade existentes sem redefinir senha. Backup e retorno
privados; nao restaura banco nem apaga aceites em retorno de codigo.
"""

import argparse
import ctypes
from datetime import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from scripts.endurecer_web_windows import Windows, backup_before_change, wait_closed
from scripts.preparar_ativacao_externa import proposed_config

OFFICIAL = Path(r"C:\endemias")
WEB_HOME = Path(r"C:\ProgramData\EndemiasWeb")
PG_CONFIG = Path(r"C:\Program Files\PostgreSQL\18\data\postgresql.conf")


def git(*arguments, check=True):
    result = subprocess.run(["git", "-C", str(OFFICIAL), *arguments], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError("Operacao Git nao concluiu; revisar estado sem sobrescrever arquivos.")
    return result.stdout.strip()


def local_only_config(text):
    pattern = r"(?m)^(\s*listen_addresses\s*=\s*)'([^']*)'"
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1 or matches[0].group(2) not in {"*", "localhost"}:
        raise ValueError("Configuracao PostgreSQL fora do formato conferido.")
    return re.sub(pattern, lambda match: match.group(1) + "'localhost'", text, count=1)


def connect(config, readonly=False):
    import psycopg2
    os.environ.update(config["env"])
    env = config["env"]
    connection = psycopg2.connect(host=env["ENDEMIAS_PG_HOST"], port=env["ENDEMIAS_PG_PORT"],
        user=env["ENDEMIAS_PG_USER"], dbname=env["ENDEMIAS_PG_DATABASE"], connect_timeout=10,
        application_name="endemias_ativacao_controlada")
    connection.set_session(readonly=readonly)
    return connection


def signatures(config, tables=None):
    from psycopg2 import sql
    connection = connect(config, readonly=True)
    try:
        with connection.cursor() as cursor:
            if tables is None:
                cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
                tables = [row[0] for row in cursor.fetchall() if row[0] not in {"endemias_schema_migrations", "usuarios_termos", "login_tentativas", "auditoria"}]
            values = {}
            for name in tables:
                cursor.execute(sql.SQL("SELECT row_to_json(t)::text FROM public.{} t ORDER BY row_to_json(t)::text").format(sql.Identifier(name)))
                digest = hashlib.sha256()
                count = 0
                for row in cursor:
                    digest.update(row[0].encode("utf-8"))
                    digest.update(b"\n")
                    count += 1
                values[name] = {"count": count, "sha256": digest.hexdigest()}
            return values
    finally:
        connection.close()


def http_login(host, port, public_host=None, timeout=40, expected_version="1.76.0"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client = http.client.HTTPConnection(host, port, timeout=3)
            headers = {} if not public_host else {"Host": public_host, "CF-Connecting-IP": "203.0.113.21", "X-Forwarded-Proto": "https"}
            client.request("GET", "/login", headers=headers)
            response = client.getresponse()
            body = response.read()
            client.close()
            if response.status == 200 and expected_version.encode() in body:
                return True
        except OSError:
            pass
        time.sleep(1)
    return False


def pg_service(action):
    import win32service
    manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    handle = win32service.OpenService(manager, "postgresql-x64-18", win32service.SERVICE_ALL_ACCESS)
    try:
        target = win32service.SERVICE_STOPPED if action == "stop" else win32service.SERVICE_RUNNING
        state = win32service.QueryServiceStatus(handle)[1]
        if state != target:
            if action == "stop":
                win32service.ControlService(handle, win32service.SERVICE_CONTROL_STOP)
            else:
                win32service.StartService(handle, None)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if win32service.QueryServiceStatus(handle)[1] == target:
                    return
                time.sleep(.5)
            raise TimeoutError("PostgreSQL nao chegou ao estado esperado.")
    finally:
        win32service.CloseServiceHandle(handle)
        win32service.CloseServiceHandle(manager)


def apply(args):
    from app_core import postgresql_migrations
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Ativacao exige administrador do Windows.")
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (args.release, args.expected_current)):
        raise ValueError("Informe commits completos e imutaveis do pacote e da origem.")
    old_head = git("rev-parse", "HEAD")
    if old_head != args.expected_current or git("branch", "--show-current") != "master" or git("status", "--porcelain"):
        raise ValueError("A master mudou ou tem alteracoes locais; revisar antes da janela.")
    git("merge-base", "--is-ancestor", old_head, args.release)
    cfg_path = WEB_HOME / "config.json"
    entry_path = WEB_HOME / "servico_web_windows.py"
    original = json.loads(cfg_path.read_text(encoding="utf-8"))
    if original.get("version") != "1.75.0" or original["env"].get("ENDEMIAS_DB_BACKEND") != "postgresql":
        raise ValueError("Instalacao oficial nao corresponde a origem conferida.")
    proposed = proposed_config(original, args.host, args.local_ip)
    pg_bytes = PG_CONFIG.read_bytes()
    pg_text = pg_bytes.decode("utf-8-sig")
    new_pg_text = local_only_config(pg_text)
    auto_conf = PG_CONFIG.with_name("postgresql.auto.conf").read_text(encoding="utf-8-sig")
    if re.search(r"(?m)^\s*listen_addresses\s*=", auto_conf):
        raise ValueError("Existe override de listen_addresses; revisar antes de aplicar.")
    connection = connect(original, readonly=True)
    try:
        status = postgresql_migrations.status(connection, SOURCE / "migrations/postgresql")
        pending = [item["version"] for item in status if item["state"] == "pending"]
        if pending not in ([], ["0030"]) or any(item["state"] == "checksum_mismatch" for item in status):
            raise ValueError("Migracoes nao correspondem a unica 0030 pendente.")
        with connection.cursor() as cursor:
            cursor.execute("SELECT has_schema_privilege(current_user,'public','CREATE'), has_table_privilege(current_user,'usuarios','REFERENCES')")
            if not all(cursor.fetchone()):
                raise ValueError("Papel configurado nao tem permissoes para a migracao aditiva.")
    finally:
        connection.close()
    win = Windows()
    task = win.folder.GetTask("Endemias - Servidor")
    task_sid = win.sec.ConvertSidToStringSid(win.sec.LookupAccountName(None, task.Definition.Principal.UserId)[0])
    if task_sid != original["sid"] or task.Definition.Principal.RunLevel != 0 or task.State != 4:
        raise ValueError("A tarefa oficial nao esta na identidade limitada esperada.")
    state = WEB_HOME / ("ativacao176-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    state.mkdir()
    win.protect(state, remember=False, operator=False)
    shutil.copyfile(cfg_path, state / "config-anterior.json")
    shutil.copyfile(entry_path, state / "entrada-anterior.py")
    (state / "postgresql-anterior.conf").write_bytes(pg_bytes)
    (state / "tarefa.xml").write_text(task.Xml, encoding="utf-8")
    report = {"status": "preparando", "state": str(state), "old_head": old_head, "release": args.release,
              "hostname": args.host, "stage": "backup", "producao_publicada": False}
    output = WEB_HOME / "ativacao176-resultado.json"

    def save(stage):
        report["stage"] = stage
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    stopped, integrated, pg_changed = False, False, False
    protected = [OFFICIAL / name for name in ("secret.key", "kobo_config.json", "config.json", "endemias.db")]
    before_files = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    try:
        save("backup")
        report["backup"] = backup_before_change(original, state)
        save("parando_aplicacao")
        task.Stop(0)
        stopped = True
        if not wait_closed():
            raise RuntimeError("Porta oficial nao liberada; nao iniciar outra instancia.")
        save("assinaturas_anteriores")
        before_data = signatures(original)
        (state / "assinaturas-antes.json").write_text(json.dumps(before_data), encoding="utf-8")
        save("postgresql_localhost")
        pg_changed = True
        pg_service("stop")
        PG_CONFIG.write_bytes(new_pg_text.encode("utf-8"))
        pg_service("start")
        save("integrando_codigo")
        git("merge", "--ff-only", args.release)
        integrated = True
        save("migracao_0030")
        connection = connect(original)
        try:
            applied = postgresql_migrations.apply_pending(connection, OFFICIAL / "migrations/postgresql")
            assert applied in ([], ["0030_usuarios_termos.sql"])
            report["migrations_applied"] = applied
        finally:
            connection.close()
        save("ensaio_identidade_final")
        shutil.copyfile(OFFICIAL / "scripts/servico_web_windows.py", entry_path)
        probe_path = WEB_HOME / "runtime/probe.json"
        probe_path.unlink(missing_ok=True)
        proposed["probe_only"] = True
        cfg_path.write_text(json.dumps(proposed, indent=2), encoding="utf-8")
        task.Run("")
        deadline = time.monotonic() + 140
        while time.monotonic() < deadline:
            if probe_path.is_file():
                try:
                    probe = json.loads(probe_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    time.sleep(.2)
                    continue
                report["probe"] = probe
                if not probe.get("ok"):
                    raise RuntimeError("Ensaio da identidade final falhou; retornar.")
                break
            time.sleep(1)
        else:
            raise TimeoutError("Ensaio da conta limitada excedeu o prazo.")
        while task.State == 4 and time.monotonic() < deadline:
            time.sleep(.5)
        if task.State == 4:
            raise TimeoutError("Tarefa de ensaio nao encerrou.")
        proposed["probe_only"] = False
        cfg_path.write_text(json.dumps(proposed, indent=2), encoding="utf-8")
        save("iniciando_waitress")
        task.Run("")
        assert http_login("127.0.0.1", 5000)
        assert http_login(args.local_ip, 5000)
        assert http_login("127.0.0.1", 5001, args.host)
        save("conferencia_final")
        after_data = signatures(original, before_data.keys())
        report["tables_compared"] = len(before_data)
        report["data_preserved"] = before_data == after_data
        report["files_preserved"] = all(hashlib.sha256(path.read_bytes()).hexdigest() == before_files[str(path)] for path in protected)
        if not report["data_preserved"] or not report["files_preserved"]:
            raise RuntimeError("Dados/configuracoes mudaram; preservar arquivos e revisar sem restaurar banco.")
        connection = connect(original, readonly=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SHOW listen_addresses")
                assert cursor.fetchone()[0] == "localhost"
                cursor.execute("SELECT COUNT(*) FROM usuarios_termos")
                report["terms_count_after_install"] = cursor.fetchone()[0]
        finally:
            connection.close()
        report.update(status="aplicado", version="1.76.0", postgres_localhost=True,
                      local_login_200=True, tunnel_origin_login_200=True, task_identity_preserved=True)
        save("concluido")
    except Exception as error:
        report.update(status="falhou", error_type=type(error).__name__,
            trace=[{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                   for frame in traceback.extract_tb(error.__traceback__)])
        save("retorno")
        if stopped:
            if task.State == 4:
                task.Stop(0)
            if not wait_closed():
                raise RuntimeError("Retorno aguarda encerramento da tarefa; nao sobrescrever codigo em uso.")
            shutil.copyfile(state / "config-anterior.json", cfg_path)
            shutil.copyfile(state / "entrada-anterior.py", entry_path)
        if integrated:
            # Somente a integracao deste pacote, se nao houver edicoes posteriores.
            if git("status", "--porcelain") or git("rev-parse", "HEAD") != args.release:
                raise RuntimeError("Arvore mudou durante a janela; retorno de codigo exige revisao.")
            git("restore", "--source=" + old_head, "--staged", "--worktree", ".")
            git("commit", "-m", "rollback: retorna codigo anterior preservando banco e aceites")
        if pg_changed:
            pg_service("stop")
            PG_CONFIG.write_bytes(pg_bytes)
            pg_service("start")
        if stopped:
            task.Run("")
            report["rollback_login_ok"] = http_login("127.0.0.1", 5000, expected_version="1.75.0")
        report["database_restored_or_deleted"] = False
        report["migration_0030_rolled_back"] = False
        save("retornado")
    finally:
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["status"] == "aplicado" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--aplicar", action="store_true", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--expected-current", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--local-ip", required=True)
    args = parser.parse_args()
    return apply(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        (WEB_HOME / "ativacao176-falha.json").write_text(json.dumps({"error_type": type(error).__name__,
            "trace": [{"line": frame.lineno, "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)]}), encoding="utf-8")
        raise SystemExit(1)
