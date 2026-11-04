"""Fronteiras de privilegio em dados inteiramente sinteticos."""

import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
import criar_banco
from app_core import auth, db, permissoes, recuperacao_senha, usuarios, sqlite_maintenance, modules


class SuperadminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "sintetico.db")
        with mock.patch.object(criar_banco, "BANCO", self.path), contextlib.redirect_stdout(io.StringIO()):
            criar_banco.main()
        self.hash = auth.hash_senha("SenhaFicticia123!")
        c = sqlite3.connect(self.path)
        c.execute("UPDATE usuarios SET nivel='superadmin',senha_hash=? WHERE id_usuario=1", (self.hash,))
        for uid, level in ((21, "admin"), (22, "admin"), (23, "operador"), (24, "visualizador"), (25, "usuario")):
            c.execute("INSERT INTO usuarios(id_usuario,usuario,nome,nivel,senha_hash,criado_em) VALUES(?,?,?,?,?,?)",
                      (uid, f"ficticio{uid}", f"Pessoa Ficticia {uid}", level, self.hash, "2026-11-04"))
        c.commit(); c.close()
        self.app = app.create_app({"DB_PATH": self.path, "TESTING": True, "WTF_CSRF_ENABLED": False})

    def logged(self, uid):
        client = self.app.test_client()
        with self.app.app_context(), client.session_transaction() as s:
            s.update(uid=uid, nome="Pessoa Ficticia", auth_token=auth.token_sessao(self.hash))
        return client

    def row(self, uid):
        return db.query_one(self.path, "SELECT * FROM usuarios WHERE id_usuario=?", (uid,))

    def test_admin_nao_acessa_operacoes_tecnicas_por_url(self):
        client = self.logged(21)
        for method, url in (("GET", "/admin/sistema"), ("GET", "/api/admin/sistema/diagnostico"),
            ("POST", "/admin/sistema/backups/criar"), ("POST", "/admin/sistema/backups/restaurar"),
            ("GET", "/admin/sistema/backups/baixar/ficticio.dump"), ("GET", "/admin/sistema/dbml"),
            ("POST", "/admin/sistema/backups/excluir"), ("POST", "/admin/sistema/backups-completos/criar"),
            ("GET", "/admin/sistema/backups-completos/baixar/ficticio.zip"),
            ("POST", "/admin/sistema/backups-completos/excluir"), ("GET", "/api/kobo/config"),
            ("POST", "/api/kobo/config"), ("POST", "/api/kobo/testar"), ("POST", "/liraa/kobo/configurar")):
            with self.subTest(url=url, method=method):
                self.assertEqual(client.open(url, method=method).status_code, 403)

    def test_admin_mantem_gestao_operacional(self):
        client = self.logged(21)
        for url in ("/admin/usuarios", "/admin/usuarios/presenca", "/admin/agentes", "/admin/auditoria", "/processar", "/liraa", "/agenda"):
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 200)
        html = client.get("/processar").get_data(as_text=True)
        self.assertNotIn('id="kobo-token"', html)
        self.assertNotIn('name="uid"', client.get("/liraa").get_data(as_text=True))

    def test_admin_nao_altera_superadmin_outro_admin_ou_a_si(self):
        client = self.logged(21)
        for uid in (1, 21, 22):
            before = self.row(uid)
            for field, value in (("nivel", "usuario"), ("ativo", "0"), ("id_agente", ""), ("senha", "SenhaInvasoraFicticia!"), ("somente_laboratorio", "1")):
                with self.subTest(uid=uid, field=field):
                    self.assertEqual(client.post(f"/admin/usuarios/{uid}/editar", data={"campo":field, "valor":value}).status_code, 400)
            self.assertEqual(client.post(f"/admin/usuarios/{uid}/resetar-senha").status_code, 400)
            self.assertEqual(client.post(f"/admin/usuarios/{uid}/recuperacao-senha").status_code, 400)
            self.assertEqual(self.row(uid), before)

    def test_admin_nao_promove_conta_inferior_para_admin_ou_superadmin(self):
        client = self.logged(21)
        for level in ("admin", "superadmin"):
            self.assertEqual(client.post("/admin/usuarios/24/editar", data={"campo":"nivel","valor":level}).status_code, 400)
            response = client.post("/admin/usuarios/criar", data={"usuario":"elevacao-ficticia", "nome":"Ficticio", "senha":"SenhaFicticia123!", "nivel":level})
            self.assertNotEqual(response.status_code, 302)
            self.assertIsNone(db.query_one(self.path, "SELECT 1 FROM usuarios WHERE usuario='elevacao-ficticia'"))
        self.assertEqual(self.row(24)["nivel"], "visualizador")

    def test_superadmin_gerencia_admin_mas_nao_cria_segundo_superadmin(self):
        client = self.logged(1)
        self.assertEqual(client.post("/admin/usuarios/24/editar", data={"campo":"nivel","valor":"admin"}).status_code, 200)
        self.assertEqual(self.row(24)["nivel"], "admin")
        self.assertEqual(client.post("/admin/usuarios/24/editar", data={"campo":"nivel","valor":"superadmin"}).status_code, 400)
        for field, value in (("nivel","admin"), ("ativo","0")):
            self.assertEqual(client.post("/admin/usuarios/1/editar", data={"campo":field,"valor":value}).status_code, 400)
        self.assertEqual(self.row(1)["nivel"], "superadmin")
        self.assertEqual(self.row(1)["ativo"], 1)

    def test_admin_pode_gerenciar_e_recuperar_conta_inferior(self):
        client = self.logged(21)
        self.assertEqual(client.post("/admin/usuarios/24/editar", data={"campo":"nivel","valor":"operador"}).status_code, 200)
        response = client.post("/admin/usuarios/24/recuperacao-senha")
        self.assertEqual(response.status_code, 200)
        token = response.json["url"].split("#")[1]
        self.assertEqual(recuperacao_senha.consumir(self.path, token, "SenhaNovaFicticia!"), 24)

    def test_link_anterior_a_promocao_nao_recupera_conta_protegida(self):
        token = recuperacao_senha.gerar(self.path, 24, 21)
        # Simula promocao administrativa controlada, nao disponivel pela web.
        c = sqlite3.connect(self.path)
        c.execute("UPDATE usuarios SET nivel='admin' WHERE id_usuario=24")
        c.commit(); c.close()
        with self.assertRaisesRegex(ValueError, "inválido"):
            recuperacao_senha.consumir(self.path, token, "SenhaNovaFicticia!")
        c = sqlite3.connect(self.path)
        c.execute("UPDATE usuarios SET nivel='admin' WHERE id_usuario=1")
        c.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=24")
        c.commit(); c.close()
        with self.assertRaisesRegex(ValueError, "inválido"):
            recuperacao_senha.consumir(self.path, token, "SenhaNovaFicticia!")

    def test_banco_impede_segundo_superadmin(self):
        c = sqlite3.connect(self.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=21")
        finally:
            c.close()

    def test_superadmin_tem_modulos_operacionais_e_tecnicos(self):
        owner = {m.key for m in modules.visible_modules({"nivel":"superadmin"})}
        manager = {m.key for m in modules.visible_modules({"nivel":"admin"})}
        self.assertIn("sistema", owner)
        self.assertNotIn("sistema", manager)
        self.assertIn("processar", manager)
        self.assertTrue(owner.issuperset(manager))

    def test_alterar_role_na_sessao_nao_substitui_role_do_banco(self):
        client = self.logged(21)
        with client.session_transaction() as s:
            s["nivel"] = "superadmin"
        self.assertEqual(client.get("/admin/sistema").status_code, 403)

    def test_core_rejeita_ator_ausente(self):
        with self.assertRaises(ValueError):
            usuarios.resetar_senha(self.path, 1, "SenhaInvasoraFicticia!")
        with self.assertRaises(ValueError):
            usuarios.criar(self.path, {"usuario":"ficticio","nome":"Ficticio","senha":"SenhaFicticia!"})

    def test_migracao_sqlite_legada_preserva_dados_fk_indices_e_sequencia(self):
        path = str(Path(self.tmp.name) / 'legado.db')
        c = sqlite3.connect(path)
        c.executescript("""CREATE TABLE usuarios(id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE, nivel TEXT CHECK(nivel IN ('admin','usuario')), extra TEXT);
            CREATE INDEX idx_usuario_extra ON usuarios(extra);
            CREATE TABLE vinculo(uid INTEGER REFERENCES usuarios(id_usuario));
            INSERT INTO usuarios VALUES(1,'ficticio','admin','preservar');
            INSERT INTO usuarios VALUES(99,'removido','usuario','excluir');
            DELETE FROM usuarios WHERE id_usuario=99;
            INSERT INTO vinculo VALUES(1);""")
        c.execute('PRAGMA foreign_keys=OFF')
        c.execute('BEGIN IMMEDIATE')
        self.assertTrue(sqlite_maintenance._ensure_superadmin(c))
        c.commit()
        c.execute('PRAGMA foreign_keys=ON')
        self.assertEqual(c.execute('SELECT * FROM usuarios').fetchone(), (1,'ficticio','admin','preservar'))
        self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        c.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=1")
        c.execute("INSERT INTO usuarios(usuario,nivel) VALUES('novo','usuario')")
        self.assertGreater(c.execute("SELECT id_usuario FROM usuarios WHERE usuario='novo'").fetchone()[0], 99)
        self.assertIsNotNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='idx_usuario_extra'").fetchone())
        c.close()


if __name__ == "__main__":
    unittest.main()
