"""Aplicacao delimitada de conta/ACL para o servidor local existente.

Requer pywin32 somente no Python administrativo. Nao publica Tunnel, muda
firewall/PostgreSQL, integra codigo ou executa migracoes. Sem --aplicar apenas
valida o pacote. Senha aleatoria existe somente em memoria e no Agendador.
"""

import argparse
import ctypes
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import traceback
from urllib.request import urlopen


ROOT = Path(r"C:\endemias")
HOME = Path(r"C:\ProgramData\EndemiasWeb")
PYTHON = HOME / "python/Scripts/python.exe"
TASK = "Endemias - Servidor"
PROBE_TASK = "Endemias - Validacao Conta Web"
ACCOUNT = "EndemiasWeb"
VERSION = "1.75.0"
COMMIT = "f7a98a0"
WRITE_NAMES = {"anexos", "uploads_temp", "notificacoes_geradas", "saida"}
NO_WEB_NAMES = {".git", "backups", ".tmp_test_db_merge_pe0045"}
FULL = 0x1F01FF
READ = 0x120089
EXECUTE = 0x1200A0
WRITE = 0x120116


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def progress(stage, **extra):
    (HOME / "progresso.json").write_text(json.dumps({"stage": stage, **extra}), encoding="utf-8")


def descendants(root, exclude=()):
    """Nao atravessa junction/symlink: falha antes de qualquer alteracao."""
    root = Path(root)
    result = [root]
    if root.is_dir():
        for parent, directories, files in os.walk(root, followlinks=False):
            directories[:] = [name for name in directories if name not in exclude]
            for name in directories + files:
                path = Path(parent) / name
                if path.lstat().st_file_attributes & 0x400:
                    raise ValueError("Reparse point no escopo de permissoes; revisar manualmente.")
                result.append(path)
    return result


def policy_for(path):
    relative = Path(path).relative_to(ROOT)
    first = relative.parts[0] if relative.parts else ""
    if first in NO_WEB_NAMES or (relative.parts and first.startswith("endemias.db")):
        return "private"
    if first in WRITE_NAMES:
        return "modify"
    if relative.as_posix() == "kobo_config.json":
        return "write_file"
    if relative.as_posix() == "secret.key":
        return "read_file"
    return "read"


def split_windows(text):
    count = ctypes.c_int()
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    pointer = shell.CommandLineToArgvW("program.exe " + text, ctypes.byref(count))
    if not pointer:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [pointer[index] for index in range(1, count.value)]
    finally:
        kernel = ctypes.WinDLL("kernel32")
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))


def task_parameters(arguments):
    tokens = split_windows(arguments)
    flags = {"-noprofile", "-noninteractive"}
    allowed = {"-executionpolicy", "-file", "-backend", "-database", "-hostname",
               "-port", "-username", "-sslmode", "-pgpassfile", "-pythonpath"}
    params = {}
    index = 0
    while index < len(tokens):
        name = tokens[index].lower()
        if name in flags:
            index += 1
            continue
        if name not in allowed or index + 1 >= len(tokens) or name in params:
            raise ValueError("Acao atual possui opcoes nao previstas; revisar sem altera-la.")
        params[name] = tokens[index + 1]
        index += 2
    if params.get("-backend") != "postgresql" or params.get("-database") != "endemias":
        raise ValueError("Tarefa atual nao aponta para a producao PostgreSQL esperada.")
    if Path(params.get("-file", "")).resolve() != ROOT / "scripts/iniciar_servidor.ps1":
        raise ValueError("Iniciador atual nao corresponde ao arquivo esperado.")
    if params.get("-hostname", "127.0.0.1") not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Banco nao esta configurado para conexao local.")
    if Path(params.get("-pgpassfile", "")).resolve() != Path(r"C:\ProgramData\Endemias\pgpass.conf"):
        raise ValueError("Credencial atual exige revisao do escopo de ACL.")
    return params


def package_check():
    if not PYTHON.is_file() or not (ROOT / "secret.key").is_file():
        raise ValueError("Python dedicado ou chave existente ausentes.")
    current = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short=7", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip()
    if current != COMMIT or dirty:
        raise ValueError("A master mudou ou tem alteracoes locais; rever pacote antes de aplicar.")
    subprocess.run([str(PYTHON), "-I", "-c", "import flask,flask_wtf,pandas,openpyxl,PIL,pymupdf,reportlab,psycopg2,shapely,docx,waitress"], check=True)
    base = subprocess.check_output([str(PYTHON), "-I", "-c", "import sys; print(sys.base_prefix)"], text=True).strip()
    if Path(base).resolve() != HOME / "base-python":
        raise ValueError("Python dedicado ainda depende do perfil do usuario; preparar runtime proprio.")
    descendants(ROOT)
    descendants(HOME)


class Windows:
    def __init__(self):
        import win32api
        import win32com.client
        import win32con
        import win32net
        import win32netcon
        import win32security
        self.api, self.con, self.net, self.netcon, self.sec = win32api, win32con, win32net, win32netcon, win32security
        self.scheduler = win32com.client.Dispatch("Schedule.Service")
        self.scheduler.Connect()
        self.folder = self.scheduler.GetFolder("\\")
        self.system = self.sec.ConvertStringSidToSid("S-1-5-18")
        self.admins = self.sec.ConvertStringSidToSid("S-1-5-32-544")
        self.operator = self.sec.GetTokenInformation(self.sec.OpenProcessToken(self.api.GetCurrentProcess(), self.con.TOKEN_QUERY), self.sec.TokenUser)[0]
        self.web = None
        self.journal = []
        self.seen = set()
        self.journal_path = None
        self.account_created = False

    def remember(self, path):
        path = str(path)
        if path in self.seen:
            return
        sd = self.sec.GetNamedSecurityInfo(path, self.sec.SE_FILE_OBJECT, self.sec.DACL_SECURITY_INFORMATION)
        text = self.sec.ConvertSecurityDescriptorToStringSecurityDescriptor(sd, 1, self.sec.DACL_SECURITY_INFORMATION)
        self.journal.append({"path": path, "sddl": text})
        self.seen.add(path)

    def protect(self, path, policy="private", remember=True, operator=True):
        if remember:
            self.remember(path)
        flags = self.con.OBJECT_INHERIT_ACE | self.con.CONTAINER_INHERIT_ACE if Path(path).is_dir() else 0
        acl = self.sec.ACL()
        principals = [(self.system, FULL), (self.admins, FULL)]
        if operator:
            principals.append((self.operator, 0x1301BF))
        for sid, mask in principals:
            acl.AddAccessAllowedAceEx(self.sec.ACL_REVISION_DS, flags, mask, sid)
        rights = {"read": READ | EXECUTE,
                  "modify": 0x1301BF, "write_file": READ | WRITE,
                  "read_file": READ}
        if policy in rights:
            acl.AddAccessAllowedAceEx(self.sec.ACL_REVISION_DS, flags, rights[policy], self.web)
        self.sec.SetNamedSecurityInfo(str(path), self.sec.SE_FILE_OBJECT,
                                     self.sec.DACL_SECURITY_INFORMATION | self.sec.PROTECTED_DACL_SECURITY_INFORMATION,
                                     None, None, acl, None)

    def restore_acls(self):
        errors = 0
        # Pais primeiro: a restauracao de heranca pode propagar regras aos filhos.
        for entry in self.journal:
            try:
                sd = self.sec.ConvertStringSecurityDescriptorToSecurityDescriptor(entry["sddl"], 1)
                control, revision = sd.GetSecurityDescriptorControl()
                mode = self.sec.PROTECTED_DACL_SECURITY_INFORMATION if control & self.sec.SE_DACL_PROTECTED else self.sec.UNPROTECTED_DACL_SECURITY_INFORMATION
                self.sec.SetNamedSecurityInfo(entry["path"], self.sec.SE_FILE_OBJECT,
                    self.sec.DACL_SECURITY_INFORMATION | mode, None, None, sd.GetSecurityDescriptorDacl(), None)
            except Exception:
                errors += 1
        return errors

    def create_account(self, password):
        try:
            self.net.NetUserGetInfo(None, ACCOUNT, 1)
        except self.net.error as error:
            if error.winerror != 2221:
                raise
        else:
            raise ValueError("Conta EndemiasWeb ja existe; nao substituir identidade/senha automaticamente.")
        self.net.NetUserAdd(None, 1, {
            "name": ACCOUNT, "password": password, "priv": self.netcon.USER_PRIV_USER,
            "home_dir": "", "comment": "Servidor Endemias - tarefa limitada sem login interativo",
            "flags": self.netcon.UF_SCRIPT | self.netcon.UF_DONT_EXPIRE_PASSWD | self.netcon.UF_PASSWD_CANT_CHANGE,
            "script_path": "",
        })
        self.account_created = True
        self.web = self.sec.LookupAccountName(None, ACCOUNT)[0]
        users_name = self.sec.LookupAccountSid(None, self.sec.ConvertStringSidToSid("S-1-5-32-545"))[0]
        try:
            self.net.NetLocalGroupAddMembers(None, users_name, 0, [{"sid": self.web}])
        except self.net.error as error:
            if error.winerror != 1378:  # A API pode incluir Users ao criar a conta.
                raise
        policy = self.sec.LsaOpenPolicy(None, self.sec.POLICY_ALL_ACCESS)
        try:
            self.sec.LsaAddAccountRights(policy, self.web, ["SeBatchLogonRight", "SeDenyInteractiveLogonRight",
                "SeDenyRemoteInteractiveLogonRight", "SeDenyNetworkLogonRight"])
        finally:
            policy.Close()
        groups = self.net.NetUserGetLocalGroups(None, ACCOUNT)
        admin_name = self.sec.LookupAccountSid(None, self.admins)[0]
        if admin_name.casefold() in {name.casefold() for name in groups}:
            raise RuntimeError("Conta web nao pode pertencer a administradores.")

    def register(self, name, original, password, probe=False):
        definition = self.scheduler.NewTask(0)
        if not probe:
            definition.XmlText = original.Xml
        account = self.api.GetComputerName() + "\\" + ACCOUNT
        definition.Principal.UserId = account
        definition.Principal.LogonType = 1  # TASK_LOGON_PASSWORD: segredo tratado pelo Agendador
        definition.Principal.RunLevel = 0
        definition.Actions.Clear()
        action = definition.Actions.Create(0)
        action.Path = str(PYTHON)
        args = ["-I", "-B", str(HOME / "servico_web_windows.py"), "--config", str(HOME / "config.json")]
        if probe:
            args.append("--probe")
            definition.Triggers.Clear()
            definition.Settings.ExecutionTimeLimit = "PT3M"
            definition.Settings.DisallowStartIfOnBatteries = False
            definition.Settings.StopIfGoingOnBatteries = False
            definition.Settings.AllowDemandStart = True
            definition.Settings.MultipleInstances = 2
            definition.RegistrationInfo.Description = "Validacao temporaria da identidade limitada do Endemias"
        action.Arguments = subprocess.list2cmdline(args)
        action.WorkingDirectory = str(ROOT)
        return self.folder.RegisterTaskDefinition(name, definition, 6, account, password, 1)


def backup_before_change(config, rollback):
    binary = Path(r"C:\Program Files\PostgreSQL\18\bin")
    if not (binary / "pg_dump.exe").is_file() or not (binary / "pg_restore.exe").is_file():
        raise ValueError("Ferramentas PostgreSQL 18 nao encontradas.")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env.update(config["env"])
    target = rollback / "antes_conta_limitada.dump"
    args = [str(binary / "pg_dump.exe"), "--no-password", "--host", config["env"]["ENDEMIAS_PG_HOST"],
            "--port", config["env"]["ENDEMIAS_PG_PORT"], "--username", config["env"]["ENDEMIAS_PG_USER"],
            "--dbname", "endemias", "--format=custom", "--no-owner", "--no-privileges", "--file", str(target)]
    result = subprocess.run(args, env=env, capture_output=True, timeout=180)
    if result.returncode or not target.is_file() or target.stat().st_size < 1000:
        raise RuntimeError("Backup previo falhou; tarefa oficial ainda nao foi alterada.")
    catalog = subprocess.run([str(binary / "pg_restore.exe"), "--list", str(target)], capture_output=True, timeout=30)
    if catalog.returncode or b"TABLE DATA" not in catalog.stdout:
        raise RuntimeError("Catalogo do backup nao foi validado.")
    return {"arquivo": str(target), "bytes": target.stat().st_size, "sha256": digest(target), "catalogo_validado": True}


def wait_login(present=True, timeout=35):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen("http://127.0.0.1:5000/login", timeout=2) as response:
                ok = response.status == 200 and VERSION.encode() in response.read()
        except OSError:
            ok = False
        if ok == present:
            return True
        time.sleep(1)
    return False


def wait_closed(timeout=35):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind(("0.0.0.0", 5000))
            except OSError:
                pass
            else:
                return True
        time.sleep(1)
    return False


def make_config(parameters, sid, rollback):
    runtime = HOME / "runtime"
    manual = Path(r"D:\BackupsEndemias\backups_web")
    write_dirs = [ROOT / name for name in sorted(WRITE_NAMES)] + [runtime, runtime / "temp", manual / "banco", manual / "completos"]
    env = {
        "ENDEMIAS_DB_BACKEND": "postgresql", "ENDEMIAS_PG_DATABASE": "endemias",
        "ENDEMIAS_PG_HOST": parameters.get("-hostname", "127.0.0.1"),
        "ENDEMIAS_PG_PORT": parameters.get("-port", "5432"),
        "ENDEMIAS_PG_USER": parameters.get("-username", "endemias_app"),
        "ENDEMIAS_PG_SSLMODE": parameters.get("-sslmode", "prefer"),
        "PGPASSFILE": parameters["-pgpassfile"],
        "ENDEMIAS_LOG_PATH": str(runtime / "endemias.log"),
        "ENDEMIAS_CONTAOVOS_STATUS_FILE": str(runtime / "contaovos_status.json"),
        "ENDEMIAS_BACKUP_DIR": str(manual / "banco"),
        "ENDEMIAS_BACKUP_COMPLETO_DIR": str(manual / "completos"),
        "TEMP": str(runtime / "temp"), "TMP": str(runtime / "temp"),
    }
    return {"root": str(ROOT), "runtime": str(runtime), "sid": sid, "version": VERSION,
            "env": env, "read_files": [parameters["-pgpassfile"], str(ROOT / "secret.key"),
                r"C:\ProgramData\Endemias\contaovos.key"], "write_dirs": [str(path) for path in write_dirs],
            "rollback_guard": str(rollback / "task.xml")}


def apply():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Executar este pacote como administrador do Windows.")
    progress("validando_pacote")
    package_check()
    win = Windows()
    if any(item.Name == PROBE_TASK for item in win.folder.GetTasks(0)):
        raise ValueError("Tarefa de validacao ja existe; conferir execucao anterior antes de prosseguir.")
    original = win.folder.GetTask(TASK)
    old_xml = original.Xml
    if original.State != 4:
        raise ValueError("A tarefa oficial nao esta em execucao; conferir dono da porta antes de alterar.")
    if original.Definition.Principal.UserId.lower() not in {"system", "s-1-5-18", "sistema"}:
        raise ValueError("A tarefa nao usa mais SYSTEM; revisar antes de aplicar.")
    if original.Definition.Actions.Count != 1:
        raise ValueError("Tarefa tem mais de uma acao; revisar antes de aplicar.")
    parameters = task_parameters(original.Definition.Actions.Item(1).Arguments)
    if not wait_login():
        raise ValueError("Servidor atual nao respondeu com a versao esperada.")
    protected = [ROOT / name for name in ("app.py", "secret.key", "kobo_config.json", "config.json", "endemias.db")]
    before = {str(path): digest(path) for path in protected}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rollback = HOME / "rollback" / stamp
    rollback.mkdir(parents=True, exist_ok=False)
    # Proteger a area de retorno ANTES de escrever XML/SDDL.
    win.protect(HOME / "rollback", remember=False, operator=False)
    win.protect(rollback, remember=False, operator=False)
    (rollback / "task.xml").write_text(old_xml, encoding="utf-8")
    win.protect(rollback / "task.xml", remember=False, operator=False)
    win.journal_path = rollback / "acls.json"
    win.journal_path.write_text("[]", encoding="utf-8")
    win.protect(win.journal_path, remember=False, operator=False)
    report = {"status": "preparando", "version": VERSION, "rollback": str(rollback), "stage": "conta"}
    task_replaced = False
    stopped = False
    probe_registered = False
    password = secrets.token_urlsafe(36) + "aA1!"
    try:
        progress("criando_conta")
        win.create_account(password)
        config = make_config(parameters, win.sec.ConvertSidToStringSid(win.web), rollback)
        report["stage"] = "backup_previo"
        progress("backup_previo")
        report["backup"] = backup_before_change(config, rollback)
        report["stage"] = "permissoes"
        progress("inventario_permissoes")
        for directory in config["write_dirs"]:
            Path(directory).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(__file__).with_name("servico_web_windows.py"), HOME / "servico_web_windows.py")
        (HOME / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        old_status = Path(r"C:\ProgramData\Endemias\contaovos_status.json")
        if old_status.is_file():
            shutil.copyfile(old_status, HOME / "runtime/contaovos_status.json")
        report["stage"] = "registrando_ensaio"
        progress("registrando_ensaio")
        # Registrar antes de mudar as ACLs; a tarefa nao possui trigger automatico.
        probe = win.register(PROBE_TASK, original, password, probe=True)
        probe_registered = True
        report["stage"] = "permissoes"
        # Snapshot completo antes de qualquer propagacao de heranca.
        code_paths = descendants(ROOT)
        home_paths = [path for path in descendants(HOME) if HOME / "rollback" not in path.parents and path != HOME / "rollback"]
        external = [Path(name) for name in config["read_files"] if ROOT not in Path(name).parents]
        manual_paths = descendants(Path(r"D:\BackupsEndemias\backups_web"))
        for path in code_paths + home_paths + external + manual_paths:
            win.remember(path)
        # Persistir o conjunto completo ANTES da propagacao de ACLs dos pais.
        with win.journal_path.open("w", encoding="utf-8") as journal_stream:
            json.dump(win.journal, journal_stream, ensure_ascii=False)
            journal_stream.flush()
            os.fsync(journal_stream.fileno())
        progress("permissoes_codigo", objetos=len(code_paths))
        for path in code_paths:
            win.protect(path, policy_for(path), operator=path not in {ROOT / "secret.key", ROOT / "kobo_config.json"})
        progress("permissoes_python", objetos=len(home_paths))
        for path in home_paths:
            policy = "modify" if path == HOME / "runtime" or HOME / "runtime" in path.parents else "read"
            win.protect(path, policy)
        for path in external:
            win.protect(path, "read_file", operator=False)
        for path in manual_paths:
            win.protect(path, "modify")
        report["stage"] = "ensaio_identidade_real"
        progress("ensaio_identidade_real")
        probe_result = HOME / "runtime/probe.json"
        probe_result.unlink(missing_ok=True)
        probe.Run("")
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            if probe_result.is_file():
                result = json.loads(probe_result.read_text(encoding="utf-8"))
                if not result.get("ok"):
                    report["probe"] = result
                    raise RuntimeError("Ensaio da identidade limitada falhou.")
                report["checks"] = result["checks"]
                break
            if probe.State != 4 and probe.LastRunTime.year > 2000:
                raise RuntimeError("Tarefa de ensaio terminou sem relatorio.")
            time.sleep(1)
        else:
            raise TimeoutError("Tempo esgotado no ensaio.")
        # Conteudos protegidos nao podem mudar durante os testes/permissoes.
        if any(digest(path) != value for path, value in before.items()):
            raise RuntimeError("Arquivo protegido mudou; preservar atividade e revisar, sem restaurar dados.")
        report["stage"] = "troca_tarefa"
        progress("troca_tarefa")
        original.Stop(0)
        stopped = True
        if not wait_closed():
            raise RuntimeError("Servidor anterior nao encerrou; nao iniciar instancia concorrente.")
        new_task = win.register(TASK, original, password)
        task_replaced = True
        new_task.Run("")
        if not wait_login():
            raise RuntimeError("Servidor limitado nao respondeu; retornando tarefa anterior.")
        report.update(status="aplicado", stage="concluido", sid=config["sid"],
                      arquivos_protegidos_preservados=all(digest(path) == value for path, value in before.items()),
                      tarefa_limitada=new_task.Definition.Principal.RunLevel == 0,
                      backups_automaticos_alterados=False, internet_publicada=False)
    except Exception as error:
        progress("retornando_configuracao_anterior")
        report.update(status="falhou", error_type=type(error).__name__,
                      trace=[{"file": Path(frame.filename).name, "line": frame.lineno,
                              "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)])
        if isinstance(getattr(error, "hresult", None), int):
            report["hresult"] = hex(error.hresult & 0xFFFFFFFF)
        info = getattr(error, "excepinfo", None)
        if info and len(info) > 5:
            report["com_code"] = hex(info[5] & 0xFFFFFFFF) if isinstance(info[5], int) else None
            report["com_description"] = str(info[2] or "").replace(password, "[omitido]")
        if task_replaced:
            limited = win.folder.GetTask(TASK)
            if limited.State == 4:
                limited.Stop(0)
            win.folder.RegisterTask(TASK, old_xml, 6, "SYSTEM", "", 5)
        report["erros_retorno_acl"] = win.restore_acls()
        if stopped:
            win.folder.GetTask(TASK).Run("")
            report["servidor_anterior_restaurado"] = wait_login()
        if probe_registered:
            active_probe = win.folder.GetTask(PROBE_TASK)
            if active_probe.State == 4:
                active_probe.Stop(0)
        if win.account_created and not task_replaced:
            win.net.NetUserDel(None, ACCOUNT)
        elif win.account_created and report.get("servidor_anterior_restaurado"):
            win.net.NetUserDel(None, ACCOUNT)
    finally:
        password = None
        if probe_registered:
            try:
                active_probe = win.folder.GetTask(PROBE_TASK)
                if active_probe.State == 4:
                    active_probe.Stop(0)
                win.folder.DeleteTask(PROBE_TASK, 0)
            except Exception:
                report["limpeza_tarefa_ensaio_pendente"] = True
        output = HOME / "resultado.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        progress(report["status"])
        print("Resultado salvo em " + str(output), flush=True)
    return 0 if report["status"] == "aplicado" else 1


def revert():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Retorno exige administrador.")
    output = HOME / "resultado.json"
    report = json.loads(output.read_text(encoding="utf-8"))
    rollback = Path(report["rollback"]).resolve()
    if rollback.parent != HOME / "rollback" or report["status"] != "aplicado":
        raise ValueError("Nao ha implantacao concluida para retornar por este pacote.")
    win = Windows()
    limited = win.folder.GetTask(TASK)
    if limited.Definition.Principal.UserId not in {report["sid"], win.api.GetComputerName() + "\\" + ACCOUNT}:
        raise ValueError("A tarefa mudou depois desta implantacao; nao sobrescrever.")
    if limited.State == 4:
        limited.Stop(0)
    if not wait_closed():
        raise RuntimeError("Servidor limitado ainda escuta; retorno interrompido.")
    old_xml = (rollback / "task.xml").read_text(encoding="utf-8")
    win.folder.RegisterTask(TASK, old_xml, 6, "SYSTEM", "", 5)
    win.journal = json.loads((rollback / "acls.json").read_text(encoding="utf-8"))
    errors = win.restore_acls()
    win.folder.GetTask(TASK).Run("")
    ok = wait_login()
    report.update(status="revertido" if ok and not errors else "retorno_requer_conferencia",
                  erros_retorno_acl=errors, servidor_anterior_restaurado=ok)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if ok and not errors:
        win.net.NetUserDel(None, ACCOUNT)
    print("Resultado de retorno salvo em " + str(output), flush=True)
    return 0 if ok and not errors else 1


def main():
    parser = argparse.ArgumentParser(description="Conta e permissoes restritas para o Endemias local")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--aplicar", action="store_true")
    modes.add_argument("--reverter", action="store_true")
    args = parser.parse_args()
    if args.reverter:
        return revert()
    if not args.aplicar:
        package_check()
        print("Pacote valido. Nenhuma conta, permissao ou tarefa foi alterada.")
        return 0
    return apply()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("Operacao interrompida: " + type(error).__name__ + ". Nenhum detalhe de credenciais foi exibido.", flush=True)
        print(json.dumps([{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                          for frame in traceback.extract_tb(error.__traceback__)]), flush=True)
        if HOME.is_dir():
            (HOME / "falha-preparacao.json").write_text(json.dumps({"error_type": type(error).__name__,
                "trace": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                          for frame in traceback.extract_tb(error.__traceback__)]}), encoding="utf-8")
        raise SystemExit(1)
