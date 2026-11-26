"""Contratos de leitura da primeira fundação cartográfica do GeoVSATT."""

import json
from pathlib import Path

from app_core import db as db_core
from app_core import permissoes
from app_core import registro_geografico as rg_core


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
        "nome": "Esporotricose",
        "descricao": "Casos, bloqueios e raios serão liberados com regras próprias de acesso.",
        "tipo": "ponto",
        "disponivel": False,
        "visivel_inicial": False,
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


def catalogo(usuario):
    return {
        "camadas": [dict(item) for item in CAMADAS],
        "pode_configurar": permissoes.permite(usuario, "tecnica"),
        "gestao_disponivel": False,
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


def quarteiroes(db_path, base_dir):
    data = rg_core.geojson_ativo(db_path, base_dir)
    resumo = rg_core.resumo_mapa(db_path, base_dir)["quarteiroes"]
    for feature in data.get("features", []):
        props = feature.setdefault("properties", {})
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
    malha = quarteiroes(db_path, base_dir)
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


def buscar(db_path, base_dir, termo, limite=30):
    termo = str(termo or "").strip()
    if not termo:
        return []
    if len(termo) > 100:
        raise ValueError("A busca deve ter no máximo 100 caracteres.")
    normalizado = termo.casefold()
    itens = []
    for feature in localidades(db_path, base_dir)["features"]:
        props = feature["properties"]
        if normalizado in props["nome"].casefold():
            itens.append({"tipo": "localidade", "titulo": props["nome"], "subtitulo": f"{props['quarteiroes']} quarteirões", "id_localidade": props["id_localidade"]})
    for item in rg_core.resumo_mapa(db_path, base_dir)["quarteiroes"].values():
        texto = f"{item['localidade']} {item['quarteirao']}"
        if normalizado in texto.casefold():
            itens.append({
                "tipo": "quarteirao",
                "titulo": f"Quarteirão {item['quarteirao']}",
                "subtitulo": item["localidade"],
                "id_localidade": item["id_localidade"],
                "quarteirao": item["quarteirao"],
                "chave": item["chave"],
            })
        if len(itens) >= limite:
            break
    return itens[:limite]


def detalhe_quarteirao(db_path, base_dir, id_localidade, numero):
    return rg_core.quarteirao(db_path, int(id_localidade), numero, base_dir)
