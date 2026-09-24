import csv
import io
import mimetypes
import os
import shutil
import sqlite3
import uuid
import warnings
import zipfile
from pathlib import Path

from flask import Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
import pymupdf
from werkzeug.utils import secure_filename

from app_core import auth as auth_core
from app_core import audit
from app_core import blueprint_helpers as bh
from app_core import db as db_core
from app_core import esporotricose as esporotricose_core
from app_core import esporotricose_humanos as humanos_core
from app_core import utils as utils_core


bp = Blueprint("esporotricose", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min

ANEXO_IMAGEM_EXTENSOES = {".png", ".jpg", ".jpeg", ".jfif", ".webp"}
ANEXO_EXTENSOES = {".pdf", *ANEXO_IMAGEM_EXTENSOES, ".doc", ".docx", ".xls", ".xlsx"}
ANEXO_MAX_BYTES = 20 * 1024 * 1024


class AnexoImagemInvalida(ValueError):
    pass


def _localidades():
    conn = db_core.connect(bh.db_target())
    esporotricose_core.ensure_schema(conn)
    try:
        return [
            dict(r) for r in conn.execute(
                """SELECT nome FROM (
                     SELECT DISTINCT localidade AS nome
                       FROM esporotricose_visitas
                      WHERE localidade IS NOT NULL AND TRIM(localidade) <> ''
                     UNION
                     SELECT DISTINCT localidade AS nome
                       FROM esporotricose_doentes_animais
                      WHERE localidade IS NOT NULL AND TRIM(localidade) <> ''
                   )
                   ORDER BY nome"""
            )
        ]
    finally:
        conn.close()


def _agentes():
    conn = db_core.connect(bh.db_target())
    esporotricose_core.ensure_schema(conn)
    try:
        return [
            dict(r) for r in conn.execute(
                """SELECT DISTINCT ag.nome
                   FROM esporotricose_visita_agentes va
                   JOIN agentes ag ON ag.id_agente = va.id_agente
                   ORDER BY ag.nome"""
            )
        ]
    finally:
        conn.close()


def _status_doente_class(status):
    text = esporotricose_core._sem_acentos(status or "").lower()
    if "acabou" in text or "final" in text:
        return "status-finalizado"
    if "faleceu" in text or "obito" in text:
        return "status-faleceu"
    if "nao e esporotricose" in text:
        return "status-nao-esporo"
    if "document" in text:
        return "status-docs"
    if "aguardando medic" in text:
        return "status-medicacao"
    if "disponivel" in text:
        return "status-disponivel"
    if "tratamento" in text:
        return "status-tratamento"
    return "status-outro"


@bp.route("/esporotricose")
@login_required
def page():
    usuario = bh.usuario_atual() or {}
    return render_template(
        "esporotricose.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(365)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        localidades=_localidades(),
        agentes=_agentes(),
        acs=esporotricose_core.opcoes_acs_visitas(bh.db_target()),
        is_admin=usuario.get("nivel") == "admin",
    )


def _usuario_nome():
    usuario = auth_core.usuario_atual(
        lambda sql, params=(): db_core.query_one(bh.db_target(), sql, params)
    ) or {}
    return usuario.get("nome") or "sistema"


def _localidades_humanos():
    conn = db_core.connect(bh.db_target())
    humanos_core.ensure_schema(conn)
    try:
        return [dict(row) for row in conn.execute("SELECT nome FROM localidades ORDER BY nome")]
    finally:
        conn.close()


@bp.route("/esporotricose/humanos")
@login_required
@nivel_min("admin")
def page_humanos():
    audit.registrar_evento(
        bh.get_db, "esporotricose_humanos_consulta", entidade="esporotricose_pacientes_humanos"
    )
    return render_template(
        "esporotricose_humanos.html",
        status_opcoes=humanos_core.STATUS,
        bloqueio_opcoes=humanos_core.BLOQUEIO_OPCOES,
        localidades=_localidades_humanos(),
    )


@bp.route("/esporotricose/humanos/novo")
@login_required
@nivel_min("admin")
def page_humano_novo():
    return render_template(
        "esporotricose_humano_form.html",
        paciente=None,
        modo="novo",
        status_opcoes=humanos_core.STATUS,
        bloqueio_opcoes=humanos_core.BLOQUEIO_OPCOES,
        localidades=_localidades_humanos(),
    )


@bp.route("/esporotricose/humanos/<int:id_paciente>")
@login_required
@nivel_min("admin")
def page_humano_detalhe(id_paciente):
    paciente = humanos_core.obter_paciente(bh.db_target(), id_paciente)
    if not paciente:
        abort(404)
    audit.registrar_evento(
        bh.get_db,
        "esporotricose_humano_visualizado",
        entidade="esporotricose_pacientes_humanos",
        entidade_id=id_paciente,
    )
    return render_template(
        "esporotricose_humano_detalhe.html",
        paciente=paciente,
        status_opcoes=humanos_core.STATUS,
        bloqueio_opcoes=humanos_core.BLOQUEIO_OPCOES,
        hoje_iso=utils_core.hoje(),
    )


@bp.route("/esporotricose/humanos/<int:id_paciente>/editar")
@login_required
@nivel_min("admin")
def page_humano_editar(id_paciente):
    paciente = humanos_core.obter_paciente(bh.db_target(), id_paciente)
    if not paciente:
        abort(404)
    return render_template(
        "esporotricose_humano_form.html",
        paciente=paciente,
        modo="editar",
        status_opcoes=humanos_core.STATUS,
        bloqueio_opcoes=humanos_core.BLOQUEIO_OPCOES,
        localidades=_localidades_humanos(),
    )


@bp.route("/api/esporotricose/humanos")
@login_required
@nivel_min("admin")
def api_humanos():
    return jsonify(humanos_core.listar_pacientes(bh.db_target(), {
        "busca": request.args.get("busca", ""),
        "status": request.args.get("status", ""),
        "localidade": request.args.get("localidade", ""),
        "bloqueio": request.args.get("bloqueio", ""),
        "pagina": request.args.get("pagina", 1),
        "por_pagina": request.args.get("por_pagina", 30),
    }))


@bp.route("/esporotricose/humanos/casos.csv")
@login_required
@nivel_min("admin")
def download_humanos_csv():
    filtros = {
        "busca": request.args.get("busca", ""),
        "status": request.args.get("status", ""),
        "localidade": request.args.get("localidade", ""),
        "bloqueio": request.args.get("bloqueio", ""),
    }
    campos = [
        "id_paciente",
        "nome",
        "data_nascimento",
        "cartao_sus",
        "nome_mae",
        "telefone",
        "data_notificacao",
        "status",
        "status_detalhe",
        "bloqueio",
        "localidade",
        "quarteirao",
        "logradouro",
        "numero",
        "complemento",
        "endereco_completo",
        "latitude",
        "longitude",
        "observacoes",
        "acompanhamentos",
        "ultimo_acompanhamento",
        "imoveis_vinculados",
        "animais_vinculados",
        "anexos",
        "criado_em",
        "atualizado_em",
    ]
    rows = humanos_core.listar_pacientes_csv(bh.db_target(), filtros)
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.DictWriter(
        buffer,
        fieldnames=campos,
        delimiter=";",
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({campo: row.get(campo) for campo in campos})
    audit.registrar_evento(
        bh.get_db,
        "esporotricose_humanos_csv_qgis",
        entidade="esporotricose_pacientes_humanos",
        detalhes={
            "quantidade": len(rows),
            "status": filtros["status"],
            "localidade": filtros["localidade"],
            "bloqueio": filtros["bloqueio"],
            "com_pesquisa": bool(filtros["busca"]),
        },
    )
    return Response(
        buffer.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=Casos-humanos-esporotricose.csv"
        },
    )


@bp.route("/api/esporotricose/humanos", methods=["POST"])
@login_required
@nivel_min("admin")
def api_criar_humano():
    try:
        id_paciente = humanos_core.salvar_paciente(
            bh.db_target(), request.get_json(silent=True) or {}, _usuario_nome()
        )
    except humanos_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        bh.get_db,
        "esporotricose_humano_criado",
        entidade="esporotricose_pacientes_humanos",
        entidade_id=id_paciente,
    )
    return jsonify(humanos_core.obter_paciente(bh.db_target(), id_paciente)), 201


@bp.route("/api/esporotricose/humanos/<int:id_paciente>", methods=["GET", "PUT"])
@login_required
@nivel_min("admin")
def api_humano(id_paciente):
    if request.method == "PUT":
        try:
            dados = dict(request.get_json(silent=True) or {})
            dados["id_paciente"] = id_paciente
            humanos_core.salvar_paciente(bh.db_target(), dados, _usuario_nome())
        except humanos_core.ValidationError as exc:
            return jsonify({"erro": str(exc)}), 400
        audit.registrar_evento(
            bh.get_db,
            "esporotricose_humano_atualizado",
            entidade="esporotricose_pacientes_humanos",
            entidade_id=id_paciente,
        )
    paciente = humanos_core.obter_paciente(bh.db_target(), id_paciente)
    if not paciente:
        return jsonify({"erro": "Paciente não encontrado."}), 404
    return jsonify(paciente)


@bp.route("/api/esporotricose/humanos/<int:id_paciente>/acompanhamentos", methods=["POST"])
@login_required
@nivel_min("admin")
def api_humano_acompanhamento(id_paciente):
    try:
        id_acompanhamento = humanos_core.salvar_acompanhamento(
            bh.db_target(), id_paciente, request.get_json(silent=True) or {}, _usuario_nome()
        )
    except humanos_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        bh.get_db,
        "esporotricose_humano_acompanhamento",
        entidade="esporotricose_pacientes_humanos",
        entidade_id=id_paciente,
        detalhes={"id_acompanhamento": id_acompanhamento},
    )
    return jsonify(humanos_core.obter_paciente(bh.db_target(), id_paciente)), 201


@bp.route("/api/esporotricose/humanos/<int:id_paciente>/sugestoes-vinculos")
@login_required
@nivel_min("admin")
def api_humano_sugestoes(id_paciente):
    try:
        return jsonify(humanos_core.sugestoes_vinculos(bh.db_target(), id_paciente))
    except humanos_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 404


@bp.route("/api/esporotricose/humanos/<int:id_paciente>/vinculos/<tipo>/<int:id_alvo>", methods=["POST", "DELETE"])
@login_required
@nivel_min("admin")
def api_humano_vinculo(id_paciente, tipo, id_alvo):
    try:
        humanos_core.alterar_vinculo(
            bh.db_target(), id_paciente, tipo, id_alvo, _usuario_nome(), request.method == "POST"
        )
    except humanos_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        bh.get_db,
        "esporotricose_humano_vinculo" if request.method == "POST" else "esporotricose_humano_desvinculo",
        entidade="esporotricose_pacientes_humanos",
        entidade_id=id_paciente,
        detalhes={"tipo": tipo, "id_alvo": id_alvo},
    )
    return jsonify(humanos_core.obter_paciente(bh.db_target(), id_paciente))


@bp.route("/esporotricose/doentes/novo")
@login_required
@nivel_min("operador")
def page_doente_novo():
    animal = None
    origem_visita = None
    id_animal_visita = (request.args.get("origem_animal") or "").strip()
    if id_animal_visita:
        cadastro = esporotricose_core.preparar_doente_de_visita(bh.db_target(), id_animal_visita)
        if not cadastro:
            abort(404)
        if cadastro.get("id_animal_doente"):
            return redirect(f"/esporotricose/doentes/{cadastro['id_animal_doente']}")
        animal = cadastro["animal"]
        origem_visita = cadastro["origem"]
    return render_template(
        "esporotricose_doente_form.html",
        animal=animal,
        origem_visita=origem_visita,
        modo="novo",
        status_opcoes=esporotricose_core.status_doentes(bh.db_target()),
        localidades=_localidades(),
    )


@bp.route("/esporotricose/doentes/<int:id_animal>")
@login_required
def page_doente_detalhe(id_animal):
    animal = esporotricose_core.obter_doente(bh.db_target(), id_animal)
    if not animal:
        abort(404)
    return render_template(
        "esporotricose_doente_detalhe.html",
        animal=animal,
        status_opcoes=esporotricose_core.status_doentes(bh.db_target()),
        status_class=_status_doente_class(animal.get("status")),
    )


@bp.route("/esporotricose/doentes/<int:id_animal>/editar")
@login_required
@nivel_min("operador")
def page_doente_editar(id_animal):
    animal = esporotricose_core.obter_doente(bh.db_target(), id_animal)
    if not animal:
        abort(404)
    return render_template(
        "esporotricose_doente_form.html",
        animal=animal,
        origem_visita=None,
        modo="editar",
        status_opcoes=esporotricose_core.status_doentes(bh.db_target()),
        localidades=_localidades(),
    )


@bp.route("/api/esporotricose")
@login_required
def api_resumo():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
    }
    return jsonify(esporotricose_core.resumo(bh.db_target(), filtros))


@bp.route("/api/esporotricose/visitas")
@login_required
def api_visitas():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
        "busca": request.args.get("busca", ""),
        "acs": request.args.getlist("acs"),
    }
    return jsonify(esporotricose_core.listar_visitas(bh.db_target(), filtros))


@bp.route("/api/esporotricose/imoveis")
@login_required
def api_imoveis():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "quarteirao": request.args.get("quarteirao", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
        "tipo_imovel": request.args.get("tipo_imovel", ""),
        "busca": request.args.get("busca", ""),
        "pagina": request.args.get("pagina", ""),
        "por_pagina": request.args.get("por_pagina", ""),
    }
    return jsonify(esporotricose_core.listar_imoveis(bh.db_target(), filtros))


@bp.route("/api/esporotricose/imoveis/<int:id_imovel>")
@login_required
def api_imovel_detalhe(id_imovel):
    dados = esporotricose_core.detalhe_imovel(bh.db_target(), id_imovel)
    if not dados:
        return jsonify({"erro": "Imóvel acompanhado não encontrado."}), 404
    return jsonify(dados)


@bp.route("/api/esporotricose/imoveis/previa-vinculos")
@login_required
@nivel_min("admin")
def api_imoveis_previa_vinculos():
    return jsonify(esporotricose_core.previsualizar_vinculos_imoveis(bh.db_target()))


@bp.route("/api/esporotricose/imoveis/sugestoes-vinculos")
@login_required
@nivel_min("admin")
def api_imoveis_sugestoes_vinculos():
    return jsonify(esporotricose_core.sugestoes_vinculo_imoveis(bh.db_target(), request.args.get("limite", 50)))


@bp.route("/api/esporotricose/imoveis/vincular-exatos", methods=["POST"])
@login_required
@nivel_min("admin")
def api_imoveis_vincular_exatos():
    try:
        resultado = esporotricose_core.vincular_visitas_exatas(bh.db_target())
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        bh.get_db, "esporotricose_imoveis_vinculo_exato", entidade="esporotricose_imoveis",
        detalhes=resultado,
    )
    return jsonify({"ok": True, **resultado})


@bp.route("/api/esporotricose/imoveis/vincular-manual", methods=["POST"])
@login_required
@nivel_min("admin")
def api_imoveis_vincular_manual():
    try:
        resultado = esporotricose_core.vincular_visitas_manual(
            bh.db_target(), (request.get_json(silent=True) or {}).get("ids_visitas") or []
        )
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        bh.get_db, "esporotricose_imoveis_vinculo_manual", entidade="esporotricose_imoveis",
        entidade_id=resultado.get("id_imovel"), detalhes={"visitas": resultado.get("vinculadas")},
    )
    return jsonify({"ok": True, **resultado})


@bp.route("/api/esporotricose/animais")
@login_required
def api_animais():
    def multi(nome):
        valores = [v for v in request.args.getlist(nome) if v]
        return valores if valores else ""

    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
        "busca": request.args.get("busca", ""),
        "especie": multi("especie"),
        "feridas": multi("feridas"),
        "vacinado": multi("vacinado"),
        "castrado": multi("castrado"),
        "ambiente": multi("ambiente"),
        "motivo_atencao": multi("motivo_atencao"),
        "prioritarios": request.args.get("prioritarios", ""),
        "evolucao": multi("evolucao"),
    }
    return jsonify(esporotricose_core.listar_animais(bh.db_target(), filtros))


@bp.route("/api/esporotricose/visitas/<id_visita>", methods=["PUT"])
@login_required
@nivel_min("operador")
def api_atualizar_visita(id_visita):
    try:
        dados = request.get_json(silent=True) or {}
        resultado = esporotricose_core.atualizar_visita(bh.db_target(), id_visita, dados)
        return jsonify(resultado)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        import logging
        logging.exception("Erro ao atualizar visita esporotricose")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.route("/api/esporotricose/animais/<id_animal>", methods=["PUT"])
@login_required
@nivel_min("operador")
def api_atualizar_animal(id_animal):
    try:
        dados = request.get_json(silent=True) or {}
        resultado = esporotricose_core.atualizar_animal(bh.db_target(), id_animal, dados)
        return jsonify(resultado)
    except (ValueError, esporotricose_core.ValidationError) as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        import logging
        logging.exception("Erro ao atualizar animal esporotricose")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.route("/api/esporotricose/animais/<id_animal>/buscas-ferido", methods=["POST"])
@login_required
@nivel_min("operador")
def api_salvar_busca_ferido(id_animal):
    try:
        busca = esporotricose_core.salvar_busca_ferido(
            bh.db_target(), id_animal, request.get_json(silent=True) or {}
        )
        return jsonify({"ok": True, "busca": busca}), 201
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        import logging
        logging.exception("Erro ao salvar busca de animal ferido")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.route("/api/esporotricose/localidades")
@login_required
def api_localidades():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
    }
    return jsonify(esporotricose_core.resumo_localidades(bh.db_target(), filtros))


@bp.route("/api/esporotricose/dashboard")
@login_required
def api_dashboard():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
    }
    return jsonify(esporotricose_core.dashboard(bh.db_target(), filtros))


@bp.route("/api/esporotricose/doentes")
@login_required
def api_doentes():
    filtros = {
        "busca": request.args.get("busca", ""),
        "status": request.args.get("status", ""),
        "especie": request.args.get("especie", ""),
        "localidade": request.args.get("localidade", ""),
        "bloqueio": request.args.get("bloqueio", ""),
        "pedido_zoomed": request.args.get("pedido_zoomed", ""),
        "baixa_zoomed": request.args.get("baixa_zoomed", ""),
    }
    return jsonify(esporotricose_core.listar_doentes(bh.db_target(), filtros))


@bp.route("/esporotricose/doentes/casos.csv")
@login_required
def download_doentes_csv():
    campos = [
        "id_animal_doente",
        "animal",
        "tutor",
        "telefone",
        "especie",
        "sexo",
        "status",
        "data_notificacao",
        "primeira_notificacao",
        "ultima_notificacao",
        "ultima_receita",
        "receitas_pendentes",
        "localidade",
        "quarteirao",
        "endereco",
        "latitude",
        "longitude",
        "sinan",
        "bloqueio",
        "data_bloqueio",
        "pedido_zoomed",
        "baixa_zoomed",
        "receitas",
        "capsulas_receitadas",
        "capsulas_entregues",
        "capsulas_restantes",
        "proxima_entrega",
        "receita_pendente",
        "entregas",
        "anexos",
        "observacoes_entomologica",
    ]
    rows = esporotricose_core.listar_doentes_csv(bh.db_target(), {})
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=campos, delimiter=";", extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({campo: row.get(campo) for campo in campos})
    return Response(
        buffer.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=Casos-esporotricose.csv"},
    )


@bp.route("/api/esporotricose/doentes/status")
@login_required
def api_doentes_status():
    return jsonify({"registros": esporotricose_core.status_doentes(bh.db_target())})


@bp.route("/api/esporotricose/doentes/status", methods=["POST"])
@login_required
@nivel_min("operador")
def api_criar_status_doente():
    nome = (request.json or {}).get("nome")
    if not nome:
        return jsonify({"erro": "Informe o status."}), 400
    esporotricose_core.salvar_status_doente(bh.db_target(), nome)
    return jsonify({"registros": esporotricose_core.status_doentes(bh.db_target())})


@bp.route("/api/esporotricose/doentes/estoque")
@login_required
def api_doentes_estoque():
    return jsonify(esporotricose_core.estoque_medicacao(bh.db_target()))


@bp.route("/api/esporotricose/doentes/estoque", methods=["POST"])
@login_required
@nivel_min("operador")
def api_criar_movimento_estoque():
    try:
        id_movimento = esporotricose_core.salvar_estoque_medicacao(bh.db_target(), request.json or {})
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "id_movimento": id_movimento, **esporotricose_core.estoque_medicacao(bh.db_target())}), 201


@bp.route("/api/esporotricose/doentes/estoque/<int:id_movimento>", methods=["PUT", "DELETE"])
@login_required
@nivel_min("operador")
def api_doentes_estoque_item(id_movimento):
    if request.method == "DELETE":
        try:
            esporotricose_core.excluir_estoque_medicacao(bh.db_target(), id_movimento)
        except esporotricose_core.ValidationError as exc:
            return jsonify({"erro": str(exc)}), 404
        return jsonify({"ok": True})
    try:
        dados = dict(request.json or {})
        dados["id_movimento"] = id_movimento
        esporotricose_core.salvar_estoque_medicacao(bh.db_target(), dados)
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, **esporotricose_core.estoque_medicacao(bh.db_target())})


@bp.route("/api/esporotricose/doentes/estoque/automatico/<int:id_entrega>", methods=["PUT"])
@login_required
@nivel_min("operador")
def api_doentes_estoque_automatico(id_entrega):
    try:
        esporotricose_core.salvar_observacao_movimento_automatico(
            bh.db_target(), id_entrega, (request.json or {}).get("observacoes"),
        )
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 404
    return jsonify({"ok": True, **esporotricose_core.estoque_medicacao(bh.db_target())})


@bp.route("/api/esporotricose/doentes/<int:id_animal>")
@login_required
def api_doente(id_animal):
    item = esporotricose_core.obter_doente(bh.db_target(), id_animal)
    if not item:
        return jsonify({"erro": "Animal não encontrado."}), 404
    return jsonify(item)


@bp.route("/api/esporotricose/doentes/<int:id_animal>", methods=["PUT", "DELETE"])
@login_required
@nivel_min("operador")
def api_alterar_doente(id_animal):
    if request.method == "DELETE":
        try:
            resultado = esporotricose_core.excluir_doente(bh.db_target(), id_animal)
        except esporotricose_core.ValidationError as exc:
            return jsonify({"erro": str(exc)}), 404
        _remover_arquivos_anexos(resultado.get("anexos", []))
        return jsonify({"ok": True})
    if request.method == "PUT":
        try:
            dados = dict(request.json or {})
            dados["id_animal_doente"] = id_animal
            esporotricose_core.salvar_doente(bh.db_target(), dados)
        except esporotricose_core.ValidationError as exc:
            return jsonify({"erro": str(exc)}), 400
    item = esporotricose_core.obter_doente(bh.db_target(), id_animal)
    if not item:
        return jsonify({"erro": "Animal não encontrado."}), 404
    return jsonify(item)


@bp.route("/api/esporotricose/doentes", methods=["POST"])
@login_required
@nivel_min("operador")
def api_criar_doente():
    try:
        id_animal = esporotricose_core.salvar_doente(bh.db_target(), request.json or {})
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify(esporotricose_core.obter_doente(bh.db_target(), id_animal)), 201


@bp.route("/api/esporotricose/doentes/<int:id_animal>/receitas", methods=["POST"])
@login_required
@nivel_min("operador")
def api_salvar_receita_doente(id_animal):
    try:
        id_receita = esporotricose_core.salvar_receita_doente(bh.db_target(), id_animal, request.json or {})
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "id_receita": id_receita, "animal": esporotricose_core.obter_doente(bh.db_target(), id_animal)}), 201


@bp.route("/api/esporotricose/doentes/receitas/<int:id_receita>", methods=["DELETE"])
@login_required
@nivel_min("operador")
def api_excluir_receita_doente(id_receita):
    try:
        id_animal = esporotricose_core.excluir_receita_doente(bh.db_target(), id_receita)
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 404
    return jsonify({"ok": True, "id_animal_doente": id_animal})


@bp.route("/api/esporotricose/doentes/receitas/<int:id_receita>", methods=["PUT"])
@login_required
@nivel_min("operador")
def api_atualizar_receita_doente(id_receita):
    try:
        id_animal = esporotricose_core.atualizar_receita_doente(bh.db_target(), id_receita, request.json or {})
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "id_animal_doente": id_animal, "animal": esporotricose_core.obter_doente(bh.db_target(), id_animal)})


@bp.route("/api/esporotricose/doentes/receitas/<int:id_receita>/entregas", methods=["POST"])
@login_required
@nivel_min("operador")
def api_salvar_entrega_doente(id_receita):
    try:
        id_entrega = esporotricose_core.salvar_entrega_doente(bh.db_target(), id_receita, request.json or {})
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "id_entrega": id_entrega}), 201


@bp.route("/api/esporotricose/doentes/entregas/<int:id_entrega>", methods=["PUT", "DELETE"])
@login_required
@nivel_min("operador")
def api_excluir_entrega_doente(id_entrega):
    if request.method == "PUT":
        try:
            esporotricose_core.atualizar_entrega_doente(bh.db_target(), id_entrega, request.json or {})
        except esporotricose_core.ValidationError as exc:
            return jsonify({"erro": str(exc)}), 400
        return jsonify({"ok": True})
    esporotricose_core.excluir_entrega_doente(bh.db_target(), id_entrega)
    return jsonify({"ok": True})


@bp.route("/api/esporotricose/doentes/<int:id_animal>/anexos")
@login_required
def api_doente_anexos(id_animal):
    animal = esporotricose_core.obter_doente(bh.db_target(), id_animal)
    if not animal:
        return jsonify({"erro": "Animal não encontrado."}), 404
    return jsonify({"anexos": animal.get("anexos", [])})


@bp.route("/api/esporotricose/doentes/<int:id_animal>/anexos", methods=["POST"])
@login_required
@nivel_min("operador")
def api_salvar_anexos_doente(id_animal):
    animal = esporotricose_core.obter_doente(bh.db_target(), id_animal)
    if not animal:
        return jsonify({"erro": "Animal não encontrado."}), 404
    arquivos = request.files.getlist("arquivos")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400
    arquivos_validados = []
    for arquivo in arquivos:
        meta, erro = _validar_upload_anexo(arquivo)
        if erro:
            return jsonify({"erro": erro}), 400
        arquivos_validados.append((arquivo, meta))

    destino_dir = _doente_anexos_dir(id_animal)
    usuario = auth_core.usuario_atual(
        lambda sql, params=(): db_core.query_one(bh.db_target(), sql, params)
    ) or {}
    caminhos_salvos = []
    anexos_salvos = []
    try:
        for arquivo, meta in arquivos_validados:
            anexo = _salvar_upload_anexo(arquivo, meta, destino_dir)
            caminho = anexo["caminho"]
            caminhos_salvos.append(caminho)
            caminho_rel = str(caminho.relative_to(_anexos_base_dir())).replace("\\", "/")
            anexos_salvos.append(
                {
                    "nome_original": anexo["nome_original"],
                    "nome_arquivo": anexo["nome_arquivo"],
                    "caminho_rel": caminho_rel,
                    "mime_type": anexo["mime_type"],
                    "tamanho": anexo["tamanho"],
                }
            )
        salvos = esporotricose_core.salvar_anexos_doente(
            bh.db_target(),
            id_animal,
            anexos_salvos,
            usuario.get("nome") or "sistema",
        )
    except AnexoImagemInvalida as exc:
        _remover_caminhos(caminhos_salvos)
        return jsonify({"erro": str(exc)}), 400
    except sqlite3.OperationalError:
        _remover_caminhos(caminhos_salvos)
        return jsonify({"erro": "Banco de dados ocupado. Tente novamente."}), 503
    except Exception:
        _remover_caminhos(caminhos_salvos)
        current_app.logger.exception("Erro ao salvar anexo de animal com esporotricose")
        return jsonify({"erro": "Não foi possível salvar o anexo."}), 500
    return jsonify({
        "ok": True,
        "ids": salvos,
        "anexos": esporotricose_core.obter_doente(
            bh.db_target(), id_animal
        ).get("anexos", []),
    }), 201


@bp.route("/api/esporotricose/doentes/anexos/<int:id_anexo>", methods=["DELETE"])
@login_required
@nivel_min("operador")
def api_excluir_anexo_doente(id_anexo):
    try:
        row = esporotricose_core.excluir_anexo_doente(
            bh.db_target(), id_anexo
        )
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 404
    _remover_arquivos_anexos([row])
    return jsonify({"ok": True})


@bp.route("/esporotricose/doentes/anexos/<int:id_anexo>/download")
@login_required
def baixar_anexo_doente(id_anexo):
    row = esporotricose_core.obter_anexo_doente(bh.db_target(), id_anexo)
    if not row:
        abort(404)
    caminho = _path_anexo(row["caminho_rel"])
    if not caminho.exists() or not caminho.is_file():
        abort(404)
    inline = request.args.get("inline") == "1"
    return send_file(
        caminho,
        mimetype=row["mime_type"] or None,
        as_attachment=not inline,
        download_name=row["nome_original"],
        max_age=0,
    )


@bp.route("/esporotricose/doentes/anexos/<int:id_anexo>/miniatura")
@login_required
def miniatura_anexo_doente(id_anexo):
    row = esporotricose_core.obter_anexo_doente(bh.db_target(), id_anexo)
    if not row or row["mime_type"] != "application/pdf":
        abort(404)
    caminho = _path_anexo(row["caminho_rel"])
    if not caminho.exists() or not caminho.is_file():
        abort(404)
    miniatura = _miniatura_path(caminho)
    if not miniatura.exists():
        try:
            _gerar_miniatura_pdf(caminho, miniatura)
        except Exception:
            current_app.logger.exception("Erro ao gerar miniatura do anexo %s", id_anexo)
            abort(404)
    return send_file(miniatura, mimetype="image/webp", max_age=86400)


@bp.route("/esporotricose/doentes/<int:id_animal>/anexos/baixar-todos")
@login_required
def baixar_todos_anexos_doente(id_animal):
    """Baixa todos os anexos do doente em um unico arquivo ZIP."""
    animal = esporotricose_core.obter_doente(bh.db_target(), id_animal)
    if not animal:
        abort(404)
    anexos = animal.get("anexos") or []
    if not anexos:
        return jsonify({"erro": "Este doente não possui anexos para baixar."}), 404

    buffer = io.BytesIO()
    nomes_usados = {}
    total_gravados = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
        for anexo in anexos:
            caminho = _path_anexo(anexo.get("caminho_rel") or "")
            if not caminho.exists() or not caminho.is_file():
                continue
            base = os.path.basename(anexo.get("nome_original") or "") or "anexo.pdf"
            contador = nomes_usados.get(base, 0)
            nomes_usados[base] = contador + 1
            if contador == 0:
                nome_zip = base
            else:
                stem, ext = os.path.splitext(base)
                nome_zip = f"{stem}_{contador + 1}{ext}"
            arquivo_zip.write(caminho, arcname=nome_zip)
            total_gravados += 1
    buffer.seek(0)
    if not total_gravados:
        return jsonify({"erro": "Nenhum anexo do doente foi encontrado no disco."}), 404

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"anexos_doente_{id_animal:06d}.zip",
        mimetype="application/zip",
    )


@bp.route("/api/esporotricose/humanos/<int:id_paciente>/anexos", methods=["POST"])
@login_required
@nivel_min("admin")
def api_salvar_anexos_humano(id_paciente):
    if not humanos_core.obter_paciente(bh.db_target(), id_paciente):
        return jsonify({"erro": "Paciente não encontrado."}), 404
    arquivos = request.files.getlist("arquivos")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400
    validados = []
    for arquivo in arquivos:
        meta, erro = _validar_upload_anexo(arquivo)
        if erro:
            return jsonify({"erro": erro}), 400
        validados.append((arquivo, meta))
    destino = _humano_anexos_dir(id_paciente)
    caminhos = []
    metadados = []
    try:
        for arquivo, meta in validados:
            anexo = _salvar_upload_anexo(arquivo, meta, destino)
            caminhos.append(anexo["caminho"])
            metadados.append({
                "nome_original": anexo["nome_original"],
                "nome_arquivo": anexo["nome_arquivo"],
                "caminho_rel": str(anexo["caminho"].relative_to(_anexos_base_dir())).replace("\\", "/"),
                "mime_type": anexo["mime_type"],
                "tamanho": anexo["tamanho"],
            })
        ids = humanos_core.salvar_anexos(
            bh.db_target(), id_paciente, metadados, _usuario_nome()
        )
    except AnexoImagemInvalida as exc:
        _remover_caminhos(caminhos)
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        _remover_caminhos(caminhos)
        current_app.logger.exception("Erro ao salvar anexo de paciente humano")
        return jsonify({"erro": "Não foi possível salvar o anexo."}), 500
    audit.registrar_evento(
        bh.get_db,
        "esporotricose_humano_anexo_incluido",
        entidade="esporotricose_pacientes_humanos",
        entidade_id=id_paciente,
        detalhes={"quantidade": len(ids)},
    )
    return jsonify(humanos_core.obter_paciente(bh.db_target(), id_paciente)), 201


@bp.route("/api/esporotricose/humanos/anexos/<int:id_anexo>", methods=["DELETE"])
@login_required
@nivel_min("admin")
def api_excluir_anexo_humano(id_anexo):
    try:
        anexo = humanos_core.excluir_anexo(bh.db_target(), id_anexo)
    except humanos_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 404
    _remover_arquivos_anexos([anexo])
    audit.registrar_evento(
        bh.get_db,
        "esporotricose_humano_anexo_excluido",
        entidade="esporotricose_pacientes_humanos",
        entidade_id=anexo.get("id_paciente"),
        detalhes={"id_anexo": id_anexo},
    )
    return jsonify({"ok": True})


@bp.route("/esporotricose/humanos/anexos/<int:id_anexo>/download")
@login_required
@nivel_min("admin")
def baixar_anexo_humano(id_anexo):
    anexo = humanos_core.obter_anexo(bh.db_target(), id_anexo)
    if not anexo:
        abort(404)
    caminho = _path_anexo(anexo["caminho_rel"])
    if not caminho.exists() or not caminho.is_file():
        abort(404)
    audit.registrar_evento(
        bh.get_db,
        "esporotricose_humano_anexo_baixado",
        entidade="esporotricose_pacientes_humanos",
        entidade_id=anexo.get("id_paciente"),
        detalhes={"id_anexo": id_anexo},
    )
    return send_file(
        caminho,
        mimetype=anexo.get("mime_type") or None,
        as_attachment=request.args.get("inline") != "1",
        download_name=anexo["nome_original"],
        max_age=0,
    )


def _anexos_base_dir():
    base = Path(current_app.config["ANEXOS_DIR"]).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def _doente_anexos_dir(id_animal):
    caminho = _anexos_base_dir() / "esporotricose_doentes" / str(id_animal).zfill(6)
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def _humano_anexos_dir(id_paciente):
    caminho = _anexos_base_dir() / "esporotricose_humanos" / str(id_paciente).zfill(6)
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def _path_anexo(caminho_rel):
    base = _anexos_base_dir()
    caminho = (base / caminho_rel).resolve()
    if base not in caminho.parents and caminho != base:
        abort(404)
    return caminho


def _validar_upload_anexo(arquivo):
    nome_original = arquivo.filename or ""
    nome_seguro = secure_filename(nome_original)
    if not nome_seguro:
        return None, "Nome de arquivo inválido."
    ext = Path(nome_seguro).suffix.lower()
    if ext not in ANEXO_EXTENSOES:
        return None, "Tipo de arquivo não permitido."
    pos = arquivo.stream.tell()
    arquivo.stream.seek(0, os.SEEK_END)
    tamanho = arquivo.stream.tell()
    arquivo.stream.seek(pos)
    if tamanho <= 0:
        return None, "Arquivo vazio."
    if tamanho > ANEXO_MAX_BYTES:
        return None, "Arquivo maior que 20 MB."
    return {"nome_original": nome_original, "nome_seguro": nome_seguro, "ext": ext, "tamanho": tamanho}, ""


def _salvar_upload_anexo(arquivo, meta, destino_dir):
    eh_imagem = meta["ext"] in ANEXO_IMAGEM_EXTENSOES
    extensao_final = ".pdf" if eh_imagem else meta["ext"]
    nome_arquivo = f"{uuid.uuid4().hex}{extensao_final}"
    caminho = destino_dir / nome_arquivo
    try:
        if eh_imagem:
            _converter_imagem_para_pdf(arquivo, caminho)
            nome_original = _nome_original_pdf(meta["nome_original"], meta["nome_seguro"])
            mime_type = "application/pdf"
        else:
            arquivo.stream.seek(0)
            arquivo.save(caminho)
            nome_original = meta["nome_original"]
            mime_type = mimetypes.guess_type(meta["nome_seguro"])[0] or "application/octet-stream"

        tamanho = caminho.stat().st_size
        if tamanho > ANEXO_MAX_BYTES:
            raise AnexoImagemInvalida("O arquivo convertido ficou maior que 20 MB.")
        if mime_type == "application/pdf":
            try:
                _gerar_miniatura_pdf(caminho, _miniatura_path(caminho))
            except Exception:
                # O PDF continua valido mesmo quando uma previa nao pode ser produzida.
                pass
        return {
            "caminho": caminho,
            "nome_original": nome_original,
            "nome_arquivo": nome_arquivo,
            "mime_type": mime_type,
            "tamanho": tamanho,
        }
    except Exception:
        caminho.unlink(missing_ok=True)
        raise


def _converter_imagem_para_pdf(arquivo, caminho):
    try:
        arquivo.stream.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(arquivo.stream) as origem:
                imagem = ImageOps.exif_transpose(origem)
                imagem.load()
                if imagem.mode in ("RGBA", "LA") or "transparency" in imagem.info:
                    rgba = imagem.convert("RGBA")
                    pagina = Image.new("RGB", rgba.size, "white")
                    pagina.paste(rgba, mask=rgba.getchannel("A"))
                    rgba.close()
                else:
                    pagina = imagem.convert("RGB")
                try:
                    pagina.save(
                        caminho,
                        format="PDF",
                        resolution=150.0,
                        quality=90,
                        optimize=True,
                    )
                finally:
                    pagina.close()
                if imagem is not origem:
                    imagem.close()
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError):
        caminho.unlink(missing_ok=True)
        raise AnexoImagemInvalida(
            "A imagem enviada está corrompida ou não possui um formato válido."
        ) from None


def _nome_original_pdf(nome_original, nome_seguro):
    nome = (nome_original or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = Path(nome).stem.strip() or Path(nome_seguro).stem or "anexo"
    return f"{base}.pdf"


def _miniatura_path(caminho):
    return caminho.with_name(f"{caminho.stem}.thumb.webp")


def _gerar_miniatura_pdf(caminho_pdf, caminho_miniatura):
    temporario = caminho_miniatura.with_name(f".{caminho_miniatura.name}.{uuid.uuid4().hex}.tmp")
    documento = pymupdf.open(caminho_pdf)
    try:
        if documento.page_count < 1:
            raise ValueError("PDF sem paginas.")
        pagina_pdf = documento.load_page(0)
        largura = max(float(pagina_pdf.rect.width), 1.0)
        altura = max(float(pagina_pdf.rect.height), 1.0)
        escala = max(0.25, min(2.0, 480.0 / largura, 360.0 / altura))
        pixmap = pagina_pdf.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
        imagem = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        try:
            imagem.thumbnail((480, 360), Image.Resampling.LANCZOS)
            imagem.save(temporario, format="WEBP", quality=82, method=4)
        finally:
            imagem.close()
        os.replace(temporario, caminho_miniatura)
    finally:
        documento.close()
        temporario.unlink(missing_ok=True)


def _remover_caminhos(caminhos):
    for caminho in caminhos:
        try:
            caminho.unlink(missing_ok=True)
            _miniatura_path(caminho).unlink(missing_ok=True)
        except OSError:
            pass


def _remover_arquivos_anexos(rows):
    for row in rows:
        try:
            caminho = _path_anexo(row["caminho_rel"])
            if caminho.exists() and caminho.is_file():
                caminho.unlink()
            _miniatura_path(caminho).unlink(missing_ok=True)
        except Exception:
            pass
