"""Catálogo, permissões e histórico de vetores do GeoVSATT."""

from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from shapely.errors import GEOSException
from shapely.geometry import shape

from app_core import audit, db, permissoes


MAX_UPLOAD = 8 * 1024 * 1024
MAX_FEICOES = 50_000
NIVEIS = {
    "usuario": "Usuário",
    "visualizador": "Visualizador",
    "operador": "Operador",
    "admin": "Admin",
}
SETORES = {"endemias": "Endemias", "ambiental": "Ambiental"}
COR = re.compile(r"#[0-9a-fA-F]{6}")
ESTILOS_LINHA = {"solida": "Contínua", "tracejada": "Tracejada", "pontilhada": "Pontilhada", "ferrovia": "Ferrovia"}
ESTILOS_PONTO = {"circulo": "Círculo", "quadrado": "Quadrado", "losango": "Losango", "triangulo": "Triângulo"}
VALORES_ESTILO = {
    "largura": (0, 12), "opacidade": (0, 1), "opacidade_preenchimento": (0, 1), "raio": (2, 24),
    "rotulo_zoom": (10, 22), "rotulo_tamanho": (8, 24), "rotulo_zoom_max": (10, 22),
    "rotulo_halo": (0, 6),
}
ESTILO_PADRAO = {chave: None for chave in VALORES_ESTILO} | {
    "cor_preenchimento": "", "rotulo_cor": "", "linha": "", "ponto": "", "rotulo_modo": "",
    "modo_cor": "", "faixas_cor": (), "rotulo_complemento": "", "rotulo_prefixo": "",
    "rotulo_sufixo": "", "rotulo_halo_cor": "",
}
MAX_FAIXAS = 12
NUMERO_ESTILO = re.compile(r"[+-]?(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)(?:[eE][+-]?[0-9]+)?")
TIPOS = {
    "Point": ("ponto", 0), "MultiPoint": ("ponto", 1),
    "LineString": ("linha", 1), "MultiLineString": ("linha", 2),
    "Polygon": ("poligono", 2), "MultiPolygon": ("poligono", 3),
}
COLUNAS_VERSAO = "id_versao,codigo,arquivo,sha256,total,tipo,metadados,autor_id,criada_em,publicada_em,ativa"


class CatalogoErro(ValueError):
    pass


class CamadaAusente(CatalogoErro):
    pass


def ensure_schema(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        conn.execute("SELECT codigo FROM geovsatt_camadas LIMIT 0")
        conn.execute("SELECT id_versao FROM geovsatt_versoes LIMIT 0")
        return
    schema = Path(__file__).resolve().parents[1] / "migrations/postgresql/0047_geovsatt_catalogo.sql"
    conn.executescript(schema.read_text(encoding="utf-8").replace(
        "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
    ))


def configuracao_padrao(base=None):
    return {
        "niveis": list(base.get("niveis_padrao", NIVEIS)) if base else [],
        "setores": list(SETORES) if base else [],
        "usuarios": [],
        "usuarios_exportacao": [],
        "visivel_inicial": bool(base and base["visivel_inicial"]),
        "cor": "",
        "atributo_cor": "",
        "cores": {},
        "rotulo": base.get("rotulo_padrao", "") if base else "",
        **ESTILO_PADRAO,
    }


def pode_ver(camada, usuario):
    if permissoes.permite(usuario, "tecnica"):
        return True
    if not usuario or not camada["disponivel"]:
        return False
    config = camada["config"]
    return (usuario.get("id_usuario") in config["usuarios"] or (
        usuario.get("nivel") in config["niveis"] and usuario.get("setor", "endemias") in config["setores"]
    ))


def camada_base(base):
    return {**base, "origem": "sistema", "config": configuracao_padrao(base), "id_versao": None}


def _camada(row, base=None):
    camada = db.serialize_row(row)
    config = configuracao_padrao(base) | json.loads(camada.pop("configuracao"))
    if camada["codigo"] == "limite-municipal" and not config.get("abertura_configurada"):
        config["visivel_inicial"] = True
    ortofoto = config.get("formato") == "mbtiles"
    camada.update(
        id=camada["codigo"], config=config, visivel_inicial=config["visivel_inicial"],
        disponivel=bool(base or camada["id_versao"]),
        origem="sistema" if base else "ortofoto" if ortofoto else "importacao",
        tipo=base["tipo"] if base else "raster" if ortofoto else camada["tipo"] or "vetor",
    )
    return camada


def _consulta_camadas(campos_versao):
    return (f"SELECT c.*, {campos_versao} FROM geovsatt_camadas c "
            "LEFT JOIN geovsatt_versoes v ON v.codigo = c.codigo AND v.ativa = 1")


def listar(target, bases):
    camadas = {codigo: camada_base(base) for codigo, base in bases.items()}
    for row in db.query(target, _consulta_camadas("v.id_versao,v.tipo,CASE WHEN v.tipo='raster' THEN v.metadados END AS metadados")):
        camadas[row["codigo"]] = _camada(row, bases.get(row["codigo"]))
    return sorted(camadas.values(), key=lambda item: (item["grupo"].casefold(), item["nome"].casefold()))


def obter(target, codigo, bases, *, incluir_dados=False):
    campos = "v.id_versao,v.tipo,v.total,v.metadados,v.sha256"
    if incluir_dados:
        campos += ",v.geojson"
    row = db.query_one(target, _consulta_camadas(campos) + " WHERE c.codigo = ?", (codigo,))
    if row:
        return _camada(row, bases.get(codigo))
    if codigo in bases:
        return camada_base(bases[codigo])
    raise CamadaAusente("Camada não encontrada.")


def _texto(valor, limite):
    valor = (valor or "").strip()
    if len(valor) > limite or "\0" in valor:
        raise CatalogoErro(f"Campo de texto inválido ou acima de {limite} caracteres.")
    return valor


def _metadados(form):
    campos = {chave: _texto(form.get(chave), limite) for chave, limite in {
        "fonte": 180, "data_referencia": 10, "licenca": 180, "observacoes": 2000,
    }.items()}
    if not campos["fonte"]:
        raise CatalogoErro("Informe a fonte da camada.")
    if campos["data_referencia"]:
        try:
            campos["data_referencia"] = date.fromisoformat(campos["data_referencia"]).isoformat()
        except ValueError as exc:
            raise CatalogoErro("Informe uma data de referência válida.") from exc
    return campos


def _limite_faixa(texto):
    texto = _texto(texto, 40)
    if not texto:
        return None
    if NUMERO_ESTILO.fullmatch(texto):
        valor = float(texto.replace(",", "."))
        if math.isfinite(valor):
            return valor
    raise CatalogoErro("Informe limites numéricos válidos para as faixas de cor.")


def _faixas_cor(form):
    colunas = [form.getlist(chave) for chave in ("faixa_de", "faixa_ate", "faixa_cor", "faixa_legenda")]
    if len({len(coluna) for coluna in colunas}) != 1 or not 1 <= len(colunas[0]) <= MAX_FAIXAS:
        raise CatalogoErro(f"Informe de 1 a {MAX_FAIXAS} faixas de cor.")
    faixas = []
    legendas = set()
    for de, ate, cor, legenda in zip(*colunas):
        de, ate = _limite_faixa(de), _limite_faixa(ate)
        legenda = _texto(legenda, 80)
        if (de is None and ate is None) or (de is not None and ate is not None and de >= ate) or not COR.fullmatch(cor):
            raise CatalogoErro("Confira os limites e a cor de cada faixa. O limite inicial deve ser menor que o final.")
        if legenda and legenda.casefold() in legendas:
            raise CatalogoErro("Use um texto de legenda diferente em cada faixa.")
        legendas.add(legenda.casefold())
        faixas.append({"de": de, "ate": ate, "cor": cor.lower(), "legenda": legenda})
    faixas.sort(key=lambda faixa: faixa["de"] if faixa["de"] is not None else -math.inf)
    for anterior, atual in zip(faixas, faixas[1:]):
        if anterior["ate"] is None or atual["de"] is None or anterior["ate"] > atual["de"]:
            raise CatalogoErro("As faixas não podem se sobrepor.")
    return faixas


def _config(form):
    niveis = form.getlist("niveis")
    setores = form.getlist("setores")
    if set(niveis) - NIVEIS.keys() or set(setores) - SETORES.keys():
        raise CatalogoErro("Selecione níveis e setores válidos.")
    contas = {}
    for chave in ("usuarios", "usuarios_exportacao"):
        valores = form.getlist(chave)
        if len(valores) > 1000 or any(not re.fullmatch(r"[1-9][0-9]{0,9}", uid) for uid in valores):
            raise CatalogoErro("A lista de contas autorizadas é inválida.")
        contas[chave] = sorted({int(uid) for uid in valores})
    cor = _texto(form.get("cor"), 7)
    atributo = _texto(form.get("atributo_cor"), 120)
    modo_cor = form.get("modo_cor") or ""
    if modo_cor not in {"", "unico", "categorias", "faixas"} or (modo_cor in {"categorias", "faixas"} and not atributo):
        raise CatalogoErro("Selecione a classificação e o atributo usado para colorir a camada.")
    regras = _texto(form.get("regras_cor"), 5000).splitlines() if modo_cor in {"", "categorias"} else []
    if (cor and not COR.fullmatch(cor)) or (regras and not atributo):
        raise CatalogoErro("Informe a cor no formato #008c30 e indique o atributo das regras.")
    cores = {}
    for regra in regras:
        if not regra.strip():
            continue
        valor, _, cor_regra = regra.rpartition("=")
        if not valor.strip() or not COR.fullmatch(cor_regra.strip()) or valor.strip() in cores:
            raise CatalogoErro("Use uma regra por linha, no formato valor = #008c30, sem repetir valores.")
        cores[valor.strip()] = cor_regra.strip().lower()
    estilo = {chave: _texto(form.get(chave), 7) for chave in ("cor_preenchimento", "rotulo_cor", "rotulo_halo_cor")}
    if any(valor and not COR.fullmatch(valor) for valor in estilo.values()):
        raise CatalogoErro("Use uma cor no formato #008c30.")
    for chave, (minimo, maximo) in VALORES_ESTILO.items():
        raw = form.get(chave)
        try:
            valor = float(raw) if raw else None
        except ValueError:
            raise CatalogoErro(f"Informe um número válido para {chave.replace('_', ' ')}.") from None
        if valor is not None and not minimo <= valor <= maximo:
            raise CatalogoErro(f"O valor de {chave.replace('_', ' ')} deve ficar entre {minimo} e {maximo}.")
        estilo[chave] = valor
    if (estilo["rotulo_zoom"] is not None and estilo["rotulo_zoom_max"] is not None
            and estilo["rotulo_zoom_max"] < estilo["rotulo_zoom"]):
        raise CatalogoErro("O zoom máximo das etiquetas deve ser maior ou igual ao mínimo.")
    for chave, opcoes in (("linha", ESTILOS_LINHA), ("ponto", ESTILOS_PONTO),
                          ("rotulo_modo", ("oculto", "centro", "linha"))):
        valor = form.get(chave) or ""
        if valor and valor not in opcoes:
            raise CatalogoErro("Selecione uma opção de estilo válida.")
        estilo[chave] = valor
    return {
        "niveis": sorted(set(niveis)), "setores": sorted(set(setores)),
        **contas,
        "visivel_inicial": form.get("visivel_inicial") == "1",
        "abertura_configurada": True,
        "cor": cor.lower(), "atributo_cor": atributo, "cores": cores,
        "rotulo": _texto(form.get("rotulo"), 120),
        "modo_cor": modo_cor, "faixas_cor": _faixas_cor(form) if modo_cor == "faixas" else [],
        "rotulo_complemento": _texto(form.get("rotulo_complemento"), 120),
        "rotulo_prefixo": _texto(form.get("rotulo_prefixo"), 40),
        "rotulo_sufixo": _texto(form.get("rotulo_sufixo"), 40),
        **estilo,
    }


@contextmanager
def _escrita(target):
    conn = db.connect(target)
    try:
        if getattr(conn, "backend", "sqlite") == "sqlite":
            conn.execute("BEGIN IMMEDIATE")
        with conn:
            yield conn
    finally:
        conn.close()


def _evento(conn, acao, codigo, detalhes):
    audit.registrar_evento(None, f"geovsatt_{acao}", entidade="geovsatt_camada",
                           entidade_id=codigo, detalhes=detalhes, conn=conn)


def _dados_camada(codigo, form):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,59}", codigo):
        raise CatalogoErro("Use um código de 2 a 60 caracteres com letras minúsculas, números, hífen ou sublinhado.")
    nome = _texto(form.get("nome"), 100)
    grupo = _texto(form.get("grupo"), 60)
    descricao = _texto(form.get("descricao"), 1000)
    if not nome or not grupo:
        raise CatalogoErro("Informe o nome e o grupo da camada.")
    return nome, grupo, descricao, _config(form)


def _criar_camada(conn, codigo, dados, bases):
    if codigo in bases:
        raise CatalogoErro("Este código já pertence a uma camada do sistema.")
    nome, grupo, descricao, config = dados
    alteracao = conn.execute(
        """INSERT INTO geovsatt_camadas(codigo,nome,grupo,descricao,configuracao) VALUES (?,?,?,?,?)
           ON CONFLICT (codigo) DO NOTHING""",
        (codigo, nome, grupo, descricao, json.dumps(config)),
    )
    if not alteracao.rowcount:
        raise CatalogoErro("Já existe uma camada com esse código.")


def salvar_camada(target, codigo, form, bases, *, nova=False):
    nome, grupo, descricao, config = _dados_camada(codigo, form)
    with _escrita(target) as conn:
        for uid in set(config["usuarios"]) | set(config["usuarios_exportacao"]):
            if not conn.execute("SELECT 1 FROM usuarios WHERE id_usuario = ?", (uid,)).fetchone():
                raise CatalogoErro("Uma das contas selecionadas não existe.")
        if nova:
            _criar_camada(conn, codigo, (nome, grupo, descricao, config), bases)
        elif codigo not in bases:
            _bloquear_camada(conn, codigo)
            anterior = conn.execute("SELECT configuracao FROM geovsatt_camadas WHERE codigo=?", (codigo,)).fetchone()
            if anterior and json.loads(anterior[0]).get("formato") == "mbtiles":
                config["formato"] = "mbtiles"
            alteracao = conn.execute(
                "UPDATE geovsatt_camadas SET nome=?,grupo=?,descricao=?,configuracao=? WHERE codigo=?",
                (nome, grupo, descricao, json.dumps(config), codigo),
            )
            if not alteracao.rowcount:
                raise CamadaAusente("Camada não encontrada.")
        else:
            conn.execute(
                """INSERT INTO geovsatt_camadas(codigo,nome,grupo,descricao,configuracao) VALUES (?,?,?,?,?)
                   ON CONFLICT (codigo) DO UPDATE SET nome=excluded.nome, grupo=excluded.grupo,
                       descricao=excluded.descricao, configuracao=excluded.configuracao""",
                (codigo, nome, grupo, descricao, json.dumps(config)),
            )
        _evento(conn, "camada_configurada", codigo, {"criada": nova})


def _posicoes(coords, profundidade):
    if not isinstance(coords, list) or not coords:
        raise CatalogoErro("A geometria tem coordenadas vazias ou com estrutura inválida.")
    if profundidade:
        for parte in coords:
            yield from _posicoes(parte, profundidade - 1)
        return
    if (len(coords) not in (2, 3)
            or any(type(v) not in (int, float) or not -1e308 <= v <= 1e308 for v in coords)
            or not -180 <= coords[0] <= 180 or not -90 <= coords[1] <= 90):
        raise CatalogoErro("Use coordenadas WGS 84 (EPSG:4326), em longitude e latitude.")
    yield coords


def _validar_feicao(item):
    if not isinstance(item, dict) or item.get("type") != "Feature":
        raise CatalogoErro("A coleção contém um item que não é uma feição GeoJSON.")
    geom = item.get("geometry")
    tipo = geom.get("type") if isinstance(geom, dict) else None
    if not isinstance(tipo, str) or tipo not in TIPOS:
        raise CatalogoErro("Use pontos, linhas ou polígonos, incluindo suas variantes múltiplas.")
    familia, profundidade = TIPOS[tipo]
    coords = geom.get("coordinates")
    for _ in _posicoes(coords, profundidade):
        pass
    if familia == "poligono":
        poligonos = coords if tipo == "MultiPolygon" else [coords]
        if any(len(anel) < 4 or anel[0] != anel[-1] for poligono in poligonos for anel in poligono):
            raise CatalogoErro("Os anéis dos polígonos precisam estar fechados.")
    geometria = {"type": tipo, "coordinates": coords}
    try:
        if not shape(geometria).is_valid:
            raise CatalogoErro("A camada contém uma geometria inválida. Corrija-a no QGIS.")
    except (GEOSException, TypeError, ValueError) as exc:
        raise CatalogoErro("A camada contém uma geometria inválida. Corrija-a no QGIS.") from exc
    props = item.get("properties")
    if props is None:
        props = {}
    if not isinstance(props, dict) or any(
        v is not None and (type(v) not in (str, int, bool, float) or isinstance(v, float) and not math.isfinite(v))
        for v in props.values()
    ):
        raise CatalogoErro("Os atributos devem conter textos, números, valores lógicos ou nulos.")
    return familia, {"type": "Feature", "geometry": geometria, "properties": props}


def _geojson(conteudo):
    if not conteudo or len(conteudo) > MAX_UPLOAD:
        raise CatalogoErro("Selecione um GeoJSON de até 8 MiB.")
    try:
        dados = json.loads(conteudo.decode("utf-8-sig"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CatalogoErro("O arquivo precisa ser um GeoJSON válido em UTF-8.") from exc
    if not isinstance(dados, dict) or dados.get("type") != "FeatureCollection":
        raise CatalogoErro("Exporte a camada do QGIS como GeoJSON FeatureCollection.")
    if dados.get("crs") not in (None, {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}):
        crs = dados["crs"]
        if not isinstance(crs, dict) or crs.get("type") != "name" or crs.get("properties") not in (
            {"name": "urn:ogc:def:crs:EPSG::4326"}, {"name": "EPSG:4326"},
        ):
            raise CatalogoErro("Exporte a camada com SRC EPSG:4326 / WGS 84.")
    itens = dados.get("features")
    if not isinstance(itens, list) or not 1 <= len(itens) <= MAX_FEICOES:
        raise CatalogoErro("O GeoJSON precisa conter de 1 a 50.000 feições.")
    feicoes, familias = [], set()
    for indice, item in enumerate(itens, 1):
        try:
            familia, feicao = _validar_feicao(item)
        except CatalogoErro as exc:
            raise CatalogoErro(f"Feição {indice}. {exc}") from exc
        familias.add(familia)
        feicoes.append(feicao)
    tipo = next(iter(familias)) if len(familias) == 1 else "vetor"
    return json.dumps({"type": "FeatureCollection", "features": feicoes}, separators=(",", ":")), tipo, len(feicoes)


def preparar_importacao(arquivo, form):
    nome = _texto(arquivo.filename.replace("\\", "/").rsplit("/", 1)[-1], 200)
    if not nome.lower().endswith((".geojson", ".json")):
        raise CatalogoErro("Envie um arquivo .geojson ou .json.")
    metadados = _metadados(form)
    conteudo = arquivo.stream.read(MAX_UPLOAD + 1)
    geojson, tipo, total = _geojson(conteudo)
    return nome, geojson, hashlib.sha256(conteudo).hexdigest(), total, tipo, json.dumps(metadados)


def _inserir_versao(conn, codigo, dados, usuario_id, *, publicar=False):
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    identificador = db.insert_and_get_id(
        conn, """INSERT INTO geovsatt_versoes(codigo,arquivo,geojson,sha256,total,tipo,metadados,autor_id,criada_em,
                                             publicada_em,ativa) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (codigo, *dados, usuario_id, agora, agora if publicar else None, int(publicar)),
        "id_versao",
    )
    _evento(conn, "versao_importada", codigo, {"versao": identificador, "total": dados[3]})
    return identificador


def importar(target, codigo, arquivo, form, usuario_id):
    dados = preparar_importacao(arquivo, form)
    with _escrita(target) as conn:
        if not conn.execute("SELECT 1 FROM geovsatt_camadas WHERE codigo = ?", (codigo,)).fetchone():
            raise CamadaAusente("Camada não encontrada.")
        return _inserir_versao(conn, codigo, dados, usuario_id)


def importar_nova(target, codigo, arquivo, form, bases, usuario_id):
    nome, grupo, descricao, _ = _dados_camada(codigo, form)
    camada = (nome, grupo, descricao, configuracao_padrao())
    dados = preparar_importacao(arquivo, form)
    with _escrita(target) as conn:
        _criar_camada(conn, codigo, camada, bases)
        return _inserir_versao(conn, codigo, dados, usuario_id)


def _versao(row):
    item = db.serialize_row(row)
    item["metadados"] = json.loads(item["metadados"])
    return item


def listar_versoes(target, codigo):
    return [_versao(row) for row in db.query(target, f"""
        SELECT {COLUNAS_VERSAO} FROM geovsatt_versoes WHERE codigo = ? ORDER BY id_versao DESC
    """, (codigo,))]


def obter_versao(target, codigo, versao):
    row = db.query_one(target, f"""
        SELECT {COLUNAS_VERSAO},geojson FROM geovsatt_versoes WHERE codigo = ? AND id_versao = ?
    """, (codigo, versao))
    if not row:
        raise CamadaAusente("Versão não encontrada nesta camada.")
    return _versao(row)


def _exigir_versao(atualizacao):
    if not atualizacao.rowcount:
        raise CamadaAusente("Versão não encontrada nesta camada.")


def editar_metadados(target, codigo, versao, form):
    metadados = _metadados(form)
    with _escrita(target) as conn:
        _bloquear_camada(conn, codigo)
        anterior = conn.execute("SELECT metadados FROM geovsatt_versoes WHERE codigo=? AND id_versao=?",
                                (codigo, versao)).fetchone()
        if anterior:
            mbtiles = json.loads(anterior[0]).get("mbtiles")
            if mbtiles:
                metadados["mbtiles"] = mbtiles
        _exigir_versao(conn.execute(
            "UPDATE geovsatt_versoes SET metadados=? WHERE codigo=? AND id_versao=?",
            (json.dumps(metadados), codigo, versao),
        ))
        _evento(conn, "metadados_editados", codigo, {"versao": versao})


def _bloquear_camada(conn, codigo):
    # O BEGIN IMMEDIATE faz a reserva equivalente no SQLite.
    lock = " FOR UPDATE" if getattr(conn, "backend", "sqlite") == "postgresql" else ""
    return conn.execute("SELECT codigo FROM geovsatt_camadas WHERE codigo = ?" + lock, (codigo,)).fetchone()


def publicar(target, codigo, versao):
    with _escrita(target) as conn:
        _bloquear_camada(conn, codigo)
        anterior = conn.execute(
            "SELECT id_versao FROM geovsatt_versoes WHERE codigo=? AND ativa=1", (codigo,)
        ).fetchone()
        conn.execute("UPDATE geovsatt_versoes SET ativa=0 WHERE codigo=? AND ativa=1", (codigo,))
        _exigir_versao(conn.execute(
            "UPDATE geovsatt_versoes SET ativa=1, publicada_em=? WHERE codigo=? AND id_versao=?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), codigo, versao),
        ))
        _evento(conn, "versao_publicada", codigo, {"versao": versao, "anterior": anterior[0] if anterior else None})
