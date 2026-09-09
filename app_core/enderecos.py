"""Regras puras para comparar logradouros e numeros de endereco."""

import re
import unicodedata


ABREVIACOES_LOGRADOURO = {
    "r": "rua", "av": "avenida", "aven": "avenida", "rod": "rodovia",
    "rodv": "rodovia", "estr": "estrada", "tv": "travessa", "trav": "travessa",
    "prof": "professor", "profa": "professora", "dr": "doutor", "dra": "doutora",
    "sr": "senhor", "sra": "senhora", "cel": "coronel", "mal": "marechal",
    "pref": "prefeito", "pres": "presidente", "ver": "vereador", "dep": "deputado",
    "pe": "padre",
}


def normalizar_logradouro(value):
    """Chave de comparacao; a grafia original nunca e alterada por ela."""
    text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(ABREVIACOES_LOGRADOURO.get(token, token) for token in text.split())


def normalizar_numero(value):
    """Normaliza apenas espacos, caixa e marcadores usuais de sem numero."""
    text = " ".join(str(value or "").strip().upper().split())
    compactado = re.sub(r"[^A-Z0-9]", "", text)
    if not text or compactado in {"SN", "SNUMERO", "SEMNUMERO"}:
        return ""
    return text
