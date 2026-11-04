"""Acesso LAN e Tunnel ao mesmo banco, com sessoes criptograficamente separadas."""

import contextlib
import http.client
import io
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import jsonify, request

import app
import criar_banco
import servir
from app_core import auth, termos_uso, sessoes


class EntradasWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "duplo.db")
        with patch.object(criar_banco, "BANCO", self.path), contextlib.redirect_stdout(io.StringIO()):
            criar_banco.main()
        conn = sqlite3.connect(self.path)
        self.senha_hash = conn.execute("SELECT senha_hash FROM usuarios WHERE id_usuario=1").fetchone()[0]
        conn.close()
        self.external = app.create_app({"DB_PATH": self.path, "ACESSO_EXTERNO": True,
                                       "TRUSTED_HOSTS": ["vsatt.com.br"], "TESTING": True,
                                       "WTF_CSRF_ENABLED": False, "SERVER_PORT": 0})
        self.local = servir.local_application(self.external, "127.0.0.2")
        for application, name in ((self.external, "externo"), (self.local, "local")):
            application.add_url_rule("/api/prova", "prova", lambda name=name: jsonify(entrada=name, ip=request.remote_addr))

    def cookie(self, application):
        with application.app_context():
            payload = {"uid": 1, "auth_token": auth.token_sessao(self.senha_hash),
                       "termo_aceito": termos_uso.VERSAO + ":" + termos_uso.HASH}
            payload['sessao_id'] = sessoes.criar(self.path, {'id_usuario':1,'senha_hash':self.senha_hash})
            return application.session_interface.get_signing_serializer(application).dumps(payload)

    def test_credenciais_de_sessao_nao_podem_ser_reaproveitadas_entre_entradas(self):
        self.assertNotEqual(self.external.secret_key, self.local.secret_key)
        self.assertEqual(self.local.config["DB_PATH"], self.external.config["DB_PATH"])
        self.assertTrue(self.external.config["SESSION_COOKIE_SECURE"])
        self.assertFalse(self.local.config["SESSION_COOKIE_SECURE"])
        headers = {"CF-Connecting-IP": "203.0.113.21", "X-Forwarded-Proto": "https"}
        external_client = self.external.test_client()
        external_client.set_cookie("__Host-endemias", self.cookie(self.local), domain="vsatt.com.br", secure=True)
        self.assertEqual(external_client.get("/api/prova", base_url="https://vsatt.com.br", headers=headers).status_code, 401)
        external_client.set_cookie("__Host-endemias", self.cookie(self.external), domain="vsatt.com.br", secure=True)
        response = external_client.get("/api/prova", base_url="https://vsatt.com.br", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["ip"], "203.0.113.21")
        local_client = self.local.test_client()
        local_client.set_cookie("endemias_local", self.cookie(self.external), domain="127.0.0.1")
        self.assertEqual(local_client.get("/api/prova", base_url="http://127.0.0.1").status_code, 302)

    def test_local_nao_confia_em_cabecalhos_que_simulam_a_cloudflare(self):
        client = self.local.test_client()
        client.set_cookie("endemias_local", self.cookie(self.local), domain="127.0.0.1")
        response = client.get("/api/prova", base_url="http://127.0.0.1", headers={
            "CF-Connecting-IP": "203.0.113.21", "X-Forwarded-For": "203.0.113.99",
            "X-Forwarded-Proto": "https", "X-Forwarded-Host": "vsatt.com.br"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"entrada": "local", "ip": "127.0.0.1"})
        self.assertEqual(client.get("/login", base_url="http://vsatt.com.br").status_code, 400)

    def test_configuracao_recusa_ip_publico_wildcard_e_portas_iguais(self):
        env = {"ENDEMIAS_ACESSO_LOCAL": "1", "ENDEMIAS_LOCAL_PORT": "5002", "ENDEMIAS_TUNNEL_PORT": "5003"}
        for address in ("", "0.0.0.0", "8.8.8.8"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                servir.local_options(self.external.config, {**env, "ENDEMIAS_LOCAL_BIND": address})
        with self.assertRaises(ValueError):
            servir.local_options(self.external.config, {**env, "ENDEMIAS_LOCAL_BIND": "127.0.0.1", "ENDEMIAS_TUNNEL_PORT": "5002"})

    def test_http_real_duas_entradas_mesmo_pool_e_dados_compartilhados(self):
        ports = []
        while len(set(ports)) < 2:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                ports.append(sock.getsockname()[1])
        local_port, tunnel_port = list(dict.fromkeys(ports))[:2]
        env = {"ENDEMIAS_ACESSO_LOCAL": "1", "ENDEMIAS_LOCAL_BIND": "127.0.0.2",
               "ENDEMIAS_LOCAL_PORT": str(local_port), "ENDEMIAS_TUNNEL_PORT": str(tunnel_port), "ENDEMIAS_THREADS": "4"}
        external_server, local_server = servir.create_dual_servers(self.external, self.local, env)
        self.assertIs(external_server.task_dispatcher, local_server.task_dispatcher)
        self.assertEqual(set(local_server.effective_listen), {("127.0.0.1", str(local_port)), ("127.0.0.2", str(local_port))})
        self.assertEqual(external_server.adj.max_request_body_size, 95 * 1024 * 1024)
        self.assertEqual(local_server.adj.max_request_body_size, 220 * 1024 * 1024)
        worker = threading.Thread(target=external_server.run, daemon=True)
        worker.start()

        def call(port, route, method="GET", payload=None, public=False, cookie=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            headers = {"Host": "vsatt.com.br" if public else "127.0.0.1", "Connection": "close"}
            if public:
                headers.update({"CF-Connecting-IP": "203.0.113.21", "X-Forwarded-Proto": "https"})
            if cookie:
                headers["Cookie"] = ("__Host-endemias=" if public else "endemias_local=") + cookie
            body = None
            if payload is not None:
                body = json.dumps(payload)
                headers["Content-Type"] = "application/json"
            try:
                connection.request(method, route, body=body, headers=headers)
                response = connection.getresponse()
                data = response.read()
                return response.status, json.loads(data) if response.getheader("Content-Type", "").startswith("application/json") else None
            finally:
                connection.close()
        try:
            local_cookie, external_cookie = self.cookie(self.local), self.cookie(self.external)
            self.assertEqual(call(local_port, "/api/prova", cookie=local_cookie), (200, {"entrada": "local", "ip": "127.0.0.1"}))
            self.assertEqual(call(tunnel_port, "/api/prova", public=True, cookie=external_cookie)[0], 200)
            self.assertEqual(call(tunnel_port, "/login")[0], 400)
            status, data = call(local_port, "/api/formularios", "POST", {"tipo": "rg_atualizacao", "payload": {"origem": "LAN sintetica"}}, cookie=local_cookie)
            self.assertEqual(status, 200)
            status, data = call(tunnel_port, f"/api/formularios/{data['id_formulario']}", public=True, cookie=external_cookie)
            self.assertEqual(status, 200)
            self.assertEqual(data["payload"], {"origem": "LAN sintetica"})
        finally:
            external_server.close()
            local_server.close()
            external_server.task_dispatcher.shutdown()


if __name__ == "__main__":
    unittest.main()
