"""Consulta nativa da tarefa Windows; nao altera politica de scripts ou servicos."""

import ctypes
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def resumir_tarefa(xml):
    root = ET.fromstring(xml)
    def value(path):
        return root.findtext(path, default="", namespaces=NS)
    actions = []
    for action in root.findall("t:Actions/t:Exec", NS):
        arguments = action.findtext("t:Arguments", default="", namespaces=NS)
        actions.append({
            "programa": action.findtext("t:Command", default="", namespaces=NS),
            "diretorio": action.findtext("t:WorkingDirectory", default="", namespaces=NS),
            "launcher_endemias": "iniciar_servidor.ps1" in arguments.lower(),
            "backend_postgresql": bool(re.search(r'''-Backend\s+["']?postgresql''', arguments, re.I)),
            "banco_oficial": bool(re.search(r'''-Database\s+["']?endemias(?:["'\s]|$)''', arguments, re.I)),
            "usa_waitress": bool(re.search(r'''-Servidor\s+["']?waitress''', arguments, re.I)),
        })
    return {"status": "consultado", "identidade": value("t:Principals/t:Principal/t:UserId"),
            "tipo_logon": value("t:Principals/t:Principal/t:LogonType"),
            "nivel": value("t:Principals/t:Principal/t:RunLevel"), "acoes": actions}


def decode_output(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:30]:
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("mbcs", errors="replace")


def main():
    binary = Path(os.environ["SystemRoot"]) / "System32" / "schtasks.exe"
    result = subprocess.run([str(binary), "/Query", "/TN", "Endemias - Servidor", "/XML"],
                            capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        task = {"status": "nao_verificado", "motivo": decode_output(result.stderr).strip()}
    else:
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", decode_output(result.stdout), count=1)
        task = resumir_tarefa(text)
    report = {"coletado_em": datetime.now(timezone.utc).isoformat(),
              "administrador": bool(ctypes.windll.shell32.IsUserAnAdmin()),
              "alteracoes_de_configuracao": False, "tarefa_servidor": task}
    output = ROOT / ".venv" / ("tarefa-web-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Relatorio salvo em: " + str(output))
    print("Nenhuma configuracao, servico, banco ou politica do Windows foi alterada.")
    if task["status"] != "consultado":
        print("Tarefa nao acessivel. Execute o atalho como administrador.")
        return 1
    print("Tarefa consultada; argumentos completos e credenciais nao foram gravados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
