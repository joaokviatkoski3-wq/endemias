"""Localização validada de endereços sem consulta externa de dados do VSATT."""

import csv
from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile
from io import TextIOWrapper

from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from app_core import db, geovsatt_busca as busca, geovsatt_catalogo as catalogo
from app_core import registro_geografico as rg
from app_core.territorio import chave_territorial


MUNICIPIO_IBGE = "4100400"
DIAMETRO_CNEFE_COLETA_METROS = 8
COLUNAS_CSV = ("chave", "endereco_google_earth", "logradouro", "numero", "localidade", "cep", "latitude", "longitude")


def chave_endereco(endereco):
    interpretados = variantes(endereco)
    normalizado = rg._norm(endereco)
    if len(interpretados) == 1:
        via, numero, bairro = interpretados[0]
        cep = re.search(r"\b([0-9]{5})-?([0-9]{3})\b", endereco)
        normalizado = repr((via, numero, bairro, cep.groups() if cep else None))
    return sha256(normalizado.encode("utf-8")).hexdigest()


def ponto(latitude, longitude):
    try:
        lat, lon = (float(str(x).strip().replace(",", ".")) for x in (latitude, longitude))
    except (TypeError, ValueError):
        return None
    if -90 < lat < 90 and -180 < lon < 180 and (lat, lon) != (0, 0):
        return lat, lon
    return None


def chave_logradouro_numero(logradouro, numero):
    via = tuple(rg._sem_prefixo_logradouro(logradouro).split())
    numero = busca._numero(numero)
    return (via, numero) if via and numero not in {"", "0", "sn"} else None


def _cnefe_proximo(validadas):
    """Obtém um ponto medido de um único endereço com leituras próximas."""
    latitudes, longitudes = zip(*(pos for pos, _ in validadas))
    lat = sum(latitudes) / len(latitudes)
    lon = sum(longitudes) / len(longitudes)
    escala_lon = math.cos(math.radians(lat))
    diagonal = 111_195 * math.hypot(max(latitudes) - min(latitudes),
                                   (max(longitudes) - min(longitudes)) * escala_lon)
    if diagonal > DIAMETRO_CNEFE_COLETA_METROS:
        return None
    return min(validadas, key=lambda item: ((item[0][0] - lat)**2 + ((item[0][1] - lon) * escala_lon)**2, item[0]))


def variantes(endereco):
    candidatos, _ = busca._interpretar(endereco)
    return [item for item in candidatos if item.numero and item.numero != "sn"]


def endereco_rotulado(visita):
    via = (visita.get("logradouro") or "").strip()
    if not via:
        return ""
    numero = str(visita.get("numero") or "").strip()
    campos = [via, numero, visita.get("localidade")]
    return ", ".join(str(valor).strip() for valor in campos if valor)


def campos_csv(endereco):
    candidatos = variantes(endereco)
    caso = candidatos[0] if len(candidatos) == 1 else None
    cep = re.search(r"\b[0-9]{5}-[0-9]{3}\b", endereco)
    endereco_completo = endereco.rstrip(" ,")
    if "almirante tamandare" not in rg._norm(endereco_completo):
        endereco_completo += ", Almirante Tamandaré"
    endereco_completo += ", Paraná, Brasil"
    return {"chave": chave_endereco(endereco), "endereco_google_earth": endereco_completo, "logradouro": " ".join(caso.via) if caso else endereco,
            "numero": caso.numero if caso else "", "localidade": " ".join(caso.localidade) if caso else "",
            "cep": cep[0] if cep else "", "latitude": "", "longitude": ""}


def ensure_schema(conn):
    if conn.backend == "sqlite":
        pasta = Path(__file__).resolve().parents[1] / "migrations" / "postgresql"
        for nome in ("0049_geovsatt_vigilancia.sql", "0050_geovsatt_posicoes_coletas.sql"):
            for comando in (pasta / nome).read_text(encoding="utf-8").split(";"):
                if comando.strip():
                    conn.execute(comando)


def _camadas_geometricas(target, bases, malha):
    try:
        fonte = catalogo.obter(target, "limite-municipal", bases, incluir_dados=True)
    except catalogo.CamadaAusente:
        fonte = None
    limite = None
    if fonte and fonte.get("geojson"):
        dados = json.loads(fonte["geojson"])
        limite = unary_union([make_valid(shape(f["geometry"])) for f in dados.get("features", [])
                              if f.get("geometry") and f["geometry"]["type"] in {"Polygon", "MultiPolygon"}])
    geometrias, propriedades = [], []
    for feat in malha.get("features", []):
        if feat.get("geometry"):
            geometrias.append(make_valid(shape(feat["geometry"])))
            propriedades.append(feat["properties"])
    return limite, STRtree(geometrias), propriedades


@lru_cache(maxsize=2)
def _ler_cnefe(arquivo, versao):
    def indexar(f):
        leitor = csv.DictReader(f, delimiter=";")
        obrigatorias = {"COD_MUNICIPIO", "NOM_SEGLOGR", "NUM_ENDERECO", "LATITUDE", "LONGITUDE", "DSC_LOCALIDADE"}
        if not obrigatorias.issubset(leitor.fieldnames or []):
            raise ValueError("O CSV do CNEFE está fora do formato municipal esperado.")
        indice = defaultdict(set)
        for row in leitor:
            if row["COD_MUNICIPIO"] != MUNICIPIO_IBGE:
                continue
            via = rg._sem_prefixo_logradouro(" ".join(
                row[k] or "" for k in ("NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR") if k in row))
            complemento = (row.get("DSC_MODIFICADOR") or "").strip()
            numero = busca._numero((row["NUM_ENDERECO"] or "") + (complemento if complemento != "0" else ""))
            coordenadas = ponto(row["LATITUDE"], row["LONGITUDE"])
            if via and numero and numero not in {"0", "sn"} and coordenadas:
                indice[tuple(via.split()), numero].add(
                    (tuple(busca._localidade(row["DSC_LOCALIDADE"])), row.get("CEP", ""), coordenadas))
        return indice

    if arquivo.suffix.lower() == ".zip":
        try:
            with ZipFile(arquivo) as zipado:
                membro = zipado.getinfo("4100400_ALMIRANTE_TAMANDARE.csv")
                if membro.file_size > 64 * 1024**2:
                    raise ValueError("O arquivo municipal do CNEFE excede o tamanho esperado.")
                with TextIOWrapper(zipado.open(membro), encoding="utf-8-sig", newline="") as texto:
                    return indexar(texto)
        except (BadZipFile, KeyError) as exc:
            raise ValueError("Configure o ZIP municipal 4100400 do IBGE ou seu CSV extraído.") from exc
    with arquivo.open(encoding="utf-8-sig", newline="") as texto:
        return indexar(texto)


class Localizador:
    def __init__(self, target, bases, malha, caminho_cnefe):
        self.limite, self.indice, self.propriedades = _camadas_geometricas(target, bases, malha)
        self.cnefe = {}
        if caminho_cnefe:
            arquivo = Path(caminho_cnefe)
            self.cnefe = _ler_cnefe(arquivo, arquivo.stat().st_mtime_ns)
        conn = db.connect(target)
        try:
            registros = conn.execute("SELECT * FROM geovsatt_enderecos_verificados").fetchall() if (
                db.table_exists(conn, "geovsatt_enderecos_verificados")) else []
            self.verificados = {row["chave"]: db.serialize_row(row) for row in registros}
            imoveis = conn.execute("""
                SELECT id_localidade, quarteirao, logradouro, numero, localidade
                  FROM registro_geografico_imoveis
                 WHERE COALESCE(tipo,'') <> 'REF'
            """).fetchall() if db.table_exists(conn, "registro_geografico_imoveis") else []
        finally:
            conn.close()
        self.rg = defaultdict(set)
        for registro in imoveis:
            via = tuple(rg._sem_prefixo_logradouro(registro["logradouro"]).split())
            chave = chave_territorial(registro["id_localidade"], registro["quarteirao"])
            if via and chave and (numero := busca._numero(registro["numero"])) not in {"", "sn"}:
                self.rg[via, numero].add((tuple(busca._localidade(registro["localidade"])), chave))
        self.cache = {}

    def _rg(self, endereco):
        return {chave for opcao in variantes(endereco)
                for bairro, chave in self.rg.get((tuple(opcao.via), opcao.numero), ())
                if not opcao.localidade or opcao.localidade == list(bairro)}

    def validar(self, coordenadas, esperado=None, *, aceitar_sem_quarteirao=False):
        if coordenadas is None:
            return None
        lat, lon = coordenadas
        p = Point(lon, lat)
        if self.limite is not None and not self.limite.covers(p):
            return None
        dentro = self.indice.query(p, predicate="covered_by")
        blocos = {}
        for i in dentro:
            props = self.propriedades[i]
            chave = chave_territorial(props.get("Localidade"), props.get("id_quart"))
            if chave:
                blocos[chave] = props
        if esperado:
            return blocos.get(esperado)
        if len(blocos) == 1:
            return next(iter(blocos.values()))
        if self.limite is not None and (not blocos or aceitar_sem_quarteirao):
            return {}
        return None

    def localizar(self, endereco, *, coordenadas=None, esperado=None, localidade_ubs=False):
        if not endereco:
            return None
        # O nome da área de UBS não é o bairro do CNEFE. Para relaxar esse
        # filtro na coleta, exigimos a confirmação pelo quarteirão da visita.
        conferir_bairro = not (localidade_ubs and esperado)
        cache_key = (chave_endereco(endereco), coordenadas, esperado, conferir_bairro)
        if cache_key in self.cache:
            return self.cache[cache_key]
        candidatas_rg = self._rg(endereco)
        if esperado is None and len(candidatas_rg) == 1:
            esperado = next(iter(candidatas_rg))
        resultado = self._buscar(endereco, coordenadas, esperado, len(candidatas_rg), conferir_bairro)
        self.cache[cache_key] = resultado
        return resultado

    def _buscar(self, endereco, coordenadas, esperado, total_rg, conferir_bairro):
        salvo = self.verificados.get(chave_endereco(endereco))
        if salvo:
            pos = ponto(salvo["latitude"], salvo["longitude"])
            if (props := self.validar(pos, esperado)) is not None:
                return pos, props, salvo["fonte"]
        if coordenadas and esperado and (props := self.validar(coordenadas, esperado)) is not None:
            return coordenadas, props, "Planilha e RG"
        if total_rg > 1 and not esperado:
            return None
        alternativas = set()
        cep = re.search(r"\b([0-9]{5})-?([0-9]{3})\b", endereco)
        enderecos_candidatos = variantes(endereco)
        if self.cnefe:
            for opcao in enderecos_candidatos:
                for bairro, cep_base, pos in self.cnefe.get((tuple(opcao.via), opcao.numero), ()):
                    if (conferir_bairro and opcao.localidade and list(bairro) != opcao.localidade
                            or cep and "".join(cep.groups()) != cep_base.replace("-", "")):
                        continue
                    alternativas.add(pos)
        validadas = [(pos, props) for pos in alternativas
                     if (props := self.validar(pos, esperado)) is not None]
        if len(validadas) == 1:
            pos, props = validadas[0]
            return pos, props, "CNEFE 2022"
        if not conferir_bairro and len(enderecos_candidatos) == 1 and len(validadas) > 1:
            proxima = _cnefe_proximo(validadas)
            if proxima:
                return (*proxima, "CNEFE 2022 · registros próximos")
        return None
