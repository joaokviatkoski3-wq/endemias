"""Valida e publica, em transação única, o acervo cartográfico fornecido ao GeoVSATT."""

import argparse
import ctypes
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from flask import Flask, session
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from werkzeug.datastructures import FileStorage, MultiDict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_core import db, geovsatt, geovsatt_catalogo as catalogo


CAMADAS = {
    "bairros": ("bairros", "Bairros", "Território", "#5a4abc", "Name", "Name"),
    "limite-municipal": ("Limite municipal almirante tamandare", "Limite municipal", "Território", "#364850", "Name", "Name"),
    "localidades-areas-dispersas": ("Localidades e areas dispersas", "Localidades e áreas dispersas (polígonos)", "Território", "#238070", "nome", "nome cod_loc"),
    "quarteiroes-qgis": ("quarteiroes", "Quarteirões (referência QGIS)", "Território", "#845726", "id_Q", "Localidade id_Q id_Q_antig"),
    "predios_publicos": ("equipamento-publicos-municipais", "Equipamentos públicos municipais", "Equipamentos", "#a03d74", "nome", "nome tipo subtipo bairro_loteamento logradouro numero cep status_funcionamento"),
    "ferrovia": ("ferrovia", "Ferrovias", "Território", "#ad6200", "", "CdFerrovia NmMunicipi"),
    "hidrografia": ("cursodaagua", "Cursos d’água", "Meio ambiente", "#1672aa", "NOME", "NOME REGIME TIPO_DRENA"),
    "massas-de-agua": ("massasdeagua", "Massas d’água", "Meio ambiente", "#1b86bb", "HID_NOME", "HID_NOME HID_CLASSE TIPOHID_DE"),
    "geologia": ("geologia", "Geologia", "Meio ambiente", "#956086", "LEGENDA", "CODGEO ERA IDADE LEGENDA"),
    "areas-de-risco": ("pr almiran sr cprm area de alto e muito alto risco", "Áreas de risco alto e muito alto", "Riscos", "#aa2f24", "GRAU_RISCO", "NUM_SETOR GRAU_RISCO GRAU_VULNE ORGAO_EXEC DATA_SETOR"),
    "suscetibilidade-inundacao": ("suscetibilidadedeinudacao", "Suscetibilidade à inundação", "Riscos", "#355eb0", "Classe", "Classe Municipio Processo UF"),
    "suscetibilidade-movimento-massa": ("suscetibilidadedemovimentodemassa", "Suscetibilidade a movimentos de massa", "Riscos", "#af5521", "Classe", "Classe Municipio Processo UF"),
}


def _coordenadas_validas(coordenadas, nivel):
    if not nivel:
        return coordenadas
    return [_coordenadas_validas(item, nivel - 1) for item in coordenadas if item]


def _partes(geometria, tipo):
    if geometria.is_empty:
        return
    if geometria.geom_type == tipo:
        yield geometria
    elif hasattr(geometria, "geoms"):
        for parte in geometria.geoms:
            yield from _partes(parte, tipo)


def _normalizar(colecao, campos):
    feicoes = []
    corrigidas = vazias = 0
    for feicao in colecao["features"]:
        geometria = feicao.get("geometry")
        if not geometria or not geometria.get("coordinates"):
            vazias += 1
            continue
        tipo = geometria["type"]
        profundidade = catalogo.TIPOS[tipo][1]
        coords = _coordenadas_validas(geometria["coordinates"], profundidade)
        if not coords:
            vazias += 1
            continue
        objeto = shape({"type": tipo, "coordinates": coords})
        contou = coords != geometria["coordinates"]
        if not objeto.is_valid:
            partes = list(_partes(make_valid(objeto), tipo.removeprefix("Multi")))
            if not partes:
                raise ValueError("Uma feição inválida perdeu toda a geometria na correção.")
            objeto = unary_union(partes)
            contou = True
        if objeto.is_empty:
            vazias += 1
            continue
        if contou:
            corrigidas += 1
        dados = feicao.get("properties") or {}
        feicoes.append({"type": "Feature", "geometry": mapping(objeto),
                        "properties": {campo: dados.get(campo) for campo in campos if campo in dados}})
    return {"type": "FeatureCollection", "features": feicoes}, corrigidas, vazias


def _colecao_wgs84(arquivo, bruto, ogr):
    colecao = json.loads(bruto.decode("utf-8-sig"))
    crs = (colecao.get("crs") or {}).get("properties", {}).get("name")
    if crs in (None, "urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326"):
        return colecao, crs, False
    if crs not in {"urn:ogc:def:crs:EPSG::31982", "urn:ogc:def:crs:EPSG::4674"}:
        raise ValueError(f"SRC inesperado em {arquivo.name}.")
    if not ogr.is_file():
        raise ValueError("Informe o executável ogr2ogr do QGIS.")
    ambiente = dict(os.environ)
    ambiente["PROJ_DATA"] = str(ogr.parent.parent / "share" / "proj")
    saida = subprocess.run(
        [str(ogr), "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-dim", "XY", "/vsistdout/", str(arquivo)],
        check=True, capture_output=True, timeout=30, env=ambiente,
    ).stdout
    return json.loads(saida), crs, True


def preparar(pasta, ogr):
    preparados = []
    for codigo, (nome, titulo, grupo, cor, rotulo, campos) in CAMADAS.items():
        arquivo = pasta / f"{nome}.geojson"
        if arquivo.resolve().parent != pasta or arquivo.stat().st_size > catalogo.MAX_UPLOAD:
            raise ValueError(f"Arquivo fora da pasta ou acima do limite: {arquivo.name}.")
        bruto = arquivo.read_bytes()
        colecao, crs, reprojetada = _colecao_wgs84(arquivo, bruto, ogr)
        normal, corrigidas, vazias = _normalizar(colecao, campos.split())
        origem_sha = sha256(bruto).hexdigest()
        descricao = "Cartografia de referência fornecida para o GeoVSATT."
        if codigo == "quarteiroes-qgis":
            descricao = "Malha recebida do QGIS para comparação. A malha ativa do RG é apresentada separadamente."
        form = MultiDict({
            "fonte": "Acervo GeoVSATT fornecido para importação (exportação QGIS)",
            "observacoes": f"SRC recebido: {crs or 'WGS 84 presumido pelo GeoJSON'}. SHA-256 original: {origem_sha}. "
                           f"Geometrias corrigidas: {corrigidas}. Feições sem geometria: {vazias}. "
                           "Os metadados QMD anexos não informam licença. Uso interno no GeoVSATT.",
        })
        geojson = json.dumps(normal, ensure_ascii=False, separators=(",", ":")).encode()
        versao = catalogo.preparar_importacao(FileStorage(io.BytesIO(geojson), arquivo.name), form)
        config = catalogo.configuracao_padrao()
        config.update(niveis=list(catalogo.NIVEIS), setores=list(catalogo.SETORES), cor=cor, rotulo=rotulo)
        resumo = {"codigo": codigo, "arquivo": arquivo.name, "originais": len(colecao["features"]),
                  "publicaveis": versao[3], "reprojetada": reprojetada, "corrigidas": corrigidas, "vazias": vazias,
                  "sha256_original": origem_sha, "sha256_validado": versao[2]}
        preparados.append((resumo, (titulo, grupo, descricao, config), versao))
    return preparados


def publicar_lote(target, preparados):
    app = Flask(__name__)
    app.config.update(SETOR="geo", SETORES_ENABLED=True)
    app.secret_key = os.urandom(32)
    result = []
    with app.test_request_context("/operacao/geovsatt/cartografia"):
        session["nome"] = "Importação assistida GeoVSATT"
        with catalogo._escrita(target) as conn:
            for resumo, config, versao in preparados:
                codigo = resumo["codigo"]
                existe = conn.execute("SELECT 1 FROM geovsatt_camadas WHERE codigo=?", (codigo,)).fetchone()
                if existe:
                    atual = conn.execute("SELECT id_versao,sha256 FROM geovsatt_versoes WHERE codigo=? AND ativa=1",
                                         (codigo,)).fetchone()
                    if atual and atual["sha256"] == versao[2]:
                        result.append({"codigo": codigo, "versao": atual["id_versao"], "estado": "já publicada"})
                        continue
                    raise ValueError(f"A camada {codigo} já tem cadastro diferente. O lote foi interrompido.")
                catalogo._criar_camada(conn, codigo, config, geovsatt.BASES)
                identificador = catalogo._inserir_versao(conn, codigo, versao, 0, publicar=True)
                catalogo._evento(conn, "versao_publicada", codigo, {"versao": identificador, "origem": "acervo QGIS"})
                result.append({"codigo": codigo, "versao": identificador, "estado": "publicada"})
    return result


def _destino_producao():
    if os.name != "nt" or not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Execute com elevação para importar na instalação oficial.")
    config = json.loads(Path(r"C:\ProgramData\EndemiasWeb\config.json").read_text(encoding="utf-8"))
    ambiente = config["env"]
    if (ambiente.get("ENDEMIAS_DB_BACKEND"), ambiente.get("ENDEMIAS_PG_DATABASE"),
            ambiente.get("ENDEMIAS_PG_HOST"), ambiente.get("ENDEMIAS_PG_PORT")) != ("postgresql", "endemias", "127.0.0.1", "5432"):
        raise ValueError("Destino oficial divergente.")
    os.environ.update(ambiente)
    return db.DatabaseTarget("postgresql", "endemias")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pasta", type=Path)
    parser.add_argument("--ogr2ogr", type=Path, required=True)
    parser.add_argument("--aplicar", metavar="SHA256_DA_PREVIA")
    args = parser.parse_args()
    preparados = preparar(args.pasta.resolve(strict=True), args.ogr2ogr.resolve(strict=True))
    relatorio = [resumo for resumo, _, _ in preparados]
    identificador = sha256(json.dumps(relatorio, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    resultado = {"lote": identificador, "camadas": relatorio}
    if args.aplicar:
        if args.aplicar != identificador:
            raise ValueError("Arquivos ou preparação mudaram após a prévia.")
        resultado["publicacao"] = publicar_lote(_destino_producao(), preparados)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
