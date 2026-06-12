import unicodedata


LOCALIDADES_PADRAO = {
    "sede": "Sede",
    "centro": "Sede",
    "cachoeira": "Cachoeira",
    "graziela": "Graziela",
    "grasiela": "Graziela",
    "lamenha": "Lamenha",
    "paraiso": "Para\u00edso",
    "roma": "Roma",
    "rosana": "Rosana",
    "santa maria": "Santa Maria",
    "sao francisco": "S\u00e3o Francisco",
    "sao joao batista": "S\u00e3o Jo\u00e3o Batista",
    "sao venancio": "S\u00e3o Ven\u00e2ncio",
    "tamboara": "Tamboara",
    "tangua": "Tangu\u00e1",
    "tranqueira": "Tranqueira",
    "capivara dos manfron": "Capivara dos Manfron",
}


def normalizar_localidade(value):
    text = _text(value)
    if not text:
        return None
    key = _sem_acentos(text).lower()
    return LOCALIDADES_PADRAO.get(key, text.title() if text.isupper() or text.islower() else text)


def _text(value):
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    return " ".join(text.split())


def _sem_acentos(value):
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))
