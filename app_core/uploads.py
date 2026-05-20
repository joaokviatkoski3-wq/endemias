import werkzeug.utils


XLSX_MAGIC = b"PK\x03\x04"


def validar_arquivo_xlsx(file_storage):
    """
    Valida extensao e assinatura real do arquivo XLSX.
    Retorna (valido: bool, nome_seguro: str, motivo: str).
    """
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
    return True, nome_seguro, ""
