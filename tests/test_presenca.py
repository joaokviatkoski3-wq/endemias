"""Presenca em contas sinteticas, sessoes independentes e fronteiras de acesso."""

import contextlib
import io
import json
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import app
import criar_banco
import servir
from app_core import auth, db, presenca, termos_uso


class PresencaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "sintetico.db")
        with mock.patch.object(criar_banco, "BANCO", self.path), contextlib.redirect_stdout(io.StringIO()):
            criar_banco.main()
        self.hash = auth.hash_senha("SenhaFicticia123!")
        conn = sqlite3.connect(self.path)
        conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=1", (self.hash,))
        for uid, role in ((21, "usuario"), (22, "operador"), (23, "visualizador")):
            conn.execute("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em) VALUES (?,?,?,?,?,?)",
                         (uid, f"ficticio{uid}", f"Pessoa Ficticia {uid}", self.hash, role, "2026-11-04"))
        conn.commit(); conn.close()
        self.app = app.create_app({"DB_PATH": self.path, "TESTING": True,
                                   "WTF_CSRF_ENABLED": False, "REQUIRE_SESSION_TOKEN": True})
        self.user = {"id_usuario": 21, "senha_hash": self.hash}

    def sql(self, sql, params=()):
        conn = db.connect(self.path)
        try:
            rows = conn.execute(sql, params).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def logged(self, uid=21, nonce="sessao-ficticia", application=None):
        application = application or self.app
        client = application.test_client()
        base_url = "https://" + application.config["TRUSTED_HOSTS"][0] if application.config.get("ACESSO_EXTERNO") else "http://localhost"
        with application.app_context(), client.session_transaction(base_url=base_url) as s:
            s.update(uid=uid, auth_token=auth.token_sessao(self.hash), nome="Pessoa Ficticia",
                     presenca_id=nonce, _permanent=True, csrf_token="csrf-ficticio-estavel",
                     termo_aceito=termos_uso.VERSAO + ":" + termos_uso.HASH)
        return client

    def status(self, now=1000, uid=21):
        return next(u for u in presenca.resumo(self.path, agora=now)["usuarios"] if u["id_usuario"] == uid)

    def test_online_expira_e_ultima_presenca_permanece(self):
        self.assertIsNone(self.status()["ultima_presenca"])
        presenca.confirmar(self.path, self.user, "sessao1", agora=1000)
        self.assertTrue(self.status(now=1120)["online"])
        self.assertFalse(self.status(now=1121)["online"])
        self.assertEqual(self.status(now=1121)["ultima_presenca"], "1970-01-01T00:16:40+00:00")

    def test_multiplos_aparelhos_sair_de_um_preserva_outro(self):
        for sid in ("aparelho1", "aparelho2"):
            presenca.confirmar(self.path, self.user, sid, agora=1000)
        presenca.encerrar(self.path, self.user, "aparelho1", agora=1010)
        self.assertTrue(self.status(now=1011)["online"])
        presenca.encerrar(self.path, self.user, "aparelho2", agora=1020)
        self.assertFalse(self.status(now=1020)["online"])

    def test_mesma_sessao_em_varias_abas_e_contada_uma_vez(self):
        for now in (1000, 1001, 1002):
            presenca.confirmar(self.path, self.user, "mesma-sessao", agora=now)
        self.assertEqual(len(self.sql("SELECT * FROM usuarios_presenca_sessoes")), 1)
        self.assertEqual(presenca.resumo(self.path, agora=1002)["online_total"], 1)
        self.assertEqual(self.sql("SELECT ultima_presenca FROM usuarios_presenca")[0][0], 1000)

    def test_logout_antes_de_sinal_e_sinal_atrasado_nao_reabrem_sessao(self):
        presenca.encerrar(self.path, self.user, "mesma-sessao", agora=1000)
        presenca.confirmar(self.path, self.user, "mesma-sessao", agora=1030)
        self.assertFalse(self.status(now=1030)["online"])
        self.assertEqual(self.sql("SELECT ultima_presenca FROM usuarios_presenca")[0][0], 1000)

    def test_sinais_concorrentes_com_logout_nao_reabrem(self):
        presenca.confirmar(self.path, self.user, "mesma-sessao", agora=1000)
        def run(i):
            if i == 0:
                presenca.encerrar(self.path, self.user, "mesma-sessao", agora=1050)
            else:
                presenca.confirmar(self.path, self.user, "mesma-sessao", agora=1051)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(run, range(4)))
        self.assertFalse(self.status(now=1052)["online"])

    def test_troca_de_senha_e_conta_inativa_invalidam_online(self):
        presenca.confirmar(self.path, self.user, "sessao", agora=1000)
        self.sql("UPDATE usuarios SET senha_hash=? WHERE id_usuario=21", (auth.hash_senha("SenhaNovaFicticia!"),))
        self.assertFalse(self.status(now=1001)["online"])
        self.sql("UPDATE usuarios SET senha_hash=?,ativo=0 WHERE id_usuario=21", (self.hash,))
        self.assertFalse(self.status(now=1001)["online"])

    def test_limpeza_de_sessoes_nao_apaga_ultimo_online(self):
        presenca.confirmar(self.path, self.user, "antiga", agora=1000)
        presenca.confirmar(self.path, {"id_usuario": 22, "senha_hash": self.hash}, "atual", agora=100000)
        self.assertFalse(self.sql("SELECT 1 FROM usuarios_presenca_sessoes WHERE sessao_hash='antiga'"))
        self.assertIsNotNone(self.status(now=100000)["ultima_presenca"])

    def test_relogio_anterior_nao_regride_ultima_presenca(self):
        presenca.confirmar(self.path, self.user, "a", agora=2000)
        presenca.confirmar(self.path, self.user, "b", agora=1000)
        self.assertEqual(self.sql("SELECT ultima_presenca FROM usuarios_presenca WHERE usuario_id=21")[0][0], 2000)

    def test_heartbeat_nao_aceita_identidade_do_cliente(self):
        client = self.logged()
        response = client.post("/api/presenca", json={"uid": 22, "usuario_id": 22})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row[0] for row in self.sql("SELECT usuario_id FROM usuarios_presenca")], [21])

    def test_consulta_so_admin_sem_expor_credencial_ou_sessao(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get("/admin/usuarios/presenca").status_code, 302)
        self.assertEqual(anonymous.post("/api/presenca").status_code, 302)
        for uid in (21, 22, 23):
            self.assertEqual(self.logged(uid).get("/admin/usuarios/presenca").status_code, 403)
        self.logged().post("/api/presenca")
        response = self.logged(1).get("/admin/usuarios/presenca")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        raw = response.get_data(as_text=True)
        for secret in (self.hash, "senha_vinculo", "sessao_hash", "sessao-ficticia", "csrf-ficticio"):
            self.assertNotIn(secret, raw)

    def test_heartbeat_exige_csrf_e_apos_expirar_sessao_nao_grava(self):
        self.app.config["WTF_CSRF_ENABLED"] = True
        self.assertEqual(self.logged().post("/api/presenca").status_code, 400)
        self.app.config["WTF_CSRF_ENABLED"] = False
        client = self.logged()
        self.sql("UPDATE usuarios SET senha_hash=? WHERE id_usuario=21", (auth.hash_senha("NovaSenhaFicticia!"),))
        self.assertEqual(client.post("/api/presenca").status_code, 302)
        self.assertFalse(self.status()["online"])

    def test_polling_nao_renova_cookie_permanente(self):
        user = self.logged()
        admin = self.logged(1)
        self.assertIsNone(user.post("/api/presenca").headers.get("Set-Cookie"))
        self.assertIsNone(admin.get("/admin/usuarios/presenca").headers.get("Set-Cookie"))
        self.assertIsNotNone(user.get("/minha-senha").headers.get("Set-Cookie"))

    def test_logout_real_encerra_apenas_sua_sessao(self):
        first = self.logged(nonce="primeiro")
        second = self.logged(nonce="segundo")
        first.post("/api/presenca"); second.post("/api/presenca")
        self.assertEqual(first.post("/logout").status_code, 302)
        self.assertTrue(self.status(now=time.time())["online"])
        second.post("/logout")
        self.assertFalse(self.status(now=time.time())["online"])

    def test_sessao_legada_usa_csrf_estavel_sem_renovar_cookie(self):
        client = self.logged()
        with client.session_transaction() as s:
            s.pop("presenca_id")
        one = client.post("/api/presenca")
        client.post("/api/presenca")
        self.assertIsNone(one.headers.get("Set-Cookie"))
        self.assertEqual(len(self.sql("SELECT * FROM usuarios_presenca_sessoes")), 1)

    def test_entrada_local_e_externa_compartilham_resumo(self):
        external = app.create_app({"DB_PATH": self.path, "TESTING": True, "WTF_CSRF_ENABLED": False,
            "ACESSO_EXTERNO": True, "TRUSTED_HOSTS": ["endemias.vsatt.com.br"]})
        local = servir.local_application(external, "127.0.0.1")
        x, y = self.logged(application=external), self.logged(application=local)
        # Cookies das entradas sao independentes, mas os registros usam o mesmo banco.
        header = {"CF-Connecting-IP": "203.0.113.20", "X-Forwarded-Proto": "https"}
        self.assertEqual(x.post("/api/presenca", base_url="https://endemias.vsatt.com.br", headers=header).status_code, 200)
        self.assertEqual(y.post("/api/presenca").status_code, 200)
        self.assertEqual(len(self.sql("SELECT * FROM usuarios_presenca_sessoes")), 2)
        self.assertEqual(presenca.resumo(self.path)["online_total"], 1)

    def test_cookie_expirado_nao_pode_confirmar_presenca(self):
        with self.app.app_context():
            serializer = self.app.session_interface.get_signing_serializer(self.app)
            with mock.patch("itsdangerous.timed.TimestampSigner.get_timestamp",
                            return_value=int(time.time() - self.app.permanent_session_lifetime.total_seconds() - 60)):
                cookie = serializer.dumps({"uid": 21, "auth_token": auth.token_sessao(self.hash), "_permanent": True})
        client = self.app.test_client()
        client.set_cookie(self.app.config["SESSION_COOKIE_NAME"], cookie)
        self.assertEqual(client.post("/api/presenca").status_code, 302)
        self.assertFalse(self.status(now=time.time())["online"])

    def test_pagina_administrativa_carrega_colunas_e_script(self):
        html = self.logged(1).get("/admin/usuarios").get_data(as_text=True)
        for text in ("Última vez online", "Presença", "presenca-resumo", "usuarios_presenca.js", "presenca.js"):
            self.assertIn(text, html)

    def test_conta_exclusiva_laboratorio_pode_confirmar_presenca_antes_do_termo(self):
        self.app.config["TERMOS_USO_ENABLED"] = True
        self.sql("UPDATE usuarios SET somente_laboratorio=1 WHERE id_usuario=21")
        client = self.logged()
        with client.session_transaction() as s:
            s.pop("termo_aceito")
        self.assertEqual(client.post("/api/presenca").status_code, 200)
        self.assertEqual(client.get("/admin/usuarios/presenca").status_code, 302)


if __name__ == "__main__":
    unittest.main()
