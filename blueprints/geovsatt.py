from io import BytesIO
import json
import sqlite3

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for

from app_core import audit
from app_core import blueprint_helpers as bh
from app_core import geovsatt as geo
from app_core import geovsatt_busca as busca
from app_core import geovsatt_catalogo as camadas
from app_core import geovsatt_composicoes as composicoes
from app_core import geovsatt_equipamentos as equipamentos
from app_core import geovsatt_exportacao as exportacao
from app_core import geovsatt_ortofotos as ortofotos
from app_core import setores
from app_core.auth import login_required


bp = Blueprint("geovsatt", __name__)
superadmin = bh.nivel_min("superadmin")


@bp.before_request
def setor_do_mapa():
    if setores.atual() != "geo":
        abort(403)


@bp.after_request
def cache_privado(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _base_dir():
    return current_app.config["BASE_DIR"]


def _obter(codigo, **kwargs):
    return camadas.obter(bh.db_target(), codigo, geo.BASES, **kwargs)


@bp.get("/geovsatt")
@login_required
def page():
    usuario = bh.usuario_atual()
    catalogo = geo.catalogo(bh.db_target(), usuario)
    pode_rg = setores.pode_entrar(usuario, "endemias")
    pode_estimar = pode_rg and any(item["id"] == "quarteiroes" for item in catalogo["camadas"])
    ambiental = setores.url_setor(usuario, "ambiental") if geo.esporotricose_localizacao_exata(usuario) else None
    return render_template("geovsatt.html", catalogo=catalogo, pode_rg=pode_rg, pode_estimar=pode_estimar,
                           esri_licenciado=current_app.config["GEOVSATT_ESRI_LICENSED"], ambiental=ambiental)


@bp.get("/api/geovsatt/catalogo")
@login_required
def api_catalogo():
    return jsonify(geo.catalogo(bh.db_target(), bh.usuario_atual()))


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
    bases = {"none", "openfreemap", "sentinel"}
    bases.update(orto["base"] for orto in catalogo["ortofotos"])
    if current_app.config["GEOVSATT_ESRI_LICENSED"]:
        bases.add("esri")
    try:
        if request.method == "GET":
            return jsonify(composicoes.obter(target, uid, identificador, permitidas, bases))
        request.max_content_length = 131_072
        resposta = composicoes.salvar(target, uid, request.get_json(silent=True), permitidas, bases, identificador)
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
        if camada["origem"] == "importacao":
            if codigo == equipamentos.CODIGO:
                dados = equipamentos.geojson(camada, _base_dir())
                dados["metadata"] = {"versao": camada["id_versao"]}
                return current_app.response_class(json.dumps(dados, ensure_ascii=False), mimetype="application/geo+json")
            return current_app.response_class(camada["geojson"], mimetype="application/geo+json")
        return jsonify(geo.dados_nativos(target, _base_dir(), codigo, usuario, parametros=request.args))
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
    return render_template("geovsatt_camadas.html", camadas=camadas.listar(bh.db_target(), geo.BASES))


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
