import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import sqlite3

from scripts import validar_banco_teste


ROOT = Path(__file__).resolve().parents[1]


class ValidarBancoTesteTests(unittest.TestCase):
    def test_identifica_mesmo_arquivo_por_alias_fora_da_pasta(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raiz = Path(temp_dir)
            oficial = raiz / "oficial.db"
            alias = raiz / "outro-worktree.db"
            oficial.write_bytes(b"rollback congelado")
            os.link(oficial, alias)

            self.assertTrue(validar_banco_teste.mesmo_arquivo(alias, oficial))
            resultado = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "validar_banco_teste.py"), alias, oficial],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(resultado.returncode, 2)
            self.assertEqual(oficial.read_bytes(), b"rollback congelado")

    def test_aceita_arquivos_distintos(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raiz = Path(temp_dir)
            alvo = raiz / "teste.db"
            oficial = raiz / "oficial.db"
            alvo.write_bytes(b"teste")
            oficial.write_bytes(b"rollback")

            self.assertFalse(validar_banco_teste.mesmo_arquivo(alvo, oficial))
            self.assertEqual(validar_banco_teste.main([str(alvo), str(oficial)]), 0)

    def test_schema_minimo_distingue_banco_completo_de_incompleto(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            banco = Path(temp_dir) / "teste.db"
            conn = sqlite3.connect(banco)
            try:
                conn.execute("CREATE TABLE localidades (id INTEGER)")
                conn.commit()
                self.assertFalse(validar_banco_teste.schema_minimo_valido(banco))
                conn.execute("CREATE TABLE usuarios (id INTEGER)")
                conn.execute("CREATE TABLE visitas (id INTEGER)")
                conn.commit()
            finally:
                conn.close()

            self.assertTrue(validar_banco_teste.schema_minimo_valido(banco))

    def test_arquiva_banco_invalido_sem_perder_conteudo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            banco = Path(temp_dir) / "endemias.db"
            banco.write_bytes(b"banco incompleto")

            arquivado = validar_banco_teste.arquivar_invalido(banco)

            self.assertFalse(banco.exists())
            self.assertTrue(arquivado.name.startswith("endemias.invalido-"))
            self.assertEqual(arquivado.read_bytes(), b"banco incompleto")


if __name__ == "__main__":
    unittest.main()
