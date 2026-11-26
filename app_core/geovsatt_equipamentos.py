"""Cadastro de equipamentos e pontos de interesse na camada versionada do mapa."""

from collections import Counter
import csv
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from app_core import geovsatt_catalogo as catalogo


CODIGO = "predios_publicos"
CAMPOS = {
    "nome": ("Nome", 120), "tipo": ("Categoria", 80), "subtipo": ("Tipo de unidade", 100),
    "logradouro": ("Logradouro", 160), "numero": ("Número", 30), "bairro_loteamento": ("Bairro ou loteamento", 120),
    "cep": ("CEP", 9), "codigo_oficial": ("Código oficial", 60),
    "status_funcionamento": ("Situação", 80), "horario": ("Horário de atendimento", 140),
    "gestao": ("Gestão", 80), "servicos_no_local": ("Serviços no local", 400),
}
TIPOS = ("SAÚDE", "EM", "ERM", "CMEI", "CONVENIADA", "ADMINISTRAÇÃO", "ASSISTÊNCIA SOCIAL",
         "CULTURA, ESPORTE E EDUCAÇÃO", "AGRICULTURA E ABASTECIMENTO", "INFRAESTRUTURA E LOGÍSTICA",
         "SERVIÇOS AO CIDADÃO", "SEGURANÇA", "FUNERÁRIO", "PONTO DE INTERESSE")
COMPLEMENTOS = ("uid", "etiqueta", "servicos_no_local", "horario", "gestao", "codigo_oficial")


class VersaoAlterada(catalogo.CatalogoErro):
    pass


def _normalizar(valor):
    texto = unicodedata.normalize("NFD", str(valor or "").strip().casefold())
    return "".join(letra for letra in texto if not unicodedata.combining(letra))


def _chave(nome, longitude, latitude):
    return _normalizar(nome), round(float(longitude), 6), round(float(latitude), 6)


@lru_cache(maxsize=2)
def _referencia(path):
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as arquivo:
        linhas = [(_chave(row["nome"], row["longitude"], row["latitude"]), row) for row in csv.DictReader(arquivo)]
    totais = Counter(chave for chave, _ in linhas)
    return {chave: row for chave, row in linhas if totais[chave] == 1}


def geojson(camada, base_dir):
    dados = json.loads(camada["geojson"])
    referencia = _referencia(Path(base_dir) / "dados_referencia" / "equipamentos_publicos.csv")
    for feicao in dados["features"]:
        if feicao["geometry"]["type"] != "Point":
            continue
        props = feicao["properties"]
        lon, lat = feicao["geometry"]["coordinates"][:2]
        origem = referencia.get(_chave(props.get("nome"), lon, lat), {})
        for campo in COMPLEMENTOS:
            if origem.get(campo):
                props.setdefault(campo, origem[campo])
    return dados


def listar(camada, base_dir, termo=""):
    if not camada or not camada["id_versao"]:
        return []
    consulta = _normalizar(termo)
    linhas = []
    for indice, feicao in enumerate(geojson(camada, base_dir)["features"]):
        if feicao["geometry"]["type"] != "Point":
            continue
        props = feicao["properties"]
        busca = " ".join(str(props.get(campo) or "") for campo in ("nome", "tipo", "subtipo", "logradouro", "bairro_loteamento"))
        if consulta in _normalizar(busca):
            linhas.append((indice, props))
    return sorted(linhas, key=lambda linha: _normalizar(linha[1].get("nome")))


def _feicao(form):
    props = {chave: catalogo._texto(form.get(chave), limite) for chave, (_, limite) in CAMPOS.items()}
    if not props["nome"] or not props["tipo"]:
        raise catalogo.CatalogoErro("Informe o nome e a categoria do equipamento.")
    cep = props["cep"]
    if cep:
        if not re.fullmatch(r"[0-9]{5}-?[0-9]{3}", cep):
            raise catalogo.CatalogoErro("Informe um CEP com oito dígitos.")
        cep = cep.replace("-", "")
        props["cep"] = f"{cep[:5]}-{cep[5:]}"
    try:
        lon = float(form.get("longitude", "").replace(",", "."))
        lat = float(form.get("latitude", "").replace(",", "."))
    except ValueError as exc:
        raise catalogo.CatalogoErro("Informe latitude e longitude em graus decimais.") from exc
    geometria = {"type": "Point", "coordinates": [lon, lat]}
    return catalogo._validar_feicao({"type": "Feature", "geometry": geometria, "properties": props})[1]


def salvar(target, base_dir, bases, form, usuario_id, versao_esperada, indice=None):
    ponto = _feicao(form)
    with catalogo._escrita(target) as conn:
        if not catalogo._bloquear_camada(conn, CODIGO):
            config = catalogo.configuracao_padrao()
            config.update(niveis=list(catalogo.NIVEIS), setores=list(catalogo.SETORES), cor="#a03d74", rotulo="nome")
            catalogo._criar_camada(conn, CODIGO, ("Equipamentos públicos municipais", "Equipamentos",
                "Equipamentos públicos e pontos de interesse cadastrados no GeoVSATT.", config), bases)
        atual = conn.execute("SELECT id_versao,geojson,metadados FROM geovsatt_versoes WHERE codigo=? AND ativa=1",
                             (CODIGO,)).fetchone()
        versao = atual["id_versao"] if atual else 0
        if versao != versao_esperada:
            raise VersaoAlterada("A camada recebeu outra versão. Volte à lista e abra o cadastro novamente.")
        dados = json.loads(atual["geojson"]) if atual else {"type": "FeatureCollection", "features": []}
        if indice is None:
            dados["features"].append(ponto)
            indice = len(dados["features"]) - 1
        else:
            if not 0 <= indice < len(dados["features"]) or dados["features"][indice]["geometry"]["type"] != "Point":
                raise catalogo.CamadaAusente("Equipamento não encontrado nesta versão.")
            # Preserva os campos complementares do ponto editado, inclusive
            # quando a atualização muda o nome ou a posição usados na conferência.
            existentes = geojson(atual, base_dir)["features"][indice]["properties"]
            ponto["properties"] = existentes | ponto["properties"]
            dados["features"][indice] = ponto
        bruto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        normalizado, tipo, total = catalogo._geojson(bruto)
        metadata = json.loads(atual["metadados"]) if atual else {"fonte": "Cadastro manual no GeoVSATT"}
        metadata.update(data_edicao=date.today().isoformat(), origem_edicao="Cadastro manual no GeoVSATT",
                        versao_anterior=versao or None)
        conn.execute("UPDATE geovsatt_versoes SET ativa=0 WHERE codigo=? AND ativa=1", (CODIGO,))
        nova = catalogo._inserir_versao(conn, CODIGO, ("equipamentos-publicos.geojson", normalizado,
            hashlib.sha256(bruto).hexdigest(), total, tipo, json.dumps(metadata, ensure_ascii=False)), usuario_id, publicar=True)
        catalogo._evento(conn, "equipamento_salvo", CODIGO, {"versao": nova, "anterior": versao or None, "indice": indice})
        return nova
