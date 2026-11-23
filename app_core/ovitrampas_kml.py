"""Mapa de campo com coordenadas consultadas no Conta Ovos na exportação."""

from datetime import datetime
from html import escape
import math
import re
from time import monotonic
from xml.etree import ElementTree as ET

from app_core import contaovos_client, contaovos_registro, db, ovitrampas


NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", NS)
LIMITE_PONTOS = 2000
LIMITE_BYTES = 5 * 1024 * 1024
CAMPOS_LOCAIS = (
    ("localidade", "Localidade"), ("bairro", "Bairro"), ("quarteirao", "Quarteirão"),
    ("rua", "Rua"), ("numero", "Número"), ("complemento", "Complemento"),
    ("localizacao", "Local de instalação"), ("responsavel", "Responsável"),
    ("telefone_responsavel", "Telefone do responsável"),
)


def _texto(valor):
    texto = str(valor) if valor is not None else ""
    return re.sub(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]", "", texto).strip()


def _chave(ident):
    return ovitrampas.chave_comparacao_ovitrampa_id(ident) or _texto(ident).upper()


def _coordenadas_validas(registro):
    lat, lon = registro["latitude"], registro["longitude"]
    return (
        lat is not None and lon is not None
        and math.isfinite(lat) and math.isfinite(lon)
        and -90 <= lat <= 90 and -180 <= lon <= 180
        and (lat, lon) != (0, 0)
        and not registro["coordenada_erro"]
    )


def _selecionado(local, ident, filtros):
    distrito = _texto(filtros.get("distrito"))
    if distrito and _texto(local.get("localidade")).casefold() != distrito.casefold():
        return False
    busca = _texto(filtros.get("busca")).casefold()
    valores = [ident, *(local.get(campo) for campo, _ in CAMPOS_LOCAIS)]
    return not busca or any(busca in _texto(valor).casefold() for valor in valores)


def _campos(registro, local, consultado_em):
    campos = [("ID da ovitrampa", registro["ovitrampa_id_remoto"])]
    campos.extend((rotulo, local.get(campo)) for campo, rotulo in CAMPOS_LOCAIS)
    if local:
        campos.append(("Cadastro local", "Ativo" if local.get("ativo") else "Inativo"))
    else:
        campos.append(("Cadastro local", "Sem correspondência no VSATT"))
    campos.extend((
        ("Município (Conta Ovos)", registro["municipio"]),
        ("Estado (Conta Ovos)", registro["estado"]),
        ("Latitude (Conta Ovos)", registro["latitude"]),
        ("Longitude (Conta Ovos)", registro["longitude"]),
        ("Quarteirão remoto (Conta Ovos)", registro["quarteirao_remoto_id"]),
        ("Média de ovos (Conta Ovos)", registro["ovos_media"]),
        ("Atualização do cadastro no Conta Ovos", registro["atualizado_remoto_em"]),
        ("Consulta ao Conta Ovos", consultado_em),
    ))
    return [(rotulo, _texto(valor)) for rotulo, valor in campos if _texto(valor)]


def gerar_kml(target, filtros=None, *, page_fetcher=None, now=None):
    filtros = filtros or {}
    conn = db.connect(target)
    try:
        locais = {}
        for row in conn.execute(
            "SELECT ovitrampa_id, localidade, bairro, quarteirao, rua, numero, complemento, "
            "localizacao, responsavel, telefone_responsavel, ativo FROM ovitrampas_armadilhas"
        ):
            local = dict(row)
            chave = _chave(local["ovitrampa_id"])
            if chave in locais:
                raise ValueError("Há IDs equivalentes no cadastro local. Revise-os antes de exportar.")
            locais[chave] = local
    finally:
        conn.close()

    inicio = monotonic()
    vistos = {}

    def consultar_pagina(*, page):
        restante = 75 - (monotonic() - inicio)
        if restante <= 0:
            raise contaovos_registro.ContaOvosRegistroError(
                "A consulta ao Conta Ovos demorou demais. Tente exportar novamente."
            )
        rows = page_fetcher(page=page) if page_fetcher else contaovos_client.public_ovitraps_page(
            page=page, timeout=min(12, restante), max_attempts=1
        )
        for row in rows:
            registro = contaovos_registro._normalize_row(row)
            chave = _chave(registro["ovitrampa_id_remoto"])
            if chave in vistos and vistos[chave] != registro:
                raise contaovos_registro.ContaOvosRegistroError(
                    "O Conta Ovos retornou cadastros conflitantes para o mesmo ID. Tente novamente."
                )
            vistos[chave] = registro
        return rows

    remoto = contaovos_registro.fetch_registro(page_fetcher=consultar_pagina)
    consulta = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    pontos, ignoradas = [], []
    for registro in remoto["records"]:
        ident = registro["ovitrampa_id_remoto"]
        local = locais.get(_chave(ident), {})
        if not _selecionado(local, ident, filtros):
            continue
        if not _coordenadas_validas(registro):
            ignoradas.append(ident)
            continue
        pontos.append((registro, local))
    if not pontos:
        raise ValueError(
            "Nenhuma ovitrampa com coordenadas válidas no Conta Ovos para os filtros selecionados."
        )
    if len(pontos) > LIMITE_PONTOS:
        raise ValueError("Há mais de 2.000 pontos. Filtre uma localidade para importar no My Maps.")
    so_locais = sum(
        chave not in vistos and _selecionado(local, local["ovitrampa_id"], filtros)
        for chave, local in locais.items()
    )

    def elemento(pai, tag, texto=None):
        node = ET.SubElement(pai, f"{{{NS}}}{tag}")
        if texto is not None:
            node.text = _texto(texto)
        return node

    raiz = ET.Element(f"{{{NS}}}kml")
    documento = elemento(raiz, "Document")
    elemento(documento, "name", "Ovitrampas — Almirante Tamandaré")
    descricao = (
        f"Consulta ao Conta Ovos em {consulta}. Coordenadas do cadastro remoto atual. "
        "Endereço, responsável, telefone e local de instalação do cadastro local do VSATT. "
        f"{len(pontos)} pontos exportados. {len(ignoradas)} armadilhas sem coordenadas válidas "
        f"ou com sinalização de erro no Conta Ovos. {so_locais} cadastros apenas locais."
    )
    if ignoradas:
        descricao += " IDs sem ponto: " + ", ".join(ignoradas) + "."
    elemento(documento, "description", descricao)

    def ordem(item):
        ident = item[0]["ovitrampa_id_remoto"]
        return (not ident.isdigit(), int(ident) if ident.isdigit() else 0, ident)

    for registro, local in sorted(pontos, key=ordem):
        ponto = elemento(documento, "Placemark")
        elemento(ponto, "name", registro["ovitrampa_id_remoto"])
        campos = _campos(registro, local, consulta)
        html = "<p>Coordenadas do Conta Ovos. Detalhes de campo do cadastro local do VSATT.</p><table>"
        html += "".join(
            f"<tr><th>{escape(rotulo)}</th><td>{escape(valor)}</td></tr>"
            for rotulo, valor in campos
        ) + "</table>"
        elemento(ponto, "description", html)
        dados = elemento(ponto, "ExtendedData")
        for rotulo, valor in campos:
            campo = elemento(dados, "Data")
            campo.set("name", rotulo)
            elemento(campo, "displayName", rotulo)
            elemento(campo, "value", valor)
        geometria = elemento(ponto, "Point")
        elemento(geometria, "coordinates", f"{registro['longitude']},{registro['latitude']},0")
    conteudo = ET.tostring(raiz, encoding="utf-8", xml_declaration=True)
    if len(conteudo) > LIMITE_BYTES:
        raise ValueError("O KML ultrapassa 5 MB. Filtre uma localidade para importar no My Maps.")
    return conteudo, {
        "pontos": len(pontos), "ignoradas": len(ignoradas), "apenas_locais": so_locais,
        "sem_cadastro_local": sum(not local for _, local in pontos), "consultado_em": consulta,
    }
