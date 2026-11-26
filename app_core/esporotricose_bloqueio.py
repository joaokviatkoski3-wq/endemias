
"""Recorte territorial do raio de bloqueio de Esporotricose."""
import json
import math
from functools import lru_cache
from pathlib import Path

from shapely import make_valid
from shapely.geometry import Polygon, box, mapping, shape

from app_core import registro_geografico


RAIO_METROS = 150


def _circulo(latitude, longitude, raio):
    """Anel que segue a distância em metros sobre a Terra."""
    lat, lon = math.radians(latitude), math.radians(longitude)
    distance = raio / 6371000
    pontos = []
    for grau in range(0, 360, 3):
        rumo = math.radians(grau)
        y = math.asin(math.sin(lat)*math.cos(distance) + math.cos(lat)*math.sin(distance)*math.cos(rumo))
        x = lon + math.atan2(math.sin(rumo)*math.sin(distance)*math.cos(lat),
                             math.cos(distance) - math.sin(lat)*math.sin(y))
        pontos.append((math.degrees(x), math.degrees(y)))
    return Polygon(pontos)


def coordenadas(animal):
    try:
        lat, lon = float(animal.get("latitude")), float(animal.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 < lat < 90 and -180 < lon < 180) or (lat, lon) == (0, 0):
        return None
    return lat, lon


@lru_cache(maxsize=2)
def _vias(arquivo, versao):
    conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
    return tuple((shape(f["geometry"]), f["properties"]["nome"]) for f in conteudo["features"])


def _vias_no_recorte(base_dir, janela):
    arquivo = Path(base_dir) / "dados_referencia" / "esporotricose_ruas.geojson"
    marcadores = {}
    features = []
    try:
        vias = _vias(arquivo, arquivo.stat().st_mtime_ns)
    except (OSError, ValueError):
        return {"type": "FeatureCollection", "features": []}, []
    for geom, nome in vias:
        if not geom.intersects(janela):
            continue
        recorte = geom.intersection(janela)
        if recorte.length <= 0:
            continue
        features.append({"type": "Feature", "properties": {"nome": nome}, "geometry": mapping(recorte)})
        if not nome:
            continue
        for linha in getattr(recorte, "geoms", (recorte,)):
            if linha.geom_type == "LineString" and (nome not in marcadores or linha.length > marcadores[nome].length):
                marcadores[nome] = linha
    ordenados = sorted(marcadores.items(), key=lambda item: item[1].length, reverse=True)
    return {"type": "FeatureCollection", "features": features}, [
        {"nome": nome, "linha": [[y, x] for x, y in linha.coords]} for nome, linha in ordenados[:14]
    ]


def mapa(target, base_dir, centro):
    lat, lon = centro
    raio = _circulo(lat, lon, RAIO_METROS)
    _, sul, _, norte = _circulo(lat, lon, RAIO_METROS * 1.32).bounds
    oeste, _, leste, _ = _circulo(lat, lon, RAIO_METROS * 1.68).bounds
    janela = box(oeste, sul, leste, norte)
    camada = {"type": "FeatureCollection", "features": []}
    atingidos = []
    try:
        base = registro_geografico.geojson_ativo(target, base_dir)
    except ValueError:
        base = None
    for feature in (base or {}).get("features", []):
        geometria = shape(feature["geometry"])
        if not geometria.is_valid:
            geometria = make_valid(geometria)
        if not geometria.intersects(janela):
            continue
        props = feature.get("properties") or {}
        codigo = props.get("id_quart") or props.get("id_Q") or ""
        localidade = props.get("Localidade_nome") or props.get("Localidade_origem") or props.get("Localidade") or ""
        if str(localidade).isdecimal():
            localidade = ""
        area = geometria.intersection(raio).area
        if area > 0:
            atingidos.append({"codigo": str(codigo), "localidade": str(localidade),
                              "parcial": not raio.covers(geometria)})
        camada["features"].append({"type": "Feature", "properties": {"codigo": codigo, "atingido": area > 0},
                                   "geometry": mapping(geometria.intersection(janela))})
    ruas, rotulos = _vias_no_recorte(base_dir, janela)
    return {"ruas": ruas, "rotulos_ruas": rotulos, "centro": list(centro), "raio_metros": RAIO_METROS, "circulo": mapping(raio), "quarteiroes": camada,
            "atingidos": sorted(atingidos, key=lambda item: (item["localidade"], item["codigo"])),
            "camada_disponivel": base is not None}
