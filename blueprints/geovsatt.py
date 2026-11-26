from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for

from app_core import blueprint_helpers as bh
from app_core import geovsatt as geo
from app_core import geovsatt_busca as busca
from app_core import geovsatt_catalogo as camadas
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
    return render_template("geovsatt.html", catalogo=geo.catalogo(bh.db_target(), usuario),
                           pode_rg=setores.pode_entrar(usuario, "endemias"))


@bp.get("/api/geovsatt/catalogo")
@login_required
def api_catalogo():
    return jsonify(geo.catalogo(bh.db_target(), bh.usuario_atual()))


@bp.get("/api/geovsatt/camadas/<codigo>")
@login_required
def api_camada(codigo):
    usuario = bh.usuario_atual()
    target = bh.db_target()
    try:
        camada = _obter(codigo, incluir_dados=True)
        if not camada["disponivel"] or not camadas.pode_ver(camada, usuario):
            raise camadas.CamadaAusente("Camada não encontrada.")
        if camada["origem"] == "importacao":
            return current_app.response_class(camada["geojson"], mimetype="application/geo+json")
        if codigo == "localidades":
            return jsonify(geo.localidades(target, _base_dir()))
        if codigo == "quarteiroes":
            return jsonify(geo.quarteiroes(target, _base_dir(), incluir_rg=setores.pode_entrar(usuario, "endemias")))
        return jsonify(geo.logradouros(_base_dir()))
    except camadas.CamadaAusente as exc:
        return jsonify({"erro": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/api/geovsatt/busca", methods=["GET", "POST"])
@login_required
def api_busca():
    usuario = bh.usuario_atual()
    permitidas = {codigo for codigo in ("localidades", "quarteiroes") if camadas.pode_ver(_obter(codigo), usuario)}
    try:
        if request.method == "POST":
            payload = request.get_json(silent=True)
            termo = payload.get("q") if isinstance(payload, dict) else None
            if not isinstance(termo, str):
                raise ValueError("Informe um texto de busca.")
        else:
            termo = request.args.get("q")
        resultados = geo.buscar(bh.db_target(), _base_dir(), termo, permitidas,
                               incluir_rg=setores.pode_entrar(usuario, "endemias"))
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


@bp.get("/geovsatt/admin/camadas")
@login_required
@superadmin
def admin_catalogo():
    return render_template("geovsatt_camadas.html", camadas=camadas.listar(bh.db_target(), geo.BASES))


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
    return _voltar(codigo, "importar-versao")


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
    return render_template("geovsatt_camadas.html", camada=camada, contas=contas,
                           niveis=camadas.NIVEIS, setores=camadas.SETORES,
                           versoes=camadas.listar_versoes(target, codigo))


@bp.post("/geovsatt/admin/camadas/<codigo>/importar")
@login_required
@superadmin
def admin_importar(codigo):
    if codigo in geo.BASES:
        abort(404)
    try:
        arquivo = request.files.get("geojson")
        if not arquivo:
            raise camadas.CatalogoErro("Selecione um arquivo GeoJSON.")
        versao = camadas.importar(bh.db_target(), codigo, arquivo, request.form, bh.usuario_atual()["id_usuario"])
        flash(f"Versão {versao} importada como rascunho.", "ok")
        return _voltar(codigo, "versoes")
    except camadas.CatalogoErro as exc:
        flash(str(exc), "erro")
    return _voltar(codigo, "importar-versao")


@bp.get("/geovsatt/admin/camadas/<codigo>/versoes/<int:versao>/geojson")
@login_required
@superadmin
def admin_geojson(codigo, versao):
    try:
        item = camadas.obter_versao(bh.db_target(), codigo, versao)
    except camadas.CamadaAusente:
        abort(404)
    return current_app.response_class(item["geojson"], mimetype="application/geo+json",
                                      headers={"Content-Disposition": f'attachment; filename="versao-{versao}.geojson"'})


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
        camadas.publicar(bh.db_target(), codigo, versao)
        flash(f"Versão {versao} publicada no mapa.", "ok")
    except camadas.CatalogoErro as exc:
        flash(str(exc), "erro")
    return _voltar(codigo)
