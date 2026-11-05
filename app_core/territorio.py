"""Identidade territorial para consultas que cruzam fontes de cadastro."""

import re


def quarteirao_canonico(value):
    """Unifica Q1/Q0001 sem transformar uma fração como 1.1 em Q1."""
    if value is None:
        return None
    texto = str(value).strip()
    if not texto:
        return None
    if re.fullmatch(r"[0-9]+(?:\.0+)?", texto):
        return str(int(texto.split(".")[0]))
    if re.fullmatch(r"[0-9]+\.[0-9]+", texto):
        inteiro, fracao = texto.split(".", 1)
        return f"{int(inteiro)}.{fracao}"
    return texto


def chave_territorial(id_localidade, quarteirao):
    localidade = str(id_localidade).strip() if id_localidade is not None else ""
    numero = quarteirao_canonico(quarteirao)
    if not localidade or numero is None:
        return None
    return f"{localidade}:{numero}"
