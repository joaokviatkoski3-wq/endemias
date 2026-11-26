"""Abrangência geométrica da esporotricose na malha ativa do GeoVSATT."""

from collections import Counter

from shapely import orient_polygons
from shapely.geometry import mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree

from app_core import esporotricose_bloqueio
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
