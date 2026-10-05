"""Cores estáveis e contrastantes para a exportação KML de microáreas."""

import colorsys
import math


def _pontos(coordenadas):
    if not isinstance(coordenadas, (list, tuple)):
        return
    if len(coordenadas) >= 2 and all(isinstance(valor, (int, float)) for valor in coordenadas[:2]):
        yield coordenadas[0], coordenadas[1]
    else:
        for item in coordenadas:
            yield from _pontos(item)


def _caixa(geometria):
    pontos = list(_pontos(geometria.get("coordinates", [])))
    if not pontos:
        return None
    longitudes, latitudes = zip(*pontos)
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def _distancia_metros(a, b):
    dx = max(0, a[0] - b[2], b[0] - a[2])
    dy = max(0, a[1] - b[3], b[1] - a[3])
    latitude = (a[1] + a[3] + b[1] + b[3]) / 4
    return math.hypot(dx * 111320 * math.cos(math.radians(latitude)), dy * 111320)


def _lab(cor):
    canais = [int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in canais]
    xyz = [
        (r * .4124 + g * .3576 + b * .1805) / .95047,
        r * .2126 + g * .7152 + b * .0722,
        (r * .0193 + g * .1192 + b * .9505) / 1.08883,
    ]
    x, y, z = [v ** (1 / 3) if v > .008856 else 7.787 * v + 16 / 116 for v in xyz]
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def _diferenca(a, b):
    return math.dist(a, b)


def _paleta(quantidade):
    # 36 matizes e três luminosidades oferecem 216 cores antes de ampliar a
    # paleta; o salto áureo espalha matizes consecutivos pelo círculo cromático.
    matizes = max(36, math.ceil(quantidade / 6))
    cores = []
    for indice in range(matizes):
        matiz = ((indice * 137.50776405) % 360) / 360
        for luminosidade in (.42, .56, .70):
            for saturacao in (.72, .88):
                rgb = colorsys.hls_to_rgb(matiz, luminosidade, saturacao)
                cor = "#" + "".join(f"{round(canal * 255):02x}" for canal in rgb)
                if cor not in cores:
                    cores.append(cor)
    return cores


def atribuir(registros, geometrias, limite_metros=200):
    """Distribui cores únicas; áreas próximas recebem prioridade de contraste."""
    caixas = {}
    for r in registros:
        itens = [geometrias[(r["id_localidade"], q)]["geometry"]
                 for q in r["quarteiroes"] if (r["id_localidade"], q) in geometrias]
        itens.extend(p["geometry"] for p in r["partes"])
        caixas[r["id_microarea"]] = [caixa for geometria in itens if (caixa := _caixa(geometria))]
    ids = sorted(caixas)
    vizinhos = {identificador: set() for identificador in ids}
    for indice, a in enumerate(ids):
        for b in ids[indice + 1:]:
            if any(_distancia_metros(x, y) <= limite_metros for x in caixas[a] for y in caixas[b]):
                vizinhos[a].add(b)
                vizinhos[b].add(a)

    paleta = _paleta(len(ids))
    laboratorios = {cor: _lab(cor) for cor in paleta}
    disponiveis = set(paleta)
    cores = {}
    menor_global = {cor: float("inf") for cor in paleta}
    for identificador in sorted(ids, key=lambda item: (-len(vizinhos[item]), item)):
        inicio = identificador * 37 % len(paleta)
        ordenadas = paleta[inicio:] + paleta[:inicio]
        vizinhas = [laboratorios[cores[v]] for v in vizinhos[identificador] if v in cores]
        cor = max(((indice, candidata) for indice, candidata in enumerate(ordenadas)
                   if candidata in disponiveis), key=lambda item: (
            min((_diferenca(laboratorios[item[1]], outra) for outra in vizinhas), default=float("inf")),
            menor_global[item[1]], -item[0],
        ))[1]
        cores[identificador] = cor
        disponiveis.remove(cor)
        for candidata in disponiveis:
            menor_global[candidata] = min(menor_global[candidata], _diferenca(laboratorios[candidata], laboratorios[cor]))
    return cores


def cor_kml(cor, alpha="ff"):
    """Converte #RRGGBB para a ordem KML AABBGGRR."""
    return alpha + cor[5:7] + cor[3:5] + cor[1:3]


def contorno(cor):
    return "#" + "".join(f"{round(int(cor[i:i + 2], 16) * .42):02x}" for i in (1, 3, 5))
