"""Textos seguros para planilhas, preservando numeros e coordenadas tipados."""

import math
import re


def campo_csv(value, *, numerico=False):
    if value is None:
        return value
    text = str(value)
    # Apenas numeros inteiros/decimais finitos em colunas declaradas numericas.
    if numerico and re.fullmatch(r'[+-]?\d+(?:\.\d+)?', text) and math.isfinite(float(text)):
        return value
    if text.lstrip(''.join(chr(i) for i in range(33)) + '\ufeff').startswith(('=', '+', '-', '@', '＝', '＋', '－', '＠')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return value
