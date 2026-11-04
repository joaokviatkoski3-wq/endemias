"""Criptografa a copia que sai do servidor; os originais permanecem no cofre local."""
from pathlib import Path
import tempfile
import py7zr

from flask import current_app, render_template, request, send_file

from app_core import auth


def senha_exportacao_valida(senha):
    return auth.senha_valida(senha) and len(senha) >= 20


def criptografar(origem, destino, senha):
    if not senha_exportacao_valida(senha):
        raise ValueError('Use uma frase de proteção com pelo menos 20 caracteres, sem sequências triviais.')
    # O conteudo e os nomes internos ficam cifrados; formato 7z/AES-256.
    destino = getattr(destino, 'file', destino)  # TemporaryFile no Windows usa wrapper.
    with py7zr.SevenZipFile(destino, 'w', password=senha, header_encryption=True,
                          filters=[{'id':py7zr.FILTER_COPY},{'id':py7zr.FILTER_CRYPTO_AES256_SHA256}]) as archive:
        archive.write(origem, arcname=Path(origem).name)


def resposta_download(origem):
    if not request.is_secure and request.remote_addr not in {'127.0.0.1','::1'}:
        return render_template('backup_exportar.html',nome=Path(origem).name,bloqueado=True,
            erro='Use o endereço HTTPS oficial para baixar cópias. A frase de proteção não deve circular sem criptografia na rede local.'),403
    erro = None
    if request.method == 'POST':
        senha = request.form.get('senha_backup','')
        if senha != request.form.get('confirmar','') or not senha_exportacao_valida(senha):
            erro = 'As frases devem coincidir e ter ao menos 20 caracteres, sem sequências triviais.'
        else:
            # Usa a pasta privada de uploads ja concedida a conta limitada.
            temporary = tempfile.TemporaryFile(dir=current_app.config['UPLOAD_TEMP'])
            try:
                criptografar(origem, temporary, senha)
                temporary.seek(0)
                response = send_file(temporary,as_attachment=True,
                    download_name=Path(origem).name+'.7z',mimetype='application/x-7z-compressed',
                    conditional=False, etag=False, max_age=0)
                response.call_on_close(temporary.close)
                return response
            except Exception:
                temporary.close()
                raise
    return render_template('backup_exportar.html',nome=Path(origem).name,erro=erro), 400 if erro else 200
