"""Testes HTTP ponta a ponta exclusivamente no piloto ficticio publicado.

Credencial lida apenas do arquivo local; nao exporta cookies/senhas/respostas
com dados. Usa contas ficticias, faz aceite somente nelas e remove o rascunho
temporario. Nao acessa producao, nem confirma importacao de planilhas.
"""

import http.cookiejar
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".venv/piloto-web"
BASE = "https://piloto.vsatt.com.br"


class Inputs(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.values = {}
        self.feed(body.decode("utf-8"))

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and "name" in values:
            self.values[values["name"]] = values.get("value", "")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None


class Client:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies), NoRedirect())
        self.csrf = ""

    def request(self, method, path, data=None, json_body=None, raw=None, content_type=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Rota deve permanecer no piloto fixo.")
        headers = {"User-Agent": "Endemias-Piloto-QA/1.0", "Origin": BASE, "Referer": BASE + "/"}
        if self.csrf:
            headers["X-CSRFToken"] = self.csrf
        body = raw
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
            content_type = "application/x-www-form-urlencoded"
        if json_body is not None:
            body = json.dumps(json_body).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
        try:
            return self.opener.open(request, timeout=60)
        except urllib.error.HTTPError as response:
            return response

    def read(self, method, path, **kwargs):
        with self.request(method, path, **kwargs) as response:
            return response.status, response.read(), response.headers

    def login(self, username, password):
        status, body, headers = self.read("GET", "/login")
        assert status == 200 and b"1.76.0" in body and b"ambiente-teste-faixa" in body
        self.csrf = Inputs(body).values["csrf_token"]
        status, body, headers = self.read("POST", "/login", data={"usuario": username, "senha": password, "csrf_token": self.csrf})
        assert status == 302, ("login", status)
        assert any(cookie.name == "__Host-endemias" and cookie.secure for cookie in self.cookies)
        status, body, headers = self.read("GET", "/termos")
        assert status == 200
        inputs = Inputs(body).values
        self.csrf = inputs["csrf_token"]
        # Aceite de conta ficticia para o ensaio, nao de usuario real.
        status, body, headers = self.read("POST", "/termos/aceitar", data={
            "csrf_token": self.csrf, "concordo": "sim", "versao": inputs["versao"], "termo_hash": inputs["termo_hash"],
        })
        assert status == 302


def multipart(name, payload):
    boundary = "EndemiasQA" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"arquivos\"; filename=\"{name}\"\r\n"
            "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode()
    return body + payload + f"\r\n--{boundary}--\r\n".encode(), "multipart/form-data; boundary=" + boundary


def main():
    if ROOT == Path(r"C:\endemias") or json.loads((RUNTIME / "massa.json").read_text()).get("sintetico") is not True:
        raise ValueError("Ensaio exige worktree e massa sintetica.")
    text = (RUNTIME / "acesso.local.txt").read_text(encoding="utf-8")
    password = next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Senha:"))
    from openpyxl import Workbook, load_workbook
    checks = {}
    anonymous, admin, operator, viewer = Client(), Client(), Client(), Client()
    assert anonymous.read("GET", "/api/formularios")[0] == 401
    admin.login("admin", password)
    operator.login("ficticio3", password)
    viewer.login("ficticio2", password)
    password = None
    checks["login_cookies_termos_tres_perfis"] = True
    for path in ("/", "/formularios", "/formularios/rg-campo", "/territorializacao", "/processar", "/admin/sistema", "/boletim-mensal?mes=2026-06"):
        status, body, headers = admin.read("GET", path)
        assert status == 200, (path, status)
        assert "no-store" in headers.get("Cache-Control", ""), path
    checks["paginas_principais"] = True
    for path in ("/api/visitas/exportar?d_ini=2026-06-01&d_fim=2026-06-30", "/registro-geografico/exportar.xlsx?localidade=1&quarteirao=0001", "/api/boletim-mensal/exportar?mes=2026-06"):
        status, body, headers = admin.read("GET", path)
        assert status == 200 and body.startswith(b"PK"), (path, status)
        workbook = load_workbook(io.BytesIO(body), read_only=True)
        assert workbook.sheetnames
        workbook.close()
    checks["tres_exportacoes_xlsx_reabertas"] = True
    import pymupdf
    query = urllib.parse.urlencode({"agente": "Agente Ficticio", "d_ini": "2026-06-01", "d_fim": "2026-06-30"})
    status, pdf, headers = admin.read("GET", "/relatorio-agente/visitas/pdf?" + query)
    assert status == 200 and pdf.startswith(b"%PDF"), ("pdf", status)
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        assert document.page_count > 0
    checks["pdf_download_reaberto"] = True
    assert viewer.read("GET", "/admin/sistema")[0] in (302, 403)
    assert viewer.read("POST", "/api/registro-geografico", json_body={})[0] == 403
    checks["visualizador_sem_administracao_escrita"] = True
    created = None
    try:
        draft = {"tipo": "rg_atualizacao", "status": "rascunho", "uuid_cliente": "qa-publico-" + uuid.uuid4().hex,
                 "payload": {"ensaio": "somente dados ficticios", "localidade": "Localidade Ficticia"}}
        status, body, headers = operator.read("POST", "/api/formularios", json_body=draft)
        assert status == 200, ("rascunho", status)
        created = json.loads(body)["id_formulario"]
        assert operator.read("GET", "/api/formularios/" + str(created))[0] == 200
        assert viewer.read("GET", "/api/formularios/" + str(created))[0] == 404
        assert viewer.read("POST", "/api/formularios", json_body=draft)[0] == 400
        checks["rascunho_propriedade_e_recusa_sobrescrita"] = True
        workbook = Workbook()
        workbook.active.append(["Data", "Localidade", "_uuid"])
        stream = io.BytesIO()
        workbook.save(stream)
        workbook.close()
        raw, kind = multipart("TB_ensaio_ficticio.xlsx", stream.getvalue())
        status, body, headers = admin.read("POST", "/processar/iniciar", raw=raw, content_type=kind)
        assert status == 200, ("upload", status)
        job = json.loads(body)["job_id"]
        started = time.monotonic()
        with admin.request("POST", "/processar/stream/" + job, data={"csrf_token": admin.csrf}) as response:
            assert response.status == 200 and "text/event-stream" in response.headers.get("Content-Type", "")
            first = response.readline()
            first_seconds = time.monotonic() - started
            data = first + response.read()
        assert b'"done": true' in data, "SSE sem conclusao"
        assert b"Erro inesperado" not in data, "Falha interna no SSE"
        assert admin.read("POST", "/processar/cancelar/" + job, data={"csrf_token": admin.csrf})[0] in (200, 302)
        checks["upload_xlsx_e_sse_sem_confirmar_importacao"] = True
        checks["sse_primeiro_bloco_segundos"] = round(first_seconds, 3)
        raw, kind = multipart("falso.xlsx", b"nao e uma planilha")
        assert admin.read("POST", "/processar/iniciar", raw=raw, content_type=kind)[0] == 400
        checks["upload_invalido_recusado"] = True
    finally:
        if created is not None:
            assert admin.read("DELETE", "/api/formularios/" + str(created))[0] == 200
    admin.csrf = ""
    assert admin.read("POST", "/api/formularios", json_body={})[0] == 400
    checks["csrf_ausente_recusado"] = True
    output = ROOT / ".venv/piloto-publico-http.json"
    output.write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
