"""Ortofotos MBTiles no catálogo privado do GeoVSATT."""

from base64 import b64decode, b64encode
from contextlib import closing
from hashlib import sha256
import json
from math import asinh, atan, degrees, floor, isfinite, pi, radians, sinh, tan
import os
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile

from werkzeug.utils import secure_filename

from app_core import geovsatt_catalogo as catalogo


PREFIXO_BASE = "ortofoto:"
MAX_ZOOM = 22
MAX_TILE = 2 * 1024 * 1024
IMAGENS = {"png": ("image/png", b"\x89PNG\r\n\x1a\n"), "jpg": ("image/jpeg", b"\xff\xd8\xff")}
GEOJSON_VAZIO = '{"type":"FeatureCollection","features":[]}'
TRANSPARENTE = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")


def _abrir(path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        conn.execute("PRAGMA trusted_schema = OFF")
    except sqlite3.DatabaseError:
        conn.close()
        raise
    return conn


def _latitude(linha, lado):
    return degrees(atan(sinh(pi * (2 * linha / lado - 1))))


def _limites(geometria, extensao):
    try:
        oeste, sul, leste, norte = (float(valor) for valor in geometria.split(","))
        if all(isfinite(valor) for valor in (oeste, sul, leste, norte)):
            limites = [max(extensao[0], oeste), max(extensao[1], sul), min(extensao[2], leste), min(extensao[3], norte)]
            if limites[0] < limites[2] and limites[1] < limites[3]:
                return limites
    except (AttributeError, ValueError):
        pass
    return extensao


def _inspecionar(path, tamanho):
    with path.open("rb") as arquivo:
        if arquivo.read(16) != b"SQLite format 3\x00":
            raise catalogo.CatalogoErro("Selecione um MBTiles raster gerado no QGIS.")
    try:
        with closing(_abrir(path)) as conn:
            tabelas = {row[1] for row in conn.execute("PRAGMA table_list") if row[0] == "main" and row[2] == "table"}
            if not {"metadata", "tiles"} <= tabelas:
                raise catalogo.CatalogoErro("O MBTiles deve conter as tabelas raster do QGIS.")
            indices = [nome for nome, in conn.execute("""SELECT name FROM pragma_index_list('tiles')
                                                        WHERE "unique"=1 AND partial=0""")]
            if not any({campo for campo, in conn.execute("SELECT name FROM pragma_index_info(?)", (indice,))}
                       == {"zoom_level", "tile_column", "tile_row"} for indice in indices):
                raise catalogo.CatalogoErro("O MBTiles precisa do índice de mosaicos. Gere o arquivo no QGIS.")
            metadados = dict(conn.execute("""
                SELECT lower(name),value FROM metadata WHERE lower(name) IN ('format','bounds') AND length(value)<256
            """))
            formato = str(metadados.get("format", "")).strip().lower()
            if formato == "jpeg":
                formato = "jpg"
            if formato not in IMAGENS:
                raise catalogo.CatalogoErro("Use um MBTiles raster com mosaicos PNG ou JPG.")
            assinatura = IMAGENS[formato][1]
            invalido = conn.execute("""
                SELECT 1 FROM tiles WHERE typeof(zoom_level)<>'integer' OR zoom_level NOT BETWEEN 0 AND ?
                  OR typeof(tile_column)<>'integer' OR tile_column<0 OR tile_column>=(1 << zoom_level)
                  OR typeof(tile_row)<>'integer' OR tile_row<0 OR tile_row>=(1 << zoom_level)
                  OR typeof(tile_data)<>'blob' OR length(tile_data)>? OR substr(tile_data,1,?)<>? LIMIT 1
            """, (MAX_ZOOM, MAX_TILE, len(assinatura), assinatura)).fetchone()
            if invalido:
                raise catalogo.CatalogoErro("O MBTiles contém mosaicos inválidos ou fora do formato declarado.")
            niveis = conn.execute("""
                SELECT zoom_level,COUNT(*),MIN(tile_column),MIN(tile_row),MAX(tile_column),MAX(tile_row)
                  FROM tiles GROUP BY zoom_level ORDER BY zoom_level
            """).fetchall()
            if not niveis:
                raise catalogo.CatalogoErro("O MBTiles está vazio.")
            zoom, _, x1, y1, x2, y2 = niveis[-1]
            minimo = niveis[0][0]
            if len(niveis) != zoom - minimo + 1:
                raise catalogo.CatalogoErro("Gere um MBTiles com os níveis de zoom intermediários.")
            lado = 1 << zoom
            extensao = [360 * x1 / lado - 180, _latitude(y1, lado), 360 * (x2 + 1) / lado - 180, _latitude(y2 + 1, lado)]
            amostra = conn.execute("""
                SELECT tile_column,tile_row FROM tiles WHERE zoom_level=? LIMIT 1
            """, (zoom,)).fetchone()
    except sqlite3.DatabaseError as exc:
        raise catalogo.CatalogoErro("Não foi possível ler o MBTiles. Gere novamente o arquivo no QGIS.") from exc
    return {"formato": formato, "bytes": tamanho, "zoom_min": minimo, "zoom_max": zoom,
            "limites": _limites(metadados.get("bounds"), extensao),
            "amostra": [zoom, amostra[0], lado - 1 - amostra[1]], "total": sum(row[1] for row in niveis)}


def caminho(anexos, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise catalogo.CamadaAusente("Arquivo de ortofoto indisponível.")
    return Path(anexos) / "geovsatt-ortofotos" / f"{digest}.mbtiles"


def importar(target, anexos, codigo, arquivo, form, bases, usuario_id, limite, *, nova=False):
    nome = secure_filename(arquivo.filename or "")
    if not nome.lower().endswith(".mbtiles"):
        raise catalogo.CatalogoErro("Selecione um arquivo .mbtiles.")
    metadados = catalogo._metadados(form)
    if nova:
        titulo, grupo, descricao, _ = catalogo._dados_camada(codigo, form)
        cadastro = (titulo, grupo, descricao, catalogo.configuracao_padrao() | {"formato": "mbtiles"})
    destino_raiz = Path(anexos) / "geovsatt-ortofotos"
    destino_raiz.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    tamanho = 0
    temporario = None
    try:
        with NamedTemporaryFile(prefix="recebendo-", suffix=".tmp", dir=destino_raiz, delete=False) as saida:
            temporario = Path(saida.name)
            while parte := arquivo.stream.read(1024 * 1024):
                tamanho += len(parte)
                if tamanho > limite:
                    raise catalogo.CatalogoErro("O MBTiles excede o tamanho permitido nesta entrada do GeoVSATT.")
                digest.update(parte)
                saida.write(parte)
            saida.flush()
            os.fsync(saida.fileno())
        informacoes = _inspecionar(temporario, tamanho)
        hash_arquivo = digest.hexdigest()
        destino = caminho(anexos, hash_arquivo)
        with catalogo._escrita(target) as conn:
            if nova:
                catalogo._criar_camada(conn, codigo, cadastro, bases)
            else:
                camada = conn.execute("SELECT configuracao FROM geovsatt_camadas WHERE codigo=?", (codigo,)).fetchone()
                if not camada or json.loads(camada[0]).get("formato") != "mbtiles":
                    raise catalogo.CamadaAusente("Ortofoto não encontrada.")
            if not destino.is_file():
                temporario.replace(destino)
            dados = (nome, GEOJSON_VAZIO, hash_arquivo, informacoes["total"], "raster",
                     json.dumps(metadados | {"mbtiles": informacoes}))
            return catalogo._inserir_versao(conn, codigo, dados, usuario_id)
    finally:
        if temporario:
            temporario.unlink(missing_ok=True)


def mosaico(path, versao, z, x, y):
    if not 0 <= z <= MAX_ZOOM:
        return None
    lado = 1 << z
    informacoes = versao["metadados"]["mbtiles"]
    if not (informacoes["zoom_min"] <= z <= informacoes["zoom_max"] and 0 <= x < lado and 0 <= y < lado):
        return None
    with closing(_abrir(path)) as conn:
        row = conn.execute("""
            SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=? AND length(tile_data)<=?
        """, (z, x, lado - 1 - y, MAX_TILE)).fetchone()
    if row is None:
        return None
    mime, assinatura = IMAGENS[informacoes["formato"]]
    if not isinstance(row[0], bytes) or not row[0].startswith(assinatura):
        raise catalogo.CatalogoErro("O mosaico armazenado está indisponível.")
    return row[0], mime


def pacote_offline(path, versao, recorte, limite_bytes):
    """Empacota mosaicos da versão publicada no recorte XYZ escolhido."""
    info = versao["metadados"]["mbtiles"]
    mime, assinatura = IMAGENS[info["formato"]]
    oeste, sul, leste, norte = info["limites"]
    if recorte:
        oeste, sul, leste, norte = max(oeste, recorte[0]), max(sul, recorte[1]), min(leste, recorte[2]), min(norte, recorte[3])
    if oeste >= leste or sul >= norte:
        raise catalogo.CatalogoErro("A ortofoto selecionada não cobre a área visível do mapa.")

    mosaicos = {}
    bytes_usados = 0
    with closing(_abrir(path)) as conn:
        for z in range(info["zoom_min"], info["zoom_max"] + 1):
            lado = 1 << z

            def linha(lat):
                lat = max(-85.05112878, min(85.05112878, lat))
                return max(0, min(lado - 1, floor((1 - asinh(tan(radians(lat))) / pi) * lado / 2)))

            x1 = max(0, floor((oeste + 180) * lado / 360))
            x2 = min(lado - 1, floor((leste + 180) * lado / 360))
            linhas = conn.execute("""
                SELECT tile_column,tile_row,tile_data FROM tiles
                 WHERE zoom_level=? AND tile_column BETWEEN ? AND ? AND tile_row BETWEEN ? AND ?
            """, (z, x1, x2, lado - 1 - linha(sul), lado - 1 - linha(norte)))
            for x, tms, imagem in linhas:
                if not isinstance(imagem, bytes) or len(imagem) > MAX_TILE or not imagem.startswith(assinatura):
                    raise catalogo.CatalogoErro("A ortofoto contém um mosaico indisponível.")
                chave = f"{z}/{x}/{lado - 1 - tms}"
                bytes_usados += 4 * ((len(imagem) + 2) // 3) + len(chave) + 8
                if bytes_usados > limite_bytes:
                    raise catalogo.CatalogoErro("As ortofotos excedem o limite da cópia. Aproxime o mapa e baixe uma área menor.")
                mosaicos[chave] = b64encode(imagem).decode("ascii")
    if not mosaicos:
        raise catalogo.CatalogoErro("Não há mosaicos da ortofoto na área selecionada.")
    return {"mime": mime, "mosaicos": mosaicos, "limites": [oeste, sul, leste, norte]}, bytes_usados
