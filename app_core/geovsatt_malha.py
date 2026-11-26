"""Agrupamento de geometrias dos quarteirões na malha ativa."""

from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union

from app_core.territorio import chave_territorial


def _partes_poligonais(geometria):
    if geometria.geom_type == "Polygon":
        if not geometria.is_empty:
            yield geometria
    else:
        for parte in getattr(geometria, "geoms", ()):
            yield from _partes_poligonais(parte)


def blocos(malha, chaves=None):
    agrupados = {}
    for indice, feicao in enumerate(malha["features"]):
        props = feicao["properties"]
        numero = props.get("id_quart")
        localidade = props.get("Localidade_nome")
        chave = chave_territorial(props.get("Localidade"), numero)
        if chaves is not None and chave not in chaves:
            continue
        geometria = feicao.get("geometry")
        if not geometria or geometria["type"] not in {"Polygon", "MultiPolygon"}:
            continue
        geom = shape(geometria)
        if not geom.is_valid:
            geom = make_valid(geom)
        partes = list(_partes_poligonais(geom))
        if partes:
            grupo = agrupados.setdefault(chave or ((localidade, numero) if localidade and numero else indice), (props, []))
            grupo[1].extend(partes)
    return [(props, partes[0] if len(partes) == 1 else unary_union(partes))
            for props, partes in agrupados.values()]
