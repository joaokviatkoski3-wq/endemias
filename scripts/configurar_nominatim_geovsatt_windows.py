"""Configura o Nominatim no serviço Windows com o conector já publicado."""

import argparse
import ctypes
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp

ROOT = Path("C:/endemias")
sys.path.insert(0, str(ROOT))

from app_core.geovsatt_busca import buscar_nominatim, endpoint_nominatim
from app_core.version import APP_VERSION
from scripts.ativar_acesso_externo_windows import http_login
from scripts.ativar_interface_setores_windows import wait_closed
from scripts.ativar_setores_windows import origin_portal
from scripts.endurecer_web_windows import Windows

HOME = Path("C:/ProgramData/EndemiasWeb")
CONFIG = HOME / "config.json"
RELATORIO = HOME / "ativacao-nominatim-geovsatt-resultado.json"
PROVEDOR = "https://geocode.maps.co"
VAR_URL = "ENDEMIAS_GEO_NOMINATIM_URL"
VAR_TOKEN = "ENDEMIAS_GEO_NOMINATIM_TOKEN"
CONSULTA = "Almirante Tamandaré, Paraná"


def configurar(original, token):
    if original.get("version") != APP_VERSION or Path(original.get("root", "")) != ROOT:
        raise ValueError("A configuração aponta para outra instalação ou versão.")
    if original.get("server") != "waitress" or original.get("probe_only"):
        raise ValueError("A aplicação oficial precisa estar em operação.")
    ambiente = original["env"]
    if ambiente.get(VAR_URL, "").strip().rstrip("/") not in ("", PROVEDOR, PROVEDOR + "/search"):
        raise ValueError("O servidor já tem outro provedor configurado.")
    endpoint = endpoint_nominatim(PROVEDOR, token)
    if not endpoint:
        raise ValueError("O arquivo deve conter somente uma chave válida do maps.co.")
    if not buscar_nominatim(endpoint, CONSULTA, token):
        raise RuntimeError("O provedor não retornou resultado para Almirante Tamandaré.")
    return {**original, "env": {**ambiente, VAR_URL: PROVEDOR, VAR_TOKEN: token}}


def verificar_logins(porta_tunnel):
    for prefixo in ("endemias", "ambiental", "geo"):
        if not http_login("127.0.0.1", porta_tunnel, prefixo + ".vsatt.com.br", expected_version=APP_VERSION):
            raise RuntimeError("Um dos logins do VSATT não voltou.")
    if not origin_portal(geo=True):
        raise RuntimeError("O portal do VSATT não voltou.")


def substituir_config(novo, backup):
    substituir = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    substituir.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                           ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p)
    substituir.restype = ctypes.c_int
    if not substituir(str(CONFIG), str(novo), str(backup), 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def aplicar(original, proposta, conteudo_original, relatorio):
    win = Windows()
    tarefa = win.folder.GetTask("Endemias - Servidor")
    sid, _, _ = win.sec.LookupAccountName(None, tarefa.Definition.Principal.UserId)
    if win.sec.ConvertSidToStringSid(sid) != original["sid"] or tarefa.Definition.Principal.RunLevel != 0 or tarefa.State != 4:
        raise ValueError("A tarefa do serviço está em estado inesperado.")
    ambiente = original["env"]
    portas = tuple(int(ambiente.get(campo, padrao)) for campo, padrao in (
        ("ENDEMIAS_LOCAL_PORT", "5000"), ("ENDEMIAS_TUNNEL_PORT", "5001"),
        ("ENDEMIAS_AMBIENTAL_LOCAL_PORT", "5004"), ("ENDEMIAS_GEO_LOCAL_PORT", "5005"),
    ))
    if proposta == original:
        verificar_logins(portas[1])
        return

    pasta = Path(mkdtemp(prefix="ativacao-nominatim-", dir=HOME))
    win.protect(pasta, remember=False, operator=False)
    novo = pasta / "config-nova.json"
    backup = pasta / "config-anterior.json"
    with novo.open("x", encoding="utf-8") as arquivo:
        json.dump(proposta, arquivo, indent=2)
        arquivo.flush()
        os.fsync(arquivo.fileno())

    parada_solicitada = False
    try:
        if CONFIG.read_bytes() != conteudo_original:
            raise RuntimeError("A configuração mudou durante a validação.")
        relatorio["etapa"] = "reiniciando_servico"
        tarefa.Stop(0)
        parada_solicitada = True
        if not wait_closed(ports=portas):
            raise RuntimeError("As portas do servidor não foram liberadas.")
        substituir_config(novo, backup)
        if json.loads(CONFIG.read_text(encoding="utf-8")) != proposta:
            raise RuntimeError("O arquivo gravado diverge da configuração proposta.")
        tarefa.Run("")
        verificar_logins(portas[1])
    except Exception:
        if parada_solicitada:
            relatorio["etapa"] = "restaurando_servico"
            if backup.is_file():
                if tarefa.State == 4:
                    tarefa.Stop(0)
                if not wait_closed(ports=portas) or backup.read_bytes() != conteudo_original:
                    raise RuntimeError("A restauração exige revisão da configuração anterior.")
                backup.replace(CONFIG)
            if tarefa.State != 4:
                tarefa.Run("")
            verificar_logins(portas[1])
            relatorio["configuracao_anterior_restaurada"] = True
        raise
    finally:
        novo.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--verificar", action="store_true")
    modo.add_argument("--aplicar", action="store_true")
    parser.add_argument("--arquivo-chave", type=Path, required=True)
    args = parser.parse_args()
    if args.aplicar and not ctypes.windll.shell32.IsUserAnAdmin():
        print("Abra o atalho como administrador do Windows.")
        return 2

    relatorio = {"status": "falhou", "etapa": "validando_provedor", "versao": APP_VERSION}
    try:
        if args.aplicar and subprocess.check_output(
            ["git", "-C", str(ROOT), "status", "--porcelain"], text=True
        ).strip():
            raise RuntimeError("A instalação oficial tem alterações locais.")
        with (HOME / "ativacao-nominatim.lock").open("a+b") if args.aplicar else open(os.devnull, "rb") as trava:
            if args.aplicar:
                msvcrt.locking(trava.fileno(), msvcrt.LK_NBLCK, 1)
            conteudo = CONFIG.read_bytes()
            original = json.loads(conteudo)
            token = args.arquivo_chave.read_text(encoding="utf-8-sig").strip()
            proposta = configurar(original, token)
            if args.aplicar:
                aplicar(original, proposta, conteudo, relatorio)
            relatorio.update(status="aplicado" if args.aplicar else "validado", etapa="concluido")
    except Exception as erro:
        relatorio["erro"] = type(erro).__name__
        if getattr(erro, "winerror", None):
            relatorio["codigo_windows"] = erro.winerror

    if args.aplicar:
        RELATORIO.write_text(json.dumps(relatorio, indent=2), encoding="utf-8")
    print(json.dumps(relatorio))
    return int(relatorio["status"] == "falhou")


if __name__ == "__main__":
    raise SystemExit(main())
