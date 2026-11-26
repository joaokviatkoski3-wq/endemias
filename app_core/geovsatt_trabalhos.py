"""Visitas de Endemias agregadas por tipo e quarteirão para a malha ativa."""

from collections import Counter, defaultdict
from datetime import date
import re

from shapely import orient_polygons
from shapely.geometry import mapping

from app_core import db, visitas_integradas, work_types
from app_core.geovsatt_malha import blocos
from app_core.territorio import chave_territorial


CODIGO = "quarteiroes_trabalhados"
REGRAS = {("data_visita", "gte"): "inicio", ("data_visita", "lte"): "fim",
          ("tipo_trabalho", "exact"): "tipo", ("localidade_id", "exact"): "localidade"}


def _data(valor, padrao):
    if not valor:
        return padrao
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor):
            raise ValueError
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise ValueError("Informe datas válidas para o período das visitas.") from exc


def filtros(parametros):
    fim = _data(parametros.get("fim"), date.today())
    inicio = _data(parametros.get("inicio"), date(fim.year, 1, 1))
    if inicio > fim:
        raise ValueError("A data inicial deve ser anterior ou igual à data final.")
    tipo = parametros.get("tipo", "").strip().upper()
    if tipo and not re.fullmatch(r"[A-Z0-9_-]{1,24}", tipo):
        raise ValueError("O tipo de trabalho é inválido.")
    localidade = parametros.get("localidade", "").strip()
    if localidade and not re.fullmatch(r"[1-9][0-9]{0,17}", localidade):
        raise ValueError("A localidade é inválida.")
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "tipo": tipo, "localidade": localidade}


def validar_regras_composicao(regras):
    parametros = {}
    for regra in regras:
        campo = REGRAS.get((regra["field"], regra["match"]))
        if not campo or campo in parametros:
            raise ValueError("Filtro inválido para os quarteirões trabalhados.")
        parametros[campo] = regra["value"]
    filtros(parametros)


def _visitas(target, consulta, *, por_dia=False):
    condicoes = ["v.data >= ?", "v.data <= ?"]
    valores = [consulta["inicio"], consulta["fim"]]
    tipo = "COALESCE(NULLIF(UPPER(TRIM(v.tipo)),''),'SEM_TIPO')"
    if consulta["tipo"]:
        condicoes.append(f"{tipo} = ?")
        valores.append(consulta["tipo"])
    if consulta["localidade"]:
        condicoes.append("v.id_localidade = ?")
        valores.append(int(consulta["localidade"]))
    grupo_dia = ", v.data" if por_dia else ""
    return visitas_integradas.query(target, f"""
        SELECT v.id_localidade, v.quarteirao, {tipo} AS tipo,
               COUNT(DISTINCT v.id_visita) AS total,
               COUNT(DISTINCT CASE WHEN LOWER(TRIM(v.visita))='normal' THEN v.id_visita END) AS normais,
               COUNT(DISTINCT CASE WHEN LOWER(TRIM(v.visita))='fechado' THEN v.id_visita END) AS fechadas,
               COUNT(DISTINCT CASE WHEN LOWER(TRIM(v.visita))='recuperado' THEN v.id_visita END) AS recuperadas,
               MAX(v.data) AS ultima
          FROM visitas v
         WHERE {' AND '.join(condicoes)}
         GROUP BY v.id_localidade, v.quarteirao, {tipo}{grupo_dia}
    """, valores)


def _agrupar(registros, rotulos):
    por_bloco = defaultdict(list)
    for registro in registros:
        tipo = registro["tipo"] or "SEM_TIPO"
        registro["tipo"] = tipo
        rotulos.setdefault(tipo, "Tipo não informado" if tipo == "SEM_TIPO" else tipo)
        por_bloco[chave_territorial(registro["id_localidade"], registro["quarteirao"])].append(registro)
    return por_bloco


def _formas(malha, chaves):
    return {
        chave_territorial(props["Localidade"], props["id_quart"]): {
            "type": "Feature", "geometry": mapping(orient_polygons(geom)),
            "properties": {key: props.get(key) for key in ("chave", "id_quart", "Localidade", "Localidade_nome")},
        }
        for props, geom in blocos(malha, chaves - {None})
    }


def _montar_camada(target, malha, consulta, por_bloco, formas, rotulos):
    features = []
    com_malha = 0
    for codigo, forma in formas.items():
        if codigo not in por_bloco:
            continue
        props = forma["properties"]
        visitas = por_bloco[codigo]
        por_tipo = Counter()
        for registro in visitas:
            por_tipo[registro["tipo"]] += registro["total"]
        totais = {campo: sum(registro[campo] for registro in visitas)
                  for campo in ("total", "normais", "fechadas", "recuperadas")}
        com_malha += totais["total"]
        tipos = ", ".join(f"{rotulos[tipo]} ({total})" for tipo, total in sorted(por_tipo.items()))
        categoria = "Mais de um tipo" if len(por_tipo) > 1 else rotulos[next(iter(por_tipo))]
        features.append({
            **forma,
            "properties": props | {
                "rotulo": f"Q. {props['id_quart']}",
                "atividade": categoria, "tipos_registrados": tipos,
                "total_registros": totais["total"], "visitas_normais": totais["normais"],
                "visitas_fechadas": totais["fechadas"], "visitas_recuperadas": totais["recuperadas"],
                "visitas_outras_situacoes": totais["total"] - (totais["normais"] + totais["fechadas"] + totais["recuperadas"]),
                "ultimo_registro": max(registro["ultima"] for registro in visitas),
            },
        })
    if consulta["tipo"]:
        rotulos.setdefault(consulta["tipo"], consulta["tipo"])
    total = sum(registro["total"] for grupo in por_bloco.values() for registro in grupo)
    localidades = db.query(target, "SELECT id_localidade,nome FROM localidades ORDER BY nome,id_localidade")
    return {"type": "FeatureCollection", "features": features, "metadata": {
        "origem": "Registros agregados de visitas de Endemias, incluindo LIRAa",
        "origem_malha": malha["metadata"]["origem"], "consulta": consulta,
        "registros_no_recorte": total, "registros_com_malha": com_malha, "registros_sem_malha": total - com_malha,
        "tipos": [{"codigo": codigo, "nome": nome, "cor": work_types.WORK_TYPE_COLORS.get(codigo)}
                  for codigo, nome in sorted(rotulos.items(), key=lambda item: item[1].casefold())
                  if re.fullmatch(r"[A-Z0-9_-]{1,24}", codigo)],
        "localidades": [{"codigo": str(r["id_localidade"]), "nome": r["nome"]} for r in localidades],
    }}


def camada(target, malha, consulta):
    rotulos = dict(work_types.WORK_TYPE_LABELS)
    grupos = _agrupar(_visitas(target, consulta), rotulos)
    return _montar_camada(target, malha, consulta, grupos, _formas(malha, grupos.keys()), rotulos)


def preparar_offline(target, malha, consulta):
    """Guarda contagens diárias sem fichas ou identificadores de visitas."""
    periodo = {"inicio": consulta["inicio"], "fim": consulta["fim"]}
    rotulos = dict(work_types.WORK_TYPE_LABELS)
    grupos = _agrupar(_visitas(target, consulta | {"localidade": "", "tipo": ""}, por_dia=True), rotulos)
    formas = _formas(malha, grupos.keys())
    recortados = {}
    dias = []
    for chave, visitas in grupos.items():
        for registro in visitas:
            localidade = str(registro["id_localidade"]) if registro["id_localidade"] is not None else ""
            tipo = registro["tipo"]
            dia = registro["ultima"]
            dias.append({"chave": chave, "localidade": localidade, "tipo": tipo, "dia": dia,
                         **{campo: registro[campo] for campo in ("total", "normais", "fechadas", "recuperadas")}})
            if ((not consulta["localidade"] or consulta["localidade"] == localidade)
                    and (not consulta["tipo"] or consulta["tipo"] == tipo)):
                recortados.setdefault(chave, []).append(registro)
    primeira = _montar_camada(target, malha, consulta, recortados, formas, rotulos)
    return primeira, {"periodo": periodo, "malha": formas, "dias": dias}
