"""Contratos de leitura da primeira fundação cartográfica do GeoVSATT."""

from collections import Counter
import json
import math
from pathlib import Path
import re

from shapely import make_valid
from shapely.geometry import Point, Polygon, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from app_core import db as db_core
from app_core import esporotricose as esporotricose_core
from app_core import esporotricose_bloqueio
from app_core import geovsatt_bloqueios as bloqueios_core
from app_core import geovsatt_busca as busca_core
from app_core import geovsatt_catalogo as catalogo_core
from app_core import geovsatt_trabalhos as trabalhos_core
from app_core import ovitrampas as ovitrampas_core
from app_core import permissoes
from app_core import registro_geografico as rg_core
from app_core import setores


CAMADAS = (
    {
        "id": "localidades",
        "grupo": "Território",
        "nome": "Localidades",
        "descricao": "Localidades e áreas dispersas do município.",
        "tipo": "poligono",
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
        "descricao": "Animais georreferenciados no cadastro da Vigilância Ambiental.",
        "tipo": "ponto",
        "disponivel": True,
        "visivel_inicial": False,
        "niveis_padrao": ["admin"],
        "rotulo_padrao": "rotulo",
    },
    {
        "id": "esporotricose_bloqueios",
        "grupo": "Vigilância",
        "nome": "Esporotricose · Raios de bloqueio",
        "descricao": f"Raio de {esporotricose_bloqueio.RAIO_METROS} m e situação registrada para cada caso animal georreferenciado.",
        "tipo": "poligono",
        "disponivel": True,
        "visivel_inicial": False,
        "niveis_padrao": ["admin"],
        "rotulo_padrao": "rotulo",
    },
    {
        "id": "esporotricose_quarteiroes",
        "grupo": "Vigilância",
        "nome": "Esporotricose · Quarteirões nos raios",
        "descricao": "Quarteirões alcançados pelos raios de bloqueio. A cor indica a abrangência geométrica.",
        "tipo": "poligono",
        "disponivel": True,
        "visivel_inicial": False,
        "niveis_padrao": ["admin"],
    },
    {
        "id": "ovitrampas",
        "grupo": "Vigilância",
        "nome": "Ovitrampas",
        "descricao": "Armadilhas georreferenciadas e o resultado mais recente de cada uma.",
        "tipo": "ponto",
        "disponivel": True,
        "visivel_inicial": False,
        "niveis_padrao": ["admin"],
        "rotulo_padrao": "ovitrampa_id",
    },
    {
        "id": "pontos_estrategicos",
        "grupo": "Vigilância",
        "nome": "Pontos estratégicos",
        "descricao": "Pontos com coordenadas no cadastro de Endemias.",
        "tipo": "ponto",
        "disponivel": True,
        "visivel_inicial": False,
        "niveis_padrao": ["admin"],
        "rotulo_padrao": "nome",
    },
    {
        "id": "acoes_atendimentos",
        "grupo": "Vigilância",
        "nome": "Ações e atendimentos",
        "descricao": "Ações e atendimentos de Endemias com coordenadas registradas.",
        "tipo": "ponto",
        "disponivel": True,
        "visivel_inicial": False,
        "niveis_padrao": ["admin"],
        "rotulo_padrao": "rotulo",
    },
    {
        "id": trabalhos_core.CODIGO,
        "grupo": "Vigilância",
        "nome": "Quarteirões trabalhados",
        "descricao": "Registros de visitas no Endemias, por período, tipo de trabalho e localidade.",
        "tipo": "poligono",
        "disponivel": True,
        "visivel_inicial": False,
        "niveis_padrao": ["admin"],
    },
)


BASES = {item["id"]: item for item in CAMADAS if item["disponivel"]}
FONTES_TERRITORIAIS = {"localidades": "localidades-areas-dispersas", "quarteiroes": "quarteiroes-qgis"}
SETORES_VIGILANCIA = {"esporotricose": "ambiental", "ovitrampas": "endemias", "pontos_estrategicos": "endemias",
                     "acoes_atendimentos": "endemias", trabalhos_core.CODIGO: "endemias"}
BLOQUEIOS_ESPOROTRICOSE = {
    "esporotricose_bloqueios": ("esporotricose",),
    "esporotricose_quarteiroes": ("esporotricose", "quarteiroes"),
}
DEPENDENCIAS = BLOQUEIOS_ESPOROTRICOSE | {trabalhos_core.CODIGO: ("quarteiroes",)}


def pode_ver_camada(target, camada, usuario, *, cadastradas=None):
    codigo = camada["id"]
    setor = SETORES_VIGILANCIA.get(codigo)
    if setor and not setores.pode_entrar(usuario, setor):
        return False
    if not catalogo_core.pode_ver(camada, usuario):
        return False
    if codigo in BLOQUEIOS_ESPOROTRICOSE and not esporotricose_localizacao_exata(usuario):
        return False
    for origem in DEPENDENCIAS.get(codigo, ()):
        fonte = cadastradas[origem] if cadastradas is not None else catalogo_core.obter(target, origem, BASES)
        if not pode_ver_camada(target, fonte, usuario):
            return False
    return True


def pode_exportar_camada(target, camada, usuario, *, cadastradas=None):
    return (camada["disponivel"] and pode_ver_camada(target, camada, usuario, cadastradas=cadastradas)
            and (permissoes.permite(usuario, "tecnica")
                 or usuario["id_usuario"] in camada["config"]["usuarios_exportacao"]))


def dados_nativos(target, base_dir, codigo, usuario, *, parametros=None):
    if codigo == "localidades":
        return localidades(target, base_dir, usuario=usuario)
    if codigo == "quarteiroes":
        return quarteiroes(target, base_dir, incluir_rg=setores.pode_entrar(usuario, "endemias"), usuario=usuario)
    if codigo == "esporotricose":
        if esporotricose_localizacao_exata(usuario):
            return esporotricose_animal_localizada(target)
        return esporotricose_animal(target)
    if codigo in BLOQUEIOS_ESPOROTRICOSE:
        return esporotricose_abrangencia(target, base_dir, codigo, usuario)
    if codigo == "ovitrampas":
        return ovitrampas(target)
    if codigo == "pontos_estrategicos":
        return pontos_estrategicos(target)
    if codigo == "acoes_atendimentos":
        return acoes_atendimentos(target)
    if codigo == trabalhos_core.CODIGO:
        consulta = trabalhos_core.filtros(parametros if parametros is not None else {})
        malha = quarteiroes(target, base_dir, incluir_rg=False, usuario=usuario)
        return trabalhos_core.camada(target, malha, consulta)
    return logradouros(base_dir)


def catalogo(target, usuario):
    gerencia = permissoes.permite(usuario, "tecnica")
    cadastradas = {item["id"]: item for item in catalogo_core.listar(target, BASES)}
    visiveis = [item for item in cadastradas.values()
                if pode_ver_camada(target, item, usuario, cadastradas=cadastradas)]
    fontes = {item["id"]: item for item in visiveis if item["id_versao"] and item["tipo"] == "poligono"}
    camadas = [
        {key: camada[key] for key in ("id", "grupo", "nome", "descricao", "tipo", "disponivel",
                                    "visivel_inicial", "origem")}
        | ({"descricao": "Contagem de animais por célula de 250 metros. O marcador indica o centro da célula."}
           if camada["id"] == "esporotricose" and not esporotricose_localizacao_exata(usuario) else {})
        | {"estilo": {key: camada["config"][key] for key in
                      ("cor", "atributo_cor", "cores", "rotulo", *catalogo_core.ESTILO_PADRAO)}}
        | {"pode_exportar": pode_exportar_camada(target, camada, usuario, cadastradas=cadastradas)}
        | ({"tipo": fontes[FONTES_TERRITORIAIS[camada["id"]]]["tipo"]}
           if FONTES_TERRITORIAIS.get(camada["id"]) in fontes else
           {"tipo": "ponto"} if camada["id"] == "localidades" else {})
        for camada in visiveis if camada["id"] not in FONTES_TERRITORIAIS.values()
    ]
    camadas.extend(dict(item) for item in CAMADAS if item["id"] not in cadastradas)
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


def _fonte_territorial(db_path, codigo, usuario):
    if usuario is None:
        return None
    try:
        camada = catalogo_core.obter(db_path, FONTES_TERRITORIAIS[codigo], BASES, incluir_dados=True)
    except catalogo_core.CamadaAusente:
        return None
    if camada["id_versao"] and camada["tipo"] == "poligono" and pode_ver_camada(db_path, camada, usuario):
        return json.loads(camada["geojson"])
    return None


def _codigos_localidades(target):
    conn = db_core.connect(target)
    try:
        return rg_core._localidades_por_codigo_geojson(conn)
    finally:
        conn.close()


def _localidade(codigos, valor):
    candidatos = codigos.get(rg_core._normalizar_codigo_geojson(valor), [])
    if len({item["id_localidade"] for item in candidatos}) == 1:
        return candidatos[0]
    return {}


def _numero_comparavel(numero):
    texto = str(numero or "").strip().casefold()
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", texto):
        inteira, _, fracao = texto.partition(".")
        fracao = fracao.rstrip("0")
        return (inteira.lstrip("0") or "0") + (f".{fracao}" if fracao else "")
    return texto


def _vinculos_por_malha_anterior(db_path, base_dir, features, codigos):
    """Recupera nomes escritos de forma diferente quando os números confirmam a mesma localidade."""
    nomes = {f["properties"].get("Localidade") for f in features}
    pendentes = {nome for nome in nomes if nome and not _localidade(codigos, nome)}
    if not pendentes:
        return {}
    anterior = rg_core.geojson_ativo(db_path, base_dir)
    por_quarteirao = {}
    for feature in anterior.get("features", []):
        props = feature.get("properties") or {}
        numero = _numero_comparavel(props.get("id_quart"))
        localidade = props.get("Localidade")
        if numero and localidade is not None:
            por_quarteirao.setdefault(numero, set()).add(str(localidade))
    candidatos = {nome: set() for nome in pendentes}
    confirmacoes = Counter()
    for feature in features:
        props = feature["properties"]
        nome = props.get("Localidade")
        if nome in pendentes:
            correspondencias = por_quarteirao.get(_numero_comparavel(props.get("id_quart") or props.get("id_Q")), set())
            candidatos[nome].update(correspondencias)
            confirmacoes[nome] += len(correspondencias) == 1
    cadastros = {str(row["id_localidade"]): row for lista in codigos.values() for row in lista}
    return {nome: cadastros.get(next(iter(ids)), {}) for nome, ids in candidatos.items()
            if len(ids) == 1 and confirmacoes[nome] >= 2}


def quarteiroes(db_path, base_dir, *, incluir_rg=True, usuario=None):
    data = _fonte_territorial(db_path, "quarteiroes", usuario)
    importada = data is not None
    if importada:
        codigos = _codigos_localidades(db_path)
        vinculos = _vinculos_por_malha_anterior(db_path, base_dir, data["features"], codigos)
    else:
        data = rg_core.geojson_ativo(db_path, base_dir)
    resumo = rg_core.resumo_mapa(db_path, base_dir)["quarteiroes"] if incluir_rg else {}
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        if importada:
            nome = props.get("Localidade_nome") or props.get("Localidade")
            cadastro = (_localidade(codigos, props.get("Localidade")) or _localidade(codigos, nome)
                        or vinculos.get(props.get("Localidade"), {}))
            props = {"Localidade": cadastro.get("id_localidade"), "Localidade_nome": cadastro.get("nome") or nome,
                     "id_quart": props.get("id_quart") or props.get("id_Q"), "id_Q_antig": props.get("id_Q_antig")}
        elif not incluir_rg:
            props = {key: props[key] for key in ("Localidade", "Localidade_nome", "id_quart") if key in props}
        feature["properties"] = props
        localidade = props.get("Localidade")
        numero = rg_core._quarteirao_display(props.get("id_quart"))
        chave = f"{localidade}:{numero}" if localidade is not None and numero else None
        props.update(resumo.get(chave, {}))
        props["chave"] = chave
        props["id_quart"] = numero
    data.setdefault("metadata", {})
    data["metadata"].update({"camada": "quarteiroes", "origem": "Malha cartográfica QGIS" if importada else "Registro Geográfico"})
    return data


def localidades(db_path, base_dir, *, usuario=None):
    territorio = _fonte_territorial(db_path, "localidades", usuario)
    malha = quarteiroes(db_path, base_dir, incluir_rg=False, usuario=usuario)
    if territorio is not None:
        codigos = _codigos_localidades(db_path)
        contagem = Counter(feature["properties"].get("Localidade") for feature in malha["features"])
        for indice, feature in enumerate(territorio["features"]):
            props = feature["properties"]
            cadastro = _localidade(codigos, props.get("cod_loc")) or _localidade(codigos, props.get("nome"))
            codigo = cadastro.get("id_localidade")
            props.update(id_localidade=codigo if codigo is not None else f"area-{indice}",
                         quarteiroes=contagem[codigo] if codigo is not None else 0,
                         nome=cadastro.get("nome") or props.get("nome") or "Área dispersa")
        territorio["metadata"] = {"camada": "localidades", "derivada": False}
        return territorio
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


def estimar_populacao(db_path, base_dir, pontos, *, usuario, incluir_condominios=True):
    if not isinstance(pontos, list) or not 3 <= len(pontos) <= 120:
        raise ValueError("Desenhe uma área com 3 a 120 vértices.")
    for coordenada in pontos:
        if (not isinstance(coordenada, list) or len(coordenada) != 2
                or any(type(valor) not in (float, int) for valor in coordenada)
                or not (-180 <= coordenada[0] <= 180 and -90 <= coordenada[1] <= 90)):
            raise ValueError("A área contém uma coordenada inválida.")
    selecao = Polygon(pontos)
    if not selecao.is_valid or selecao.area <= 0:
        raise ValueError("Desenhe uma área sem cruzamentos e com pelo menos três vértices distintos.")
    recorte = prep(selecao)
    dados = quarteiroes(db_path, base_dir, usuario=usuario, incluir_rg=False)
    blocos = {}
    for indice, feature in enumerate(dados["features"]):
        geometria = feature.get("geometry")
        if not geometria or geometria["type"] not in {"Polygon", "MultiPolygon"}:
            continue
        props = feature["properties"]
        chave = props["chave"] or indice
        geom = shape(geometria)
        if geom.is_empty:
            continue
        blocos.setdefault(chave, []).append(geom if geom.is_valid else make_valid(geom))

    cadastrados = rg_core.resumo_mapa(db_path, base_dir)["quarteiroes"]
    com_cadastro = sem_cadastro = parciais = 0
    residencias = 0.0
    campo = "residencias_reais" if incluir_condominios else "residencias_sem_condominio"
    for chave, formas in blocos.items():
        if not any(recorte.intersects(forma) for forma in formas):
            continue
        bloco = formas[0] if len(formas) == 1 else unary_union(formas)
        area = selecao.intersection(bloco).area
        if area <= 0:
            continue
        cadastro = cadastrados.get(chave, {})
        if not cadastro.get("imoveis"):
            sem_cadastro += 1
            continue
        com_cadastro += 1
        proporcao = min(1, area / bloco.area)
        parciais += proporcao < .999999
        residencias += proporcao * cadastro[campo]

    media = rg_core.MEDIA_PESSOAS_POR_RESIDENCIA
    return {
        "populacao_estimada": round(residencias * media) if com_cadastro else None,
        "residencias_equivalentes": round(residencias, 2) if com_cadastro else None,
        "quarteiroes_com_cadastro": com_cadastro,
        "quarteiroes_sem_cadastro": sem_cadastro,
        "quarteiroes_parciais": parciais,
        "media_pessoas_por_residencia": media,
        "fonte_populacao": rg_core.FONTE_POPULACAO,
        "origem_malha": dados["metadata"]["origem"],
    }


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


def esporotricose_localizacao_exata(usuario):
    return setores.pode_entrar(usuario, "ambiental") and usuario.get("nivel") in {"admin", "superadmin"}


def esporotricose_animal_localizada(target):
    rows = db_core.query(target, """
        SELECT id_animal_doente,especie,localidade,quarteirao,status,data_notificacao,bloqueio,data_bloqueio,latitude,longitude
          FROM esporotricose_doentes_animais
         WHERE latitude IS NOT NULL AND longitude IS NOT NULL
         ORDER BY id_animal_doente
    """)

    try:
        limite = catalogo_core.obter(target, "limite-municipal", BASES, incluir_dados=True)
    except catalogo_core.CamadaAusente:
        limite = {}
    geometrias = [prep(shape(feature["geometry"])) for feature in json.loads(limite["geojson"])["features"]
                  if feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}] if limite.get("geojson") else []

    def propriedades(row):
        ponto = Point(float(row["longitude"]), float(row["latitude"]))
        conferida = ("Dentro do limite municipal" if any(area.covers(ponto) for area in geometrias)
                      else "Fora do limite municipal") if geometrias else "Limite municipal indisponível"
        return {"rotulo": f"Caso animal {row['id_animal_doente']}", **{
            chave: row[chave] for chave in ("especie", "localidade", "quarteirao", "status", "data_notificacao")
        }, "posicao_cadastrada": conferida,
            "situacao_bloqueio": esporotricose_core._normalizar_bloqueio_doente(row["bloqueio"]) or "Sem informação",
            "data_bloqueio": row["data_bloqueio"]}

    return _pontos(rows, propriedades, "Coordenadas cadastradas pela Vigilância Ambiental", id_campo="id_animal_doente")


def esporotricose_abrangencia(target, base_dir, codigo, usuario):
    pontos = esporotricose_animal_localizada(target)
    malha = None
    cadastro = catalogo_core.obter(target, "quarteiroes", BASES)
    if pode_ver_camada(target, cadastro, usuario):
        try:
            malha = quarteiroes(target, base_dir, incluir_rg=False, usuario=usuario)
        except ValueError:
            pass
    raios, abrangidos, metadata = bloqueios_core.calcular(pontos, malha)
    return {"type": "FeatureCollection", "features": raios if codigo == "esporotricose_bloqueios" else abrangidos,
            "metadata": metadata}


def _pontos(registros, preparar, origem, *, id_campo=None):
    features = []
    for registro in registros:
        props = db_core.serialize_row(registro)
        coordenadas = esporotricose_bloqueio.coordenadas(props)
        if coordenadas:
            lat, lon = coordenadas
            feicao = {"type": "Feature", "properties": preparar(props),
                      "geometry": {"type": "Point", "coordinates": [lon, lat]}}
            if id_campo:
                feicao["id"] = props[id_campo]
            features.append(feicao)
    return {"type": "FeatureCollection", "features": features, "metadata": {"origem": origem}}


def ovitrampas(target):
    conn = db_core.connect(target)
    try:
        cte = ovitrampas_core.leituras_mapa_cte(conn)
        rows = conn.execute(cte + """, ultimas AS (
            SELECT ovitrampa_id,ano,semana,data_coleta,ovos,
                   ROW_NUMBER() OVER (PARTITION BY ovitrampa_id ORDER BY ano DESC, semana DESC,
                       COALESCE(data_coleta,'') DESC, COALESCE(data_envio_contagem,'') DESC, id_leitura DESC) AS posicao
              FROM ovi_leituras
        )
        SELECT a.ovitrampa_id,a.latitude,a.longitude,a.localidade,a.quarteirao,
               CASE WHEN a.ativo=1 THEN 'Ativa' ELSE 'Inativa' END AS situacao,
               u.ano,u.semana,u.data_coleta,u.ovos
          FROM ovitrampas_armadilhas a LEFT JOIN ultimas u ON a.ovitrampa_id=u.ovitrampa_id AND u.posicao=1
         WHERE a.latitude IS NOT NULL AND a.longitude IS NOT NULL
         ORDER BY a.ovitrampa_id
        """).fetchall()
    finally:
        conn.close()

    def propriedades(row):
        ovos = row["ovos"]
        row["resultado"] = "Sem contagem" if ovos is None else "Positiva" if ovos > 0 else "Negativa"
        return {chave: valor for chave, valor in row.items() if chave not in {"latitude", "longitude"}}

    return _pontos(rows, propriedades, "Cadastro de armadilhas e leituras do VSATT")


def pontos_estrategicos(target):
    rows = db_core.query(target, """
        SELECT codigo_pe,nome,localidade,quarteirao,tipo,logradouro,numero,latitude,longitude,
               CASE WHEN situacao=1 THEN 'Ativo' ELSE 'Inativo' END AS situacao
          FROM pontos_estrategicos
         WHERE latitude IS NOT NULL AND longitude IS NOT NULL
         ORDER BY codigo_pe
    """)
    return _pontos(rows, lambda row: {chave: valor for chave, valor in row.items() if chave not in {"latitude", "longitude"}},
                   "Cadastro de Pontos Estratégicos")


def acoes_atendimentos(target):
    from blueprints.acoes_setor import SITUACOES_ACAO, TIPOS_ACAO

    rows = db_core.query(target, """
        SELECT id_acao,tipo,situacao,data,localidade,local,publico_aproximado,coordenadas
          FROM acoes_setor
         WHERE coordenadas IS NOT NULL AND TRIM(coordenadas) <> ''
         ORDER BY data DESC,id_acao DESC
    """)
    registros = []
    for raw in rows:
        row = db_core.serialize_row(raw)
        coord = str(row.pop("coordenadas")).strip()
        par = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*[,;\s]\s*([+-]?\d+(?:\.\d+)?)", coord)
        if par is None:
            par = re.fullmatch(r"([+-]?\d+(?:,\d+)?)\s*[;\s]\s*([+-]?\d+(?:,\d+)?)", coord)
        if par:
            row["latitude"], row["longitude"] = (valor.replace(",", ".") for valor in par.groups())
            row["tipo"] = TIPOS_ACAO.get(row["tipo"], row["tipo"])
            row["situacao"] = SITUACOES_ACAO.get(row["situacao"], row["situacao"])
            row["rotulo"] = row["local"] or f"Ação {row['id_acao']}"
            registros.append(row)
    return _pontos(registros, lambda row: {chave: valor for chave, valor in row.items()
                                          if chave not in {"latitude", "longitude"}}, "Ações e Atendimentos de Endemias")


def buscar(db_path, base_dir, termo, permitidas, *, incluir_rg=False, limite=30, usuario=None):
    termo = str(termo or "").strip()
    if not termo:
        return []
    if len(termo) > 180:
        raise ValueError("A busca deve ter no máximo 180 caracteres.")
    normalizado = rg_core._norm(termo)
    bloco_explicito = re.fullmatch(r"(?:quarteirao|q\.?)\s+([a-z0-9.]+)", normalizado)
    if incluir_rg and "quarteiroes" in permitidas and not bloco_explicito:
        enderecos = busca_core.buscar_enderecos(db_path, termo, limite)
        if enderecos:
            return enderecos
    itens = []
    pontos = localidades(db_path, base_dir, usuario=usuario)["features"] if "localidades" in permitidas else []
    for feature in pontos:
        props = feature["properties"]
        if normalizado in rg_core._norm(props["nome"]):
            itens.append({"tipo": "localidade", "titulo": props["nome"], "subtitulo": f"{props['quarteiroes']} quarteirões", "id_localidade": props["id_localidade"]})
        if len(itens) == limite:
            return itens
    if "quarteiroes" not in permitidas:
        return itens
    for item in _quarteiroes_busca(db_path, base_dir, incluir_rg, usuario):
        nome = item["localidade"]
        numero = item["quarteirao"]
        texto = f"{nome} {numero}"
        if (bloco_explicito and _numero_comparavel(bloco_explicito[1]) == _numero_comparavel(numero)
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


def _quarteiroes_busca(db_path, base_dir, incluir_rg, usuario):
    cadastrados = {}
    if incluir_rg:
        cadastrados = rg_core.resumo_mapa(db_path, base_dir)["quarteiroes"]
        yield from cadastrados.values()
    for feature in quarteiroes(db_path, base_dir, incluir_rg=False, usuario=usuario)["features"]:
        props = feature["properties"]
        codigo = props.get("Localidade")
        if props["chave"] and props["chave"] not in cadastrados:
            yield {"localidade": props.get("Localidade_nome") or f"Localidade {codigo}",
                   "quarteirao": props["id_quart"], "id_localidade": codigo, "chave": props["chave"]}


def detalhe_quarteirao(db_path, base_dir, id_localidade, numero):
    return rg_core.quarteirao(db_path, int(id_localidade), numero, base_dir)
