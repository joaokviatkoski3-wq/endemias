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
PREFIXOS_LOGRADOURO = {
    "rua", "avenida", "rodovia", "estrada", "travessa", "alameda", "viela",
}
ARTIGOS_LOGRADOURO = {"da", "de", "do", "das", "dos"}


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


def sem_prefixo_logradouro(value):
    tokens = normalizar_logradouro(value).split()
    while tokens and tokens[0] in PREFIXOS_LOGRADOURO:
        tokens.pop(0)
    return " ".join(tokens)


def _singular_simples(token):
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def nucleo_logradouro(value):
    """Forma auxiliar tolerante a artigos e singular/plural para sugestoes."""
    return " ".join(
        _singular_simples(token)
        for token in sem_prefixo_logradouro(value).split()
        if token not in ARTIGOS_LOGRADOURO
    )


def _levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    anterior = list(range(len(b) + 1))
    for indice_a, char_a in enumerate(a, 1):
        atual = [indice_a]
        for indice_b, char_b in enumerate(b, 1):
            custo = 0 if char_a == char_b else 1
            atual.append(
                min(atual[indice_b - 1] + 1, anterior[indice_b] + 1, anterior[indice_b - 1] + custo)
            )
        anterior = atual
    return anterior[-1]


def _similaridade_texto(a, b):
    tamanho = max(len(a or ""), len(b or ""), 1)
    return round((1 - (_levenshtein(a or "", b or "") / tamanho)) * 100)


def similaridade_logradouro(a, b):
    """Pontua uma sugestao; nunca deve ser usada como confirmacao automatica."""
    normal_a = normalizar_logradouro(a)
    normal_b = normalizar_logradouro(b)
    if normal_a == normal_b:
        return 100, "mesma grafia normalizada"
    sem_prefixo_a = sem_prefixo_logradouro(a)
    sem_prefixo_b = sem_prefixo_logradouro(b)
    if sem_prefixo_a == sem_prefixo_b:
        return 98, "variação no tipo do logradouro"
    nucleo_a = nucleo_logradouro(a)
    nucleo_b = nucleo_logradouro(b)
    if nucleo_a and nucleo_a == nucleo_b:
        return 96, "variação de artigo ou singular/plural"
    score = max(
        _similaridade_texto(normal_a, normal_b),
        _similaridade_texto(sem_prefixo_a, sem_prefixo_b),
        _similaridade_texto(nucleo_a, nucleo_b),
    )
    return score, "nomes semelhantes"
