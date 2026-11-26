"""Busca territorial pelo RG e consultas públicas de endereçamento postal."""

from collections import OrderedDict, namedtuple
from hashlib import sha256
from http.client import HTTPException
import json
import math
import re
from threading import Lock
from time import monotonic
from unicodedata import normalize
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app_core import db, registro_geografico as rg


CEP_PATTERN = re.compile(r"[0-9]{5}-?[0-9]{3}")
NUMERO_PATTERN = re.compile(r"([0-9]+)([a-z]?)")
Endereco = namedtuple("Endereco", "via numero localidade")


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_CEP_HTTP = build_opener(_SemRedirecionamento())
_NOMINATIM_CACHE = OrderedDict()
_NOMINATIM_LOCK = Lock()
_NOMINATIM_PROXIMA = 0.0
_NOMINATIM_ATIVA = False
# Almirante Tamandaré e margem para vias que chegam à divisa.
_NOMINATIM_LIMITES = (-49.46, -25.40, -49.21, -25.21)


def _numero(texto):
    normalizado = rg._norm(texto).replace(" ", "")
    if normalizado in {"s/n", "sn"}:
        return "sn"
    encontrado = NUMERO_PATTERN.fullmatch(normalizado)
    if encontrado:
        digitos, sufixo = encontrado.groups()
        return (digitos.lstrip("0") or "0") + sufixo
    return ""


def _tokens(texto):
    return rg._normalizar_logradouro(texto).split()


def _localidade(texto):
    tokens = _tokens(texto)
    return tokens[1:] if tokens[:1] in (["bairro"], ["localidade"]) else tokens


def _interpretar(termo):
    consulta = rg._norm(termo)
    consulta = re.sub(r"(?:[,;\s-]+cep\s*|[,;\s]+)\d{5}-\d{3}$|[,;\s-]+cep\s*\d{8}$", "", consulta)
    consulta = re.sub(r",\s*brasil$", "", consulta)
    consulta = re.sub(r"(?:,|\s+-)\s*(?:pr|parana)$", "", consulta)
    consulta = re.sub(r"(?:,|\s+-)\s*almirante tamandare$", "", consulta).strip(" ,;-")
    consulta = re.sub(r"\bn(?:[º°.]|o\.?)\s*(?=\d)", "", consulta)
    consulta = re.sub(r"\bs\s*/\s*n\b", "sn", consulta)
    rua, separador, resto = consulta.partition(",")
    via = rg._sem_prefixo_logradouro(rua).split()
    if not via:
        return [], None
    abreviacoes = rg.ABREVIACOES_LOGRADOURO
    variaveis = set(abreviacoes) | set(abreviacoes.values()) | rg.PREFIXOS_LOGRADOURO
    candidatos = [p for p in re.findall(r"[a-z]+", rua) if len(p) >= 3 and p not in variaveis]
    filtro = max(candidatos, key=len, default=None)
    if separador:
        resto = resto.strip(" ,-")
        numero = re.match(r"^([0-9]+[a-z]?|sn)(?=[\s,;-]|$)", resto)
        if numero:
            return [Endereco(via, _numero(numero[0]), _localidade(resto[numero.end():]))], filtro
        return [Endereco(via, "", _localidade(resto))], filtro
    opcoes = [Endereco(via, "", [])]
    for indice, token in enumerate(via[1:], 1):
        if numero := _numero(token):
            localidade = via[indice + 1:]
            if localidade[:1] in (["bairro"], ["localidade"]):
                localidade = localidade[1:]
            opcoes.append(Endereco(via[:indice], numero, localidade))
    # Um termo depois do número pode ser o bairro e não integrar o logradouro.
    # Nessa forma o filtro usa um token anterior ao primeiro número possível.
    if len(opcoes) > 1:
        texto = opcoes[1].via
        filtro = max((p for p in texto if p in candidatos), key=len, default=None)
    return opcoes, filtro


def _encontra(consulta, base):
    if not consulta:
        return True
    tamanho = len(consulta)
    for indice in range(len(base) - tamanho + 1):
        trecho = base[indice:indice + tamanho]
        if trecho[:-1] == consulta[:-1] and (
            trecho[-1] == consulta[-1] or len(consulta[-1]) >= 3 and trecho[-1].startswith(consulta[-1])
        ):
            return True
    return False


def buscar_enderecos(target, termo, limite, *, sugerir=False, por_logradouro=False):
    opcoes, filtro = _interpretar(termo)
    if not opcoes or sum(map(len, opcoes[0].via)) < 3:
        return []
    where = """
        WHERE i.logradouro IS NOT NULL AND i.logradouro <> ''
          AND i.id_localidade IS NOT NULL AND COALESCE(i.quarteirao,'') <> ''
          AND COALESCE(i.tipo,'') <> 'REF'
    """
    parametros = ()
    if filtro:
        where += " AND (i.busca_normalizada LIKE ? OR COALESCE(i.busca_normalizada,'') = '')"
        parametros = (f"%{filtro}%",)
    grupos = {}
    conn = db.connect(target)
    try:
        for registro in conn.execute(f"""
            SELECT i.id_imovel,i.id_localidade,i.localidade,i.quarteirao,i.logradouro,i.numero
              FROM registro_geografico_imoveis i {where}
        """, parametros):
            via = rg._sem_prefixo_logradouro(registro["logradouro"]).split()
            numero = _numero(registro["numero"])
            localidade = _localidade(registro["localidade"])
            for busca in opcoes:
                confere_numero = numero.startswith(busca.numero) if sugerir else busca.numero == numero
                if (busca.numero and not confere_numero) or not (
                    _encontra(busca.via, via) and _encontra(busca.localidade, localidade)
                ):
                    continue
                prioridade = (bool(busca.numero), busca.via == via, bool(busca.localidade),
                              bool(busca.numero) and busca.numero == numero)
                chave = (tuple(_tokens(registro["logradouro"])) if por_logradouro else
                         (registro["id_localidade"], registro["quarteirao"], tuple(via), numero if busca.numero else ""))
                grupo = grupos.get(chave)
                if grupo is None or prioridade > grupo[0]:
                    grupos[chave] = (prioridade, registro, [registro["id_imovel"]])
                elif busca.numero and not por_logradouro:
                    grupo[2].append(registro["id_imovel"])
    finally:
        conn.close()
    ordenados = sorted(grupos.values(), key=lambda p: (
        *(-int(item) for item in p[0]), rg._norm(p[1]["logradouro"]),
        rg._norm(p[1]["localidade"]), p[1]["quarteirao"], p[1]["id_imovel"]
    ))
    # Se o número foi reconhecido, não misturar o resultado com trechos genéricos.
    if ordenados and ordenados[0][0][0]:
        ordenados = [item for item in ordenados if item[0][0]]
    resultados = []
    for prioridade, registro, ids in ordenados[:limite]:
        quarteirao = rg._quarteirao_display(registro["quarteirao"])
        titulo = registro["logradouro"]
        if prioridade[0]:
            titulo += f", {registro['numero']}"
        resultados.append({
            "tipo": "endereco", "titulo": titulo,
            "logradouro": registro["logradouro"],
            "subtitulo": f"{registro['localidade']} · Q. {quarteirao} · Cadastro RG",
            "id_localidade": registro["id_localidade"], "quarteirao": quarteirao,
            "chave": f"{registro['id_localidade']}:{quarteirao}",
            "imoveis": sorted(set(ids))[:100] if prioridade[0] and not por_logradouro else [],
        })
    return resultados


class CepInexistente(ValueError):
    pass


def _consulta_postal(url, provedor, limite, *, erro_404=None, bearer=None):
    cabecalhos = {"Accept": "application/json", "User-Agent": "VSATT/GeoVSATT"}
    if bearer:
        cabecalhos["Authorization"] = f"Bearer {bearer}"
    requisicao = Request(url, headers=cabecalhos)
    indisponivel = f"O serviço {provedor} está indisponível. A busca no RG continua disponível."
    try:
        with _CEP_HTTP.open(requisicao, timeout=4) as resposta:
            if resposta.status != 200:
                raise RuntimeError(indisponivel)
            conteudo = resposta.read(limite + 1)
            if len(conteudo) > limite:
                raise RuntimeError(f"Resposta inesperada de {provedor}.")
            return json.loads(conteudo)
    except HTTPError as erro:
        erro.close()
        if erro.code == 404 and erro_404:
            raise CepInexistente(erro_404) from erro
        raise RuntimeError(indisponivel) from erro
    except (OSError, HTTPException, json.JSONDecodeError, UnicodeError) as erro:
        raise RuntimeError(indisponivel) from erro


def consultar_cep(cep):
    if not CEP_PATTERN.fullmatch(cep):
        raise ValueError("Informe um CEP de 8 dígitos.")
    digitos = cep.replace("-", "")
    dados = _consulta_postal(f"https://brasilapi.com.br/api/cep/v2/{digitos}", "BrasilAPI", 16_384,
                             erro_404="CEP não encontrado na BrasilAPI.")
    if not isinstance(dados, dict):
        raise RuntimeError("Resposta inesperada da BrasilAPI.")
    campos = {chave: str(dados.get(chave) or "")[:180] for chave in ("street", "neighborhood", "city", "state")}
    return {
        "cep": f"{digitos[:5]}-{digitos[5:]}", "logradouro": campos["street"], "bairro": campos["neighborhood"],
        "municipio": campos["city"], "uf": campos["state"],
        "municipio_rg": rg._norm(campos["city"]) == "almirante tamandare" and campos["state"] == "PR",
    }


def ceps_por_logradouro(logradouro):
    # ViaCEP requer UF, município e logradouro. O município é o mesmo do RG.
    if not isinstance(logradouro, str):
        raise ValueError("Informe o nome do logradouro.")
    rua = normalize("NFC", " ".join(logradouro.split(",", 1)[0].split()))
    if not 3 <= len(rua) <= 120 or not any(c.isalpha() for c in rua):
        raise ValueError("Informe pelo menos três caracteres do nome da rua, sem o número do imóvel.")
    if not all(c.isalpha() or c.isdecimal() or c in " .-'’º°" for c in rua):
        raise ValueError("Informe apenas o nome do logradouro.")
    municipio = quote("Almirante Tamandaré", safe="")
    dados = _consulta_postal(f"https://viacep.com.br/ws/PR/{municipio}/{quote(rua, safe='')}/json/",
                             "ViaCEP", 65_536)
    if not isinstance(dados, list):
        raise RuntimeError("Resposta inesperada do ViaCEP.")
    resultados = {}
    for item in dados[:50]:
        if not isinstance(item, dict):
            continue
        cep = item.get("cep")
        if not isinstance(cep, str) or not CEP_PATTERN.fullmatch(cep):
            continue
        if item.get("uf") != "PR" or rg._norm(item.get("localidade")) != "almirante tamandare":
            continue
        digitos = cep.replace("-", "")
        cep = f"{digitos[:5]}-{digitos[5:]}"
        campos = {campo: str(item.get(campo) or "")[:180] for campo in ("logradouro", "bairro", "complemento")}
        if campos["logradouro"]:
            resultados.setdefault(cep, {"cep": cep, **campos})
    return list(resultados.values())


class NominatimOcupado(RuntimeError):
    pass


def endpoint_nominatim(configurado, token=""):
    if not configurado:
        return None
    base = configurado.strip().rstrip("/")
    try:
        url = urlsplit(base)
        porta = url.port
    except ValueError:
        return None
    seguro = url.scheme == "https" or (url.scheme == "http" and url.hostname in {"127.0.0.1", "::1", "localhost"})
    if (not seguro or not url.hostname or url.username or url.password or url.query or url.fragment
            or porta == 0 or url.hostname.rstrip(".") == "nominatim.openstreetmap.org"):
        return None
    if token and (url.scheme != "https" or len(token) > 1024 or not re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,2}", token)):
        return None
    if url.hostname.rstrip(".") == "geocode.maps.co" and not token:
        return None
    return base if url.path.endswith("/search") else base + "/search"


def buscar_nominatim(endpoint, termo, token=""):
    global _NOMINATIM_PROXIMA, _NOMINATIM_ATIVA
    texto = normalize("NFC", " ".join(termo.split())) if isinstance(termo, str) else ""
    if (not 3 <= len(texto) <= 120 or sum(c.isalpha() for c in texto) < 3
            or not all(c.isalpha() or c.isdecimal() or c in " ,.-'’º°()/–" for c in texto)
            or re.search(r"\d{6,}|\d{3}[. ]\d{3}[. ]\d{3}", texto)):
        raise ValueError("Informe uma rua ou um local público de Almirante Tamandaré.")
    chave = (endpoint, sha256(token.encode("ascii")).digest() if token else None, texto.casefold())
    with _NOMINATIM_LOCK:
        agora = monotonic()
        salvo = _NOMINATIM_CACHE.get(chave)
        if salvo and salvo[0] > agora:
            _NOMINATIM_CACHE.move_to_end(chave)
            return salvo[1]
        if _NOMINATIM_ATIVA or agora < _NOMINATIM_PROXIMA:
            raise NominatimOcupado("A busca Nominatim está ocupada. Tente novamente em instantes.")
        _NOMINATIM_ATIVA, _NOMINATIM_PROXIMA = True, agora + 1.05
    oeste, sul, leste, norte = _NOMINATIM_LIMITES
    parametros = urlencode({
        "q": texto, "format": "jsonv2", "limit": 8, "addressdetails": 1,
        "countrycodes": "br", "viewbox": f"{oeste},{norte},{leste},{sul}",
        "bounded": 1, "accept-language": "pt-BR,pt",
    })
    try:
        dados = _consulta_postal(f"{endpoint}?{parametros}", "Nominatim", 65_536, bearer=token)
        if not isinstance(dados, list):
            raise RuntimeError("Resposta inesperada do Nominatim.")
        resultados = []
        for item in dados[:8]:
            if not isinstance(item, dict) or not isinstance(item.get("display_name"), str):
                continue
            try:
                lat, lon = float(item["lat"]), float(item["lon"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(lat) or not math.isfinite(lon) or not (sul <= lat <= norte and oeste <= lon <= leste):
                continue
            titulo = item["display_name"].strip()[:400]
            if titulo:
                resultados.append({
                    "tipo": "nominatim", "titulo": titulo, "latitude": lat, "longitude": lon,
                    "subtitulo": "OpenStreetMap · posição de referência",
                })
        with _NOMINATIM_LOCK:
            _NOMINATIM_CACHE[chave] = (monotonic() + 86_400, resultados)
            _NOMINATIM_CACHE.move_to_end(chave)
            if len(_NOMINATIM_CACHE) > 256:
                _NOMINATIM_CACHE.popitem(last=False)
        return resultados
    finally:
        with _NOMINATIM_LOCK:
            _NOMINATIM_ATIVA = False
