"""Normalização compartilhada das respostas de ACS nos formulários Kobo."""

import re

import pandas as pd


def _texto(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    return texto if texto and texto.casefold() not in {"nan", "none"} else None


def normalizar_acs_presente(valor):
    codigo = _texto(valor)
    if not codigo:
        return None
    codigo = codigo.casefold()
    if codigo in ("sim_acs_presente", "sim", "yes", "1", "true", "s"):
        return 1
    if codigo in ("nao_acs_presente", "não_acs_presente", "não", "nao", "no", "0", "false", "n"):
        return 0
    return None


def extrair_codigos_acs(valor):
    """Kobo separa os códigos de ``select_multiple`` por espaços."""
    if valor is None:
        return []
    valores = valor if isinstance(valor, (list, tuple, set)) else re.split(
        r"[\s,;]+", _texto(valor) or ""
    )
    codigos = []
    vistos = set()
    for item in valores:
        codigo = _texto(item)
        if codigo and codigo not in vistos:
            vistos.add(codigo)
            codigos.append(codigo)
    return codigos


def dados_acs(acs_presente_valor, acs_nome_valor):
    """Retorna presença, texto canônico e códigos sem aproveitar resposta residual."""
    presente = normalizar_acs_presente(acs_presente_valor)
    codigos = extrair_codigos_acs(acs_nome_valor) if presente == 1 else []
    return presente, " ".join(codigos) if codigos else None, codigos
