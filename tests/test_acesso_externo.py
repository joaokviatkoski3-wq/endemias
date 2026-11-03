"""Regressoes de seguranca com usuarios e dados inteiramente sinteticos."""

import contextlib
import io
import sqlite3
import queue
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import app
import criar_banco
import servir
from app_core import auth, db, formularios, termos_uso
from blueprints import processar


class AcessoExternoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "ensaio.db")
        with mock.patch.object(criar_banco, "BANCO", self.path), contextlib.redirect_stdout(io.StringIO()):
            criar_banco.main()
        self.password = "SenhaSintetica123!"
        self.hash = auth.hash_senha(self.password)
        conn = sqlite3.connect(self.path)
        conn.execute("UPDATE usuarios SET senha_hash=? WHERE usuario='admin'", (self.hash,))
        for uid, nivel in ((21, "usuario"), (22, "usuario"), (23, "operador")):
            conn.execute("INSERT INTO usuarios (id_usuario,usuario,nome,senha_hash,nivel,criado_em) VALUES (?,?,?,?,?,?)",
                         (uid, f"teste{uid}", f"Pessoa ficticia {uid}", self.hash, nivel, "2026-11-03"))
        conn.commit()
        conn.close()
        self.app = app.create_app({"DB_PATH": self.path, "TESTING": True, "WTF_CSRF_ENABLED": False})
        self.client = self.app.test_client()

    def logged(self, client=None, uid=21, signed=False):
        client = client or self.client
        with client.session_transaction() as sess:
            sess["uid"] = uid
            if signed:
                with self.app.app_context():
                    sess["auth_token"] = auth.token_sessao(self.hash)
        return client

    def test_formulario_de_outro_usuario_nao_pode_ser_lido(self):
        fid = formularios.salvar(self.path, "rg_atualizacao", {"teste": "sigiloso"}, {"id_usuario": 22}, uuid_cliente="outro")
        self.logged()
        response = self.client.get(f"/api/formularios/{fid}")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"sigiloso", response.data)
        self.logged(uid=1)
        self.assertEqual(self.client.get(f"/api/formularios/{fid}").status_code, 200)

    def test_uuid_alheio_e_status_privilegiado_nao_sobrescrevem_formulario(self):
        fid = formularios.salvar(self.path, "rg_atualizacao", {"original": 1}, {"id_usuario": 22}, uuid_cliente="outro")
        for uid, status in ((21, "enviado"), (22, "oficializado"), (22, "aprovado")):
            with self.assertRaises(ValueError):
                formularios.salvar(self.path, "rg_atualizacao", {}, {"id_usuario": uid}, uuid_cliente="outro", status=status)
        formularios.marcar_oficializado(self.path, fid, {"id_usuario": 1})
        with self.assertRaises(ValueError):
            formularios.salvar(self.path, "rg_atualizacao", {}, {"id_usuario": 22}, uuid_cliente="outro")
        self.assertEqual(formularios.obter(self.path, fid)["payload"], {"original": 1})

    def test_redefinir_senha_invalida_cookie_anterior(self):
        self.logged(signed=True)
        self.assertEqual(self.client.get("/api/formularios").status_code, 200)
        conn = sqlite3.connect(self.path)
        conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=21", (auth.hash_senha("SenhaNovaSintetica"),))
        conn.commit()
        conn.close()
        self.assertIn(self.client.get("/api/formularios").status_code, (302, 401))

    def test_nova_rota_sem_decorador_fica_protegida(self):
        self.app.add_url_rule("/nova-rota", "nova_rota", lambda: "conteudo privado")
        response = self.client.get("/nova-rota")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(b"conteudo privado", response.data)

    def test_redirecionamento_nao_aceita_barras_invertidas_ou_downgrade(self):
        with self.app.test_request_context("/login", base_url="https://vsatt.com.br"):
            for url in ("//intruso.invalid", "\\\\intruso.invalid", "http://vsatt.com.br/", "/\n/intruso"):
                self.assertFalse(auth.url_segura(url))
            self.assertTrue(auth.url_segura("/formularios"))

    def test_paginas_apis_e_anexos_sem_login_nao_revelam_conteudo(self):
        for path in ("/", "/liraa", "/api/dashboard", "/api/formularios/1", "/acoes-setor/anexos/1/download", "/admin/sistema/backups/baixar/teste.zip"):
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (302, 401))

    def test_nao_ha_cache_compartilhado_para_respostas_privadas(self):
        self.logged()
        response = self.client.get("/api/formularios")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("private", response.headers["Cache-Control"])
        self.assertIn("Cookie", response.headers["Vary"])
        with self.client.get("/static/css/app.css") as static_response:
            self.assertNotIn("X-Endemias-User", static_response.headers)

    def test_termo_bloqueia_paginas_e_api_ate_aceite_explicito(self):
        self.app.config["TERMOS_USO_ENABLED"] = True
        self.logged()
        self.assertEqual(self.client.get("/formularios").location, "/termos")
        self.assertEqual(self.client.get("/api/formularios").status_code, 403)
        self.assertEqual(self.client.get("/termos").status_code, 200)
        self.assertEqual(self.client.post("/termos/aceitar", data={}).status_code, 400)
        data = {"concordo": "sim", "versao": termos_uso.VERSAO, "termo_hash": termos_uso.HASH}
        self.assertEqual(self.client.post("/termos/aceitar", data=data).status_code, 302)
        self.assertEqual(self.client.get("/api/formularios").status_code, 200)
        # Outro navegador/sessao reconhece aceite persistido, nao so cookie.
        other = self.app.test_client()
        self.logged(other)
        self.assertEqual(other.get("/api/formularios").status_code, 200)
        conn = sqlite3.connect(self.path)
        row = conn.execute("SELECT versao,texto_termo,aceito_em,ip FROM usuarios_termos WHERE usuario_id=21").fetchone()
        conn.close()
        self.assertEqual(row[0], termos_uso.VERSAO)
        self.assertEqual(row[1], termos_uso.TEXTO)
        self.assertIn("+00:00", row[2])
        self.assertEqual(row[3], "127.0.0.1")
        with mock.patch.object(termos_uso, "HASH", "versao-seguinte"):
            self.assertEqual(self.client.get("/api/formularios").status_code, 403)

    def test_aceite_exige_csrf(self):
        self.app.config.update(TERMOS_USO_ENABLED=True, WTF_CSRF_ENABLED=True)
        self.logged()
        response = self.client.post("/termos/aceitar", data={"concordo": "sim", "versao": termos_uso.VERSAO, "termo_hash": termos_uso.HASH})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(termos_uso.aceitou(self.path, 21))

    def test_contagem_de_falhas_concorrentes_nao_perde_incrementos(self):
        get_db = lambda: db.connect(self.path)
        auth.garantir_tabela_login_tentativas(get_db)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: auth.registrar_login_falha_db(get_db, "chave-concorrente", agora=100), range(24)))
        conn = sqlite3.connect(self.path)
        self.assertEqual(conn.execute("SELECT tentativas FROM login_tentativas WHERE chave='chave-concorrente'").fetchone()[0], 24)
        conn.close()

    def test_nomes_diferentes_nao_contornam_limite_por_ip(self):
        get_db = lambda: db.connect(self.path)
        for _ in range(auth.LOGIN_MAX_POR_IP):
            auth.registrar_login_falha_db(get_db, "ip:127.0.0.1")
        self.assertEqual(self.client.post("/login", data={"usuario": "nome-novo", "senha": "errada"}).status_code, 429)

    def test_sse_envia_comentarios_de_manutencao_sem_alterar_dados(self):
        q = mock.Mock()
        q.get.side_effect = queue.Empty
        done = mock.Mock()
        done.is_set.side_effect = [False, True]
        q.empty.return_value = True
        with mock.patch.object(processar.time, "monotonic", side_effect=[0, 16, 16]):
            messages = list(processar._stream_log(q, done))
        self.assertEqual(messages, [": conectado\n\n", ": keepalive\n\n"])

    def test_perfil_externo_exige_hosts_e_escuta_local(self):
        with self.assertRaises(ValueError):
            app.create_app({"DB_PATH": self.path, "ACESSO_EXTERNO": True})
        with self.assertRaises(ValueError):
            servir.server_options({"ACESSO_EXTERNO": True, "SERVER_PORT": 5002, "MAX_CONTENT_LENGTH": 1}, {"ENDEMIAS_BIND": "0.0.0.0"})

    def test_tunnel_ignora_cabecalhos_forjados_e_exige_https_host_correto(self):
        external = app.create_app({"DB_PATH": self.path, "ACESSO_EXTERNO": True, "TRUSTED_HOSTS": ["vsatt.com.br"], "TESTING": True})
        external.add_url_rule("/prova", "static.prova", lambda: "nao-publica")
        client = external.test_client()
        headers = {"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-Proto": "https", "X-Forwarded-For": "198.51.100.9", "X-Forwarded-Host": "intruso.invalid"}
        response = client.get("/login", base_url="https://vsatt.com.br", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertIn("Strict-Transport-Security", response.headers)
        self.assertTrue(external.config["SESSION_COOKIE_SECURE"])
        self.assertEqual(external.config["SESSION_COOKIE_NAME"], "__Host-endemias")
        self.assertEqual(client.get("/login", base_url="https://intruso.invalid", headers=headers).status_code, 400)
        self.assertEqual(client.get("/login", base_url="https://vsatt.com.br", headers=headers, environ_overrides={"REMOTE_ADDR": "192.168.1.9"}).status_code, 403)
        self.assertEqual(client.get("/login", base_url="https://vsatt.com.br").status_code, 400)
        # Identidade normalizada fica disponivel aos limites e auditoria.
        with external.test_request_context("/", headers=headers):
            self.assertFalse(external.config["TRUST_PROXY_HEADERS"])


if __name__ == "__main__":
    unittest.main()
