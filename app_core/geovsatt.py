"""Contratos de leitura da primeira fundação cartográfica do GeoVSATT."""

from collections import Counter
import json
import math
from pathlib import Path
import re

from app_core import db as db_core
from app_core import esporotricose_bloqueio
from app_core import geovsatt_busca as busca_core
from app_core import geovsatt_catalogo as catalogo_core
from app_core import permissoes
from app_core import registro_geografico as rg_core
from app_core import setores


CAMADAS = (
    {
        "id": "localidades",
        "grupo": "Território",
        "nome": "Localidades",
        "descricao": "Pontos de referência derivados da malha de quarteirões, até a entrada dos limites oficiais.",
        "tipo": "ponto",
        "disponivel": True,
        "visivel_inicial": True,
    },
    {
        "id": "quarteiroes",
        "grupo": "Território",
        "nome": "Quarteirões",
        "descricao": "Malha territorial ativa vinculada ao Registro Geográfico.",
        "tipo": "poligono",
        "disponivel": True,
        "visivel_inicial": True,
    },
    {
        "id": "logradouros",
        "grupo": "Território",
        "nome": "Logradouros",
        "descricao": "Eixos de vias disponíveis na base cartográfica municipal.",
        "tipo": "linha",
        "disponivel": True,
        "visivel_inicial": True,
    },
    {
        "id": "bairros",
        "grupo": "Território",
        "nome": "Bairros",
        "descricao": "Aguardando a camada oficial de limites para não apresentar geometrias presumidas.",
        "tipo": "poligono",
        "disponivel": False,
        "visivel_inicial": False,
    },
    {
        "id": "hidrografia",
        "grupo": "Meio ambiente",
        "nome": "Hidrografia",
        "descricao": "Camada prevista para importação e versionamento pelo superadmin.",
        "tipo": "linha",
        "disponivel": False,
        "visivel_inicial": False,
    },
    {
        "id": "predios_publicos",
        "grupo": "Equipamentos",
        "nome": "Prédios públicos",
        "descricao": "Catálogo previsto para unidades e equipamentos públicos com metadados.",
        "tipo": "ponto",
        "disponivel": False,
        "visivel_inicial": False,
    },
    {
        "id": "esporotricose",
        "grupo": "Vigilância",
        "nome": "Esporotricose animal",
        "descricao": "Animais cadastrados com coordenadas, agrupados em células de aproximadamente 250 metros.",
        "tipo": "ponto",
        "disponivel": True,
        "visivel_inicial": False,
        "niveis_padrao": ["admin"],
        "rotulo_padrao": "rotulo",
    },
    {
        "id": "ovitrampas",
        "grupo": "Vigilância",
        "nome": "Ovitrampas",
        "descricao": "Armadilhas, leituras e raios de bloqueio em preparação.",
        "tipo": "ponto",
        "disponivel": False,
        "visivel_inicial": False,
    },
    {
        "id": "pontos_estrategicos",
        "grupo": "Vigilância",
        "nome": "Pontos estratégicos",
        "descricao": "Camada operacional em preparação.",
        "tipo": "ponto",
        "disponivel": False,
        "visivel_inicial": False,
    },
)


BASES = {item["id"]: item for item in CAMADAS if item["disponivel"]}


def pode_ver_camada(camada, usuario):
    if camada["id"] == "esporotricose" and not setores.pode_entrar(usuario, "ambiental"):
        return False
    return catalogo_core.pode_ver(camada, usuario)


def catalogo(target, usuario):
    gerencia = permissoes.permite(usuario, "tecnica")
    cadastradas = catalogo_core.listar(target, BASES)
    reservadas = {item["id"] for item in cadastradas}
    camadas = [
        {key: camada[key] for key in ("id", "grupo", "nome", "descricao", "tipo", "disponivel",
                                    "visivel_inicial", "origem")}
        | {"estilo": {key: camada["config"][key] for key in ("cor", "atributo_cor", "cores", "rotulo")}}
        for camada in cadastradas if pode_ver_camada(camada, usuario)
    ]
    camadas.extend(dict(item) for item in CAMADAS if item["id"] not in reservadas)
    return {
        "camadas": camadas,
        "pode_configurar": gerencia,
        "gestao_disponivel": gerencia,
    }


def _corrigir_texto(value):
    if not isinstance(value, str) or "�" not in value:
        return value
    # A base histórica contém alguns acentos já substituídos. Não adivinhamos o
    # caractere perdido; apenas mantemos o valor e deixamos a fonte identificada.
    return value


def _caminhar_coordenadas(coordinates):
    if not isinstance(coordinates, list):
        return
    if len(coordinates) >= 2 and all(isinstance(item, (int, float)) for item in coordinates[:2]):
        yield float(coordinates[0]), float(coordinates[1])
        return
    for item in coordinates:
        yield from _caminhar_coordenadas(item)


def quarteiroes(db_path, base_dir, *, incluir_rg=True):
    data = rg_core.geojson_ativo(db_path, base_dir)
    resumo = rg_core.resumo_mapa(db_path, base_dir)["quarteiroes"] if incluir_rg else {}
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        if not incluir_rg:
            props = {key: props[key] for key in ("Localidade", "Localidade_nome", "id_quart") if key in props}
        feature["properties"] = props
        localidade = props.get("Localidade")
        numero = rg_core._quarteirao_display(props.get("id_quart"))
        chave = f"{localidade}:{numero}"
        props.update(resumo.get(chave, {}))
        props["chave"] = chave
        props["id_quart"] = numero
    data.setdefault("metadata", {})
    data["metadata"].update({"camada": "quarteiroes", "origem": "Registro Geográfico"})
    return data


def localidades(db_path, base_dir):
    malha = rg_core.geojson_ativo(db_path, base_dir)
    grupos = {}
    for feature in malha.get("features", []):
        props = feature.get("properties") or {}
        codigo = props.get("Localidade")
        if codigo in (None, ""):
            continue
        pontos = list(_caminhar_coordenadas((feature.get("geometry") or {}).get("coordinates")))
        if not pontos:
            continue
        grupo = grupos.setdefault(str(codigo), {"xs": [], "ys": [], "quarteiroes": 0, "nome": props.get("Localidade_nome")})
        grupo["xs"].extend(point[0] for point in pontos)
        grupo["ys"].extend(point[1] for point in pontos)
        grupo["quarteiroes"] += 1
    conn = db_core.connect(db_path)
    try:
        nomes = {str(row["id_localidade"]): row["nome"] for row in conn.execute("SELECT id_localidade,nome FROM localidades")}
    finally:
        conn.close()
    features = []
    for codigo, grupo in grupos.items():
        x = (min(grupo["xs"]) + max(grupo["xs"])) / 2
        y = (min(grupo["ys"]) + max(grupo["ys"])) / 2
        features.append({
            "type": "Feature",
            "properties": {
                "id_localidade": codigo,
                "nome": grupo["nome"] or nomes.get(codigo) or f"Localidade {codigo}",
                "quarteiroes": grupo["quarteiroes"],
                "representacao": "ponto de referência derivado da malha",
            },
            "geometry": {"type": "Point", "coordinates": [x, y]},
        })
    return {"type": "FeatureCollection", "features": features, "metadata": {"camada": "localidades", "derivada": True}}


def logradouros(base_dir):
    path = Path(base_dir) / "dados_referencia" / "esporotricose_ruas.geojson"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Não foi possível carregar a camada de logradouros.") from exc
    for feature in data.get("features", []):
        feature["properties"] = {key: _corrigir_texto(value) for key, value in (feature.get("properties") or {}).items()}
    data["metadata"] = {"camada": "logradouros", "origem": "base cartográfica municipal existente"}
    return data


def esporotricose_animal(db_path):
    """Exibe contagens territoriais sem entregar coordenadas ou atributos de casos."""
    celulas = Counter()
    grade = 0.0025
    total = 0
    registros = db_core.query(db_path, "SELECT latitude,longitude FROM esporotricose_doentes_animais")
    for registro in registros:
        coordenada = esporotricose_bloqueio.coordenadas(registro)
        if not coordenada:
            continue
        lat, lon = coordenada
        if -25.6 < lat < -25 and -49.7 < lon < -48.9:
            total += 1
            celulas[(math.floor(lon / grade), math.floor(lat / grade))] += 1
    features = [{
        "type": "Feature",
        "properties": {"animais": quantidade, "rotulo": f"{quantidade} {'animal' if quantidade == 1 else 'animais'} no recorte"},
        "geometry": {"type": "Point", "coordinates": [round((x + .5) * grade, 6), round((y + .5) * grade, 6)]},
    } for (x, y), quantidade in sorted(celulas.items())]
    return {"type": "FeatureCollection", "features": features, "metadata": {
        "representacao": "Agrupamento em células de 0,0025°; a posição é o centro da célula.",
        "animais_representados": total, "animais_no_cadastro": len(registros),
    }}


def buscar(db_path, base_dir, termo, permitidas, *, incluir_rg=False, limite=30):
    termo = str(termo or "").strip()
    if not termo:
        return []
    if len(termo) > 180:
        raise ValueError("A busca deve ter no máximo 180 caracteres.")
    normalizado = rg_core._norm(termo)
    bloco_explicito = re.fullmatch(r"(?:quarteirao|q\.?)\s+([a-z0-9]+)", normalizado)
    if incluir_rg and "quarteiroes" in permitidas and not bloco_explicito:
        enderecos = busca_core.buscar_enderecos(db_path, termo, limite)
        if enderecos:
            return enderecos
    itens = []
    pontos = localidades(db_path, base_dir)["features"] if "localidades" in permitidas else []
    for feature in pontos:
        props = feature["properties"]
        if normalizado in rg_core._norm(props["nome"]):
            itens.append({"tipo": "localidade", "titulo": props["nome"], "subtitulo": f"{props['quarteiroes']} quarteirões", "id_localidade": props["id_localidade"]})
        if len(itens) == limite:
            return itens
    if "quarteiroes" not in permitidas:
        return itens
    for item in _quarteiroes_busca(db_path, base_dir, incluir_rg):
        nome = item["localidade"]
        numero = item["quarteirao"]
        texto = f"{nome} {numero}"
        if (bloco_explicito and rg_core._quarteirao_display(bloco_explicito[1]) == numero
                or not bloco_explicito and normalizado in rg_core._norm(texto)):
            itens.append({
                "tipo": "quarteirao",
                "titulo": f"Quarteirão {numero}",
                "subtitulo": nome,
                "id_localidade": item["id_localidade"],
                "quarteirao": numero,
                "chave": item["chave"],
            })
        if len(itens) >= limite:
            break
    return itens


def _quarteiroes_busca(db_path, base_dir, incluir_rg):
    if incluir_rg:
        yield from rg_core.resumo_mapa(db_path, base_dir)["quarteiroes"].values()
        return
    for feature in quarteiroes(db_path, base_dir, incluir_rg=False)["features"]:
        props = feature["properties"]
        codigo = props.get("Localidade")
        if codigo is not None:
            yield {"localidade": props.get("Localidade_nome") or f"Localidade {codigo}",
                   "quarteirao": props["id_quart"], "id_localidade": codigo, "chave": props["chave"]}


def detalhe_quarteirao(db_path, base_dir, id_localidade, numero):
    return rg_core.quarteirao(db_path, int(id_localidade), numero, base_dir)
