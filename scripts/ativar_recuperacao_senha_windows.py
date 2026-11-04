"""Atualiza 1.76 para 1.77 preservando identidade, ambiente e dados reais.

Backup antes da troca, somente migracao 0031 e retorno de codigo/config em
falha. Nao restaura dump nem desfaz migracoes/operacoes de usuarios.
"""

import argparse
import copy
import ctypes
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from scripts.ativar_acesso_externo_windows import connect, git, http_login, signatures
from scripts.endurecer_web_windows import Windows, backup_before_change, wait_closed

OFFICIAL = Path(r"C:\endemias")
HOME = Path(r"C:\ProgramData\EndemiasWeb")


@dataclass(frozen=True)
class Release:
    origin: str = "1.76.0"
    target: str = "1.77.0"
    migration: str = "0031_recuperacao_senha.sql"
    marker: str = "ativacao177"
    owner_id: int | None = None
    owner_login: str | None = None
    snapshot_completo: bool = False


def promover_owner(config, release):
    connection = connect(config)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (1840364333,))
            cursor.execute("SELECT row_to_json(u) FROM usuarios u ORDER BY id_usuario")
            before = [row[0] for row in cursor.fetchall()]
            selected = next((u for u in before if u['id_usuario'] == release.owner_id), None)
            if (not selected or selected['usuario'] != release.owner_login or selected['nivel'] != 'admin'
                    or not selected['ativo'] or any(u['nivel'] == 'superadmin' for u in before)):
                raise ValueError("Conta pessoal nao corresponde ao estado confirmado pelo usuario.")
            cursor.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=%s AND usuario=%s AND nivel='admin' AND ativo=1",
                           (release.owner_id, release.owner_login))
            if cursor.rowcount != 1:
                raise ValueError("Conta pessoal mudou durante a ativacao.")
            cursor.execute("SELECT row_to_json(u) FROM usuarios u ORDER BY id_usuario")
            after = [row[0] for row in cursor.fetchall()]
            expected = copy.deepcopy(before)
            next(u for u in expected if u['id_usuario'] == release.owner_id)['nivel'] = 'superadmin'
            if after != expected:
                raise RuntimeError("Mudanca de conta diferente da unica promocao autorizada.")
            cursor.execute("""INSERT INTO auditoria_eventos
                (acao,entidade,entidade_id,usuario_id,usuario_nome,ip,detalhes_json,criado_em)
                VALUES ('superadmin_ativado','usuarios',%s,NULL,'Operador Windows','local',%s,%s)""",
                (str(release.owner_id), json.dumps({"usuario": release.owner_login, "nivel_anterior": "admin", "nivel_novo": "superadmin"}), datetime.now().isoformat()))
        connection.commit()
        return {"id": release.owner_id, "usuario": release.owner_login, "nivel": "superadmin", "outras_contas_preservadas": True}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def config_atualizada(original, release=Release()):
    if (original.get("version") != release.origin or original.get("server") != "waitress"
            or original.get("probe_only") or original["env"].get("ENDEMIAS_DB_BACKEND") != "postgresql"):
        raise ValueError("Origem diferente da instalacao conferida.")
    proposed = copy.deepcopy(original)
    proposed["version"] = release.target
    return proposed


def apply(args, release=Release()):
    from app_core import postgresql_migrations
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Atualizacao exige administrador do Windows.")
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (args.release, args.expected_current)):
        raise ValueError("Informe commits completos.")
    old_head = git("rev-parse", "HEAD")
    if old_head != args.expected_current or git("branch", "--show-current") != "master" or git("status", "--porcelain"):
        raise ValueError("A master mudou; conferir antes de atualizar.")
    git("merge-base", "--is-ancestor", old_head, args.release)
    if (SOURCE / "app_core/version.py").read_text(encoding="utf-8").splitlines()[0] != f'APP_VERSION = "{release.target}"':
        raise ValueError("Pacote com versao inesperada.")
    original = json.loads((HOME / "config.json").read_text(encoding="utf-8"))
    proposed = config_atualizada(original, release)
    env = original["env"]
    host = env["ENDEMIAS_ALLOWED_HOSTS"]
    local_ip = env["ENDEMIAS_LOCAL_BIND"]
    if host != "endemias.vsatt.com.br" or env.get("ENDEMIAS_TUNNEL_PORT") != "5001" or env.get("ENDEMIAS_LOCAL_PORT") != "5000":
        raise ValueError("Entradas oficiais mudaram; nao sobrescrever.")
    connection = connect(original, readonly=True)
    try:
        states = postgresql_migrations.status(connection, SOURCE / "migrations/postgresql")
        if ([row["version"] for row in states if row["state"] == "pending"] != [release.migration[:4]]
                or any(row["state"] == "checksum_mismatch" for row in states)):
            raise ValueError("Migracoes pendentes diferentes do pacote conferido.")
    finally:
        connection.close()
    win = Windows()
    task = win.folder.GetTask("Endemias - Servidor")
    task_sid = win.sec.ConvertSidToStringSid(win.sec.LookupAccountName(None, task.Definition.Principal.UserId)[0])
    if task_sid != original["sid"] or task.Definition.Principal.RunLevel != 0 or task.State != 4:
        raise ValueError("Tarefa nao esta na identidade limitada esperada.")
    state = HOME / (release.marker + "-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    state.mkdir()
    win.protect(state, remember=False, operator=False)
    shutil.copyfile(HOME / "config.json", state / "config-anterior.json")
    report = {"status": "preparando", "stage": "backup", "state": str(state),
              "old_head": old_head, "release": args.release}
    output = HOME / (release.marker + "-resultado.json")
    protected = [OFFICIAL / name for name in ("secret.key", "kobo_config.json", "config.json", "endemias.db")]
    files = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}

    def save(stage):
        report["stage"] = stage
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    stopped = integrated = False
    try:
        report["backup"] = backup_before_change(original, state)
        save("parando_aplicacao")
        task.Stop(0)
        stopped = True
        if not wait_closed():
            raise RuntimeError("Aguardar liberacao da porta antes de alterar codigo.")
        before = signatures(original)
        (state / "assinaturas-antes.json").write_text(json.dumps(before), encoding="utf-8")
        if release.snapshot_completo:
            from app_core import backup_completo, db
            save('backup_completo_antes_migracao')
            info = backup_completo.criar_backup_completo(
                destino_dir=env['ENDEMIAS_BACKUP_COMPLETO_DIR'], raiz=OFFICIAL, manter=None,
                anexos_dir=env.get('ENDEMIAS_ANEXOS_DIR', str(OFFICIAL/'anexos')),
                kobo_config_path=env.get('ENDEMIAS_KOBO_CONFIG_PATH', str(OFFICIAL/'kobo_config.json')),
                secret_key_path=env.get('ENDEMIAS_SECRET_KEY_PATH', str(OFFICIAL/'secret.key')),
                db_target=db.DatabaseTarget('postgresql', env['ENDEMIAS_PG_DATABASE']),
                postgresql_env=env)
            archive = Path(info['arquivo'])
            with archive.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            report['backup_completo'] = {'arquivo': str(archive), 'bytes': archive.stat().st_size,
                'sha256': checksum, 'integridade_banco': info.get('integridade_banco')}
        save("integrando_codigo")
        git("merge", "--ff-only", args.release)
        integrated = True
        save("migracao_" + release.migration[:4])
        connection = connect(original)
        try:
            report["migrations_applied"] = postgresql_migrations.apply_pending(connection, OFFICIAL / "migrations/postgresql")
            if report["migrations_applied"] != [release.migration]:
                raise RuntimeError("Migracao aplicada diferente da prevista.")
        finally:
            connection.close()
        after = signatures(original, before.keys())
        report.update(tables_compared=len(before), data_preserved=before == after,
            files_preserved=all(hashlib.sha256(path.read_bytes()).hexdigest() == files[str(path)] for path in protected))
        if not report["data_preserved"] or not report["files_preserved"]:
            raise RuntimeError("Dados/configuracoes mudaram; revisar sem restaurar banco.")
        if release.owner_id is not None:
            save("promocao_unica_autorizada")
            report["owner_promovido"] = promover_owner(original, release)
        save("ensaio_identidade_limitada")
        proposed["probe_only"] = True
        probe_path = HOME / "runtime/probe.json"
        probe_path.unlink(missing_ok=True)
        (HOME / "config.json").write_text(json.dumps(proposed, indent=2), encoding="utf-8")
        task.Run("")
        deadline = time.monotonic() + 140
        while time.monotonic() < deadline:
            if probe_path.is_file():
                try:
                    report["probe"] = json.loads(probe_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    time.sleep(.2)
                    continue
                if not report["probe"].get("ok"):
                    raise RuntimeError("Ensaio da conta limitada falhou.")
                break
            time.sleep(1)
        else:
            raise TimeoutError("Ensaio nao terminou no prazo.")
        while task.State == 4 and time.monotonic() < deadline:
            time.sleep(.5)
        if task.State == 4:
            raise TimeoutError("Tarefa de ensaio nao encerrou.")
        proposed["probe_only"] = False
        (HOME / "config.json").write_text(json.dumps(proposed, indent=2), encoding="utf-8")
        save("iniciando_aplicacao")
        task.Run("")
        for address, port, public in (("127.0.0.1", 5000, None), (local_ip, 5000, None), ("127.0.0.1", 5001, host)):
            if not http_login(address, port, public, expected_version=release.target):
                raise RuntimeError("Login nao confirmou a versao nova.")
        report.update(status="aplicado", version=release.target, task_identity_preserved=True,
                      existing_environment_preserved=proposed["env"] == original["env"],
                      password_resets_on_real_users=0, local_login_200=True, tunnel_origin_login_200=True)
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
                raise RuntimeError("Retorno aguarda parada do servidor.")
            shutil.copyfile(state / "config-anterior.json", HOME / "config.json")
        if integrated:
            if report.get("owner_promovido"):
                connection = connect(original)
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE usuarios SET nivel='admin' WHERE id_usuario=%s AND usuario=%s AND nivel='superadmin'",
                                       (release.owner_id, release.owner_login))
                        if cursor.rowcount != 1:
                            raise RuntimeError("Conta mudou; retorno exige conferencia manual.")
                    connection.commit()
                    report["owner_retornado_a_admin"] = True
                finally:
                    connection.close()
            if git("status", "--porcelain") or git("rev-parse", "HEAD") != args.release:
                raise RuntimeError("Arvore mudou; retorno de codigo exige revisao.")
            git("restore", "--source=" + old_head, "--staged", "--worktree", ".")
            git("commit", "-m", "rollback: retorna " + release.origin + " preservando banco e dados novos")
        if stopped:
            task.Run("")
            report["rollback_login_ok"] = http_login("127.0.0.1", 5000, expected_version=release.origin)
        report["database_restored_or_deleted"] = False
        save("retornado")
    finally:
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["status"] == "aplicado" else 1


def main(release=Release()):
    parser = argparse.ArgumentParser()
    parser.add_argument("--aplicar", action="store_true", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--expected-current", required=True)
    try:
        return apply(parser.parse_args(), release)
    except Exception as error:
        (HOME / (release.marker + "-falha.json")).write_text(json.dumps({"error_type": type(error).__name__,
            "trace": [{"line": f.lineno, "function": f.name} for f in traceback.extract_tb(error.__traceback__)]}), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
