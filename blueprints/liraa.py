"""Planejamento de ciclos, estratos e sorteios do LIRAa."""

import logging
import csv
from functools import wraps
from io import BytesIO, StringIO
from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for, jsonify, send_file

from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import db as db_core
from app_core import liraa as liraa_core
from app_core import liraa_kobo, kobo_api
from app_core import liraa_acompanhamento, liraa_resumo
from app_core import agentes as agentes_core
from app_core import visitas as visitas_core
from app_core import liraa_operacional as op, liraa_xlsform, liraa_relatorios, liraa_boletim, liraa_laboratorio
from blueprints.laboratorio_lancamentos import laboratorio_required


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
nivel_superadmin = auth_core.nivel_min("superadmin", _usuario)


def _catalogo_ciclos():
    conn = _get_db()
    try:
        liraa_core._schema(conn)
        encerrados = liraa_core.ciclos_encerrados(conn)
        rows = conn.execute("SELECT id_ciclo, ano, nome, inicio, fim FROM liraa_ciclos ORDER BY ano DESC,id_ciclo DESC")
        return [dict(db_core.serialize_row(row), encerrado=row["id_ciclo"] in encerrados) for row in rows]
    finally:
        conn.close()


def _encerrado(id_ciclo):
    conn = _get_db()
    try:
        return id_ciclo in liraa_core.ciclos_encerrados(conn)
    finally:
        conn.close()


def _acesso_operacional(view):
    @wraps(view)
    def wrapped(id_ciclo, *args, **kwargs):
        if (_usuario() or {}).get("nivel") != "superadmin" and _encerrado(id_ciclo):
            abort(403)
        return view(id_ciclo, *args, **kwargs)
    return wrapped


def _kobo_config_path():
    return current_app.config.get("KOBO_CONFIG_PATH")


@bp.route("/liraa")
@login_required
def page():
    nivel = (_usuario() or {}).get("nivel")
    superadmin = nivel == "superadmin"
    hoje = date.today().isoformat()
    try:
        catalogo = _catalogo_ciclos()
    except Exception:
        logging.exception("Falha ao consultar os ciclos LIRAa")
        return render_template("liraa.html", dados=None, erro="Não foi possível consultar os ciclos do LIRAa."), 503
    selecionado = request.args.get("ciclo")
    preferido = next((c for c in catalogo if str(c["id_ciclo"]) == selecionado), None)
    if selecionado and preferido is None:
        abort(404)
    if preferido is None:
        preferido = next((c for c in catalogo if not c["encerrado"] and c["inicio"]
                         and c["inicio"] <= hoje and (not c["fim"] or hoje <= c["fim"])),
                         catalogo[0] if catalogo else None)
    id_preferido = preferido["id_ciclo"] if preferido else None
    encerrado = bool(preferido and preferido["encerrado"])
    resumo = None
    resumo_erro = None
    if id_preferido:
        try:
            resumo = liraa_resumo.resumir(_target(), id_preferido)
            encerrado = bool(resumo.get("encerramento"))
        except Exception:
            logging.exception("Falha ao consultar resumo LIRAa")
            resumo_erro = "Não foi possível consultar o resumo deste ciclo."
    contexto_resumo = dict(resumo=resumo, resumo_erro=resumo_erro, catalogo_ciclos=catalogo,
                           ciclo_selecionado=id_preferido, encerrado=encerrado,
                           superadmin=superadmin, avisos_resumo=liraa_resumo.AVISOS,
                           colunas_entrada=liraa_resumo.COLUNAS_ENTRADA, colunas_indices=liraa_resumo.COLUNAS_INDICES,
                           grupos_entrada=liraa_resumo.GRUPOS_ENTRADA, celula_resumo=liraa_resumo.celula)
    if encerrado and not superadmin:
        return render_template("liraa.html", dados=None, erro=None, **contexto_resumo)
    dados, erro = None, None
    try:
        dados = liraa_core.painel(_target(), _base_dir())
    except Exception:
        logging.exception("Falha ao carregar planejamento LIRAa")
        erro = "Planejamento indisponível. Confirme as migrações 0023/0024 e a camada de quarteirões ativa."
    if dados and not superadmin:
        dados["ciclos"] = [c for c in dados["ciclos"] if not c["encerrado"]]
    editando = None
    try:
        id_edicao = int(request.args.get("editar", "0"))
    except ValueError:
        id_edicao = 0
    if dados and id_edicao and not encerrado:
        editando = next((e for c in dados["ciclos"] for e in c["estratos"]
                         if e["id_estrato"] == id_edicao and not e["sorteio"] and not c["encerrado"]), None)
    admin = nivel in {"admin", "superadmin"}
    kobo_dados = {"uid": "", "visitas": [], "previa": None, "erro": None,
                  "correcao_habilitada": not encerrado, "exclusoes": [],
                  "ciclo": id_preferido or "",
                  "inicio": request.values.get("inicio", (date.today() - timedelta(days=6)).isoformat()),
                  "fim": request.values.get("fim", date.today().isoformat()),
                  "visita_inicio": request.args.get("visita_inicio", ""),
                  "visita_fim": request.args.get("visita_fim", ""),
                  "visita_busca": request.args.get("visita_busca", "")}
    if admin:
        if _kobo_config_path():
            kobo_dados["uid"] = (kobo_api.load_config(_kobo_config_path())
                                .get("assets") or {}).get("LIRAA", "")
        kobo_dados["uid_ativo"] = kobo_dados["uid"]
        if dados:
            selected_cycle = next((c for c in dados['ciclos'] if str(c['id_ciclo']) == str(kobo_dados['ciclo'])), None)
            if selected_cycle and selected_cycle['config']['kobo_uid']:
                kobo_dados["uid_ativo"] = selected_cycle['config']['kobo_uid']
        try:
            kobo_dados["pagina"] = max(1, int(request.args.get("pagina", "1")))
            rows = liraa_kobo.listar(_target(), kobo_dados["ciclo"] or None, limite=101,
                                    deslocamento=(kobo_dados["pagina"] - 1) * 100,
                                    inicio=kobo_dados["visita_inicio"], fim=kobo_dados["visita_fim"],
                                    busca=kobo_dados["visita_busca"])
            kobo_dados["proxima_pagina"] = len(rows) > 100
            kobo_dados["visitas"] = rows[:100]
            kobo_dados["exclusoes"] = liraa_kobo.exclusoes(_target(), kobo_dados["ciclo"] or None)
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
                if visita.get("acs_outros"):
                    visita["acs_nomes"] += " · Outros: " + visita["acs_outros"]
        except (ValueError, liraa_kobo.LiraaKoboError) as exc:
            kobo_dados["erro"] = str(exc)
        if dados and not encerrado and request.args.get("consulta_kobo") == "1":
            try:
                id_ciclo = int(kobo_dados["ciclo"])
                registros = _buscar_kobo(kobo_dados["inicio"], kobo_dados["fim"], id_ciclo)
                kobo_dados["previa"] = liraa_kobo.previa(_target(), id_ciclo, registros)
            except (ValueError, liraa_kobo.LiraaKoboError, kobo_api.KoboError) as exc:
                kobo_dados["erro"] = str(exc)
            except Exception:
                logging.exception("Falha na prévia Kobo LIRAa")
                kobo_dados["erro"] = "Não foi possível consultar os envios LIRAa."
    operacao = {"plano": None, "boletim": None, "acs": [], "erro": None}
    if dados and dados["ciclos"]:
        try:
            ciclo = id_preferido
            operacao["plano"] = op.plano(_target(), ciclo, _base_dir(), request.args.get("estrato"), request.args.get("localidade"))
            if admin:
                operacao["acs"] = op.catalogo_acs(_target())
                operacao["boletim"] = liraa_boletim.resumir(_target(), ciclo, _base_dir(),
                    request.args.get("agrupar", "estrato"), request.args.get("estrato"), request.args.get("localidade"))
            for c in dados["ciclos"]:
                for e in c["estratos"]:
                    e["historico_sorteios"] = op.historico_sorteios(_target(), e["id_estrato"])
        except (ValueError, liraa_core.LiraaError) as exc:
            operacao["erro"] = str(exc)
        except Exception:
            logging.exception("Falha ao carregar operação LIRAa")
            operacao["erro"] = "Não foi possível carregar a operação do ciclo. Confira a migração 0026."
    return render_template("liraa.html", dados=dados, erro=erro,
                           editando=editando, is_admin=admin, liraa_kobo=kobo_dados, operacao=operacao,
                           acompanhamento_hoje=hoje, acompanhamento_ciclo=preferido,
                           acompanhamento_turnos=liraa_acompanhamento.TURNOS, **contexto_resumo)


@bp.get("/liraa/acompanhamento")
@login_required
def acompanhamento():
    try:
        ciclo = int(request.args.get("ciclo", ""))
        if (_usuario() or {}).get("nivel") != "superadmin" and _encerrado(ciclo):
            return render_template("liraa_acompanhamento.html", erro="Ciclo encerrado. Consulte o resumo."), 403
        resumo = liraa_acompanhamento.resumir(
            _target(), ciclo, request.args.get("dia") or date.today().isoformat(),
            request.args.get("turno", "dia"),
        )
    except (ValueError, liraa_core.LiraaError) as exc:
        return render_template("liraa_acompanhamento.html", erro=str(exc)), 400
    except Exception:
        logging.exception("Falha ao consultar acompanhamento LIRAa")
        return render_template(
            "liraa_acompanhamento.html", erro="O acompanhamento está indisponível no momento."
        ), 500
    return render_template("liraa_acompanhamento.html", resumo=resumo), 200, {"Cache-Control": "no-store"}


@bp.post("/liraa/ciclos/<int:id_ciclo>/encerrar")
@login_required
@nivel_superadmin
def encerrar(id_ciclo):
    return _alterar_encerramento(id_ciclo, liraa_resumo.encerrar, "encerrado", "observacoes")


@bp.post("/liraa/ciclos/<int:id_ciclo>/reabrir")
@login_required
@nivel_superadmin
def reabrir(id_ciclo):
    return _alterar_encerramento(id_ciclo, liraa_resumo.reabrir, "reaberto", "motivo")


def _alterar_encerramento(id_ciclo, operacao, estado, campo):
    try:
        operacao(_target(), id_ciclo, _usuario(), request.form.get(campo),
                 auditar=lambda conn, detalhes: audit.registrar_evento(
                     _get_db, f"liraa_ciclo_{estado}", entidade="liraa_ciclo",
                     entidade_id=id_ciclo, detalhes=detalhes, conn=conn))
        flash(f"Ciclo {estado}.", "success")
    except (liraa_core.LiraaError, liraa_kobo.LiraaKoboError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("liraa.page", ciclo=id_ciclo) + "#liraa-tab-resumo")


@bp.get("/liraa/ciclos/<int:id_ciclo>/resumo.csv")
@login_required
def resumo_csv(id_ciclo):
    try:
        dados = liraa_resumo.resumir(_target(), id_ciclo)
    except liraa_kobo.LiraaKoboError:
        abort(404)
    campos = liraa_resumo.COLUNAS_ENTRADA + liraa_resumo.COLUNAS_INDICES[2:]
    saida = StringIO()
    writer = csv.writer(saida, delimiter=";")
    writer.writerow(liraa_resumo.cabecalho_csv())
    for row in [*dados["estratos"], dados["total"]]:
        writer.writerow([row.get("estrato", "Total"), *(liraa_resumo.celula(row, campo) for campo, _ in campos)])
    return send_file(BytesIO(saida.getvalue().encode("utf-8-sig")), mimetype="text/csv",
                     as_attachment=True, download_name=f"LIRAa-{dados['ciclo']['ano']}-ciclo-{id_ciclo}-resumo.csv")


def _buscar_kobo(inicio, fim, id_ciclo=None):
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
    if id_ciclo:
        if _encerrado(id_ciclo):
            raise liraa_kobo.LiraaKoboError("Ciclo encerrado. Reabra-o antes de consultar os envios.")
        conn = _get_db()
        try:
            if db_core.table_exists(conn, "liraa_ciclo_config"):
                row = conn.execute("SELECT kobo_uid FROM liraa_ciclo_config WHERE id_ciclo=?", (id_ciclo,)).fetchone()
                if row and row["kobo_uid"]:
                    uid = row["kobo_uid"]
        finally:
            conn.close()
    if not uid:
        raise liraa_kobo.LiraaKoboError("Configure o UID do formulário LIRAa nesta aba.")
    return kobo_api.fetch_complete_submissions(cfg, uid, start=inicio, end=fim)


@bp.route("/liraa/kobo/configurar", methods=["POST"])
@login_required
@auth_core.nivel_min("superadmin", _usuario)
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
        records = _buscar_kobo(inicio, fim, id_ciclo)
        revisoes = identidades = 0

        def registrar(conn, detalhes):
            nonlocal revisoes, identidades
            revisoes = detalhes["edicoes_para_revisao"]
            identidades = detalhes["pendencias_identidade"]
            audit.registrar_evento(_get_db, "liraa_visitas_importadas", entidade="liraa_ciclo",
                                   entidade_id=id_ciclo, detalhes=detalhes, conn=conn)

        novos = liraa_kobo.importar(_target(), id_ciclo, records, auditar=registrar)
        mensagem = f"Importação LIRAa concluída: {novos} visita(s) nova(s)."
        if revisoes:
            mensagem += f" Edições do Kobo aguardando revisão: {revisoes}."
        if identidades:
            mensagem += f" Envios com identificação pendente: {identidades}."
        flash(mensagem, "success")
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


@bp.route("/liraa/visitas/<int:id_visita>/corrigir", methods=["POST"])
@login_required
@nivel_admin
def corrigir_visita(id_visita):
    ciclo = request.form.get("ciclo", "")
    try:
        ciclo = liraa_kobo.corrigir(_target(), id_visita, request.form,
            auditar=lambda conn, detalhes: audit.registrar_evento(_get_db, "liraa_visita_corrigida",
                entidade="liraa_visita", entidade_id=id_visita, detalhes=detalhes, conn=conn))
        flash("Correção local salva; as leituras foram preservadas. O Kobo não foi alterado.", "success")
    except liraa_kobo.LiraaKoboError as exc:
        flash(str(exc), "error")
    return redirect(url_for("liraa.page", ciclo=ciclo) + "#liraa-tab-visitas")


@bp.route("/liraa/visitas/permitir-reimportacao", methods=["POST"])
@login_required
@nivel_admin
def permitir_reimportacao():
    ciclo = request.form.get("ciclo", "")
    try:
        if request.form.get("confirmar_reimportacao") != "sim":
            raise liraa_kobo.LiraaKoboError("Confirme a liberação da reimportação.")
        ciclo = liraa_kobo.permitir_reimportacao(_target(), request.form.get("uuid"), request.form.get("motivo"),
            auditar=lambda conn, detalhes: audit.registrar_evento(_get_db, "liraa_reimportacao_permitida",
                entidade="liraa_visita", detalhes=detalhes, conn=conn))
        flash("Bloqueio removido. Consulte e importe o envio pelo Kobo; as leituras apagadas não são recuperadas.", "success")
    except liraa_kobo.LiraaKoboError as exc:
        flash(str(exc), "error")
    return redirect(url_for("liraa.page", ciclo=ciclo) + "#liraa-tab-visitas")


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
@nivel_superadmin
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
    repetir = request.form.get("ressortear") == "sim"
    return _resposta("liraa_estrato_sorteado", lambda: liraa_core.sortear(
        _target(), id_estrato, _base_dir(), inicio_casual=request.form.get("inicio_casual"),
        ressortear=repetir, id_sorteio_esperado=request.form.get("id_sorteio_esperado"),
        auditar=lambda conn, detalhes: audit.registrar_evento(_get_db, "liraa_estrato_ressorteado" if repetir else "liraa_estrato_sorteado",
            entidade="liraa_estrato", entidade_id=id_estrato, detalhes=detalhes, conn=conn))["id_sorteio"], "liraa_sorteio",
        {"id_estrato": id_estrato}, auditoria_embutida=True)


def _download_error(exc, tab="campo"):
    flash(str(exc), "error")
    return redirect(url_for("liraa.page", ciclo=request.args.get("ciclo", "")) + f"#liraa-tab-{tab}")


@bp.route("/liraa/ciclos/<int:id_ciclo>/configuracao", methods=["POST"])
@login_required
@nivel_admin
def configurar_ciclo(id_ciclo):
    try:
        op.salvar_configuracao(_target(), id_ciclo, request.form.getlist("acs"), request.form.get("kobo_uid"),
            alterar_uid=(_usuario() or {}).get('nivel') == 'superadmin',
            auditar=lambda conn, detalhes: audit.registrar_evento(_get_db, "liraa_ciclo_formulario_configurado",
                entidade="liraa_ciclo", entidade_id=id_ciclo, detalhes=detalhes, conn=conn))
        flash("Participantes e formulário do ciclo salvos.", "success")
    except liraa_core.LiraaError as exc:
        flash(str(exc), "error")
    return redirect(url_for("liraa.page", ciclo=id_ciclo) + "#liraa-tab-formulario")


@bp.route("/api/liraa/ciclos/<int:id_ciclo>/plano-mapa")
@login_required
@_acesso_operacional
def plano_mapa(id_ciclo):
    try:
        return jsonify(op.geojson(_target(), id_ciclo, _base_dir(), request.args.get("estrato"), request.args.get("localidade")))
    except liraa_core.LiraaError as exc:
        return jsonify({"erro": str(exc)}), 400


@bp.route("/liraa/ciclos/<int:id_ciclo>/plano.<formato>")
@login_required
@_acesso_operacional
def exportar_plano(id_ciclo, formato):
    try:
        args = (_target(), id_ciclo, _base_dir(), request.args.get("estrato"), request.args.get("localidade"))
        if formato == "kml":
            content, mimetype = op.kml(*args), "application/vnd.google-earth.kml+xml"
        elif formato == "pdf":
            content, mimetype = liraa_relatorios.plano_pdf(*args), "application/pdf"
        else:
            return jsonify({"erro": "Formato inválido."}), 400
        return send_file(BytesIO(content), mimetype=mimetype, as_attachment=True, download_name=f"liraa-ciclo-{id_ciclo}-plano.{formato}")
    except liraa_core.LiraaError as exc:
        return _download_error(exc)


@bp.route("/liraa/ciclos/<int:id_ciclo>/formulario.xlsx")
@login_required
@nivel_admin
@_acesso_operacional
def formulario(id_ciclo):
    try:
        content = liraa_xlsform.gerar(_target(), id_ciclo, _base_dir())
        return send_file(BytesIO(content), as_attachment=True, download_name=f"LIRAa-ciclo-{id_ciclo}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except liraa_core.LiraaError as exc:
        return _download_error(exc, "formulario")


@bp.route("/liraa/ciclos/<int:id_ciclo>/boletim.pdf")
@login_required
@nivel_admin
@_acesso_operacional
def boletim(id_ciclo):
    try:
        content = liraa_relatorios.boletim_pdf(_target(), id_ciclo, _base_dir(), request.args.get("agrupar", "estrato"),
                                             request.args.get("estrato"), request.args.get("localidade"))
        return send_file(BytesIO(content), mimetype="application/pdf", as_attachment=True, download_name=f"LIRAa-ciclo-{id_ciclo}-boletim.pdf")
    except liraa_core.LiraaError as exc:
        return _download_error(exc, "boletins")


@bp.route("/liraa/laboratorio")
@login_required
@laboratorio_required
def laboratorio():
    return redirect(url_for("laboratorio_lancamentos.page",tipo="LIRAA",ciclo=request.args.get("ciclo","")))


@bp.route("/liraa/laboratorio/<int:id_tubito>", methods=["POST"])
@login_required
@laboratorio_required
def salvar_leitura(id_tubito):
    try:
        liraa_laboratorio.salvar(_target(), id_tubito, request.form, _usuario(),
            auditar=lambda conn, detalhes: audit.registrar_evento(_get_db, "liraa_leitura_salva", entidade="liraa_tubito",
                entidade_id=id_tubito, detalhes=detalhes, conn=conn))
        flash("Leitura LIRAa salva.", "success")
    except liraa_core.LiraaError as exc:
        flash(str(exc), "error")
    endpoint = "laboratorio_lancamentos.page" if request.form.get("integrado") == "1" else "liraa.laboratorio"
    return redirect(url_for(endpoint, modulo="liraa", ciclo=request.form.get("ciclo", ""),
                            pendentes=request.form.get("pendentes", "1")))


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
