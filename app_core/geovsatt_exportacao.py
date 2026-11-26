"""Formatos de exportação para os vetores autorizados no GeoVSATT."""

import csv
from io import StringIO
import json
import re
from xml.etree import ElementTree as ET

from shapely.geometry import shape
from shapely.geometry.polygon import orient

from app_core.csv_seguranca import campo_csv


FORMATOS = {"csv": "text/csv", "geojson": "application/geo+json", "kml": "application/vnd.google-earth.kml+xml"}
_INVALIDO_XML = re.compile(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _valor(valor):
    return json.dumps(valor, ensure_ascii=False) if isinstance(valor, (list, dict)) else valor


def _csv(features):
    campos = sorted({campo for f in features for campo in f.get("properties", {})}, key=str.casefold)
    geometria = "geometria_wkt_epsg4326"
    while geometria in campos:
        geometria += "_"
    saida = StringIO(newline="")
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow([campo_csv(campo) for campo in campos] + [geometria])
    for feature in features:
        props = feature.get("properties", {})
        atributos = [campo_csv(_valor(props.get(campo)), numerico=type(props.get(campo)) in (int, float)) for campo in campos]
        geom = feature.get("geometry")
        escritor.writerow(atributos + [shape(geom).wkt if geom else ""])
    return saida.getvalue().encode("utf-8-sig")


def _xml(valor):
    return _INVALIDO_XML.sub("", str(_valor(valor)))


def _coordenadas_kml(elemento, coords):
    ET.SubElement(elemento, "coordinates").text = " ".join(",".join(str(valor) for valor in ponto) for ponto in coords)


def _geometria_kml(placemark, geom):
    if geom.is_empty:
        return
    if hasattr(geom, "geoms"):
        multigeometria = ET.SubElement(placemark, "MultiGeometry")
        for parte in geom.geoms:
            _geometria_kml(multigeometria, parte)
    elif geom.geom_type == "Polygon":
        geom = orient(geom, sign=1.0)
        poligono = ET.SubElement(placemark, "Polygon")
        externo = ET.SubElement(poligono, "outerBoundaryIs")
        _coordenadas_kml(ET.SubElement(externo, "LinearRing"), geom.exterior.coords)
        for anel in geom.interiors:
            interno = ET.SubElement(poligono, "innerBoundaryIs")
            _coordenadas_kml(ET.SubElement(interno, "LinearRing"), anel.coords)
    else:
        _coordenadas_kml(ET.SubElement(placemark, geom.geom_type), geom.coords)


def _kml(features, camada, fonte):
    raiz = ET.Element("kml", {"xmlns": "http://www.opengis.net/kml/2.2"})
    doc = ET.SubElement(raiz, "Document")
    ET.SubElement(doc, "name").text = _xml(camada["nome"])
    if fonte:
        ET.SubElement(doc, "description").text = _xml(fonte)
    campos_rotulo = (camada["config"]["rotulo"], "nome", "NOME", "Name", "rotulo", "id_quart")
    for i, feature in enumerate(features, 1):
        placemark = ET.SubElement(doc, "Placemark")
        props = feature.get("properties", {})
        titulo = next((props[campo] for campo in campos_rotulo if props.get(campo) not in (None, "")), f"Feição {i}")
        ET.SubElement(placemark, "name").text = _xml(titulo)
        dados = ET.SubElement(placemark, "ExtendedData")
        for chave, valor in props.items():
            if valor is not None:
                ET.SubElement(ET.SubElement(dados, "Data", {"name": _xml(chave)}), "value").text = _xml(valor)
        if feature.get("geometry"):
            _geometria_kml(placemark, shape(feature["geometry"]))
    return ET.tostring(raiz, encoding="utf-8", xml_declaration=True)


def gerar(dados, camada, formato):
    if formato == "geojson":
        return json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if formato == "csv":
        return _csv(dados["features"])
    fonte = dados.get("metadata", {}).get("fonte") or dados.get("metadata", {}).get("origem")
    return _kml(dados["features"], camada, fonte)
