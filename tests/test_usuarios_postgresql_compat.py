import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_core import auth
from app_core import usuarios


def _create_users_table(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE usuarios (
                id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                nivel TEXT NOT NULL DEFAULT 'visualizador',
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL,
                acesso_laboratorio INTEGER NOT NULL DEFAULT 0,
                somente_laboratorio INTEGER NOT NULL DEFAULT 0,
                id_agente INTEGER
            )
            """
        )
        conn.execute(
            """CREATE TABLE agentes (
                id_agente INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1
            )"""
        )
        conn.commit()
    finally:
        conn.close()


class UsuariosDualBackendTests(unittest.TestCase):
    def test_sqlite_crud_preserves_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "usuarios.db"
            _create_users_table(path)

            uid = usuarios.criar(
                path,
                {
                    "usuario": " TESTE.ADMIN ",
                    "nome": "Usuario Teste",
                    "senha": "SenhaForte123",
                    "nivel": "admin",
                    "somente_laboratorio": "1",
                },
                agora="2026-07-29T10:00:00",
            )
            listed = usuarios.listar(path)
            previous, new_level = usuarios.editar(
                path,
                uid,
                "nivel",
                "operador",
            )
            target = usuarios.resetar_senha(
                path,
                uid,
                "OutraSenha456",
            )

            conn = sqlite3.connect(path)
            row = conn.execute(
                "SELECT * FROM usuarios WHERE id_usuario=?",
                (uid,),
            ).fetchone()
            conn.close()

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["usuario"], "teste.admin")
        self.assertEqual(listed[0]["acesso_laboratorio"], 1)
        self.assertEqual(listed[0]["somente_laboratorio"], 1)
        self.assertEqual(previous["nivel"], "admin")
        self.assertEqual(new_level, "operador")
        self.assertEqual(target["usuario"], "teste.admin")
        self.assertTrue(auth.verificar_senha("OutraSenha456", row[3])[0])

    def test_user_cannot_disable_own_account(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "usuarios.db"
            _create_users_table(path)
            uid = usuarios.criar(
                path,
                {
                    "usuario": "proprio",
                    "nome": "Proprio Usuario",
                    "senha": "SenhaForte123",
                },
            )

            with self.assertRaisesRegex(ValueError, "propria conta"):
                usuarios.editar(
                    path,
                    uid,
                    "ativo",
                    "0",
                    usuario_atual_id=uid,
                )

    def test_vinculo_com_agente_ativo_e_editavel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "usuarios.db"
            _create_users_table(path)
            conn = sqlite3.connect(path)
            conn.execute(
                "INSERT INTO agentes(id_agente,nome,ativo) VALUES (7,'Adilson',1)"
            )
            conn.commit()
            conn.close()

            uid = usuarios.criar(
                path,
                {
                    "usuario": "adilson.ribas",
                    "nome": "Adilson Ribas",
                    "senha": "SenhaForte123",
                    "id_agente": "7",
                },
            )
            anterior, novo = usuarios.editar(path, uid, "id_agente", "")
            vinculado = usuarios.listar(path)[0]

        self.assertEqual(7, anterior["id_agente"])
        self.assertIsNone(novo)
        self.assertIsNone(vinculado["id_agente"])

    def test_postgresql_insert_uses_returning_identity(self):
        conn = mock.Mock()
        conn.backend = "postgresql"
        conn.execute.return_value.fetchone.return_value = [17]

        uid = usuarios._insert_id(
            conn,
            "INSERT INTO usuarios(usuario) VALUES (?)",
            ("teste",),
        )

        self.assertEqual(uid, 17)
        statement, parameters = conn.execute.call_args.args
        self.assertEqual(
            statement,
            "INSERT INTO usuarios(usuario) VALUES (?) RETURNING id_usuario",
        )
        self.assertEqual(parameters, ("teste",))


if __name__ == "__main__":
    unittest.main()
