"""Abrangência dos raios e execução de bloqueios na malha ativa."""

from collections import Counter, defaultdict
from datetime import date, timedelta
import json

from shapely import orient_polygons
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree

from app_core import db, esporotricose_bloqueio, visitas_integradas

from app_core.geovsatt_malha import _partes_poligonais
from app_core.territorio import chave_territorial
from app_core.geovsatt_malha import blocos as agrupar_blocos


def calcular(pontos, malha):
    """Calcula o raio nominal e os quarteirões sobrepostos, sem inferir execução."""
    raio_metros = esporotricose_bloqueio.RAIO_METROS
    blocos = agrupar_blocos(malha) if malha else []
    indice = STRtree([geom for _, geom in blocos])
    recortes = {}
    raios = []
    for ponto in pontos["features"]:
        lon, lat = ponto["geometry"]["coordinates"]
        raio = esporotricose_bloqueio._circulo(lat, lon, raio_metros)
        props = ponto["properties"]
        campos = props | {"raio_metros": raio_metros}
        if malha is not None:
            total = integrais = 0
            for i in sorted(indice.query(raio, predicate="intersects")):
                _, geom = blocos[i]
                recorte = raio.intersection(geom)
                if recorte.area <= 0:
                    continue
                recortes.setdefault(i, []).append((recorte, props["situacao_bloqueio"]))
                total += 1
                integrais += raio.covers(geom)
            campos.update(quarteiroes_abrangidos=total, quarteiroes_integrais=integrais,
                          quarteiroes_parciais=total - integrais)
        raios.append({"type": "Feature", "id": ponto["id"], "properties": campos,
                      "geometry": mapping(orient_polygons(raio))})

    abrangidos = []
    for i, recortes_bloco in sorted(recortes.items()):
        props, geom = blocos[i]
        recortes_unidos = unary_union([recorte for recorte, _ in recortes_bloco])
        porcentagem = min(100.0, 100 * recortes_unidos.area / geom.area)
        situacoes = Counter(situacao for _, situacao in recortes_bloco)
        numero = props.get("id_quart")
        localidade = props.get("Localidade_nome")
        rotulo = f"Q. {numero}" if numero else "Quarteirão sem código"
        if localidade:
            rotulo += f" · {localidade}"
        abrangidos.append({
            "type": "Feature", "geometry": mapping(orient_polygons(geom)),
            "properties": {chave: props.get(chave) for chave in ("chave", "id_quart", "Localidade", "Localidade_nome")} | {
                "rotulo": rotulo, "cobertura": "Integral" if recortes_unidos.covers(geom) else "Parcial",
                "percentual_no_raio": round(porcentagem, 1), "raios_sobrepostos": len(recortes_bloco),
                "casos_com_bloqueio_realizado": situacoes["Realizado"],
                "casos_com_bloqueio_nao_realizado": situacoes["Não realizado"],
                "casos_com_bloqueio_nao_necessario": situacoes["Não necessário"],
                "casos_sem_situacao_padronizada": len(recortes_bloco) - sum(
                    situacoes[nome] for nome in ("Realizado", "Não realizado", "Não necessário")),
            },
        })

    metadata = {
        "origem": pontos["metadata"]["origem"],
        "origem_malha": malha["metadata"]["origem"] if malha is not None else None,
        "raio_metros": raio_metros,
        "representacao": "Abrangência geométrica. O cadastro informa a situação do caso.",
    }
    return raios, abrangidos, metadata


RAIOS = {"esporotricose": esporotricose_bloqueio.RAIO_METROS, "dengue": 200, "ovitrampas": 200}


def parametros_impressao(parametros, fonte):
    texto = parametros.get("raio", "").strip()
    if texto and (not texto.isascii() or not texto.isdecimal() or len(texto) > 5 or not 0 < int(texto) <= 10000):
        raise ValueError("Informe um raio entre 1 e 10.000 metros.")
    inicio = parametros.get("visitas_inicio", "").strip()
    fim = parametros.get("visitas_fim", "").strip()
    if inicio or fim:
        try:
            data_inicio, data_fim = date.fromisoformat(inicio), date.fromisoformat(fim)
            if data_inicio.isoformat() != inicio or data_fim.isoformat() != fim or inicio > fim:
                raise ValueError
        except ValueError as exc:
            raise ValueError("Informe as duas datas válidas do período de visitas, em ordem.") from exc
    return int(texto) if texto else RAIOS[fonte], (inicio, fim) if inicio else None


def _visitas(target, fonte, inicio, fim):
    condicoes = """
        id_localidade IS NOT NULL AND quarteirao IS NOT NULL
        AND LOWER(TRIM(COALESCE(visita,''))) IN ('normal', 'recuperado')
    """
    if fonte == "esporotricose":
        return db.query(target, f"""
            SELECT data, id_localidade, quarteirao
              FROM esporotricose_visitas WHERE {condicoes} AND data BETWEEN ? AND ?
        """, (inicio, fim))
    tipo = "TB" if fonte == "dengue" else "TBO"
    conn = visitas_integradas.integrar(db.connect(target))
    try:
        referencia = ", ovitrampas_bloqueio" if fonte == "ovitrampas" and db.column_exists(
            conn, "visitas", "ovitrampas_bloqueio") else ""
        return [db.serialize_row(row) for row in conn.execute(f"""
            SELECT data, id_localidade, quarteirao{referencia}
              FROM visitas WHERE {condicoes} AND tipo = ? AND data BETWEEN ? AND ?
        """, (tipo, inicio, fim))]
    finally:
        conn.close()


def _armadilhas_da_visita(valor):
    try:
        ids = json.loads(valor or "[]") if isinstance(valor, (str, type(None))) else valor
    except ValueError:
        return set()
    return {str(item.get("id", item.get("ovitrampa_id"))) if isinstance(item, dict) else str(item)
            for item in ids} if isinstance(ids, list) else set()


def _janela(evento, periodo):
    if periodo:
        return periodo
    if evento.get("data_bloqueio"):
        dia = str(evento["data_bloqueio"])[:10]
        return dia, dia
    return None


def execucao(target, fonte, eventos, malha, *, periodo=None, raio_mapa=None):
    """Recorta a malha pelo raio e cruza visitas elegíveis pelo código territorial."""
    if not eventos or not malha:
        return []
    operacional = RAIOS[fonte]
    raio_mapa = raio_mapa or operacional
    blocos = agrupar_blocos(malha)
    indice = STRtree([geom for _, geom in blocos])
    janelas = [_janela(evento, periodo) or evento.get("periodo_vinculo") for evento in eventos]
    datas = [dia for janela in janelas if janela for dia in janela]
    por_dia = defaultdict(list)
    if datas:
        for visita in _visitas(target, fonte, min(datas), max(datas)):
            chave = chave_territorial(visita["id_localidade"], visita["quarteirao"])
            ids = _armadilhas_da_visita(visita.get("ovitrampas_bloqueio"))
            por_dia[str(visita["data"])[:10]].append((chave, ids))

    features = []
    for evento, janela in zip(eventos, janelas):
        lat, lon = evento["centro"]
        consulta = esporotricose_bloqueio._circulo(lat, lon, raio_mapa)
        aplicado = esporotricose_bloqueio._circulo(lat, lon, min(operacional, raio_mapa))
        trabalhados = set()
        aceita_legado = _janela(evento, periodo) is not None
        if janela:
            inicio, fim = janela
            trabalhados = {chave for dia, visitas in por_dia.items() if inicio <= dia <= fim
                           for chave, ids in visitas
                           if (ids and evento.get("armadilha_id") in ids) or (not ids and aceita_legado)}
        for indice_bloco in sorted(indice.query(consulta, predicate="intersects")):
            props, geom = blocos[indice_bloco]
            chave = chave_territorial(props.get("Localidade"), props.get("id_quart"))
            recorte = consulta.intersection(geom)
            operacional_no_bloco = aplicado.intersection(geom)
            if chave and chave in trabalhados:
                feito, pendente = operacional_no_bloco, Polygon()
            else:
                feito, pendente = Polygon(), operacional_no_bloco
            situacao_pendente = "Sem visita registrada" if janela and chave and aceita_legado else "Sem dados para cruzar"
            for parte, situacao in ((feito, "Trabalhado"), (pendente, situacao_pendente),
                                    (recorte.difference(operacional_no_bloco), "Fora do raio operacional")):
                poligonos = list(_partes_poligonais(parte))
                if not poligonos:
                    continue
                features.append({"type": "Feature", "geometry": mapping(orient_polygons(unary_union(poligonos))),
                                 "properties": {"evento": evento["id"], "raio_metros": raio_mapa,
                                     "raio_operacional": operacional, "situacao_execucao": situacao,
                                     "chave": props.get("chave"), "id_quart": props.get("id_quart"),
                                     "Localidade": props.get("Localidade"),
                                     "Localidade_nome": props.get("Localidade_nome"),
                                     "rotulo": evento.get("rotulo"),
                                     "data_bloqueio": evento.get("data_bloqueio"),
                                     "visitas_inicio": janela[0] if janela else None,
                                     "visitas_fim": janela[1] if janela else None}})
    features.sort(key=lambda feature: feature["properties"]["situacao_execucao"] == "Trabalhado")
    return features


def evento_ovitrampa(row):
    coleta = row["data_coleta"]
    proxima = row.get("proxima_coleta")
    fim = (date.fromisoformat(proxima) - timedelta(days=1)).isoformat() if proxima else date.today().isoformat()
    centro = esporotricose_bloqueio.coordenadas({"latitude": row.get("latitude_leitura"),
                                                  "longitude": row.get("longitude_leitura")})
    return {"id": row["id_leitura"], "armadilha_id": str(row["ovitrampa_id"]),
            "rotulo": f"Ovitrampa {row['ovitrampa_id']}", "centro": centro or esporotricose_bloqueio.coordenadas(row),
            "periodo_vinculo": (coleta, fim) if coleta and coleta <= fim else None}


def folha(target, base_dir, fonte, evento, parametros, malha):
    raio, periodo = parametros_impressao(parametros, fonte)
    if not evento["centro"]:
        return None
    mapa = esporotricose_bloqueio.mapa(target, base_dir, evento["centro"], raio, malha=malha)
    mapa["execucao"] = {"type": "FeatureCollection", "features": execucao(
        target, fonte, [evento], malha, periodo=periodo, raio_mapa=raio)}
    return mapa
