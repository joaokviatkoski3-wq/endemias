"""Consultas e importação territorial de dengue, ovitrampas e coletas."""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import csv
from io import BytesIO, StringIO
from math import cos, radians
import re
from zipfile import BadZipFile, ZipFile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from shapely.affinity import scale
from shapely.geometry import Point, mapping, shape
from shapely.ops import nearest_points
from werkzeug.datastructures import MultiDict

from app_core import ambiental, db, esporotricose_bloqueio, geovsatt_bloqueios as bloqueios
from app_core import geovsatt_dengue as dengue, geovsatt_enderecos as enderecos
from app_core import laboratorio, ovitrampas, pontos_estrategicos, registro_geografico as rg, visitas_integradas
from app_core.geovsatt_malha import blocos
from app_core.territorio import chave_territorial


DENGUE = ("dengue", "dengue_bloqueios", "dengue_quarteiroes")
OVITRAMPAS = ("ovitrampas", "ovitrampas_bloqueios", "ovitrampas_quarteiroes")
RECORTE_ESPO = "esporotricose_trabalhados"
TUBOS = "coletas_tubos"
ESPECIES_TUBOS = {"aegypt": "Aedes aegypti", "albopictus": "Aedes albopictus", "outra": "Outras espécies"}
INICIO_COLETAS = "2026-01-01"
LIMITE_COORDENADAS = 12 * 1024**2
KML = "{http://www.opengis.net/kml/2.2}"
CHAVE_ENDERECO_KML = re.compile(r"[0-9a-f]{64}")


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


def coletas(target, id_coleta=None):
    presencas = ", ".join(f"""EXISTS (SELECT 1 FROM resultados_laboratorio r
                                     WHERE r.id_coleta=c.id_coleta AND {laboratorio._presence_sql(especie, "r")}) AS tem_{especie}"""
                         for especie in ESPECIES_TUBOS)
    conn = visitas_integradas.connect(target)
    try:
        tem_posicoes = db.table_exists(conn, "geovsatt_posicoes_coletas")
        tem_posicoes_liraa = db.table_exists(conn, "geovsatt_posicoes_tubitos_liraa")
        campos_posicao = []
        vinculos_posicao = []
        if tem_posicoes:
            campos_posicao.append("p")
            vinculos_posicao.append("LEFT JOIN geovsatt_posicoes_coletas p ON p.id_coleta=c.id_coleta")
        if tem_posicoes_liraa:
            campos_posicao.append("pl")
            vinculos_posicao.append(f"""LEFT JOIN geovsatt_posicoes_tubitos_liraa pl
                ON v.tipo='LIRAA' AND c.id_coleta='{visitas_integradas.TUBO_PREFIXO}' || CAST(pl.id_tubito AS TEXT)""")
        posicoes_sql = ", ".join(
            f"COALESCE({', '.join(alias + '.' + campo for alias in campos_posicao)}, NULL) AS {campo}"
            if campos_posicao else f"NULL AS {campo}" for campo in ("latitude", "longitude")
        )
        condicao = " AND c.id_coleta=?" if id_coleta is not None else ""
        parametros = (INICIO_COLETAS, id_coleta) if condicao else (INICIO_COLETAS,)
        registros = [db.serialize_row(row) for row in conn.execute(f"""
        SELECT {posicoes_sql}, c.id_coleta, c.num_tubo, v.id_localidade, v.localidade, v.quarteirao,
               v.logradouro, v.numero, v.data, v.tipo, v.id_pe, v.codigo_pe,
               pe.id_pe AS pe_id_cadastrado, pe.codigo_pe AS pe_cadastrado,
               pe.latitude AS pe_latitude, pe.longitude AS pe_longitude,
               {presencas},
               EXISTS (SELECT 1 FROM resultados_laboratorio r WHERE r.id_coleta=c.id_coleta) AS tem_resultado
          FROM coletas c JOIN visitas v ON v.id_visita=c.id_visita
          LEFT JOIN pontos_estrategicos pe ON pe.id_pe=v.id_pe
                OR (v.id_pe IS NULL AND pe.codigo_pe=NULLIF(TRIM(v.codigo_pe),''))
          {" ".join(vinculos_posicao)}
         WHERE v.data >= ?{condicao}
         ORDER BY v.data DESC,c.id_coleta
        """, parametros)]
        aliases = {}
        for row in registros:
            row["especies"] = [especie for especie in ESPECIES_TUBOS if row.pop(f"tem_{especie}")]
            tem_resultado = row.pop("tem_resultado")
            row["situacao"] = "Positiva" if row["especies"] else ("Negativa" if tem_resultado else "Aguardando resultado")
            if row["tipo"] != "PE" or row["id_pe"] is not None or (row["codigo_pe"] or "").strip():
                continue
            chave = (row["logradouro"], row["localidade"])
            if chave not in aliases:
                vinculo = pontos_estrategicos.resolver_alias_visita(conn, *chave)
                aliases[chave] = conn.execute("""
                    SELECT id_pe AS pe_id_cadastrado, codigo_pe AS pe_cadastrado,
                           latitude AS pe_latitude, longitude AS pe_longitude
                      FROM pontos_estrategicos WHERE id_pe=?
                """, (vinculo["id_pe"],)).fetchone() if vinculo else None
            if aliases[chave]:
                row.update(db.serialize_row(aliases[chave]))
        return registros
    finally:
        conn.close()


def _e_coleta_pe(row):
    return row["tipo"] == "PE" or row["id_pe"] is not None or bool((row["codigo_pe"] or "").strip())


def _ovitrampas_por_endereco(target):
    posicoes = defaultdict(set)
    conn = db.connect(target)
    try:
        if not db.table_exists(conn, "ovitrampas_armadilhas"):
            return posicoes
        for row in conn.execute("""SELECT rua, numero, latitude, longitude FROM ovitrampas_armadilhas
                                   WHERE latitude IS NOT NULL AND longitude IS NOT NULL"""):
            chave = enderecos.chave_logradouro_numero(row["rua"], row["numero"])
            pos = enderecos.ponto(row["latitude"], row["longitude"])
            if chave and pos:
                posicoes[chave].add(pos)
    finally:
        conn.close()
    return posicoes


def filtros_coletas(parametros):
    parametros = parametros or {}
    tipo = rg._norm(parametros.get("tipo")).upper()
    especie = rg._norm(parametros.get("especie"))
    if especie and especie not in ESPECIES_TUBOS:
        raise ValueError("Selecione uma espécie disponível para as coletas.")
    return {campo: valor for campo, valor in (("especie", especie), ("tipo", tipo)) if valor}


def enderecos_coletas(target, localizador, id_coleta=None, *, parametros=None):
    recorte = filtros_coletas(parametros)
    especie, tipo = recorte.get("especie"), recorte.get("tipo")
    ovitrampas_por_endereco = None
    for row in coletas(target, id_coleta):
        if ((tipo and rg._norm(row["tipo"]).upper() != tipo)
                or (especie and especie not in row["especies"])):
            continue
        if _e_coleta_pe(row):
            pos = enderecos.ponto(row["pe_latitude"], row["pe_longitude"])
            fonte = f"Ponto estratégico · {row['pe_cadastrado']}" if pos else None
            yield row, "", None, (pos, {}, fonte) if pos else None
            continue
        endereco = enderecos.endereco_rotulado(row)
        chave = chave_territorial(row["id_localidade"], row["quarteirao"])
        posicao = enderecos.ponto(row["latitude"], row["longitude"])
        if (props := localizador.validar(posicao, aceitar_sem_quarteirao=True)) is not None:
            yield row, endereco, chave, (posicao, props, "Ajuste no GeoVSATT")
            continue
        localizado = localizador.localizar(endereco, esperado=chave, localidade_ubs=True)
        if localizado is None and chave:
            via_numero = enderecos.chave_logradouro_numero(row["logradouro"], row["numero"])
            if via_numero:
                if ovitrampas_por_endereco is None:
                    ovitrampas_por_endereco = _ovitrampas_por_endereco(target)
                opcoes = [(pos, props) for pos in ovitrampas_por_endereco.get(via_numero, ())
                          if (props := localizador.validar(pos, chave)) is not None]
                if len(opcoes) == 1:
                    localizado = (*opcoes[0], "Cadastro de ovitrampas · mesmo endereço")
        yield row, endereco, chave, localizado


class PosicaoJaConfirmada(ValueError):
    pass


def reposicionar_coleta(target, localizador, id_coleta, latitude, longitude, *, primeira_posicao=False):
    if primeira_posicao:
        registro = next(enderecos_coletas(target, localizador, id_coleta), None)
        if registro is None:
            raise LookupError
        row, _, _, localizado = registro
    else:
        registros = coletas(target, id_coleta)
        if not registros:
            raise LookupError
        row = registros[0]
    if _e_coleta_pe(row):
        raise ValueError("A posição deste tubo vem do cadastro do ponto estratégico.")
    if primeira_posicao and localizado:
        raise PosicaoJaConfirmada("A coleta já tem uma posição. Abra o mapa para revisar o marcador.")
    posicao = enderecos.ponto(latitude, longitude)
    if localizador.validar(posicao, aceitar_sem_quarteirao=True) is None:
        raise ValueError("Marque uma posição válida no município.")
    conn = db.connect(target)
    try:
        enderecos.ensure_schema(conn)
        prefixo = visitas_integradas.TUBO_PREFIXO
        if row["tipo"] == "LIRAA" and id_coleta.startswith(prefixo):
            tabela, campo, chave = "geovsatt_posicoes_tubitos_liraa", "id_tubito", int(id_coleta[len(prefixo):])
        else:
            tabela, campo, chave = "geovsatt_posicoes_coletas", "id_coleta", id_coleta
        acao = "DO NOTHING" if primeira_posicao else (
            "DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,atualizado_em=excluded.atualizado_em")
        escrita = conn.execute(f"""INSERT INTO {tabela}({campo},latitude,longitude,atualizado_em)
                                   VALUES(?,?,?,?) ON CONFLICT({campo}) {acao}""",
                                (chave, *posicao, datetime.now(timezone.utc).isoformat()))
        if primeira_posicao and not escrita.rowcount:
            raise PosicaoJaConfirmada("A coleta já tem uma posição. Abra o mapa para revisar o marcador.")
        conn.commit()
    finally:
        conn.close()
    return posicao


def pendencias_csv(target, localizador, *, incluir_automaticos=False, listar=False, parametros=None):
    pendentes = {}
    resumo = dict(coletas=0, com_resultado=0, sem_endereco=0, pe_aguardando=0,
                  pe_georreferenciado=0, outras_localizadas=0, coletas_endereco_pendente=0)
    if listar:
        resumo["lista_pendencias"] = []
    for row, endereco, esperado, localizado in enderecos_coletas(target, localizador, parametros=parametros):
        if listar and not localizado:
            resumo["lista_pendencias"].append({
                "id": row["id_coleta"], "tubo": row["num_tubo"], "data": row["data"],
                "logradouro": row["logradouro"], "numero": row["numero"], "localidade": row["localidade"],
                "quarteirao": row["quarteirao"], "tipo": row["tipo"], "pe": _e_coleta_pe(row),
                "especies": ", ".join(ESPECIES_TUBOS[e] for e in row["especies"]),
                "codigo_pe": row["pe_cadastrado"] or row["codigo_pe"], "pe_id": row["pe_id_cadastrado"],
            })
        resumo["coletas"] += 1
        resumo["com_resultado"] += row["situacao"] != "Aguardando resultado"
        if _e_coleta_pe(row):
            resumo["pe_georreferenciado" if localizado else "pe_aguardando"] += 1
            continue
        chave = enderecos.chave_endereco(endereco) if endereco else None
        if localizado:
            resumo["outras_localizadas"] += 1
            if not incluir_automaticos or not chave or chave in localizador.verificados or localizado[2] == "Ajuste no GeoVSATT":
                continue
        elif not endereco:
            resumo["sem_endereco"] += 1
            continue
        else:
            resumo["coletas_endereco_pendente"] += 1
        endereco_earth = ", ".join(str(x).strip() for x in
                                  (row["logradouro"], row["numero"], "Almirante Tamandaré", "Paraná", "Brasil")
                                  if x is not None and str(x).strip())
        registro = pendentes.setdefault(chave, {"endereco": endereco, "endereco_earth": endereco_earth,
                                                "esperados": set(), "total": 0})
        if esperado:
            registro["esperados"].add(esperado)
        registro["total"] += 1
    return pendentes, resumo


def _registros_csv(conteudo):
    cabecalho = conteudo.partition("\n")[0]
    leitor = csv.DictReader(StringIO(conteudo), delimiter=";" if ";" in cabecalho else ",")
    if not {"chave", "latitude", "longitude"}.issubset(leitor.fieldnames or []):
        raise ValueError("Use o CSV exportado pelo GeoVSATT e preserve chave, latitude e longitude.")
    for item in leitor:
        yield leitor.line_num, item


def _chave_do_marcador(marcador, esquemas):
    nome = marcador.findtext(f"{KML}name", "").strip()
    if CHAVE_ENDERECO_KML.fullmatch(nome):
        return nome
    chaves = set()
    for dados in marcador.findall(f"{KML}ExtendedData/{KML}SchemaData"):
        campos = esquemas.get(dados.get("schemaUrl"), ())
        for campo in dados.findall(f"{KML}SimpleData"):
            valor = (campo.text or "").strip()
            if campo.get("name") in campos and CHAVE_ENDERECO_KML.fullmatch(valor):
                chaves.add(valor)
    return next(iter(chaves)) if len(chaves) == 1 else nome


def _registros_kml(conteudo):
    try:
        if conteudo.startswith(b"PK"):
            with ZipFile(BytesIO(conteudo)) as kmz:
                arquivos = [info for info in kmz.infolist() if info.filename.lower().endswith(".kml")]
                if len(arquivos) != 1 or arquivos[0].file_size > LIMITE_COORDENADAS:
                    raise ValueError("O KMZ deve conter um único KML de até 12 MiB.")
                conteudo = kmz.read(arquivos[0])
        arvore = ElementTree.fromstring(conteudo)
    except (BadZipFile, DefusedXmlException, ElementTree.ParseError, RuntimeError) as exc:
        raise ValueError("Não foi possível ler o KML ou KMZ.") from exc
    esquemas = {
        f"#{esquema.get('id')}": {
            campo.get("name") for campo in esquema.findall(f"{KML}SimpleField")
            if campo.get("name") and campo.findtext(f"{KML}displayName", "").strip().casefold() in {"name", "chave"}
        }
        for esquema in arvore.findall(f".//{KML}Schema") if esquema.get("id")
    }
    pontos = arvore.findall(f".//{KML}Placemark")
    if not pontos:
        raise ValueError("O arquivo não contém marcadores do Google Earth.")
    for i, marcador in enumerate(pontos, 1):
        chave = _chave_do_marcador(marcador, esquemas)
        coordenadas = marcador.findtext(f"{KML}Point/{KML}coordinates", "").strip()
        lon, lat, *_ = coordenadas.split(",") + ["", ""]
        if not lat or not lon:
            lat = "inválida"
        yield i, {"chave": chave, "latitude": lat, "longitude": lon}


def importar_coordenadas(target, conteudo, localizador, *, formato="csv", aplicar=False):
    # Um CSV anterior pode conter endereços já localizados automaticamente.
    pendentes, _ = pendencias_csv(target, localizador, incluir_automaticos=True)
    if formato == "csv":
        leitor = _registros_csv(conteudo.decode("utf-8-sig"))
        fonte = "CSV verificado"
    elif formato in {"kml", "kmz"}:
        leitor = _registros_kml(conteudo)
        fonte = "Google Earth"
    else:
        raise ValueError("Selecione um arquivo CSV, KML ou KMZ.")
    alteracoes, problemas, vistos = [], [], set()
    ignorados = 0
    for linha, item in leitor:
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
            problemas.append({"linha": linha, "erro": erro})
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
                                ON CONFLICT (chave) DO NOTHING""", (chave, lat, lon, fonte, agora))
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
            props = localizador.validar(coords, aceitar_sem_quarteirao=True)
            localizado = (coords, props, "Google Sheets") if props is not None else localizador.localizar(row["endereco"])
            if localizado:
                row["centro"], props, row["fonte_coordenadas"] = localizado
            elif coords:
                row["estado"] = "Coordenadas fora da cobertura municipal"
            if row["centro"]:
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
        elif row["ano"] >= 2026 and row["situacao"] != "Negativo ou descartado":
            if codigo == DENGUE[1]:
                features.append(_raio(row, raio, campos))
            else:
                eventos.append(row)
    if codigo == DENGUE[2]:
        features = bloqueios.execucao(target, "dengue", eventos, malha, periodo=periodo, raio_mapa=raio)
    return colecao(features, "Abas gerais de dengue do Google Sheets")


def _pontos_aproximados(aproximaveis, localizador, malha, obter_logradouros):
    if not aproximaveis:
        return {}
    solicitadas = set(aproximaveis.values())
    vias = {via for _, via in solicitadas if via}
    try:
        dados_ruas = obter_logradouros() if vias else {}
    except (OSError, ValueError):
        dados_ruas = {}
    eixos = defaultdict(list)
    for feicao in dados_ruas.get("features", []):
        rua = rg._sem_prefixo_logradouro((feicao.get("properties") or {}).get("nome"))
        geometria = feicao.get("geometry") or {}
        if rua in vias and geometria.get("type") in {"LineString", "MultiLineString"}:
            eixo = shape(geometria)
            if not eixo.is_empty:
                eixos[rua].append(eixo)

    geometria_por_chave = {chave_territorial(props.get("Localidade"), props.get("id_quart")): geometria
                           for props, geometria in blocos(malha, {chave for chave, _ in solicitadas})}
    resultado = {}
    for chave, rua in solicitadas:
        geometria = geometria_por_chave.get(chave)
        if geometria is None:
            continue
        centro = geometria.centroid
        if not geometria.contains(centro):
            centro = geometria.representative_point()
        pos = (centro.y, centro.x)
        fonte = "Posição aproximada no quarteirão · aguarda confirmação"
        if eixos[rua]:
            # A longitude representa uma distância menor que a latitude no município.
            escala = cos(radians(centro.y))
            linhas = (scale(eixo, xfact=escala, origin=centro) for eixo in eixos[rua])
            mais_proxima = min(linhas, key=centro.distance)
            _, projecao = nearest_points(centro, mais_proxima)
            metade = Point(centro.x + (projecao.x - centro.x) / (2 * escala), (centro.y + projecao.y) / 2)
            if geometria.contains(metade) and localizador.validar((metade.y, metade.x), chave) is not None:
                pos = (metade.y, metade.x)
                fonte = "Posição aproximada entre o centro do quarteirão e o logradouro · aguarda confirmação"
        if localizador.validar(pos, chave) is not None:
            resultado[chave, rua] = pos, fonte
    return resultado


def camada_tubos(target, parametros, localizador, malha, obter_logradouros):
    registros = {row["id_coleta"]: (row, endereco, esperado, localizado)
                 for row, endereco, esperado, localizado in enderecos_coletas(target, localizador, parametros=parametros)}
    selecionados = list(filtrar((v[0] for v in registros.values()), parametros, "data", "localidade", "situacao"))
    aproximaveis = {}
    for row in selecionados:
        _, endereco, esperado, localizado = registros[row["id_coleta"]]
        if (not localizado and esperado and endereco and not _e_coleta_pe(row)
                and not enderecos.chave_logradouro_numero(row["logradouro"], row["numero"])):
            aproximaveis[row["id_coleta"]] = (esperado, rg._sem_prefixo_logradouro(row["logradouro"]))

    pontos_do_quarteirao = _pontos_aproximados(aproximaveis, localizador, malha, obter_logradouros)

    features = []
    for row in selecionados:
        id_coleta = row["id_coleta"]
        _, _, _, localizado = registros[id_coleta]
        campos = {k: row[k] for k in ("num_tubo", "data", "localidade", "quarteirao", "situacao", "tipo")}
        if localizado:
            pos, _, fonte = localizado
        elif posicao := pontos_do_quarteirao.get(aproximaveis.get(id_coleta)):
            pos, fonte = posicao
            campos["localizacao_aproximada"] = True
        else:
            continue
        features.append(_ponto(id_coleta, pos, campos | {"fonte_coordenadas": fonte,
                               "especies": ", ".join(ESPECIES_TUBOS[e] for e in row["especies"]),
                               "vinculado_pe": _e_coleta_pe(row), "rotulo": f"Tubo {row['num_tubo']}"}))
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
