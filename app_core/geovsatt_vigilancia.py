"""Consultas e importação territorial de dengue, ovitrampas e coletas."""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import csv
from io import StringIO

from shapely.geometry import mapping
from werkzeug.datastructures import MultiDict

from app_core import ambiental, db, esporotricose_bloqueio, geovsatt_bloqueios as bloqueios
from app_core import geovsatt_dengue as dengue, geovsatt_enderecos as enderecos
from app_core import laboratorio, ovitrampas, registro_geografico as rg, visitas_integradas
from app_core.geovsatt_malha import blocos
from app_core.territorio import chave_territorial


DENGUE = ("dengue", "dengue_bloqueios", "dengue_quarteiroes")
OVITRAMPAS = ("ovitrampas", "ovitrampas_bloqueios", "ovitrampas_quarteiroes")
RECORTE_ESPO = "esporotricose_trabalhados"
TUBOS = "coletas_tubos"


def _intervalo(parametros):
    inicio, fim = parametros.get("inicio"), parametros.get("fim")
    periodo = parametros.get("periodo", "")
    try:
        if periodo == "mes":
            ano, mes = map(int, parametros["mes"].split("-"))
            return date(ano, mes, 1).isoformat(), date(ano, mes, monthrange(ano, mes)[1]).isoformat()
        if periodo == "semana":
            ano = int(parametros["ano"])
            semana = int(parametros["semana"])
            janeiro = date(ano, 1, 1)
            primeiro_domingo = janeiro + timedelta(days=(6 - janeiro.weekday()) % 7)
            inicio = primeiro_domingo + timedelta(weeks=semana - 1)
            if not 1 <= semana <= 53 or inicio.year != ano:
                raise ValueError
            return inicio.isoformat(), (inicio + timedelta(days=6)).isoformat()
        if inicio:
            inicio = date.fromisoformat(inicio).isoformat()
        if fim:
            fim = date.fromisoformat(fim).isoformat()
        if inicio and fim and inicio > fim:
            raise ValueError
        return inicio, fim
    except (ValueError, KeyError, OverflowError) as exc:
        raise ValueError("Informe um período válido para a camada.") from exc


def filtrar(registros, parametros, campo_data, campo_localidade, campo_situacao):
    inicio, fim = _intervalo(parametros)
    situacao = rg._norm(parametros.get("situacao"))
    localidade = rg._norm(parametros.get("localidade"))
    for row in registros:
        dia = str(row.get(campo_data) or "")[:10]
        if (inicio or fim) and (not dia or (inicio and dia < inicio) or (fim and dia > fim)):
            continue
        if situacao and situacao != rg._norm(row.get(campo_situacao)):
            continue
        if localidade and localidade not in rg._norm(row.get(campo_localidade)):
            continue
        yield row


def coletas(target):
    presencas = " OR ".join(laboratorio._presence_sql(especie, "r")
                             for especie in ("aegypt", "albopictus", "outra"))
    return visitas_integradas.query(target, f"""
        SELECT c.id_coleta, c.num_tubo, v.id_localidade, v.localidade, v.quarteirao,
               v.logradouro, v.numero, v.data, v.tipo,
               CASE WHEN EXISTS (SELECT 1 FROM resultados_laboratorio r
                                    WHERE r.id_coleta=c.id_coleta AND ({presencas})) THEN 'Positiva'
                    WHEN EXISTS (SELECT 1 FROM resultados_laboratorio r WHERE r.id_coleta=c.id_coleta)
                         THEN 'Negativa'
                    ELSE 'Aguardando resultado' END AS situacao
          FROM coletas c JOIN visitas v ON v.id_visita=c.id_visita
         ORDER BY v.data DESC,c.id_coleta
    """)


def enderecos_coletas(target, localizador):
    for row in coletas(target):
        endereco = enderecos.endereco_rotulado(row)
        chave = chave_territorial(row["id_localidade"], row["quarteirao"])
        if endereco:
            yield row, endereco, chave, localizador.localizar(endereco, esperado=chave)
        else:
            yield row, "", chave, None


def pendencias_csv(target, localizador):
    pendentes = {}
    sem_endereco = 0
    for _, endereco, esperado, localizado in enderecos_coletas(target, localizador):
        if not endereco:
            sem_endereco += 1
        elif not localizado:
            chave = enderecos.chave_endereco(endereco)
            registro = pendentes.setdefault(chave, {"endereco": endereco, "esperados": set(), "total": 0})
            if esperado:
                registro["esperados"].add(esperado)
            registro["total"] += 1
    return pendentes, sem_endereco


def importar_csv(target, conteudo, localizador, *, aplicar=False):
    pendentes, _ = pendencias_csv(target, localizador)
    cabecalho = conteudo.partition("\n")[0]
    leitor = csv.DictReader(StringIO(conteudo), delimiter=";" if ";" in cabecalho else ",")
    if not {"chave", "latitude", "longitude"}.issubset(leitor.fieldnames or []):
        raise ValueError("Use o CSV exportado pelo GeoVSATT e preserve chave, latitude e longitude.")
    alteracoes, problemas, vistos = [], [], set()
    ignorados = 0
    for item in leitor:
        chave = (item.get("chave") or "").strip()
        lat = (item.get("latitude") or "").strip()
        lon = (item.get("longitude") or "").strip()
        if not lat and not lon:
            ignorados += 1
            continue
        pos = enderecos.ponto(lat, lon)
        registro = pendentes.get(chave)
        if chave in vistos:
            erro = "Chave repetida no arquivo."
        elif chave in localizador.verificados and pos == enderecos.ponto(
                localizador.verificados[chave]["latitude"], localizador.verificados[chave]["longitude"]):
            ignorados += 1
            continue
        elif not registro:
            erro = "Chave ausente das pendências atuais."
        elif not pos:
            erro = "Latitude ou longitude inválida."
        elif len(registro["esperados"]) > 1:
            erro = "O endereço está associado a quarteirões divergentes nas visitas."
        elif localizador.validar(pos, next(iter(registro["esperados"]), None)) is None:
            erro = "O ponto está fora do município ou do quarteirão esperado."
        else:
            alteracoes.append((chave, *pos))
            erro = None
        if erro:
            problemas.append({"linha": leitor.line_num, "erro": erro})
        vistos.add(chave)
    if aplicar and alteracoes and not problemas:
        conn = db.connect(target)
        try:
            if db.is_sqlite(target):
                conn.execute("BEGIN IMMEDIATE")
            enderecos.ensure_schema(conn)
            agora = datetime.now(timezone.utc).isoformat()
            for chave, lat, lon in alteracoes:
                conn.execute("""INSERT INTO geovsatt_enderecos_verificados
                                    (chave,latitude,longitude,fonte,atualizado_em) VALUES (?,?,?,?,?)
                                ON CONFLICT (chave) DO NOTHING""", (chave, lat, lon, "CSV verificado", agora))
                salvo = conn.execute("SELECT latitude,longitude FROM geovsatt_enderecos_verificados WHERE chave=?",
                                     (chave,)).fetchone()
                if (salvo["latitude"], salvo["longitude"]) != (lat, lon):
                    raise ValueError("Outra importação alterou um dos pontos. Baixe novamente as pendências.")
            conn.commit()
        finally:
            conn.close()
    return {"validas": len(alteracoes), "ignoradas": ignorados, "problemas": problemas[:100],
            "total_problemas": len(problemas)}


def preparar_dengue(target, localizador, chave=None):
    for row in dengue.casos(target, chave):
        row["situacao"] = dengue.situacao(row["resultado"])
        row["centro"] = None
        row["estado"] = "Notificação conflitante" if row["conflito"] else (
            "Endereço pendente de localização" if row["endereco"] else "Sem endereço")
        if not row["conflito"]:
            coords = enderecos.ponto(row["latitude"], row["longitude"])
            if localizado := localizador.localizar(row["endereco"], coordenadas=coords):
                row["centro"], props, row["fonte_coordenadas"] = localizado
                row["localidade"] = props.get("Localidade_nome")
                row["quarteirao"] = props.get("id_quart")
                row["estado"] = "Localizado"
        row["rotulo"] = f"Notificação {row['notificacao']}"
        row["id"] = row["chave"]
        yield row


def colecao(features, origem):
    return {"type": "FeatureCollection", "features": features, "metadata": {"origem": origem}}


def _ponto(identificador, coordenadas, campos):
    return {"type": "Feature", "id": identificador, "geometry": {"type": "Point",
            "coordinates": list(reversed(coordenadas))}, "properties": campos}


def _raio(evento, raio_metros, campos):
    return {"type": "Feature", "id": evento["id"], "geometry": mapping(
            esporotricose_bloqueio._circulo(*evento["centro"], raio_metros)),
            "properties": campos | {"raio_metros": raio_metros}}


def filtrar_dengue(casos, parametros):
    unidade = rg._norm(parametros.get("unidade"))
    return [row for row in filtrar(casos, parametros, "data_notificacao", "localidade", "situacao")
            if not unidade or unidade in rg._norm(row.get("unidade") or row.get("origem"))]


def camada_dengue(target, codigo, parametros, malha, localizador):
    selecionados = filtrar_dengue(preparar_dengue(target, localizador), parametros)
    colunas = ("notificacao", "ano", "rotulo", "data_notificacao", "data_bloqueio", "situacao",
               "localidade", "quarteirao", "unidade", "fonte_coordenadas")
    features = []
    eventos = []
    raio, periodo = bloqueios.parametros_impressao(parametros, "dengue")
    for row in selecionados:
        if not row["centro"]:
            continue
        campos = {k: row.get(k) for k in colunas}
        if codigo == DENGUE[0]:
            features.append(_ponto(row["id"], row["centro"], campos))
        elif codigo == DENGUE[1]:
            features.append(_raio(row, raio, campos))
        else:
            eventos.append(row)
    if codigo == DENGUE[2]:
        features = bloqueios.execucao(target, "dengue", eventos, malha, periodo=periodo, raio_mapa=raio)
    return colecao(features, "Abas gerais de dengue do Google Sheets")


def camada_tubos(target, parametros, localizador):
    features = []
    registros = {row["id_coleta"]: (row, endereco, esperado, localizado)
                 for row, endereco, esperado, localizado in enderecos_coletas(target, localizador)}
    for row in filtrar((v[0] for v in registros.values()), parametros, "data", "localidade", "situacao"):
        _, _, _, localizado = registros[row["id_coleta"]]
        if localizado:
            pos, _, fonte = localizado
            campos = {k: row[k] for k in ("num_tubo", "data", "localidade", "quarteirao", "situacao", "tipo")}
            features.append(_ponto(row["id_coleta"], pos, campos | {"fonte_coordenadas": fonte,
                                  "rotulo": f"Tubo {row['num_tubo']}"}))
    return colecao(features, "Coletas e resultados do laboratório VSATT")


def camada_ovitrampas(target, codigo, parametros, malha):
    registros = ovitrampas.leituras_para_bloqueio(target)
    for row in registros:
        ovos = row["ovos"]
        row["situacao"] = "Sem contagem" if ovos is None else "Positiva" if ovos > 0 else "Negativa"
    if parametros.get("periodo") == "semana":
        selecionados = [row for row in registros if str(row["ano"]) == str(parametros.get("ano"))
                        and str(row["semana"]) == str(parametros.get("semana", "")).lstrip("0")]
        _intervalo(parametros)
        params_semana = dict(parametros, periodo="", inicio="", fim="")
        registros = filtrar(selecionados, params_semana, "data_coleta", "localidade", "situacao")
    else:
        registros = filtrar(registros, parametros, "data_coleta", "localidade", "situacao")
    raio, periodo = bloqueios.parametros_impressao(parametros, "ovitrampas")
    features, eventos, vistos, positivas = [], [], set(), set()
    historico = any(_intervalo(parametros))
    for row in registros:
        evento = bloqueios.evento_ovitrampa(row)
        if not evento["centro"]:
            continue
        campos = {k: row[k] for k in ("ovitrampa_id", "data_coleta", "ano", "semana", "ovos",
                                     "situacao", "localidade", "quarteirao")}
        campos["resultado"] = campos["situacao"]
        if row["situacao"] == "Positiva":
            campos["leitura_bloqueio"] = row["id_leitura"]
        if codigo == OVITRAMPAS[0] and row["ovitrampa_id"] not in vistos:
            features.append(_ponto(row["ovitrampa_id"], evento["centro"], campos))
            vistos.add(row["ovitrampa_id"])
        if row["situacao"] == "Positiva" and (historico or row["ovitrampa_id"] not in positivas):
            positivas.add(row["ovitrampa_id"])
            if codigo == OVITRAMPAS[1]:
                features.append(_raio(evento, raio, campos))
            elif codigo == OVITRAMPAS[2]:
                eventos.append(evento)
    if codigo == OVITRAMPAS[2]:
        features = bloqueios.execucao(target, "ovitrampas", eventos, malha, periodo=periodo, raio_mapa=raio)
    return colecao(features, "Leituras válidas no cadastro de ovitrampas do VSATT")


def camada_esporotricose(target, parametros, malha, pontos):
    candidatos = []
    for ponto in pontos["features"]:
        props = ponto["properties"]
        lon, lat = ponto["geometry"]["coordinates"]
        candidatos.append(props | {"id": ponto["id"], "centro": (lat, lon)})
    eventos = list(filtrar(candidatos, parametros, "data_bloqueio", "localidade", "situacao_bloqueio"))
    raio, periodo = bloqueios.parametros_impressao(parametros, "esporotricose")
    features = bloqueios.execucao(target, "esporotricose", eventos, malha, periodo=periodo, raio_mapa=raio)
    return colecao(features, "Visitas registradas pela Vigilância Ambiental")


def _camada_indicadores(malha, dados, parametros, origem):
    feicoes = []
    localidade = rg._norm(parametros.get("localidade"))
    quarteirao = parametros.get("quarteirao")
    for props, geom in blocos(malha):
        chave = chave_territorial(props.get("Localidade"), props.get("id_quart"))
        if not chave or chave not in dados:
            continue
        if localidade and localidade != rg._norm(props.get("Localidade_nome")):
            continue
        if quarteirao and chave_territorial(props["Localidade"], quarteirao) != chave:
            continue
        feicoes.append({"type": "Feature", "id": chave, "geometry": mapping(geom),
                        "properties": {k: props.get(k) for k in ("chave", "id_quart", "Localidade", "Localidade_nome")}
                                      | dados[chave] | {"rotulo": f"Q. {props['id_quart']}"}})
    return colecao(feicoes, origem)


def indicadores_endemias(target, parametros, malha):
    from blueprints.mapa import resumo_endemias
    inicio, fim = _intervalo(parametros)
    args = MultiDict((k, v) for k, v in (("d_ini", inicio), ("d_fim", fim),
                                            ("tipo", parametros.get("tipo"))) if v)
    dados = resumo_endemias(db.connect(target), args)
    modo = parametros.get("modo", "")
    for row in dados.values():
        score = (2*min(row["focos"], 4) + 2*min(row["focos_pendentes"], 3)
                 + 2*min(row["pes_atrasados"], 3) + min(row["ovi_positivas"], 4) + min(row["fechados"], 6))
        row["pontuacao_atencao"] = score
        metricas = {"focos": row["focos"], "acesso": row["fechados"] + row["recusas"],
                    "pes": row["pes_ativos"], "ovis": row["ovi_positivas"], "atencao": score}
        quantidade = metricas.get(modo, row["total"])
        row["faixa"] = "0" if not quantidade else "1" if quantidade == 1 else "2–3" if quantidade <= 3 else "4 ou mais"
        row["tipos_registrados"] = ", ".join(f"{tipo} ({total})" for tipo, total in sorted(row.pop("tipos").items()))
    return _camada_indicadores(malha, dados, parametros, "Indicadores do Endemias por quarteirão")


def visitas_ambientais(target, parametros, malha):
    from blueprints.ambiental import filtros
    inicio, fim = _intervalo(parametros)
    args = filtros(dict(parametros) | {"d_ini": inicio or "", "d_fim": fim or ""})
    dados = defaultdict(lambda: {"total_registros": 0, "esporotricose": 0, "amostras_animais": 0})
    for row in ambiental.linhas(target, args):
        chave = chave_territorial(row["id_localidade"], row["quarteirao"])
        if chave:
            contadores = dados[chave]
            contadores["total_registros"] += row["registros"]
            campo = "esporotricose" if row["fonte"] == "Esporotricose" else "amostras_animais"
            contadores[campo] += row["registros"]
    for row in dados.values():
        n = row["total_registros"]
        row["faixa"] = "1" if n == 1 else "2–3" if n <= 3 else "4 ou mais"
    return _camada_indicadores(malha, dados, parametros, "Visitas e amostras da Vigilância Ambiental")
