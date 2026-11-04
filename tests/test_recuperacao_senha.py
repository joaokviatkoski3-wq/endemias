"""Recuperacao de contas ficticias, sem consulta a contas operacionais."""

import contextlib
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import app
import criar_banco
from app_core import auth, db, sessoes, recuperacao_senha as recovery


class RecuperacaoSenhaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "sintetico.db")
        with mock.patch.object(criar_banco, "BANCO", self.path), contextlib.redirect_stdout(io.StringIO()):
            criar_banco.main()
        self.old = auth.hash_senha("SenhaAnteriorFicticia!")
        conn = sqlite3.connect(self.path)
        conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=1", (self.old,))
        for uid, role in ((21, "usuario"), (22, "operador"), (23, "visualizador")):
            conn.execute("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em) VALUES(?,?,?,?,?,?)",
                         (uid, f"ficticio{uid}", f"Pessoa Ficticia {uid}", self.old, role, "2026-11-04"))
        conn.commit(); conn.close()
        self.app = app.create_app({"DB_PATH": self.path, "TESTING": True, "WTF_CSRF_ENABLED": False,
                                   "REQUIRE_SESSION_TOKEN": True})
        self.client = self.app.test_client()

    def query(self, sql, params=()):
        conn = db.connect(self.path)
        try:
            rows = conn.execute(sql, params).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def logged(self, uid=1):
        client = self.app.test_client()
        with self.app.app_context(), client.session_transaction() as s:
            s.update(uid=uid, nome="Pessoa Ficticia", auth_token=auth.token_sessao(self.old))
            s['sessao_id'] = sessoes.criar(self.path, {'id_usuario':uid, 'senha_hash':self.old})
        return client

    def test_geracao_so_guarda_hash_e_preserva_senha(self):
        token = recovery.gerar(self.path, 21, 1, agora=1000)
        row = self.query("SELECT * FROM usuarios_recuperacao_senha")[0]
        self.assertEqual(row["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, str(dict(row)))
        self.assertEqual(row["expira_em"], 1900)
        self.assertEqual(self.query("SELECT senha_hash FROM usuarios WHERE id_usuario=21")[0][0], self.old)

    def test_consumo_unico_e_nao_autentica_usuario(self):
        token = recovery.gerar(self.path, 21, 1)
        old_client = self.logged(21)
        self.assertEqual(old_client.get("/api/formularios").status_code, 200)
        response = self.client.post("/recuperar-senha", data={"token": token, "nova": "NovaSenhaFicticia!", "confirmar": "NovaSenhaFicticia!"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Senha alterada com sucesso", response.get_data(as_text=True))
        self.assertNotIn(token, response.get_data(as_text=True))
        self.assertEqual(old_client.get("/api/formularios").status_code, 302)
        with self.client.session_transaction() as s:
            self.assertNotIn("uid", s)
        with self.assertRaisesRegex(ValueError, "inválido"):
            recovery.consumir(self.path, token, "MaisUmaSenhaFicticia!")
        password = self.query("SELECT senha_hash FROM usuarios WHERE id_usuario=21")[0][0]
        self.assertTrue(auth.verificar_senha("NovaSenhaFicticia!", password)[0])

    def test_link_expira_no_limite_sem_alterar_senha(self):
        token = recovery.gerar(self.path, 21, 1, agora=1000)
        with self.assertRaises(ValueError):
            recovery.consumir(self.path, token, "NovaSenhaFicticia!", agora=1900)
        self.assertEqual(self.query("SELECT senha_hash FROM usuarios WHERE id_usuario=21")[0][0], self.old)

    def test_novo_link_invalida_anterior(self):
        old = recovery.gerar(self.path, 21, 1, agora=1000)
        new = recovery.gerar(self.path, 21, 1, agora=1001)
        with self.assertRaises(ValueError):
            recovery.consumir(self.path, old, "NovaSenhaFicticia!", agora=1100)
        self.assertEqual(recovery.consumir(self.path, new, "NovaSenhaFicticia!", agora=1100), 21)

    def test_troca_de_senha_ou_desativacao_invalida_link(self):
        for statement, values in (("UPDATE usuarios SET senha_hash=? WHERE id_usuario=21", (auth.hash_senha("OutraSenhaFicticia!"),)),
                                  ("UPDATE usuarios SET ativo=0 WHERE id_usuario=21", ()),
                                  ("UPDATE usuarios SET nivel='operador' WHERE id_usuario=1", ())):
            with self.subTest(statement=statement):
                token = recovery.gerar(self.path, 21, 1, agora=1000)
                self.query(statement, values)
                with self.assertRaises(ValueError):
                    recovery.consumir(self.path, token, "NovaSenhaFicticia!", agora=1100)
                self.query("UPDATE usuarios SET ativo=1,senha_hash=? WHERE id_usuario=21", (self.old,))
                self.query("UPDATE usuarios SET nivel='admin' WHERE id_usuario=1")

    def test_geracao_recusa_operador_conta_inativa_e_inexistente(self):
        for uid, actor in ((21, 22), (999, 1)):
            with self.assertRaises(ValueError):
                recovery.gerar(self.path, uid, actor)
        self.query("UPDATE usuarios SET ativo=0 WHERE id_usuario=21")
        with self.assertRaises(ValueError):
            recovery.gerar(self.path, 21, 1)

    def test_duas_tentativas_simultaneas_so_uma_troca(self):
        token = recovery.gerar(self.path, 21, 1)
        def run(_):
            try:
                recovery.consumir(self.path, token, "NovaSenhaFicticia!")
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(run, range(2))), 1)

    def test_falha_auditoria_desfaz_senha_e_consumo(self):
        token = recovery.gerar(self.path, 21, 1)
        with self.assertRaises(RuntimeError):
            recovery.consumir(self.path, token, "NovaSenhaFicticia!", auditar=mock.Mock(side_effect=RuntimeError("ficticio")))
        self.assertIsNone(self.query("SELECT usado_em FROM usuarios_recuperacao_senha")[0][0])
        self.assertEqual(self.query("SELECT senha_hash FROM usuarios WHERE id_usuario=21")[0][0], self.old)
        self.assertEqual(recovery.consumir(self.path, token, "NovaSenhaFicticia!"), 21)

    def test_falha_auditoria_geracao_preserva_link_anterior(self):
        token = recovery.gerar(self.path, 21, 1)
        with self.assertRaises(RuntimeError):
            recovery.gerar(self.path, 21, 1, auditar=mock.Mock(side_effect=RuntimeError("ficticio")))
        self.assertEqual(recovery.consumir(self.path, token, "NovaSenhaFicticia!"), 21)

    def test_senha_fraca_e_confirmacao_errada_nao_consumem(self):
        token = recovery.gerar(self.path, 21, 1)
        for nova, confirmar in (("curta", "curta"), ("NovaSenhaFicticia!", "DiferenteFicticia!")):
            r = self.client.post("/recuperar-senha", data={"token": token, "nova": nova, "confirmar": confirmar})
            self.assertEqual(r.status_code, 400)
            self.assertIsNone(self.query("SELECT usado_em FROM usuarios_recuperacao_senha")[0][0])

    def test_paginas_publicas_nao_exibem_contas_e_nao_consumem_por_get(self):
        token = recovery.gerar(self.path, 21, 1)
        for path in ("/esqueci-senha", "/recuperar-senha"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertNotIn("Pessoa Ficticia", r.get_data(as_text=True))
        self.assertIsNone(self.query("SELECT usado_em FROM usuarios_recuperacao_senha")[0][0])
        self.assertEqual(self.client.get("/recuperar-senha").headers["Referrer-Policy"], "no-referrer")
        self.assertIn("Esqueci minha senha", self.client.get("/login").get_data(as_text=True))

    def test_rota_administrativa_exige_admin_e_url_independe_do_host(self):
        endpoint = "/admin/usuarios/21/recuperacao-senha"
        self.assertEqual(self.client.post(endpoint).status_code, 302)
        for uid in (21, 22, 23):
            self.assertEqual(self.logged(uid).post(endpoint).status_code, 403)
        administrator = self.logged()
        cookie_name = self.app.config["SESSION_COOKIE_NAME"]
        administrator.set_cookie(cookie_name, administrator.get_cookie(cookie_name).value, domain="intruso.invalid")
        response = administrator.post(endpoint, base_url="http://intruso.invalid")
        self.assertEqual(response.status_code, 200)
        link = response.json["url"]
        self.assertTrue(link.startswith("https://endemias.vsatt.com.br/recuperar-senha#"))
        token = link.split("#")[1]
        self.assertIn("no-store", response.headers["Cache-Control"])
        events = self.query("SELECT detalhes_json FROM auditoria_eventos WHERE acao='usuario_recuperacao_gerada'")
        self.assertEqual(len(events), 1)
        self.assertNotIn(token, json.dumps([r[0] for r in events]))

    def test_paginas_de_recuperacao_publicas_no_perfil_externo(self):
        external = app.create_app({"DB_PATH": self.path, "TESTING": True,
            "SECRET_KEY": "chave-sintetica-com-mais-de-32-caracteres", "ACESSO_EXTERNO": True,
            "TRUSTED_HOSTS": ["endemias.vsatt.com.br"]})
        client = external.test_client()
        headers = {"CF-Connecting-IP": "203.0.113.20", "X-Forwarded-Proto": "https"}
        for path in ("/esqueci-senha", "/recuperar-senha"):
            response = client.get(path, base_url="https://endemias.vsatt.com.br", headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response.headers["Cache-Control"])
        response = client.post("/recuperar-senha", base_url="https://endemias.vsatt.com.br", headers=headers, data={"token": "x" * 17000})
        self.assertEqual(response.status_code, 413)

    def test_rotas_exigem_csrf(self):
        self.app.config["WTF_CSRF_ENABLED"] = True
        self.assertEqual(self.logged().post("/admin/usuarios/21/recuperacao-senha").status_code, 400)
        self.assertEqual(self.client.post("/recuperar-senha").status_code, 400)

    def test_limite_de_tentativas_nao_bloqueia_a_conta(self):
        for _ in range(10):
            response = self.client.post("/recuperar-senha", data={"token": "x" * 43, "nova": "NovaSenhaFicticia!", "confirmar": "NovaSenhaFicticia!"})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/recuperar-senha").status_code, 429)
        self.assertEqual(self.query("SELECT ativo FROM usuarios WHERE id_usuario=21")[0][0], 1)

    def test_limite_emissao_preserva_ultimo_link(self):
        client = self.logged()
        for _ in range(20):
            last = client.post("/admin/usuarios/21/recuperacao-senha")
            self.assertEqual(last.status_code, 200)
        token = last.json["url"].split("#")[1]
        self.assertEqual(client.post("/admin/usuarios/21/recuperacao-senha").status_code, 429)
        self.assertEqual(recovery.consumir(self.path, token, "NovaSenhaFicticia!"), 21)

    def test_conclusao_limpa_bloqueio_usuario_ip_e_audita_sem_segredo(self):
        token = recovery.gerar(self.path, 21, 1)
        key = "127.0.0.1:ficticio21"
        for _ in range(5):
            auth.registrar_login_falha_db(lambda: db.connect(self.path), key)
        response = self.client.post("/recuperar-senha", data={"token": token, "nova": "NovaSenhaFicticia!", "confirmar": "NovaSenhaFicticia!"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(auth.login_bloqueado_db(lambda: db.connect(self.path), key))
        event = self.query("SELECT * FROM auditoria_eventos WHERE acao='usuario_senha_recuperada'")[0]
        self.assertEqual(event["entidade_id"], "21")
        self.assertIsNone(event["usuario_id"])
        self.assertNotIn(token, str(dict(event)))
        self.assertNotIn("NovaSenhaFicticia!", str(dict(event)))

    def test_url_configurada_exige_https_sem_usuario_query_ou_fragmento(self):
        for base in ("http://endemias.vsatt.com.br", "https://user@vsatt.com.br", "https://vsatt.com.br/?x=1", "https://vsatt.com.br/#x"):
            with self.assertRaises(ValueError):
                recovery.url_publica("ficticio", base)


if __name__ == "__main__":
    unittest.main()
