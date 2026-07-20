import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask
from PIL import Image
from werkzeug.datastructures import FileStorage

from blueprints.esporotricose import (
    AnexoImagemInvalida,
    _miniatura_path,
    _salvar_upload_anexo,
    _validar_upload_anexo,
    baixar_anexo_doente,
)


class EsporotricoseAnexosTests(unittest.TestCase):
    @staticmethod
    def _imagem_upload(formato, nome, modo="RGB"):
        stream = io.BytesIO()
        cor = (20, 80, 160, 120) if modo == "RGBA" else (20, 80, 160)
        imagem = Image.new(modo, (24, 18), cor)
        imagem.save(stream, format=formato)
        imagem.close()
        stream.seek(0)
        return FileStorage(stream=stream, filename=nome)

    def test_png_com_transparencia_e_convertido_para_pdf(self):
        arquivo = self._imagem_upload("PNG", "foto do animal.png", modo="RGBA")
        meta, erro = _validar_upload_anexo(arquivo)
        self.assertEqual(erro, "")

        with tempfile.TemporaryDirectory() as tmpdir:
            anexo = _salvar_upload_anexo(arquivo, meta, Path(tmpdir))
            self.assertEqual(anexo["mime_type"], "application/pdf")
            self.assertEqual(anexo["nome_original"], "foto do animal.pdf")
            self.assertEqual(anexo["caminho"].suffix, ".pdf")
            self.assertTrue(anexo["caminho"].read_bytes().startswith(b"%PDF"))
            miniatura = _miniatura_path(anexo["caminho"])
            self.assertTrue(miniatura.exists())
            self.assertTrue(miniatura.read_bytes().startswith(b"RIFF"))

    def test_jfif_e_reconhecido_como_imagem_e_convertido(self):
        arquivo = self._imagem_upload("JPEG", "animal.jfif")
        meta, erro = _validar_upload_anexo(arquivo)
        self.assertEqual(erro, "")
        self.assertEqual(meta["ext"], ".jfif")

        with tempfile.TemporaryDirectory() as tmpdir:
            anexo = _salvar_upload_anexo(arquivo, meta, Path(tmpdir))
            self.assertEqual(anexo["nome_original"], "animal.pdf")
            self.assertEqual(anexo["mime_type"], "application/pdf")
            self.assertTrue(anexo["caminho"].read_bytes().startswith(b"%PDF"))
            self.assertTrue(_miniatura_path(anexo["caminho"]).exists())

    def test_pdf_enviado_permanece_inalterado(self):
        conteudo = b"%PDF-1.4\nconteudo de teste\n%%EOF"
        arquivo = FileStorage(stream=io.BytesIO(conteudo), filename="receita.pdf")
        meta, erro = _validar_upload_anexo(arquivo)
        self.assertEqual(erro, "")

        with tempfile.TemporaryDirectory() as tmpdir:
            anexo = _salvar_upload_anexo(arquivo, meta, Path(tmpdir))
            self.assertEqual(anexo["nome_original"], "receita.pdf")
            self.assertEqual(anexo["mime_type"], "application/pdf")
            self.assertEqual(anexo["caminho"].read_bytes(), conteudo)

    def test_imagem_corrompida_e_rejeitada_sem_deixar_arquivo(self):
        arquivo = FileStorage(stream=io.BytesIO(b"nao e uma imagem"), filename="foto.jpeg")
        meta, erro = _validar_upload_anexo(arquivo)
        self.assertEqual(erro, "")

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(AnexoImagemInvalida):
                _salvar_upload_anexo(arquivo, meta, Path(tmpdir))
            self.assertEqual(list(Path(tmpdir).iterdir()), [])

    def test_download_aceita_linha_sqlite_e_entrega_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "teste.db"
            anexos_dir = base / "anexos"
            arquivo_pdf = anexos_dir / "esporotricose_doentes" / "000001" / "anexo.pdf"
            arquivo_pdf.parent.mkdir(parents=True)
            conteudo = b"%PDF-1.4\nteste\n%%EOF"
            arquivo_pdf.write_bytes(conteudo)

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """CREATE TABLE esporotricose_doentes_anexos (
                           id_anexo INTEGER PRIMARY KEY,
                           nome_original TEXT,
                           caminho_rel TEXT,
                           mime_type TEXT
                       )"""
                )
                conn.execute(
                    """INSERT INTO esporotricose_doentes_anexos
                       (id_anexo, nome_original, caminho_rel, mime_type)
                       VALUES (1, 'anexo.pdf', 'esporotricose_doentes/000001/anexo.pdf', 'application/pdf')"""
                )
                conn.commit()
            finally:
                conn.close()

            app = Flask(__name__)
            app.config.update(DB_PATH=str(db_path), ANEXOS_DIR=str(anexos_dir))
            with app.test_request_context("/download?inline=1"):
                resposta = baixar_anexo_doente.__wrapped__(1)
                try:
                    resposta.direct_passthrough = False
                    self.assertEqual(resposta.status_code, 200)
                    self.assertEqual(resposta.mimetype, "application/pdf")
                    self.assertEqual(resposta.get_data(), conteudo)
                finally:
                    resposta.close()


if __name__ == "__main__":
    unittest.main()
