import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from werkzeug.datastructures import FileStorage

from blueprints.esporotricose import (
    AnexoImagemInvalida,
    _salvar_upload_anexo,
    _validar_upload_anexo,
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


if __name__ == "__main__":
    unittest.main()
