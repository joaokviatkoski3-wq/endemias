"""Ensaio HTTP real em loopback com Waitress, cookies, CSRF e carga sintetica."""

import http.client
import json
import re
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.preparar_massa_web_teste import preparar


def main():
    path = ROOT / ".venv" / ("http-sintetico-" + uuid.uuid4().hex + ".db")
    preparar(path)
    from app import create_app
    from waitress import create_server
    from servir import server_options
    from app_core import termos_uso
    app = create_app({"DB_PATH": str(path), "ACESSO_EXTERNO": True, "TRUSTED_HOSTS": ["vsatt.com.br"], "SERVER_PORT": 0})
    server = create_server(app, **server_options(app.config))
    port = server.effective_port
    threading.Thread(target=server.run, daemon=True).start()
    cookies = {}

    def request(method, route, data=None, remember=False, length=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        headers = {"Host": "vsatt.com.br", "CF-Connecting-IP": "203.0.113.21", "X-Forwarded-Proto": "https", "Connection": "close"}
        headers.update(Referer="https://vsatt.com.br/", Origin="https://vsatt.com.br")
        if cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        body = urlencode(data) if data is not None else None
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if length:
            headers["Content-Length"] = str(length)
        try:
            connection.request(method, route, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            if remember:
                for name, value in response.getheaders():
                    if name.lower() == "set-cookie":
                        parsed = SimpleCookie(value)
                        cookies.update({k: v.value for k, v in parsed.items()})
            return response.status, payload, response.getheaders()
        finally:
            connection.close()

    try:
        code, body, _ = request("GET", "/api/formularios")
        assert code == 401
        code, body, _ = request("GET", "/login", remember=True)
        csrf = re.search(rb'name="csrf_token" value="([^"]+)"', body).group(1).decode()
        code, _, headers = request("POST", "/login", {"usuario": "admin", "senha": "SenhaSomenteDeTeste123!", "csrf_token": csrf}, remember=True)
        assert code == 302
        assert any("__Host-endemias=" in value and "Secure" in value and "HttpOnly" in value for name, value in headers if name.lower() == "set-cookie")
        assert request("GET", "/api/formularios")[0] == 403
        code, body, _ = request("GET", "/termos", remember=True)
        assert code == 200
        csrf = re.search(rb'name="csrf_token" value="([^"]+)"', body).group(1).decode()
        assert request("POST", "/termos/aceitar", {"concordo": "sim", "versao": termos_uso.VERSAO, "termo_hash": termos_uso.HASH, "csrf_token": csrf}, remember=True)[0] == 302
        assert request("GET", "/api/formularios")[0] == 200
        assert request("POST", "/termos/aceitar", {})[0] == 400
        assert request("POST", "/processar/iniciar", length=app.config["MAX_CONTENT_LENGTH"] + 1)[0] == 413
        assert request("GET", "/")[0] == 200
        print("OK HTTP: login real, cookie Secure/HttpOnly, CSRF, termo, paginas e limite de upload.")
        results = []
        for concurrency in (10, 30, 60):
            def visit(i):
                start = time.perf_counter()
                route = ("/api/formularios", "/formularios", "/minha-senha")[i % 3]
                code = request("GET", route)[0]
                assert code == 200, (route, code)
                return time.perf_counter() - start
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                durations = list(pool.map(visit, range(concurrency * 3)))
            results.append({"concorrencia": concurrency, "requisicoes": len(durations), "erros": 0,
                            "tempo_total_s": round(time.perf_counter() - start, 3),
                            "mediana_ms": round(statistics.median(durations) * 1000),
                            "p95_ms": round(sorted(durations)[int(len(durations) * .95) - 1] * 1000)})
        (ROOT / ".venv/carga_http.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results))
    finally:
        server.close()
        server.task_dispatcher.shutdown()


if __name__ == "__main__":
    main()
