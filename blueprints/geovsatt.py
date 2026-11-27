import csv
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import json
from pathlib import Path
import sqlite3

from shapely.geometry import mapping

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, stream_with_context, url_for

from app_core import audit
from app_core import blueprint_helpers as bh
from app_core import geovsatt as geo
from app_core import geovsatt_busca as busca
from app_core import geovsatt_catalogo as camadas
from app_core import geovsatt_composicoes as composicoes
from app_core import geovsatt_bloqueios as bloqueios
from app_core import geovsatt_dengue as dengue
from app_core import geovsatt_enderecos as enderecos
from app_core import geovsatt_vigilancia as vigilancia
from app_core.csv_seguranca import campo_csv
from app_core import geovsatt_equipamentos as equipamentos
from app_core import geovsatt_exportacao as exportacao
from app_core import geovsatt_openfreemap as base_vetorial
from app_core import geovsatt_ortofotos as ortofotos
from app_core import geovsatt_trabalhos
from app_core.geovsatt_malha import blocos
from app_core import registro_geografico as rg
from app_core import setores
from app_core.auth import login_required
from app_core.version import APP_VERSION


bp = Blueprint("geovsatt", __name__)
superadmin = bh.nivel_min("superadmin")
LIMITE_PACOTE_OFFLINE = 50 * 1024**2


@bp.before_request
def setor_do_mapa():
    setor = setores.atual()
    if setor == "endemias" and request.endpoint in {"geovsatt.pacientes_dengue", "geovsatt.imprimir_dengue"}:
        return
    if setor != "geo":
        abort(403)


@bp.after_request
def cache_privado(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _base_dir():
    return current_app.config["BASE_DIR"]


def _obter(codigo, **kwargs):
    return camadas.obter(bh.db_target(), codigo, geo.BASES, **kwargs)


def _colecao_camada(target, camada, usuario, parametros=None):
    codigo = camada["id"]
    if camada["origem"] != "importacao":
        return geo.dados_nativos(target, _base_dir(), codigo, usuario, parametros=parametros,
                                cnefe=current_app.config["GEOVSATT_CNEFE_CSV"])
    if codigo == equipamentos.CODIGO:
        dados = equipamentos.geojson(camada, _base_dir())
        dados["metadata"] = {"versao": camada["id_versao"]}
        return dados
    return json.loads(camada["geojson"])


def _localizador(target, usuario):
    malha = geo.malha_bloqueios(target, _base_dir(), usuario)
    localizador = enderecos.Localizador(target, geo.BASES, malha, current_app.config["GEOVSATT_CNEFE_CSV"])
    return malha, localizador


def _acesso_dengue(usuario):
    camada = _obter("dengue")
    if not camada["disponivel"] or not geo.pode_ver_camada(bh.db_target(), camada, usuario):
        abort(404)


@bp.get("/geovsatt/dengue")
@login_required
@superadmin
def page_dengue():
    return redirect(url_for("geovsatt.admin_catalogo", aba="dengue", **{
        k: request.args[k] for k in ("inicio", "fim", "localidade", "unidade", "pendentes") if k in request.args
    }), code=303)


def _dados_dengue():
    target, usuario = bh.db_target(), bh.usuario_atual()
    try:
        _, localizador = _localizador(target, usuario)
        casos = list(vigilancia.preparar_dengue(target, localizador))
        anos = sorted({str(caso["ano"]) for caso in casos} | {str(datetime.now().year)}, reverse=True)
        ano = request.args.get("ano", str(datetime.now().year))
        selecionados = vigilancia.filtrar_dengue(
            (caso for caso in casos if not ano or str(caso["ano"]) == ano), request.args)
    except (OSError, ValueError):
        abort(400, "Confira o período e a configuração da base municipal de endereços.")
    total = len(selecionados)
    pendentes = sum(not row["centro"] for row in selecionados)
    if request.args.get("pendentes") == "1":
        selecionados = [row for row in selecionados if not row["centro"]]
    estado = dengue.estado(target)
    desatualizada = estado and datetime.fromisoformat(estado["sincronizado_em"]) < datetime.now(timezone.utc) - timedelta(minutes=30)
    return {"casos": selecionados, "sincronizacao": estado, "desatualizada": desatualizada,
            "total": total, "pendentes": pendentes, "ano": ano, "anos": anos,
            "configurado": dengue.configurado(current_app.config)}


@bp.get("/pacientes-dengue")
@login_required
def pacientes_dengue():
    if setores.atual() not in (None, "endemias"):
        abort(404)
    _acesso_dengue(bh.usuario_atual())
    dados = _dados_dengue()
    dados["casos"] = [caso for caso in dados["casos"] if caso["situacao"] != "Negativo ou descartado" or caso["ano"] < 2026]
    return render_template("pacientes_dengue.html", **dados)


@bp.get("/pacientes-dengue/<chave>/mapa-bloqueio")
@bp.get("/geovsatt/dengue/<chave>/mapa-bloqueio")
@login_required
def imprimir_dengue(chave):
    target, usuario = bh.db_target(), bh.usuario_atual()
    _acesso_dengue(usuario)
    try:
        malha, localizador = _localizador(target, usuario)
        evento = next(vigilancia.preparar_dengue(target, localizador, chave), None)
        if evento is None or not evento["centro"]:
            abort(404)
        if evento["ano"] < 2026 or evento["situacao"] == "Negativo ou descartado":
            abort(404)
        mapa = bloqueios.folha(target, _base_dir(), "dengue", evento, request.args, malha)
    except (OSError, ValueError) as exc:
        abort(400, str(exc) if isinstance(exc, ValueError) else "A base municipal de endereços está indisponível.")
    audit.registrar_evento(bh.get_db, "geovsatt_imprimir_bloqueio", "dengue", chave)
    return render_template("esporotricose_mapa_bloqueio.html", mapa=mapa, animal=None,
        voltar=url_for("geovsatt.pacientes_dengue") if setores.atual() == "endemias" else (
            url_for("geovsatt.admin_catalogo", aba="dengue") if usuario["nivel"] == "superadmin" else url_for("geovsatt.page")),
        titulo="Mapa de bloqueio de dengue",
        setor_titulo="Vigilância de Endemias",
        referencia=[("Notificação", evento["notificacao"]), ("Data da notificação", evento["data_notificacao"]),
                    ("Localidade", evento["localidade"]), ("Quarteirão", evento["quarteirao"]),
                    ("Data de bloqueio", evento["data_bloqueio"])])


@bp.post("/geovsatt/dengue/sincronizar")
@login_required
@superadmin
def sincronizar_dengue():
    try:
        resultado = dengue.sincronizar(bh.db_target(), current_app.config)
    except ValueError as exc:
        flash(str(exc), "erro")
    else:
        audit.registrar_evento(bh.get_db, "geovsatt_sincronizar_dengue", "dengue", detalhes={"total": resultado["total"]})
        flash(f'{resultado["total"]} notificações no espelho anual.', "sucesso")
    return redirect(url_for("geovsatt.admin_catalogo", aba="dengue"), code=303)


@bp.get("/geovsatt/admin/coletas-tubo")
@login_required
@superadmin
def coletas_tubo():
    return redirect(url_for("geovsatt.admin_catalogo", aba="coletas"), code=303)


def _recorte_coletas():
    try:
        return vigilancia.filtros_coletas(request.args)
    except ValueError as exc:
        abort(400, str(exc))


def _pendencias_coletas_tubo(*, listar=False):
    target = bh.db_target()
    recorte = _recorte_coletas()
    try:
        _, localizador = _localizador(target, bh.usuario_atual())
        return vigilancia.pendencias_csv(target, localizador, listar=listar, parametros=recorte)
    except (OSError, ValueError):
        abort(400, "Confira a base municipal de endereços.")


def _dados_coletas_tubo():
    pendentes, resumo = _pendencias_coletas_tubo(listar=True)
    return {"total": len(pendentes), "endemias": setores.url_setor(bh.usuario_atual(), "endemias"),
            "especies_tubos": vigilancia.ESPECIES_TUBOS, "recorte_coletas": _recorte_coletas(), **resumo}


@bp.get("/geovsatt/admin/coletas-tubo/pendencias.csv")
@login_required
@superadmin
def coletas_tubo_csv():
    pendentes, _ = _pendencias_coletas_tubo()
    earth = request.args.get("destino") == "earth"
    campos = ("name", "address") if earth else enderecos.COLUNAS_CSV
    texto = StringIO(newline="")
    escritor = csv.DictWriter(texto, fieldnames=campos)
    escritor.writeheader()
    for item in pendentes.values():
        dados = enderecos.campos_csv(item["endereco"])
        dados["endereco_google_earth"] = item["endereco_earth"]
        if earth:
            dados = {"name": dados["chave"], "address": dados["endereco_google_earth"]}
        escritor.writerow({k: campo_csv(v) for k, v in dados.items()})
    audit.registrar_evento(bh.get_db, "geovsatt_exportar_pendencias", "coletas_tubos",
                           detalhes={"total": len(pendentes), "destino": "earth" if earth else "csv"})
    nome = "coletas-google-earth.csv" if earth else "coletas-enderecos-pendentes.csv"
    return send_file(BytesIO(texto.getvalue().encode("utf-8" if earth else "utf-8-sig")), mimetype="text/csv",
                     as_attachment=True, download_name=nome)


@bp.get("/geovsatt/admin/coletas-tubo/localizar/<id_coleta>")
@login_required
@superadmin
def coletas_tubo_localizar(id_coleta):
    target = bh.db_target()
    try:
        malha, localizador = _localizador(target, bh.usuario_atual())
        registro = next(vigilancia.enderecos_coletas(target, localizador, id_coleta), None)
    except (OSError, ValueError):
        abort(400, "Confira a base municipal de endereços.")
    if not registro or vigilancia._e_coleta_pe(registro[0]):
        abort(404)
    row, endereco, chave, localizado = registro
    if localizado:
        return redirect(url_for("geovsatt.admin_catalogo", aba="coletas", _anchor="pendencias-tubos",
                                **_recorte_coletas()), code=303)
    quarteirao = blocos(malha, {chave}) if chave else []
    return _pagina_mapa(coleta_pendente={
        "id": row["id_coleta"], "tubo": row["num_tubo"], "endereco": endereco,
        "quarteirao": row["quarteirao"], "localidade": row["localidade"],
        "geometria": mapping(quarteirao[0][1]) if quarteirao else None,
    })


@bp.post("/api/geovsatt/admin/coletas-tubo/posicao")
@login_required
@superadmin
def coletas_tubo_posicao():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not payload["id"]:
        return jsonify(erro="Informe a coleta a reposicionar."), 400
    target = bh.db_target()
    primeira_posicao = payload.get("primeira_posicao") is True
    try:
        _, localizador = _localizador(target, bh.usuario_atual())
        posicao = vigilancia.reposicionar_coleta(target, localizador, payload["id"],
                                                 payload.get("latitude"), payload.get("longitude"),
                                                 primeira_posicao=primeira_posicao)
    except vigilancia.PosicaoJaConfirmada as exc:
        return jsonify(erro=str(exc)), 409
    except LookupError:
        abort(404)
    except ValueError as exc:
        return jsonify(erro=str(exc)), 400
    acao = "geovsatt_marcar_coleta" if primeira_posicao else "geovsatt_reposicionar_coleta"
    audit.registrar_evento(bh.get_db, acao, "coletas_tubos", payload["id"])
    return jsonify(coordenadas=posicao, fonte="Ajuste no GeoVSATT")


@bp.post("/api/geovsatt/admin/coletas-tubo/importar")
@login_required
@superadmin
def coletas_tubo_importar():
    request.max_content_length = vigilancia.LIMITE_COORDENADAS + 32 * 1024
    arquivo = request.files.get("arquivo") or request.files.get("csv")
    if not arquivo:
        return jsonify({"erro": "Selecione o CSV, KML ou KMZ com as coordenadas."}), 400
    formato = Path(arquivo.filename).suffix.lower().lstrip(".")
    aplicar = request.form.get("etapa") == "aplicar"
    try:
        _, localizador = _localizador(bh.db_target(), bh.usuario_atual())
        conteudo = arquivo.read(vigilancia.LIMITE_COORDENADAS + 1)
        if len(conteudo) > vigilancia.LIMITE_COORDENADAS:
            raise ValueError("O arquivo deve ter até 12 MiB.")
        resultado = vigilancia.importar_coordenadas(bh.db_target(), conteudo, localizador,
                                                    formato=formato, aplicar=aplicar)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        mensagem = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError) else (
            "Confira o arquivo de coordenadas e a base municipal de endereços.")
        return jsonify({"erro": mensagem}), 400
    if aplicar and not resultado["total_problemas"] and resultado["validas"]:
        audit.registrar_evento(bh.get_db, "geovsatt_importar_coordenadas", "coletas_tubos",
                               detalhes={"total": resultado["validas"]})
    return jsonify(resultado)


def _nominatim():
    token = current_app.config["GEOVSATT_NOMINATIM_TOKEN"].strip()
    return busca.endpoint_nominatim(current_app.config["GEOVSATT_NOMINATIM_URL"], token), token


@bp.get("/geovsatt")
@login_required
def page():
    return _pagina_mapa()


def _pagina_mapa(*, coleta_pendente=None):
    usuario = bh.usuario_atual()
    catalogo = geo.catalogo(bh.db_target(), usuario)
    pode_rg = setores.pode_entrar(usuario, "endemias")
    pode_estimar = pode_rg and any(item["id"] == "quarteiroes" for item in catalogo["camadas"])
    ambiental = setores.url_setor(usuario, "ambiental") if geo.esporotricose_localizacao_exata(usuario) else None
    endemias = setores.url_setor(usuario, "endemias")
    return render_template("geovsatt.html", catalogo=catalogo, pode_rg=pode_rg, pode_estimar=pode_estimar,
                           esri_licenciado=current_app.config["GEOVSATT_ESRI_LICENSED"], ambiental=ambiental,
                           conta_geo=usuario["id_usuario"], endemias=endemias,
                           nominatim=bool(_nominatim()[0]), coleta_pendente=coleta_pendente,
                           especies_tubos=vigilancia.ESPECIES_TUBOS,
                           recorte_coletas=_recorte_coletas() if coleta_pendente else {})


@bp.get("/geovsatt/manifest.webmanifest")
def manifest_mapa():
    return send_from_directory(current_app.static_folder, "manifest-geovsatt.webmanifest",
                               mimetype="application/manifest+json")


@bp.get("/geovsatt-sw.js")
def worker_mapa():
    if request.args.get("v", APP_VERSION) != APP_VERSION:
        abort(409)
    resposta = send_from_directory(current_app.static_folder, "geovsatt-sw.js", mimetype="application/javascript")
    resposta.headers["Service-Worker-Allowed"] = "/geovsatt"
    return resposta


@bp.get("/geovsatt/offline")
def mapa_offline():
    if request.args.get("v", APP_VERSION) != APP_VERSION:
        abort(409)
    return render_template("geovsatt.html", titulo="GeoVSATT offline", modo_offline=True,
                           catalogo={"camadas": []})


@bp.get("/api/geovsatt/catalogo")
@login_required
def api_catalogo():
    return jsonify(geo.catalogo(bh.db_target(), bh.usuario_atual()))


def _camadas_para_copia(target, usuario):
    catalogo = geo.catalogo(target, usuario)
    return (
        {item["id"]: item for item in catalogo["camadas"] if item["disponivel"] and item.get("pode_exportar")},
        {item["id"]: item for item in catalogo["ortofotos"] if item["pode_exportar"]},
    )


def _recorte_valido(recorte):
    return (isinstance(recorte, list) and len(recorte) == 4 and all(type(valor) in (int, float) for valor in recorte)
            and -180 <= recorte[0] < recorte[2] <= 180 and -90 <= recorte[1] < recorte[3] <= 90)


@bp.get("/api/geovsatt/pacote-offline/estado")
@login_required
def api_estado_pacote():
    usuario = bh.usuario_atual()
    vetores, imagens = _camadas_para_copia(bh.db_target(), usuario)
    return jsonify({
        "usuario": usuario["id_usuario"],
        "camadas": list(vetores),
        "ortofotos": {codigo: item["versao"] for codigo, item in imagens.items()},
        "rg": setores.pode_entrar(usuario, "endemias"),
        "esporotricose_exata": geo.esporotricose_localizacao_exata(usuario),
    })


@bp.post("/api/geovsatt/pacote-offline")
@login_required
def api_pacote_offline():
    request.max_content_length = 16_384
    payload = request.get_json(silent=True)
    codigos = payload.get("camadas") if isinstance(payload, dict) else None
    imagens = payload.get("ortofotos", []) if isinstance(payload, dict) else None
    ofm = payload.get("openfreemap", False) if isinstance(payload, dict) else None
    if (not isinstance(codigos, list) or not isinstance(imagens, list) or type(ofm) is not bool
            or not (codigos or imagens or ofm)
            or any(not isinstance(codigo, str) or len(codigo) > 60 for codigo in codigos + imagens)
            or type(payload.get("enderecos", False)) is not bool):
        return jsonify({"erro": "Selecione as camadas do pacote offline."}), 400
    recorte = payload.get("recorte")
    if recorte is not None and not _recorte_valido(recorte):
        return jsonify({"erro": "O recorte das imagens está inválido."}), 400
    trabalhos = payload.get("trabalhos", {})
    if (not isinstance(trabalhos, dict) or set(trabalhos) - {"inicio", "fim", "tipo", "localidade"}
            or any(not isinstance(valor, str) for valor in trabalhos.values())):
        return jsonify({"erro": "Os filtros de quarteirões trabalhados estão inválidos."}), 400

    target, usuario = bh.db_target(), bh.usuario_atual()
    catalogo, catalogo_ortos = _camadas_para_copia(target, usuario)
    selecionadas = list(dict.fromkeys(codigos))
    ortos_selecionadas = list(dict.fromkeys(imagens))
    if set(selecionadas) - catalogo.keys() or set(ortos_selecionadas) - catalogo_ortos.keys():
        return jsonify({"erro": "O pacote inclui uma camada indisponível para download nesta conta."}), 403
    tem_rg = "quarteiroes" in selecionadas and setores.pode_entrar(usuario, "endemias")
    if payload.get("enderecos") and not tem_rg:
        return jsonify({"erro": "Os endereços do RG exigem acesso ao Endemias e a camada Quarteirões."}), 403

    gerado = datetime.now(timezone.utc)
    pacote = {
        "formato": 1, "usuario": usuario["id_usuario"], "criado_em": gerado.isoformat(),
        "valido_ate": (gerado + timedelta(days=7)).isoformat(),
        "camadas": [catalogo[codigo] for codigo in selecionadas], "dados": {},
        "ortofotos": [],
        "esporotricose_exata": "esporotricose" in selecionadas and geo.esporotricose_localizacao_exata(usuario),
    }
    try:
        for codigo in selecionadas:
            camada = _obter(codigo, incluir_dados=True)
            if not geo.pode_exportar_camada(target, camada, usuario):
                return jsonify({"erro": "A permissão da camada mudou. Atualize o catálogo e tente novamente."}), 403
            if codigo == geovsatt_trabalhos.CODIGO:
                consulta = geovsatt_trabalhos.filtros(trabalhos)
                malha = geo.quarteiroes(target, _base_dir(), usuario=usuario, incluir_rg=False)
                dados, historico = geovsatt_trabalhos.preparar_offline(target, malha, consulta)
                pacote["dados"][codigo] = dados
                pacote["historico_trabalhos"] = historico
            else:
                pacote["dados"][codigo] = _colecao_camada(target, camada, usuario)
    except camadas.CamadaAusente:
        return jsonify({"erro": "Uma camada deixou de estar disponível. Atualize o catálogo e tente novamente."}), 409
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400

    if tem_rg:
        pacote["populacao"] = {"media": rg.MEDIA_PESSOAS_POR_RESIDENCIA, "fonte": rg.FONTE_POPULACAO}
    if payload.get("enderecos"):
        pacote["rg"] = rg.detalhes_quarteiroes_offline(target, (
            feature["properties"] for feature in pacote["dados"]["quarteiroes"]["features"]
        ))
        pacote["rg_vocabulario"] = {"abreviacoes": rg.ABREVIACOES_LOGRADOURO, "prefixos": sorted(rg.PREFIXOS_LOGRADOURO)}
    projetos = []
    pontos = {codigo for codigo in selecionadas if catalogo[codigo]["tipo"] == "ponto"}
    bases = {"none"} | {catalogo_ortos[codigo]["base"] for codigo in ortos_selecionadas}
    if ofm:
        bases.add("openfreemap")
    for item in composicoes.listar(target, usuario["id_usuario"]):
        try:
            projetos.append(composicoes.obter(target, usuario["id_usuario"], item["id_composicao"],
                                               set(selecionadas), bases, pontos=pontos))
        except composicoes.ComposicaoAusente:
            continue
    pacote["composicoes"] = projetos

    restantes = LIMITE_PACOTE_OFFLINE
    if ortos_selecionadas:
        restantes -= len(json.dumps(pacote, ensure_ascii=False, separators=(",", ":"), default=str).encode())
    try:
        for codigo in ortos_selecionadas:
            orto = _obter(codigo, incluir_dados=True)
            item = catalogo_ortos[codigo]
            if orto["id_versao"] != item["versao"] or not geo.pode_exportar_camada(target, orto, usuario):
                return jsonify({"erro": "A publicação da ortofoto mudou. Atualize o mapa e tente novamente."}), 409
            orto["metadados"] = json.loads(orto["metadados"])
            blocos, tamanho = ortofotos.pacote_offline(_arquivo_ortofoto(orto), orto, recorte, restantes)
            pacote["ortofotos"].append(item | blocos)
            restantes -= tamanho
    except (camadas.CamadaAusente, OSError, sqlite3.DatabaseError):
        return jsonify({"erro": "O arquivo da ortofoto selecionada está indisponível."}), 409
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400

    conteudo = json.dumps(pacote, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    if len(conteudo) > LIMITE_PACOTE_OFFLINE:
        return jsonify({"erro": "O pacote ultrapassa 50 MiB. Selecione menos camadas para este aparelho."}), 413
    audit.registrar_evento(bh.get_db, "geovsatt_pacote_offline_gerado", entidade="geovsatt_camada",
                           detalhes={"camadas": selecionadas, "ortofotos": ortos_selecionadas,
                                     "bytes": len(conteudo), "enderecos_rg": bool(pacote.get("rg"))})
    return current_app.response_class(conteudo, mimetype="application/json")


@bp.post("/api/geovsatt/pacote-offline/openfreemap")
@login_required
def api_copia_openfreemap():
    request.max_content_length = 2_048
    carga = request.get_json(silent=True)
    recorte = carga.get("recorte") if isinstance(carga, dict) else None
    limite = carga.get("limite") if isinstance(carga, dict) else None
    if not _recorte_valido(recorte) or type(limite) is not int or not 1 <= limite <= LIMITE_PACOTE_OFFLINE:
        return jsonify({"erro": "Informe a área e o tamanho disponível para a base vetorial."}), 400
    try:
        base_vetorial.planejar(recorte, base_vetorial.ZOOM_FINAL)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    return current_app.response_class(stream_with_context(base_vetorial.transmitir(recorte, limite)),
                                      mimetype="application/x-ndjson")


@bp.route("/api/geovsatt/composicoes", methods=["GET", "POST"])
@bp.route("/api/geovsatt/composicoes/<int:identificador>", methods=["GET", "PUT"])
@login_required
def api_composicoes(identificador=None):
    usuario = bh.usuario_atual()
    target = bh.db_target()
    uid = usuario["id_usuario"]
    if identificador is None and request.method == "GET":
        return jsonify(composicoes.listar(target, uid))
    catalogo = geo.catalogo(target, usuario)
    permitidas = {item["id"] for item in catalogo["camadas"] if item["disponivel"]}
    pontos = {item["id"] for item in catalogo["camadas"] if item["disponivel"] and item["tipo"] == "ponto"}
    bases = {"none", "openfreemap", "sentinel"}
    bases.update(orto["base"] for orto in catalogo["ortofotos"])
    if current_app.config["GEOVSATT_ESRI_LICENSED"]:
        bases.add("esri")
    try:
        if request.method == "GET":
            return jsonify(composicoes.obter(target, uid, identificador, permitidas, bases, pontos=pontos))
        request.max_content_length = 131_072
        resposta = composicoes.salvar(target, uid, request.get_json(silent=True), permitidas, bases, identificador, pontos=pontos)
        return jsonify(resposta), 201 if identificador is None else 200
    except composicoes.ComposicaoAusente as exc:
        return jsonify({"erro": str(exc)}), 404
    except composicoes.ComposicaoAlterada as exc:
        return jsonify({"erro": str(exc)}), 409
    except camadas.CatalogoErro as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.get("/api/geovsatt/camadas/<codigo>")
@login_required
def api_camada(codigo):
    usuario = bh.usuario_atual()
    target = bh.db_target()
    try:
        camada = _obter(codigo, incluir_dados=True)
        if camada["origem"] == "ortofoto" or not camada["disponivel"] or not geo.pode_ver_camada(target, camada, usuario):
            raise camadas.CamadaAusente("Camada não encontrada.")
        if camada["origem"] == "importacao" and codigo != equipamentos.CODIGO:
            return current_app.response_class(camada["geojson"], mimetype="application/geo+json")
        dados = _colecao_camada(target, camada, usuario, request.args)
        if camada["origem"] == "importacao":
            return current_app.response_class(json.dumps(dados, ensure_ascii=False), mimetype="application/geo+json")
        return jsonify(dados)
    except camadas.CamadaAusente as exc:
        return jsonify({"erro": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.get("/geovsatt/camadas/<codigo>/exportar/<formato>")
@login_required
def baixar_camada(codigo, formato):
    if formato not in {*exportacao.FORMATOS, "mbtiles"}:
        abort(404)
    usuario = bh.usuario_atual()
    target = bh.db_target()
    try:
        camada = _obter(codigo, incluir_dados=True)
    except camadas.CamadaAusente:
        abort(404)
    if not camada["disponivel"] or not geo.pode_ver_camada(target, camada, usuario):
        abort(404)
    if (camada["origem"] == "ortofoto") != (formato == "mbtiles"):
        abort(404)
    if not geo.pode_exportar_camada(target, camada, usuario):
        abort(403)
    if formato == "mbtiles":
        try:
            path = _arquivo_ortofoto(camada)
        except camadas.CamadaAusente:
            abort(404)
        audit.registrar_evento(bh.get_db, "geovsatt_camada_exportada", entidade="geovsatt_camada", entidade_id=codigo,
                               detalhes={"formato": formato, "total": camada["total"], "versao": camada["id_versao"]})
        return _enviar_ortofoto(path, codigo, camada["id_versao"])
    if camada["origem"] == "importacao":
        dados = equipamentos.geojson(camada, _base_dir()) if codigo == equipamentos.CODIGO else json.loads(camada["geojson"])
        dados["metadata"] = json.loads(camada["metadados"])
    else:
        try:
            dados = geo.dados_nativos(target, _base_dir(), codigo, usuario, parametros=request.args)
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 400
    conteudo = exportacao.gerar(dados, camada, formato)
    consulta = dados.get("metadata", {}).get("consulta") if codigo == "quarteiroes_trabalhados" else None
    sufixo = f"-{consulta['inicio']}-{consulta['fim']}" if consulta else ""
    audit.registrar_evento(bh.get_db, "geovsatt_camada_exportada", entidade="geovsatt_camada", entidade_id=codigo,
                           detalhes={"formato": formato, "total": len(dados["features"]), "versao": camada["id_versao"]}
                           | ({"consulta": consulta} if consulta else {}))
    return send_file(BytesIO(conteudo), mimetype=exportacao.FORMATOS[formato], as_attachment=True,
                     download_name=f"geovsatt-{codigo}{sufixo}.{formato}", etag=False, max_age=0)


def _arquivo_ortofoto(versao):
    path = ortofotos.caminho(current_app.config["ANEXOS_DIR"], versao["sha256"])
    if not path.is_file():
        raise camadas.CamadaAusente("Arquivo de ortofoto indisponível.")
    return path


def _enviar_ortofoto(path, codigo, versao):
    return send_file(path, mimetype="application/octet-stream", as_attachment=True,
                     download_name=f"geovsatt-{codigo}-v{versao}.mbtiles", etag=False, max_age=0)


def _responder_mosaico(item, z, x, y):
    try:
        mosaico = ortofotos.mosaico(_arquivo_ortofoto(item), item, z, x, y)
    except (camadas.CatalogoErro, OSError, sqlite3.DatabaseError):
        abort(503)
    conteudo, tipo = mosaico or (ortofotos.TRANSPARENTE, "image/png")
    return current_app.response_class(conteudo, mimetype=tipo)


@bp.get("/api/geovsatt/ortofotos/<codigo>/<int:versao>/<int:z>/<int:x>/<int:y>")
@login_required
def mosaico_ortofoto(codigo, versao, z, x, y):
    target = bh.db_target()
    try:
        camada = _obter(codigo)
    except camadas.CamadaAusente:
        abort(404)
    if (camada["origem"] != "ortofoto" or camada["id_versao"] != versao
            or not geo.pode_ver_camada(target, camada, bh.usuario_atual())):
        abort(404)
    camada["metadados"] = json.loads(camada["metadados"])
    return _responder_mosaico(camada, z, x, y)


@bp.route("/api/geovsatt/busca", methods=["GET", "POST"])
@login_required
def api_busca():
    usuario = bh.usuario_atual()
    target = bh.db_target()
    permitidas = {codigo for codigo in ("localidades", "quarteiroes") if geo.pode_ver_camada(target, _obter(codigo), usuario)}
    pode_rg = setores.pode_entrar(usuario, "endemias")
    try:
        if request.method == "POST":
            request.max_content_length = 4_096
            payload = request.get_json(silent=True)
            termo = payload.get("q") if isinstance(payload, dict) else None
            if not isinstance(termo, str):
                raise ValueError("Informe um texto de busca.")
            if payload.get("sugestao") is True:
                termo = termo.strip()
                resultados = []
                if 3 <= len(termo) <= 180 and "quarteiroes" in permitidas and pode_rg:
                    resultados = busca.buscar_enderecos(target, termo, 7, sugerir=True,
                                                        por_logradouro=payload.get("logradouro") is True)
                return jsonify({"resultados": resultados})
        else:
            termo = request.args.get("q")
        resultados = geo.buscar(target, _base_dir(), termo, permitidas,
                               incluir_rg=pode_rg, usuario=usuario)
        return jsonify({"resultados": resultados})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.get("/api/geovsatt/cep/<cep>")
@login_required
def api_cep(cep):
    try:
        return jsonify(busca.consultar_cep(cep))
    except busca.CepInexistente as exc:
        return jsonify({"erro": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 502


@bp.post("/api/geovsatt/ceps-por-logradouro")
@login_required
def api_ceps_por_logradouro():
    request.max_content_length = 2_048
    payload = request.get_json(silent=True)
    try:
        rua = payload.get("logradouro") if isinstance(payload, dict) else None
        return jsonify({"resultados": busca.ceps_por_logradouro(rua)})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 502


@bp.post("/api/geovsatt/nominatim")
@login_required
def api_nominatim():
    endpoint, token = _nominatim()
    if not endpoint:
        return jsonify({"erro": "O provedor Nominatim ainda não foi configurado."}), 503
    request.max_content_length = 2_048
    payload = request.get_json(silent=True)
    try:
        texto = payload.get("q") if isinstance(payload, dict) else None
        return jsonify({"resultados": busca.buscar_nominatim(endpoint, texto, token)})
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except busca.NominatimOcupado as exc:
        return jsonify({"erro": str(exc)}), 429, {"Retry-After": "2"}
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 502


@bp.get("/api/geovsatt/quarteiroes/<int:id_localidade>/<numero>")
@login_required
def api_detalhe_quarteirao(id_localidade, numero):
    usuario = bh.usuario_atual()
    if not setores.pode_entrar(usuario, "endemias") or not camadas.pode_ver(_obter("quarteiroes"), usuario):
        return jsonify({"erro": "Acesso aos detalhes do Registro Geográfico indisponível para esta conta."}), 403
    try:
        return jsonify(geo.detalhe_quarteirao(bh.db_target(), _base_dir(), id_localidade, numero))
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 404


@bp.post("/api/geovsatt/populacao")
@login_required
def api_populacao():
    usuario = bh.usuario_atual()
    if not setores.pode_entrar(usuario, "endemias") or not geo.pode_ver_camada(bh.db_target(), _obter("quarteiroes"), usuario):
        return jsonify({"erro": "Estimativa restrita a perfis com acesso aos quarteirões do RG."}), 403
    request.max_content_length = 12_288
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or type(payload.get("incluir_condominios", True)) is not bool:
        return jsonify({"erro": "Informe os vértices da área e a opção de condomínios."}), 400
    try:
        resultado = geo.estimar_populacao(bh.db_target(), _base_dir(), payload.get("pontos"), usuario=usuario,
                                         incluir_condominios=payload.get("incluir_condominios", True))
        return jsonify(resultado)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.get("/geovsatt/admin/camadas")
@login_required
@superadmin
def admin_catalogo():
    aba = request.args.get("aba", "catalogo")
    if aba == "dengue":
        dados = _dados_dengue()
    elif aba == "coletas":
        dados = _dados_coletas_tubo()
    elif aba in {"catalogo", "estilos", "importacao"}:
        dados = {"camadas": camadas.listar(bh.db_target(), geo.BASES)}
    else:
        abort(404)
    return render_template("geovsatt_camadas.html", aba=aba, **dados)


def _camada_equipamentos():
    try:
        return _obter(equipamentos.CODIGO, incluir_dados=True)
    except camadas.CamadaAusente:
        return None


@bp.get("/geovsatt/admin/equipamentos")
@login_required
@superadmin
def admin_equipamentos():
    camada = _camada_equipamentos()
    termo = (request.args.get("q") or "").strip()[:120]
    return render_template("geovsatt_equipamentos.html", camada=camada, termo=termo,
                           pontos=equipamentos.listar(camada, _base_dir(), termo))


@bp.route("/geovsatt/admin/equipamentos/novo", methods=["GET", "POST"])
@bp.route("/geovsatt/admin/equipamentos/<int:versao>/<int:indice>/editar", methods=["GET", "POST"])
@login_required
@superadmin
def admin_equipamento(versao=None, indice=None):
    camada = _camada_equipamentos()
    vigente = (camada and camada["id_versao"]) or 0
    if versao is not None and vigente != versao:
        flash("A camada recebeu outra versão. Abra o equipamento novamente.", "erro")
        return redirect(url_for("geovsatt.admin_equipamentos"), code=303)
    valores = {"status_funcionamento": "Ativo", "latitude": request.args.get("latitude", "")[:24],
               "longitude": request.args.get("longitude", "")[:24]}
    if indice is not None:
        if not vigente:
            abort(404)
        feicoes = equipamentos.geojson(camada, _base_dir())["features"]
        if indice >= len(feicoes) or feicoes[indice]["geometry"]["type"] != "Point":
            abort(404)
        feicao = feicoes[indice]
        lon, lat = feicao["geometry"]["coordinates"][:2]
        valores = feicao["properties"] | {"latitude": lat, "longitude": lon}
    versao_formulario = vigente
    erro = None
    status = 200
    if request.method == "POST":
        valores = request.form
        versao_formulario = request.form.get("versao", "")
        try:
            if not versao_formulario.isascii() or not versao_formulario.isdecimal() or len(versao_formulario) > 18:
                raise camadas.CatalogoErro("Versão do formulário inválida. Abra o cadastro novamente.")
            nova = equipamentos.salvar(bh.db_target(), _base_dir(), geo.BASES, valores, bh.usuario_atual()["id_usuario"],
                                       int(versao_formulario) if versao is None else versao, indice)
            flash(f"Equipamento salvo e publicado na versão {nova} da camada.", "ok")
            return redirect(url_for("geovsatt.admin_equipamentos"), code=303)
        except equipamentos.VersaoAlterada as exc:
            erro, status = str(exc), 409
        except camadas.CatalogoErro as exc:
            erro, status = str(exc), 400
    return render_template("geovsatt_equipamentos.html", formulario=True, campos=equipamentos.CAMPOS,
                           tipos=equipamentos.TIPOS, valores=valores, indice=indice, versao=versao_formulario, erro=erro), status


@bp.get("/geovsatt/admin/atualizar")
@login_required
@superadmin
def admin_atualizar():
    return render_template("geovsatt_camadas.html", modo="atualizar",
                           camadas=camadas.listar(bh.db_target(), geo.BASES))


@bp.route("/geovsatt/admin/importar", methods=["GET", "POST"])
@login_required
@superadmin
def admin_importar_nova():
    if request.method == "GET":
        return render_template("geovsatt_camadas.html", modo="nova")
    codigo = request.form.get("codigo", "").strip()
    try:
        arquivo = _arquivo_geojson()
        versao = camadas.importar_nova(bh.db_target(), codigo, arquivo, request.form, geo.BASES,
                                      bh.usuario_atual()["id_usuario"])
    except camadas.CatalogoErro as exc:
        flash(str(exc), "erro")
        return render_template("geovsatt_camadas.html", modo="nova", campos=request.form), 400
    flash(f"Camada criada e versão {versao} importada como rascunho.", "ok")
    return _voltar(codigo, "versoes")


@bp.route("/geovsatt/admin/ortofotos/importar", methods=["GET", "POST"])
@bp.route("/geovsatt/admin/ortofotos/<codigo>/importar", methods=["GET", "POST"])
@login_required
@superadmin
def admin_importar_ortofoto(codigo=None):
    camada = None
    if codigo is not None:
        try:
            camada = _obter(codigo)
        except camadas.CamadaAusente:
            abort(404)
        if camada["origem"] != "ortofoto":
            abort(404)
    limite = current_app.config["MAX_CONTENT_LENGTH"] - 256 * 1024
    status = 200
    if request.method == "POST":
        codigo = codigo or request.form.get("codigo", "").strip()
        try:
            arquivo = request.files.get("mbtiles")
            if not arquivo:
                raise camadas.CatalogoErro("Selecione o arquivo MBTiles.")
            reservados = {item["id"] for item in geo.CAMADAS} | set(geo.FONTES_TERRITORIAIS.values()) | {"limite-municipal"}
            versao = ortofotos.importar(bh.db_target(), current_app.config["ANEXOS_DIR"], codigo, arquivo,
                                       request.form, reservados, bh.usuario_atual()["id_usuario"], limite,
                                       nova=camada is None)
            flash(f"Ortofoto importada como rascunho na versão {versao}.", "ok")
            return _voltar(codigo, "versoes")
        except camadas.CatalogoErro as exc:
            flash(str(exc), "erro")
            status = 400
        except OSError:
            current_app.logger.exception("Falha no armazenamento de uma ortofoto.")
            flash("O arquivo de ortofoto não pôde ser armazenado.", "erro")
            status = 503
    return render_template("geovsatt_camadas.html", camada=camada,
                           modo="orto_arquivo" if camada else "orto_nova",
                           campos=request.form, limite_mib=limite // (1024 * 1024)), status


def _arquivo_geojson():
    arquivo = request.files.get("geojson")
    if not arquivo:
        raise camadas.CatalogoErro("Selecione um arquivo GeoJSON.")
    return arquivo


@bp.post("/geovsatt/admin/camadas")
@login_required
@superadmin
def admin_criar():
    codigo = request.form.get("codigo", "").strip()
    try:
        camadas.salvar_camada(bh.db_target(), codigo, request.form, geo.BASES, nova=True)
    except camadas.CatalogoErro as exc:
        flash(str(exc), "erro")
        return redirect(url_for("geovsatt.admin_catalogo"), code=303)
    flash("Camada criada. Importe um GeoJSON para preparar a primeira versão.", "ok")
    return redirect(url_for("geovsatt.admin_importar", codigo=codigo), code=303)


def _voltar(codigo, ancora=None):
    return redirect(url_for("geovsatt.admin_camada", codigo=codigo, _anchor=ancora), code=303)


@bp.route("/geovsatt/admin/camadas/<codigo>", methods=["GET", "POST"])
@login_required
@superadmin
def admin_camada(codigo):
    target = bh.db_target()
    try:
        camada = _obter(codigo)
    except camadas.CamadaAusente:
        abort(404)
    if request.method == "POST":
        try:
            camadas.salvar_camada(target, codigo, request.form, geo.BASES)
            flash("Configuração salva.", "ok")
        except camadas.CatalogoErro as exc:
            flash(str(exc), "erro")
        return _voltar(codigo)
    contas = bh.q("SELECT id_usuario,nome,usuario,ativo FROM usuarios WHERE nivel <> 'superadmin' ORDER BY nome")
    camada_mapa = next((id_mapa for id_mapa, fonte in geo.FONTES_TERRITORIAIS.items() if fonte == codigo), None)
    return render_template("geovsatt_camadas.html", camada=camada, contas=contas,
                           camada_mapa=camada_mapa, fonte_territorial=geo.FONTES_TERRITORIAIS.get(codigo),
                           acesso_localizacao_exata=codigo in geo.BLOQUEIOS_ESPOROTRICOSE,
                           niveis=camadas.NIVEIS, setores=camadas.SETORES,
                           versoes=camadas.listar_versoes(target, codigo))


@bp.route("/geovsatt/admin/camadas/<codigo>/importar", methods=["GET", "POST"])
@login_required
@superadmin
def admin_importar(codigo):
    if codigo in geo.BASES:
        abort(404)
    try:
        camada = _obter(codigo)
    except camadas.CamadaAusente:
        abort(404)
    if camada["origem"] == "ortofoto":
        abort(404)
    if request.method == "GET":
        return render_template("geovsatt_camadas.html", camada=camada, modo="arquivo")
    try:
        arquivo = _arquivo_geojson()
        versao = camadas.importar(bh.db_target(), codigo, arquivo, request.form, bh.usuario_atual()["id_usuario"])
        flash(f"Versão {versao} importada como rascunho.", "ok")
        return _voltar(codigo, "versoes")
    except camadas.CatalogoErro as exc:
        flash(str(exc), "erro")
        return render_template("geovsatt_camadas.html", camada=camada, modo="arquivo", campos=request.form), 400


@bp.get("/geovsatt/admin/camadas/<codigo>/versoes/<int:versao>/geojson")
@login_required
@superadmin
def admin_geojson(codigo, versao):
    try:
        item = camadas.obter_versao(bh.db_target(), codigo, versao)
    except camadas.CamadaAusente:
        abort(404)
    if item["tipo"] == "raster":
        abort(404)
    return current_app.response_class(item["geojson"], mimetype="application/geo+json",
                                      headers={"Content-Disposition": f'attachment; filename="versao-{versao}.geojson"'})


@bp.get("/geovsatt/admin/ortofotos/<codigo>/versoes/<int:versao>/<acao>")
@login_required
@superadmin
def admin_arquivo_ortofoto(codigo, versao, acao):
    if acao not in {"amostra", "mbtiles"}:
        abort(404)
    try:
        item = camadas.obter_versao(bh.db_target(), codigo, versao)
        if item["tipo"] != "raster":
            abort(404)
        if acao == "mbtiles":
            path = _arquivo_ortofoto(item)
            audit.registrar_evento(bh.get_db, "geovsatt_camada_exportada", entidade="geovsatt_camada", entidade_id=codigo,
                                   detalhes={"formato": "mbtiles", "total": item["total"], "versao": versao})
            return _enviar_ortofoto(path, codigo, versao)
    except camadas.CamadaAusente:
        abort(404)
    return _responder_mosaico(item, *item["metadados"]["mbtiles"]["amostra"])


@bp.post("/geovsatt/admin/camadas/<codigo>/versoes/<int:versao>/metadados")
@login_required
@superadmin
def admin_metadados(codigo, versao):
    try:
        camadas.editar_metadados(bh.db_target(), codigo, versao, request.form)
        flash("Metadados salvos.", "ok")
    except camadas.CatalogoErro as exc:
        flash(str(exc), "erro")
    return _voltar(codigo)


@bp.post("/geovsatt/admin/camadas/<codigo>/versoes/<int:versao>/publicar")
@login_required
@superadmin
def admin_publicar(codigo, versao):
    try:
        camada = _obter(codigo)
        if camada["origem"] == "ortofoto":
            _arquivo_ortofoto(camadas.obter_versao(bh.db_target(), codigo, versao))
        camadas.publicar(bh.db_target(), codigo, versao)
        flash(f"Versão {versao} publicada no mapa.", "ok")
    except camadas.CatalogoErro as exc:
        flash(str(exc), "erro")
    return _voltar(codigo)
