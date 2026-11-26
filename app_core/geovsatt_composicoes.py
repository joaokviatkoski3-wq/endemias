"""Composições privadas de mapas, com permissões reavaliadas na abertura."""

from datetime import datetime, timezone
import json
from pathlib import Path

from app_core import audit, db, geovsatt_catalogo as catalogo
from app_core import geovsatt_trabalhos as trabalhos_core


class ComposicaoAusente(catalogo.CatalogoErro):
    pass


class ComposicaoAlterada(catalogo.CatalogoErro):
    pass


OPERADORES = {"contains", "exact", "not_equal", "empty", "filled", "gte", "lte"}


def ensure_schema(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        conn.execute("SELECT id_composicao FROM geovsatt_composicoes LIMIT 0")
        return
    schema = Path(__file__).resolve().parents[1] / "migrations/postgresql/0048_geovsatt_composicoes.sql"
    conn.executescript(schema.read_text(encoding="utf-8").replace(
        "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
    ))


def _texto(valor, limite):
    if not isinstance(valor, str):
        raise catalogo.CatalogoErro("Preencha os campos da composição.")
    return catalogo._texto(valor, limite)


def _validar(payload, permitidas, bases, pontos):
    if not isinstance(payload, dict):
        raise catalogo.CatalogoErro("Informe uma composição válida.")
    titulo = _texto(payload.get("titulo"), 84)
    nota = _texto(payload.get("nota", ""), 140)
    orientacao, layout, base = (payload.get(campo) for campo in ("orientacao", "layout", "base"))
    if (not titulo or orientacao not in ("paisagem", "retrato") or layout not in ("inferior", "lateral", "superior")
            or not isinstance(base, str) or base not in bases or type(payload.get("legenda")) is not bool):
        raise catalogo.CatalogoErro("Confira o título, a orientação, o layout e a imagem-base.")
    centro, zoom = payload.get("centro"), payload.get("zoom")
    if (not isinstance(centro, list) or len(centro) != 2 or any(type(n) not in (int, float) for n in centro)
            or not (-85.05113 <= centro[0] <= 85.05113 and -180 <= centro[1] <= 180)
            or type(zoom) is not int or not 10 <= zoom <= 22):
        raise catalogo.CatalogoErro("O recorte do mapa é inválido.")
    camadas = payload.get("camadas")
    filtros = payload.get("filtros", {})
    if (not isinstance(camadas, list) or any(not isinstance(codigo, str) or codigo not in permitidas for codigo in camadas)
            or len(set(camadas)) != len(camadas) or not isinstance(filtros, dict)):
        raise catalogo.CatalogoErro("A composição contém camadas indisponíveis.")
    fontes = set(camadas)
    calor = payload.get("calor")
    if calor is not None:
        if not isinstance(calor, dict) or set(calor) != {"camada", "raio", "ponderar_ovos"}:
            raise catalogo.CatalogoErro("A configuração do mapa de calor é inválida.")
        codigo, raio, ponderar = (calor[campo] for campo in ("camada", "raio", "ponderar_ovos"))
        if (not isinstance(codigo, str) or codigo not in pontos or codigo not in permitidas
                or type(raio) is not int or not 16 <= raio <= 64 or type(ponderar) is not bool
                or (ponderar and codigo != "ovitrampas")):
            raise catalogo.CatalogoErro("A composição contém um mapa de calor inválido ou indisponível.")
        fontes.add(codigo)
    if filtros.keys() - fontes:
        raise catalogo.CatalogoErro("A composição contém camadas indisponíveis.")
    filtros_validos = {}
    for codigo, regras in filtros.items():
        if not isinstance(regras, list) or len(regras) > 4:
            raise catalogo.CatalogoErro("A composição contém filtros inválidos.")
        linhas = []
        for regra in regras:
            if not isinstance(regra, dict) or not isinstance(regra.get("match"), str) or regra["match"] not in OPERADORES:
                raise catalogo.CatalogoErro("A composição contém uma comparação inválida.")
            campo = _texto(regra.get("field"), 120)
            valor = _texto(regra.get("value"), 400)
            if not campo or (not valor and regra["match"] not in {"empty", "filled"}):
                raise catalogo.CatalogoErro("Informe o campo e o valor do filtro.")
            linhas.append({"field": campo, "match": regra["match"], "value": valor})
        if linhas:
            if codigo == trabalhos_core.CODIGO:
                try:
                    trabalhos_core.validar_regras_composicao(linhas)
                except ValueError as exc:
                    raise catalogo.CatalogoErro(str(exc)) from exc
            filtros_validos[codigo] = linhas
    configuracao = {"titulo": titulo, "nota": nota, "orientacao": orientacao, "layout": layout, "base": base,
                    "legenda": payload["legenda"], "centro": centro, "zoom": zoom, "camadas": camadas, "filtros": filtros_validos}
    if calor is not None:
        configuracao["calor"] = calor
    return configuracao


def listar(target, usuario_id):
    return [db.serialize_row(row) for row in db.query(target, """
        SELECT id_composicao,titulo,atualizada_em FROM geovsatt_composicoes
        WHERE usuario_id=? ORDER BY atualizada_em DESC,id_composicao DESC
    """, (usuario_id,))]


def obter(target, usuario_id, identificador, permitidas, bases, *, pontos=()):
    row = db.query_one(target, """
        SELECT id_composicao,configuracao,atualizada_em FROM geovsatt_composicoes WHERE id_composicao=? AND usuario_id=?
    """, (identificador, usuario_id))
    if not row:
        raise ComposicaoAusente("Composição não encontrada.")
    configuracao = json.loads(row["configuracao"])
    camadas = [codigo for codigo in configuracao["camadas"] if codigo in permitidas]
    indisponiveis = len(configuracao["camadas"]) - len(camadas)
    base_indisponivel = configuracao["base"] not in bases
    fontes = set(camadas)
    calor = configuracao.get("calor")
    calor_indisponivel = False
    if calor:
        codigo = calor["camada"]
        if codigo in pontos and codigo in permitidas:
            fontes.add(codigo)
        else:
            configuracao.pop("calor")
            calor_indisponivel = True
    configuracao.update(camadas=camadas, filtros={codigo: regras for codigo, regras in configuracao["filtros"].items() if codigo in fontes})
    if base_indisponivel:
        configuracao["base"] = "none"
    return {"id_composicao": identificador, "atualizada_em": row["atualizada_em"], "configuracao": configuracao,
            "camadas_indisponiveis": indisponiveis, "base_indisponivel": base_indisponivel,
            "calor_indisponivel": calor_indisponivel}


def salvar(target, usuario_id, payload, permitidas, bases, identificador=None, *, pontos=()):
    configuracao = _validar(payload, permitidas, bases, pontos)
    agora = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    dados = (configuracao["titulo"], json.dumps(configuracao, ensure_ascii=False), agora)
    with catalogo._escrita(target) as conn:
        if identificador is None:
            identificador = db.insert_and_get_id(conn, """
                INSERT INTO geovsatt_composicoes(titulo,configuracao,atualizada_em,criada_em,usuario_id) VALUES (?,?,?,?,?)
            """, (*dados, agora, usuario_id), "id_composicao")
        else:
            resultado = conn.execute("""
                UPDATE geovsatt_composicoes SET titulo=?,configuracao=?,atualizada_em=?
                WHERE id_composicao=? AND usuario_id=? AND atualizada_em=?
            """, (*dados, identificador, usuario_id, _texto(payload.get("atualizada_em"), 40)))
            if not resultado.rowcount:
                if not conn.execute("SELECT 1 FROM geovsatt_composicoes WHERE id_composicao=? AND usuario_id=?",
                                    (identificador, usuario_id)).fetchone():
                    raise ComposicaoAusente("Composição não encontrada.")
                raise ComposicaoAlterada("A composição foi alterada. Abra-a novamente antes de atualizar.")
        audit.registrar_evento(None, "geovsatt_composicao_salva", entidade="geovsatt_composicao", entidade_id=identificador,
                               detalhes={"camadas": len(configuracao["camadas"])}, conn=conn)
    return {"id_composicao": identificador, "titulo": configuracao["titulo"], "atualizada_em": agora}
