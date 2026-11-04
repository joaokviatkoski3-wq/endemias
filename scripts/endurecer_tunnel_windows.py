"""Troca somente a identidade/permissoes do Cloudflared instalado.

Mantem o mesmo executavel, argumentos, token e inicializacao automatica.
Nao le/copia o conteudo do token. Retorna ao estado anterior se a conexao
publica de ensaio nao voltar. pywin32 somente no Python administrativo.
"""

import argparse
import ctypes
from datetime import datetime
import json
from pathlib import Path
import sys
import time
import traceback
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.endurecer_web_windows import Windows, split_windows

SERVICE = "Cloudflared"
ACCOUNT = r"NT SERVICE\Cloudflared"
STATE_DIR = Path(r"C:\ProgramData\EndemiasTunnel")
URL = "https://piloto.vsatt.com.br/login"


def validate_command(command):
    parts = split_windows(command)
    if not parts or Path(parts[0]).name.lower() != "cloudflared.exe":
        raise ValueError("Executavel do conector nao reconhecido.")
    if "--token" in parts or parts.count("--token-file") != 1:
        raise ValueError("Exige token em arquivo; nao exportar argumentos do servico.")
    position = parts.index("--token-file") + 1
    if position >= len(parts):
        raise ValueError("Argumento do arquivo do token ausente.")
    token = Path(parts[position]).resolve()
    expected = Path(r"C:\ProgramData\cloudflared\token")
    if token != expected or not token.is_file():
        raise ValueError("Arquivo do token fora do escopo previsto.")
    return Path(parts[0]).resolve(), token


def public_ready(timeout=65):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        request = urllib.request.Request(URL, headers={"User-Agent": "Endemias-Piloto-Verificacao/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                if response.status == 200 and b"1.76.0" in response.read():
                    return True
        except (OSError, urllib.error.HTTPError):
            pass
        time.sleep(2)
    return False


class Tunnel:
    def __init__(self, read_only=False):
        import win32service
        import win32api
        import win32con
        self.svc, self.api, self.con = win32service, win32api, win32con
        self.win = Windows()
        self.manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        access = (win32service.SERVICE_QUERY_CONFIG | win32service.SERVICE_QUERY_STATUS) if read_only else win32service.SERVICE_ALL_ACCESS
        self.handle = win32service.OpenService(self.manager, SERVICE, access)

    def wait(self, target, timeout=40):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.svc.QueryServiceStatus(self.handle)[1] == target:
                return
            time.sleep(.5)
        raise TimeoutError("Tempo esgotado aguardando estado do conector.")

    def stop(self):
        state = self.svc.QueryServiceStatus(self.handle)[1]
        if state != self.svc.SERVICE_STOPPED:
            if state != self.svc.SERVICE_STOP_PENDING:
                self.svc.ControlService(self.handle, self.svc.SERVICE_CONTROL_STOP)
            self.wait(self.svc.SERVICE_STOPPED)

    def start(self):
        self.svc.StartService(self.handle, None)
        self.wait(self.svc.SERVICE_RUNNING)

    def set_identity(self, account, sid_type, privileges):
        unchanged = self.svc.SERVICE_NO_CHANGE
        self.svc.ChangeServiceConfig(self.handle, unchanged, unchanged, unchanged,
            None, None, 0, None, account, None if account == ACCOUNT else "", None)
        self.svc.ChangeServiceConfig2(self.handle, self.svc.SERVICE_CONFIG_SERVICE_SID_INFO, sid_type)
        self.svc.ChangeServiceConfig2(self.handle, self.svc.SERVICE_CONFIG_REQUIRED_PRIVILEGES_INFO, privileges)

    def verify_process(self):
        sec = self.win.sec
        pid = self.svc.QueryServiceStatusEx(self.handle)["ProcessId"]
        process = self.api.OpenProcess(0x1000, False, pid)
        try:
            token = sec.OpenProcessToken(process, self.con.TOKEN_QUERY)
            try:
                assert sec.GetTokenInformation(token, sec.TokenUser)[0] == self.win.web
                groups = sec.GetTokenInformation(token, sec.TokenGroups)
                assert not any(sid == self.win.admins and flags & 4 and not flags & 16 for sid, flags in groups)
                enabled = sec.GetTokenInformation(token, sec.TokenPrivileges)
                forbidden = {"SeDebugPrivilege", "SeImpersonatePrivilege", "SeBackupPrivilege", "SeRestorePrivilege"}
                assert not {sec.LookupPrivilegeName(None, luid) for luid, flags in enabled if flags & 2} & forbidden
            finally:
                token.Close()
        finally:
            process.Close()
        return {"sid_real_conferido": True, "sem_administrador": True, "privilegios_reduzidos": True}


def run(apply=False, revert=False):
    if (apply or revert) and not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Mudanca do conector exige administrador do Windows.")
    tunnel = Tunnel(read_only=not (apply or revert))
    win = tunnel.win
    service_config = tunnel.svc.QueryServiceConfig(tunnel.handle)
    binary, token_file = validate_command(service_config[3])
    if not apply and not revert:
        print(json.dumps({"servico": SERVICE, "identidade": service_config[7], "token_em_arquivo": True,
                          "inicializacao_automatica": service_config[1] == 2}))
        return 0
    STATE_DIR.mkdir(exist_ok=True)
    # Saida sanitizada pode ser lida pelo operador; retorno privado so por admin.
    win.protect(STATE_DIR, "private", remember=False)
    output = STATE_DIR / "resultado.json"
    if revert:
        report = json.loads(output.read_text(encoding="utf-8"))
        state = Path(report["retorno"]).resolve()
        if state.parent != STATE_DIR or report["status"] != "aplicado":
            raise ValueError("Retorno nao corresponde a aplicacao concluida.")
        previous = json.loads((state / "estado.json").read_text(encoding="utf-8"))
        tunnel.stop()
        tunnel.set_identity(previous["account"], previous["sid_type"], previous["privileges"])
        win.journal = previous["acls"]
        errors = win.restore_acls()
        tunnel.start()
        report.update(status="revertido", erros_retorno_acl=errors, piloto_responde=public_ready())
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0 if report["piloto_responde"] and not errors else 1
    if service_config[7].lower() != "localsystem" or service_config[1] != 2:
        raise ValueError("Servico nao esta no estado inicial esperado; nao sobrescrever.")
    if not public_ready(timeout=15):
        raise ValueError("Piloto deve estar respondendo antes de alterar o conector.")
    win.web = win.sec.LookupAccountName(None, ACCOUNT)[0]
    before = {"account": service_config[7], "sid_type": tunnel.svc.QueryServiceConfig2(tunnel.handle, 5),
              "privileges": tunnel.svc.QueryServiceConfig2(tunnel.handle, 6)}
    state = STATE_DIR / ("retorno-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    state.mkdir(exist_ok=False)
    win.protect(state, remember=False, operator=False)
    for path in (token_file.parent, token_file):
        if path.lstat().st_file_attributes & 0x400:
            raise ValueError("Arquivo/diretorio do token e um reparse point.")
        win.remember(path)
    before["acls"] = win.journal
    (state / "estado.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    report = {"status": "preparando", "retorno": str(state), "token_conteudo_lido": False,
              "programa_argumentos_alterados": False, "inicializacao_automatica": True}
    output.write_text(json.dumps(report), encoding="utf-8")
    stopped = False
    try:
        # Diretorio somente RX; arquivo somente R. Sem escrita para o conector.
        win.protect(token_file.parent, "read", operator=False)
        win.protect(token_file, "read_file", operator=False)
        tunnel.stop()
        stopped = True
        tunnel.set_identity(ACCOUNT, 1, ["SeChangeNotifyPrivilege"])
        tunnel.start()
        report["processo"] = tunnel.verify_process()
        if not public_ready():
            raise RuntimeError("Piloto nao voltou com o conector limitado.")
        after = tunnel.svc.QueryServiceConfig(tunnel.handle)
        assert after[3] == service_config[3] and after[1] == service_config[1]
        assert after[7].lower() == ACCOUNT.lower()
        report.update(status="aplicado", identidade=ACCOUNT, piloto_responde=True,
                      token_acl_protegida=True, privileges=["SeChangeNotifyPrivilege"])
    except Exception as error:
        report.update(status="falhou", error_type=type(error).__name__, winerror=getattr(error, "winerror", None),
            trace=[{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                   for frame in traceback.extract_tb(error.__traceback__)])
        if stopped:
            tunnel.stop()
            tunnel.set_identity(before["account"], before["sid_type"], before["privileges"])
        report["erros_retorno_acl"] = win.restore_acls()
        if stopped:
            tunnel.start()
        report["piloto_anterior_restaurado"] = public_ready()
    finally:
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Resultado sanitizado salvo em " + str(output), flush=True)
    return 0 if report["status"] == "aplicado" else 1


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--aplicar", action="store_true")
    modes.add_argument("--reverter", action="store_true")
    args = parser.parse_args()
    return run(args.aplicar, args.reverter)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Nao serializar excecao completa/argumentos do servico.
        STATE_DIR.mkdir(exist_ok=True)
        (STATE_DIR / "falha.json").write_text(json.dumps({"error_type": type(error).__name__,
            "winerror": getattr(error, "winerror", None),
            "trace": [{"line": frame.lineno, "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)]}), encoding="utf-8")
        raise SystemExit(1)
