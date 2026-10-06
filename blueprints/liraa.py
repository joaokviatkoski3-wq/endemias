"""Planejamento de ciclos, estratos e sorteios do LIRAa."""

import logging
from datetime import date, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import db as db_core
from app_core import liraa as liraa_core
from app_core import liraa_kobo, kobo_api
from app_core import agentes as agentes_core
from app_core import visitas as visitas_core


bp = Blueprint("liraa", __name__)
login_required = auth_core.login_required


def _target():
    return bh.db_target()


def _base_dir():
    return current_app.config.get("BASE_DIR")


def _get_db():
    return db_core.connect(_target())


def _q1(sql, params=()):
    return db_core.query_one(_target(), sql, params)


def _usuario():
    return auth_core.usuario_atual(_q1)


nivel_admin = auth_core.nivel_min("admin", _usuario)


def _kobo_config_path():
    return current_app.config.get("KOBO_CONFIG_PATH")


@bp.route("/liraa")
@login_required
def page():
    dados, erro = None, None
    try:
        dados = liraa_core.painel(_target(), _base_dir())
    except Exception:
        logging.exception("Falha ao carregar planejamento LIRAa")
        erro = "Planejamento indisponível. Confirme as migrações 0023/0024 e a camada de quarteirões ativa."
    editando = None
    try:
        id_edicao = int(request.args.get("editar", "0"))
    except ValueError:
        id_edicao = 0
    if dados and id_edicao:
        editando = next((e for c in dados["ciclos"] for e in c["estratos"]
                         if e["id_estrato"] == id_edicao and not e["sorteio"]), None)
    admin = (_usuario() or {}).get("nivel") == "admin"
    kobo_dados = {"uid": "", "visitas": [], "previa": None, "erro": None,
                  "ciclo": request.values.get("ciclo", ""),
                  "inicio": request.values.get("inicio", (date.today() - timedelta(days=6)).isoformat()),
                  "fim": request.values.get("fim", date.today().isoformat()),
                  "visita_inicio": request.args.get("visita_inicio", ""),
                  "visita_fim": request.args.get("visita_fim", ""),
                  "visita_busca": request.args.get("visita_busca", "")}
    if admin:
        if _kobo_config_path():
            kobo_dados["uid"] = (kobo_api.load_config(_kobo_config_path())
                                .get("assets") or {}).get("LIRAA", "")
        try:
            kobo_dados["pagina"] = max(1, int(request.args.get("pagina", "1")))
            rows = liraa_kobo.listar(_target(), kobo_dados["ciclo"] or None, limite=101,
                                    deslocamento=(kobo_dados["pagina"] - 1) * 100,
                                    inicio=kobo_dados["visita_inicio"], fim=kobo_dados["visita_fim"],
                                    busca=kobo_dados["visita_busca"])
            kobo_dados["proxima_pagina"] = len(rows) > 100
            kobo_dados["visitas"] = rows[:100]
            conn = _get_db()
            try:
                catalogo_acs = visitas_core.catalogo_acs(conn)
            finally:
                conn.close()
            for visita in kobo_dados["visitas"]:
                visita["agentes_nomes"] = ", ".join(
                    agentes_core.normalizar_nome(code) for code in visita["agentes_codigos"].split()
                ) or "—"
                acs_codes = [code for code in visita["acs_codigos"].split() if code != "no-acs"]
                visita["acs_nomes"] = visitas_core.formatar_acs_codigos(
                    ",".join(acs_codes), catalogo_acs) if acs_codes else "Nenhum"
        except (ValueError, liraa_kobo.LiraaKoboError) as exc:
            kobo_dados["erro"] = str(exc)
        if dados and request.args.get("consulta_kobo") == "1":
            try:
                id_ciclo = int(kobo_dados["ciclo"])
                registros = _buscar_kobo(kobo_dados["inicio"], kobo_dados["fim"])
                kobo_dados["previa"] = liraa_kobo.previa(_target(), id_ciclo, registros)
            except (ValueError, liraa_kobo.LiraaKoboError, kobo_api.KoboError) as exc:
                kobo_dados["erro"] = str(exc)
            except Exception:
                logging.exception("Falha na prévia Kobo LIRAa")
                kobo_dados["erro"] = "Não foi possível consultar os envios LIRAa."
    return render_template("liraa.html", dados=dados, erro=erro,
                           editando=editando, is_admin=admin, liraa_kobo=kobo_dados)


def _buscar_kobo(inicio, fim):
    try:
        first, last = date.fromisoformat(inicio), date.fromisoformat(fim)
    except (TypeError, ValueError):
        raise liraa_kobo.LiraaKoboError("Informe datas válidas para a consulta Kobo.") from None
    if last < first or (last - first).days > 90:
        raise liraa_kobo.LiraaKoboError("O período deve ter no máximo 91 dias.")
    if not _kobo_config_path():
        raise liraa_kobo.LiraaKoboError("Configuração Kobo indisponível neste ambiente.")
    cfg = kobo_api.load_config(_kobo_config_path())
    uid = str((cfg.get("assets") or {}).get("LIRAA") or "").strip()
    if not uid:
        raise liraa_kobo.LiraaKoboError("Configure o UID do formulário LIRAa nesta aba.")
    records, response = kobo_api.fetch_submissions(cfg, uid, limit=5000,
                                                    start=inicio, end=fim)
    if not isinstance(response, dict) or "count" not in response or response.get("next"):
        raise liraa_kobo.LiraaKoboError("Kobo não confirmou que a resposta está completa; reduza o período.")
    try:
        count = int(response["count"])
    except (ValueError, TypeError):
        raise liraa_kobo.LiraaKoboError("Total de envios Kobo inválido.") from None
    if count != len(records):
        raise liraa_kobo.LiraaKoboError(f"Kobo retornou {len(records)} de {count} envios; reduza o período.")
    return records


@bp.route("/liraa/kobo/configurar", methods=["POST"])
@login_required
@nivel_admin
def configurar_kobo():
    if not _kobo_config_path():
        flash("Configuração Kobo indisponível neste ambiente.", "error")
        return redirect(url_for("liraa.page") + "#liraa-tab-visitas")
    uid = str(request.form.get("uid") or "").strip()
    if uid and (len(uid) > 100 or not uid.isalnum()):
        flash("UID Kobo inválido.", "error")
        return redirect(url_for("liraa.page") + "#liraa-tab-visitas")
    kobo_api.save_config(_kobo_config_path(),
                         {"assets": {"LIRAA": uid}}, keep_token=True)
    audit.registrar_evento(_get_db, "liraa_kobo_configurado", entidade="liraa_kobo",
                           detalhes={"uid": uid})
    flash("Formulário LIRAa configurado.", "success")
    return redirect(url_for("liraa.page") + "#liraa-tab-visitas")


@bp.route("/liraa/kobo/importar", methods=["POST"])
@login_required
@nivel_admin
def importar_kobo():
    try:
        id_ciclo = int(request.form.get("ciclo") or 0)
        inicio, fim = request.form.get("inicio"), request.form.get("fim")
        records = _buscar_kobo(inicio, fim)
        novos = liraa_kobo.importar(_target(), id_ciclo, records, auditar=lambda conn, detalhes:
            audit.registrar_evento(_get_db, "liraa_visitas_importadas", entidade="liraa_ciclo",
                                   entidade_id=id_ciclo, detalhes=detalhes, conn=conn))
        flash(f"Importação LIRAa concluída: {novos} visita(s) nova(s).", "success")
    except (ValueError, liraa_kobo.LiraaKoboError, kobo_api.KoboError) as exc:
        flash(str(exc), "error")
    except Exception:
        logging.exception("Falha ao importar diário Kobo LIRAa")
        flash("Não foi possível importar as visitas LIRAa; nenhuma visita do lote foi gravada.", "error")
    return redirect(url_for("liraa.page", ciclo=request.form.get("ciclo") or "") + "#liraa-tab-visitas")


@bp.route("/liraa/visitas/<int:id_visita>/excluir", methods=["POST"])
@login_required
@nivel_admin
def excluir_visita(id_visita):
    if request.form.get("confirmar_exclusao") != "sim":
        flash("Confirme a exclusão da visita LIRAa.", "error")
        return redirect(url_for("liraa.page") + "#liraa-tab-visitas")
    try:
        ciclo = liraa_kobo.excluir(_target(), id_visita, request.form.get("motivo") or "",
            auditar=lambda conn, detalhes: audit.registrar_evento(
                _get_db, "liraa_visita_excluida", entidade="liraa_visita",
                entidade_id=id_visita, detalhes=detalhes, conn=conn))
        flash("Visita e tubitos removidos do Endemias. O envio permanece no Kobo e não será reimportado.", "success")
        return redirect(url_for("liraa.page", ciclo=ciclo) + "#liraa-tab-visitas")
    except liraa_kobo.LiraaKoboError as exc:
        flash(str(exc), "error")
    except Exception:
        logging.exception("Falha ao excluir visita LIRAa")
        flash("Não foi possível excluir a visita LIRAa.", "error")
    return redirect(url_for("liraa.page") + "#liraa-tab-visitas")


def _resposta(acao, func, entidade, detalhes, auditoria_embutida=False):
    try:
        identificador = func()
        if not auditoria_embutida:
            audit.registrar_evento(_get_db, acao, entidade=entidade,
                                   entidade_id=identificador, detalhes=detalhes)
        flash("Alteração salva com sucesso.", "success")
    except liraa_core.LiraaError as exc:
        flash(str(exc), "error")
    except Exception:
        logging.exception("Falha na operação LIRAa: %s", acao)
        flash("Não foi possível concluir a operação. Confirme a migração e tente novamente.", "error")
    return redirect(url_for("liraa.page"))


@bp.route("/liraa/ciclos", methods=["POST"])
@login_required
@nivel_admin
def criar_ciclo():
    payload = request.form.to_dict()
    return _resposta("liraa_ciclo_criado", lambda: liraa_core.criar_ciclo(_target(), payload),
                     "liraa_ciclo", {k: payload.get(k) for k in ("ano", "nome", "inicio", "fim")})


@bp.route("/liraa/ciclos/<int:id_ciclo>/editar", methods=["POST"])
@login_required
@nivel_admin
def atualizar_ciclo(id_ciclo):
    payload = request.form.to_dict()
    return _resposta("liraa_ciclo_atualizado", lambda: liraa_core.atualizar_ciclo(
        _target(), id_ciclo, payload), "liraa_ciclo",
        {k: payload.get(k) for k in ("ano", "nome", "inicio", "fim")})


@bp.route("/liraa/ciclos/<int:id_ciclo>/excluir", methods=["POST"])
@login_required
@nivel_admin
def excluir_ciclo(id_ciclo):
    if request.form.get("confirmar_exclusao") != "sim":
        flash("Confirme a exclusão do ciclo antes de continuar.", "error")
        return redirect(url_for("liraa.page"))
    def excluir():
        liraa_core.excluir_ciclo(_target(), id_ciclo, auditar=lambda conn, detalhes:
            audit.registrar_evento(_get_db, "liraa_ciclo_excluido", entidade="liraa_ciclo",
                                   entidade_id=id_ciclo, detalhes=detalhes, conn=conn))
        return id_ciclo
    return _resposta("liraa_ciclo_excluido", excluir, "liraa_ciclo", {}, auditoria_embutida=True)


@bp.route("/liraa/ciclos/<int:id_ciclo>/estratos", methods=["POST"])
@login_required
@nivel_admin
def salvar_estrato(id_ciclo):
    payload = request.form.to_dict()
    payload["localidades"] = request.form.getlist("localidades")
    if "quarteiroes" in request.form:
        payload["quarteiroes"] = request.form.getlist("quarteiroes")
    id_estrato = request.form.get("id_estrato") or None
    return _resposta("liraa_estrato_salvo", lambda: liraa_core.salvar_estrato(
        _target(), id_ciclo, payload, id_estrato, _base_dir()), "liraa_estrato",
        {k: payload.get(k) for k in ("numero", "tipo", "imoveis_confirmados", "localidades", "quarteiroes")})


@bp.route("/liraa/estratos/<int:id_estrato>/sortear", methods=["POST"])
@login_required
@nivel_admin
def sortear(id_estrato):
    return _resposta("liraa_estrato_sorteado", lambda: liraa_core.sortear(
        _target(), id_estrato, _base_dir())["id_sorteio"], "liraa_sorteio",
        {"id_estrato": id_estrato})


@bp.route("/liraa/estratos/<int:id_estrato>/excluir", methods=["POST"])
@login_required
@nivel_admin
def excluir_estrato(id_estrato):
    if request.form.get("confirmar_exclusao") != "sim":
        flash("Confirme a exclusão do estrato antes de continuar.", "error")
        return redirect(url_for("liraa.page"))
    def excluir():
        liraa_core.excluir_estrato(_target(), id_estrato, auditar=lambda conn, detalhes:
            audit.registrar_evento(_get_db, "liraa_estrato_excluido", entidade="liraa_estrato",
                                   entidade_id=id_estrato, detalhes=detalhes, conn=conn))
        return id_estrato
    return _resposta("liraa_estrato_excluido", excluir, "liraa_estrato", {}, auditoria_embutida=True)
