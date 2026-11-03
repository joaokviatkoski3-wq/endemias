import zipfile

import werkzeug.utils


XLSX_MAGIC = b"PK\x03\x04"
XLSX_REQUIRED_ENTRIES = {"[Content_Types].xml", "xl/workbook.xml"}
XLSX_MAX_EXPANDED = 512 * 1024 * 1024
XLSX_MAX_ENTRIES = 10000


def validar_arquivo_xlsx(file_storage):
    """Valida extensao, assinatura e estrutura minima de um arquivo XLSX."""
    nome_original = file_storage.filename or ""
    if not nome_original.lower().endswith(".xlsx"):
        return False, "", f"Extensao invalida: '{nome_original}'"
    nome_seguro = werkzeug.utils.secure_filename(nome_original)
    if not nome_seguro:
        return False, "", "Nome de arquivo invalido"
    cabecalho = file_storage.read(4)
    file_storage.seek(0)
    if cabecalho != XLSX_MAGIC:
        return False, nome_seguro, (
            f"'{nome_original}' nao e um arquivo XLSX valido "
            f"(assinatura inesperada: {cabecalho.hex()})"
        )
    try:
        with zipfile.ZipFile(file_storage.stream) as zf:
            infos = zf.infolist()
            if len(infos) > XLSX_MAX_ENTRIES or sum(i.file_size for i in infos) > XLSX_MAX_EXPANDED:
                return False, nome_seguro, "Planilha excede o limite seguro de conteudo descompactado. Divida o arquivo."
            if any(i.flag_bits & 1 for i in infos):
                return False, nome_seguro, "Planilha protegida por criptografia nao pode ser importada."
            entradas = {i.filename for i in infos}
    except zipfile.BadZipFile:
        return False, nome_seguro, f"'{nome_original}' nao e um arquivo XLSX valido"
    finally:
        file_storage.seek(0)
    if not XLSX_REQUIRED_ENTRIES.issubset(entradas):
        return False, nome_seguro, f"'{nome_original}' nao possui estrutura XLSX esperada"
    return True, nome_seguro, ""
