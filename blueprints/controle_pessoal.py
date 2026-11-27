import logging
from datetime import date, timedelta
from functools import wraps

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, url_for

from app_core import agentes as agentes_core
from app_core import audit
from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import pessoal_folgas
from app_core import pessoal_folgas_relatorio as relatorio
from app_core import permissoes
from app_core import setores
from app_core import utils as utils_core


bp = Blueprint("controle_pessoal", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


def _invalidate_globals():
    fn = current_app.extensions.get("invalidar_cache_globals")
    if fn:
        fn()


@bp.route("/admin/agentes")
@login_required
@nivel_min("admin")
def page():
    aba = request.args.get("aba")
    if aba in {"folgas", "relatorios"}:
        conn = bh.get_db()
        try:
            _iniciar_leitura(conn)
            servidores = conn.execute(
                """SELECT id_agente, COALESCE(NULLIF(TRIM(nome_completo), ''), nome) AS nome, ativo
                     FROM agentes ORDER BY ativo DESC, LOWER(COALESCE(NULLIF(TRIM(nome_completo), ''), nome))"""
            ).fetchall()
            agente_id = request.args.get("id_agente", type=int)
            contexto = {}
            if aba == "relatorios":
                try:
                    contexto = {"relatorio": _dados_relatorio(conn)}
                except ValueError as exc:
                    return render_template("admin_agentes.html", aba=aba, erro=str(exc),
                                           servidores_folgas=servidores, agente_folgas=agente_id,
                                           filtros_relatorio=request.args), 400
        finally:
            conn.close()
        return render_template(
            "admin_agentes.html", aba=aba, servidores_folgas=[dict(row) for row in servidores],
            agente_folgas=next((row["id_agente"] for row in servidores if row["id_agente"] == agente_id), None),
            pode_apagar=permissoes.permite(bh.usuario_atual(), "tecnica"), **contexto,
        )

    filtros = {
        "status": request.args.get("status", "ativos"),
        "busca": request.args.get("busca", ""),
    }
    agentes = agentes_core.listar(bh.db_target(), filtros)
    return render_template(
        "admin_agentes.html",
        aba="servidores",
        agentes=agentes,
        filtros=filtros,
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(30)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
    )


@bp.route("/admin/agentes/criar", methods=["POST"])
@login_required
@nivel_min("admin")
def criar():
    dados = request.form.to_dict()
    try:
        novo_id = agentes_core.criar(bh.db_target(), dados)
        _invalidate_globals()
        audit.registrar_evento(
            bh.get_db,
            "agente_criado",
            entidade="agentes",
            entidade_id=novo_id,
            detalhes={"nome": dados.get("nome") or dados.get("nome_completo"), "matricula": dados.get("matricula")},
        )
    except Exception as exc:
        logging.exception("Erro ao criar agente")
        filtros = {"status": "todos", "busca": ""}
        return render_template(
            "admin_agentes.html",
            aba="servidores",
            agentes=agentes_core.listar(bh.db_target(), filtros),
            filtros=filtros,
            d_ini=utils_core.data_n_dias(30),
            d_fim=utils_core.hoje(),
            erro=str(exc),
        ), 400
    return redirect(url_for("controle_pessoal.page", status="todos"))


@bp.route("/admin/agentes/<int:id_agente>/editar", methods=["POST"])
@login_required
@nivel_min("admin")
def editar(id_agente):
    campo = request.form.get("campo", "")
    valor = request.form.get("valor", "")
    try:
        anterior, novo = agentes_core.atualizar_campo(
            bh.db_target(),
            id_agente,
            campo,
            valor,
        )
        _invalidate_globals()
        audit.registrar_evento(
            bh.get_db,
            "agente_editado",
            entidade="agentes",
            entidade_id=id_agente,
            detalhes={
                "nome": anterior.get("nome"),
                "campo": campo,
                "valor_antigo": anterior.get(campo),
                "valor_novo": novo,
            },
        )
        return jsonify({"ok": True})
    except Exception as exc:
        logging.exception("Erro ao editar agente")
        return jsonify({"erro": str(exc)}), 400


def _iniciar_leitura(conn):
    if conn.backend == "postgresql":
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    else:
        conn.execute("BEGIN")


def _api_pessoal(view):
    @wraps(view)
    @login_required
    @nivel_min("admin")
    def responder(*args, **kwargs):
        conn = bh.get_db()
        try:
            if request.method in {"GET", "HEAD"}:
                _iniciar_leitura(conn)
            return view(conn, *args, **kwargs)
        except pessoal_folgas.NaoEncontrado as exc:
            return jsonify(erro=str(exc)), 404
        except pessoal_folgas.Conflito as exc:
            return jsonify(erro=str(exc)), 409
        except ValueError as exc:
            return jsonify(erro=str(exc)), 400
        finally:
            try:
                conn.rollback()
            finally:
                conn.close()

    return responder


def _dados_json():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        raise ValueError("Envie os dados do registro em formato JSON.")
    return dados


def _id_filtro():
    valor = request.args.get("id_agente")
    if valor in (None, ""):
        return None
    if len(valor) > 19 or not valor.isascii() or not valor.isdecimal() or not 0 < int(valor) < 2**63:
        raise ValueError("Servidor inválido.")
    return int(valor)


def _intervalo_agenda():
    try:
        inicio, fim = (date.fromisoformat(request.args.get(campo, "")) for campo in ("inicio", "fim"))
    except ValueError:
        raise ValueError("Informe datas inicial e final válidas para a agenda.") from None
    if not 1 <= (fim - inicio).days <= 370:
        raise ValueError("Selecione um período de até 370 dias para a agenda.")
    return inicio.isoformat(), fim.isoformat()


def _dados_relatorio(conn):
    hoje = date.fromisoformat(utils_core.hoje())
    inicio = request.args.get("inicio") or hoje.replace(day=1).isoformat()
    fim = request.args.get("fim") or hoje.isoformat()
    try:
        inicio, fim = date.fromisoformat(inicio), date.fromisoformat(fim)
        fim_exclusivo = fim + timedelta(days=1)
    except (ValueError, OverflowError):
        raise ValueError("Informe datas inicial e final válidas.") from None
    if not 1 <= (fim_exclusivo - inicio).days <= 370:
        raise ValueError("Escolha um período de até 370 dias, com a data inicial antes ou igual à final.")
    id_agente = _id_filtro()
    return relatorio.montar(conn, inicio, fim, fim_exclusivo, id_agente)


def _gravar(conn, acao, entidade, registro_id, *, criado=False, detalhes=None):
    audit.registrar_evento(bh.get_db, acao, entidade=entidade, entidade_id=registro_id,
                           detalhes=detalhes, conn=conn)
    conn.commit()
    return jsonify(id=registro_id), 201 if criado else 200


@bp.get("/api/pessoal/folgas/ocorrencias")
@_api_pessoal
def listar_ocorrencias(conn):
    inicio, fim = _intervalo_agenda()
    tipo = request.args.get("tipo") or None
    status = request.args.get("status") or None
    if tipo not in (None, "folga", "falta"):
        raise ValueError("Tipo de ocorrência inválido.")
    if status not in (None, "agendada", "aguardando_confirmacao", "utilizada", "registrada", "cancelada"):
        raise ValueError("Situação de ocorrência inválida.")
    ocorrencias = pessoal_folgas.listar_ocorrencias(conn, inicio, fim, _id_filtro(), tipo)
    if status:
        ocorrencias = [item for item in ocorrencias if item["status"] == status]
    elif request.args.get("incluir_canceladas") != "1":
        ocorrencias = [item for item in ocorrencias if item["status"] != "cancelada"]
    return jsonify(ocorrencias=ocorrencias)


@bp.get("/api/pessoal/folgas/saldos")
@_api_pessoal
def listar_saldos(conn):
    return jsonify(saldos=pessoal_folgas.listar_saldos(conn, _id_filtro()))


@bp.get("/api/pessoal/folgas/servidores/<int:id_agente>/extrato")
@_api_pessoal
def consultar_extrato(conn, id_agente):
    return jsonify(pessoal_folgas.extrato(conn, id_agente))


@bp.post("/api/pessoal/folgas/creditos")
@_api_pessoal
def criar_credito(conn):
    registro_id = pessoal_folgas.criar_credito(conn, _dados_json(), bh.usuario_atual()["id_usuario"], setores.atual())
    return _gravar(conn, "pessoal_credito_criado", "pessoal_folga_creditos", registro_id, criado=True)


@bp.post("/api/pessoal/folgas/ocorrencias")
@_api_pessoal
def criar_ocorrencia(conn):
    dados = _dados_json()
    registro_id = pessoal_folgas.criar_ocorrencia(conn, dados, bh.usuario_atual()["id_usuario"], setores.atual())
    detalhes = {"tipo": dados["tipo"]}
    if dados["tipo"] == "falta":
        detalhes["classificacao"] = dados.get("classificacao") or "pendente"
    elif dados.get("autorizar_adiantamento"):
        detalhes["adiantamento_autorizado"] = True
    return _gravar(conn, "pessoal_ocorrencia_criada", "pessoal_ocorrencias", registro_id, criado=True, detalhes=detalhes)


@bp.post("/api/pessoal/folgas/ocorrencias/<int:registro_id>/confirmar")
@_api_pessoal
def confirmar_folga(conn, registro_id):
    pessoal_folgas.confirmar_folga(conn, registro_id, bh.usuario_atual()["id_usuario"])
    return _gravar(conn, "pessoal_folga_confirmada", "pessoal_ocorrencias", registro_id)


@bp.post("/api/pessoal/folgas/ocorrencias/<int:registro_id>/cancelar")
@_api_pessoal
def cancelar_ocorrencia(conn, registro_id):
    pessoal_folgas.cancelar_ocorrencia(conn, registro_id, _dados_json().get("motivo"), bh.usuario_atual()["id_usuario"])
    return _gravar(conn, "pessoal_ocorrencia_cancelada", "pessoal_ocorrencias", registro_id)


@bp.post("/api/pessoal/folgas/ocorrencias/<int:registro_id>/classificar")
@_api_pessoal
def classificar_falta(conn, registro_id):
    dados = _dados_json()
    pessoal_folgas.classificar_falta(
        conn, registro_id, dados.get("classificacao"), dados.get("motivo"), bh.usuario_atual()["id_usuario"],
    )
    return _gravar(conn, "pessoal_falta_classificada", "pessoal_ocorrencias", registro_id,
                   detalhes={"classificacao": dados["classificacao"]})


@bp.post("/api/pessoal/folgas/creditos/<int:registro_id>/cancelar")
@_api_pessoal
def cancelar_credito(conn, registro_id):
    pessoal_folgas.cancelar_credito(conn, registro_id, _dados_json().get("motivo"), bh.usuario_atual()["id_usuario"])
    return _gravar(conn, "pessoal_credito_cancelado", "pessoal_folga_creditos", registro_id)


@bp.post("/api/pessoal/folgas/ocorrencias/<int:registro_id>/compensar")
@_api_pessoal
def compensar(conn, registro_id):
    dados = _dados_json()
    ids = pessoal_folgas.compensar_folga(conn, registro_id, dados, bh.usuario_atual()["id_usuario"])
    return _gravar(conn, "pessoal_folga_compensada", "pessoal_ocorrencias", registro_id, criado=True,
                   detalhes={"origem": dados["origem"], "compensacoes": ids})


def _confirmacao_exclusao(dados):
    motivo = dados.get("motivo")
    if dados.get("confirmacao") != "APAGAR":
        raise ValueError("Digite APAGAR para confirmar a exclusão definitiva.")
    if motivo not in ("lancamento_teste", "lancamento_duplicado", "erro_lancamento", "correcao_administrativa"):
        raise ValueError("Selecione o motivo da exclusão.")
    return motivo


@bp.post("/api/pessoal/folgas/<categoria>/<int:registro_id>/apagar")
@nivel_min("superadmin")
@_api_pessoal
def apagar_lancamento(conn, categoria, registro_id):
    if categoria not in {"creditos", "ocorrencias", "compensacoes"}:
        raise pessoal_folgas.NaoEncontrado("Categoria de lançamento inexistente.")
    motivo = _confirmacao_exclusao(_dados_json())
    id_agente = pessoal_folgas.apagar_registro(conn, categoria, registro_id)
    return _gravar(conn, "pessoal_lancamento_apagado", categoria, registro_id,
                   detalhes={"id_agente": id_agente, "motivo_codigo": motivo})


@bp.post("/api/pessoal/folgas/servidores/<int:id_agente>/apagar-historico")
@nivel_min("superadmin")
@_api_pessoal
def apagar_historico(conn, id_agente):
    motivo = _confirmacao_exclusao(_dados_json())
    apagados = pessoal_folgas.apagar_historico(conn, id_agente)
    return _gravar(conn, "pessoal_historico_apagado", "agentes", id_agente,
                   detalhes={"motivo_codigo": motivo, "apagados": apagados})


@bp.get("/admin/agentes/relatorios/<formato>")
@_api_pessoal
def exportar_relatorio(conn, formato):
    if formato not in {"xlsx", "pdf"}:
        raise pessoal_folgas.NaoEncontrado("Formato de relatório inexistente.")
    dados = _dados_relatorio(conn)
    arquivo, tipo = relatorio.exportar(dados, formato)
    audit.registrar_evento(bh.get_db, "pessoal_relatorio_exportado", entidade="pessoal",
                           detalhes={"formato": formato, **dados["filtros"]})
    return send_file(arquivo, mimetype=tipo, as_attachment=True,
                     download_name=f"controle-pessoal-{dados['filtros']['fim']}.{formato}")
