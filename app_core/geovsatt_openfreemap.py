"""Cópia explícita de uma área da base OpenFreeMap para uso offline."""

from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from gzip import GzipFile
from http.client import HTTPException
from io import BytesIO
import json
from math import asinh, floor, pi, radians, tan
import re
from threading import BoundedSemaphore
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request

from app_core.geovsatt_busca import _CEP_HTTP


ORIGEM = "https://tiles.openfreemap.org"
MAX_MOSAICOS = 3000
MAX_BYTES = 50_000_000
ZOOM_INICIAL = 9  # O adaptador Leaflet usa zoom - 1 no MapLibre.
ZOOM_FINAL = 14
FONTE = "openmaptiles"
FONTES = {"Noto Sans Regular", "Noto Sans Italic", "Noto Sans Bold"}
PROTOCOLO = "geovsatt-ofm://"
_CONEXOES = BoundedSemaphore(4)
_MODELO_DOS_MOSAICOS = re.compile(r"/(?:backup_)?planet/[a-zA-Z0-9_-]+/\{z\}/\{x\}/\{y\}\.pbf")
_CAMINHO_TILEJSON = re.compile(r"/(?:backup_)?planet(?:/[a-zA-Z0-9_-]+)?/?")
_CAMINHO_SPRITE = re.compile(r"/sprites/[a-zA-Z0-9_/-]+")
_CAMINHO_GLYPH = "/fonts/{fontstack}/{range}.pbf"


def _caminho_remoto(link, padrao):
    url = urlsplit(link or "")
    if url.scheme != "https" or url.netloc != "tiles.openfreemap.org" or url.query or url.fragment:
        raise ValueError("A base offline do OpenFreeMap mudou de endereço.")
    if not padrao.fullmatch(url.path) or ".." in url.path:
        raise ValueError("A configuração da base offline do OpenFreeMap mudou.")
    return url.path


def _recurso(caminho, *, mosaico=False, limite=4_194_304):
    requisicao = Request(ORIGEM + caminho, headers={
        "User-Agent": "GeoVSATT-AlmiranteTamandare/Offline (+https://geo.vsatt.com.br)",
        "Accept-Encoding": "identity",
    })
    try:
        with _CONEXOES, _CEP_HTTP.open(requisicao, timeout=9) as resposta:
            bruto = resposta.read(limite + 1)
            if bruto.startswith(b"\x1f\x8b"):
                with GzipFile(fileobj=BytesIO(bruto)) as descompactar:
                    bruto = descompactar.read(limite + 1)
            if len(bruto) > limite:
                raise ValueError("Um recurso do OpenFreeMap excedeu o tamanho esperado.")
            return bruto
    except (OSError, HTTPException, EOFError) as exc:
        if isinstance(exc, HTTPError):
            exc.close()
            if mosaico and exc.code == 404:
                return b""
        raise RuntimeError("O OpenFreeMap não respondeu. A cópia anterior permanece disponível.") from exc


def _tile_x(lon, z):
    lado = 1 << z
    return min(lado - 1, max(0, floor((lon + 180) * lado / 360)))


def _tile_y(lat, z):
    lado = 1 << z
    restringida = max(-85.05112878, min(85.05112878, lat))
    return min(lado - 1, max(0, floor((1 - asinh(tan(radians(restringida))) / pi) * lado / 2)))


def planejar(recorte, max_zoom):
    oeste, sul, leste, norte = recorte
    chaves = []
    for z in range(ZOOM_INICIAL, max_zoom + 1):
        x1, x2 = _tile_x(oeste, z), _tile_x(leste, z)
        y1, y2 = _tile_y(norte, z), _tile_y(sul, z)
        if len(chaves) + (x2 - x1 + 1) * (y2 - y1 + 1) > MAX_MOSAICOS:
            raise ValueError("A área excede 3.000 mosaicos. Aproxime o mapa antes de baixar a base.")
        chaves.extend((z, x, y) for x in range(x1, x2 + 1) for y in range(y1, y2 + 1))
    return chaves


def _estilo_e_recursos(recorte):
    estilo = json.loads(_recurso("/styles/positron"))
    origem = estilo["sources"][FONTE]
    meta = json.loads(_recurso(_caminho_remoto(origem["url"], _CAMINHO_TILEJSON)))
    modelo = _caminho_remoto(meta["tiles"][0], _MODELO_DOS_MOSAICOS)
    if meta.get("scheme") not in (None, "xyz") or not ZOOM_INICIAL <= int(meta["maxzoom"]) <= 22:
        raise ValueError("O esquema de mosaicos do OpenFreeMap mudou.")
    zoom_max = min(ZOOM_FINAL, int(meta["maxzoom"]))
    tiles = planejar(recorte, zoom_max)

    sprite = _caminho_remoto(estilo["sprite"], _CAMINHO_SPRITE)
    if estilo["glyphs"] != ORIGEM + _CAMINHO_GLYPH:
        raise ValueError("O endereço das fontes do OpenFreeMap mudou.")
    camadas = [camada for camada in estilo["layers"] if camada.get("source") in (None, FONTE)]
    for camada in camadas:
        layout = camada.get("layout", {})
        if "text-field" in layout and (
            not layout.get("text-font") or not isinstance(layout["text-font"], list)
            or not all(isinstance(fonte, str) and fonte in FONTES for fonte in layout["text-font"])
        ):
            layout["text-font"] = ["Noto Sans Regular"]
    pilhas = {",".join(camada["layout"]["text-font"]) for camada in camadas
              if camada.get("layout", {}).get("text-field")}
    arquivos = [
        (f"fonte/{pilha}/{faixa}.pbf", "/fonts/" + quote(pilha, safe=",") + f"/{faixa}.pbf", False)
        for pilha in sorted(pilhas) for faixa in ("0-255", "256-511")
    ]
    arquivos.extend(("sprite/ofm" + sufixo, sprite + sufixo, False)
                    for sufixo in (".json", ".png", "@2x.json", "@2x.png"))
    arquivos.extend((f"tile/{z}/{x}/{y}", modelo.format(z=z, x=x, y=y), True) for z, x, y in tiles)

    local = {"version": 8, "glyphs": PROTOCOLO + "fonte/{fontstack}/{range}.pbf", "sprite": PROTOCOLO + "sprite/ofm",
             "sources": {FONTE: {"type": "vector", "tiles": [PROTOCOLO + "tile/{z}/{x}/{y}"],
                                  "minzoom": ZOOM_INICIAL, "maxzoom": zoom_max, "bounds": recorte}},
             "layers": camadas}
    return local, arquivos, len(tiles)


def transmitir(recorte, limite):
    """Cada linha é independente, com confirmação final após todos os recursos."""
    serializar = lambda dados: json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    try:
        # Envia os cabeçalhos enquanto o leitor monta o plano no fornecedor.
        yield serializar({"preparando": True})
        estilo, arquivos, total_mosaicos = _estilo_e_recursos(recorte)
        inicio = serializar({"estilo": estilo, "recorte": recorte, "total": len(arquivos), "mosaicos": total_mosaicos})
        saldo = min(limite, MAX_BYTES) - len(inicio)
        if saldo < 0:
            raise ValueError("O pacote está cheio. Selecione menos camadas para baixar a base.")
        yield inicio

        def baixar(item):
            chave, caminho, mosaico = item
            bruto = _recurso(caminho, mosaico=mosaico)
            if not mosaico and not bruto:
                raise RuntimeError("Um recurso de desenho do OpenFreeMap está indisponível.")
            return serializar({"chave": chave, "dados": b64encode(bruto).decode("ascii")})

        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="geovsatt-ofm") as pool:
            for inicio in range(0, len(arquivos), 4):
                for linha in pool.map(baixar, arquivos[inicio:inicio + 4]):
                    saldo -= len(linha)
                    if saldo < 0:
                        raise ValueError("A base excede o tamanho da cópia. Aproxime o mapa e baixe uma área menor.")
                    yield linha
        yield serializar({"concluido": True})
    except (TypeError, KeyError, IndexError):
        yield serializar({"erro": "A configuração do OpenFreeMap mudou e precisa ser conferida."})
    except (ValueError, RuntimeError) as exc:
        yield serializar({"erro": str(exc)})
