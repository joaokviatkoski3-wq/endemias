import zipfile

import werkzeug.utils


XLSX_MAGIC = b"PK\x03\x04"
XLSX_REQUIRED_ENTRIES = {"[Content_Types].xml", "xl/workbook.xml"}


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
            entradas = set(zf.namelist())
    except zipfile.BadZipFile:
        return False, nome_seguro, f"'{nome_original}' nao e um arquivo XLSX valido"
    finally:
        file_storage.seek(0)
    if not XLSX_REQUIRED_ENTRIES.issubset(entradas):
        return False, nome_seguro, f"'{nome_original}' nao possui estrutura XLSX esperada"
    return True, nome_seguro, ""
