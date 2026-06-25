import csv
import io
import mimetypes
import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import esporotricose as esporotricose_core
from app_core import utils as utils_core


bp = Blueprint("esporotricose", __name__)
login_required = auth_core.login_required

ANEXO_EXTENSOES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".xls", ".xlsx"}
ANEXO_MAX_BYTES = 20 * 1024 * 1024


def _db_path():
    return current_app.config["DB_PATH"]


def _localidades():
    conn = db_core.connect(_db_path())
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
    conn = db_core.connect(_db_path())
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
    return render_template(
        "esporotricose.html",
        d_ini=request.args.get("d_ini", utils_core.data_n_dias(365)),
        d_fim=request.args.get("d_fim", utils_core.hoje()),
        localidades=_localidades(),
        agentes=_agentes(),
    )


@bp.route("/esporotricose/doentes/novo")
@login_required
def page_doente_novo():
    return render_template(
        "esporotricose_doente_form.html",
        animal=None,
        modo="novo",
        status_opcoes=esporotricose_core.status_doentes(_db_path()),
        localidades=_localidades(),
    )


@bp.route("/esporotricose/doentes/<int:id_animal>")
@login_required
def page_doente_detalhe(id_animal):
    animal = esporotricose_core.obter_doente(_db_path(), id_animal)
    if not animal:
        abort(404)
    return render_template(
        "esporotricose_doente_detalhe.html",
        animal=animal,
        status_opcoes=esporotricose_core.status_doentes(_db_path()),
        status_class=_status_doente_class(animal.get("status")),
    )


@bp.route("/esporotricose/doentes/<int:id_animal>/editar")
@login_required
def page_doente_editar(id_animal):
    animal = esporotricose_core.obter_doente(_db_path(), id_animal)
    if not animal:
        abort(404)
    return render_template(
        "esporotricose_doente_form.html",
        animal=animal,
        modo="editar",
        status_opcoes=esporotricose_core.status_doentes(_db_path()),
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
    return jsonify(esporotricose_core.resumo(_db_path(), filtros))


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
    }
    return jsonify(esporotricose_core.listar_visitas(_db_path(), filtros))


@bp.route("/api/esporotricose/animais")
@login_required
def api_animais():
    filtros = {
        "d_ini": request.args.get("d_ini", ""),
        "d_fim": request.args.get("d_fim", ""),
        "localidade": request.args.get("localidade", ""),
        "visita": request.args.get("visita", ""),
        "agente": request.args.get("agente", ""),
        "busca": request.args.get("busca", ""),
        "especie": request.args.get("especie", ""),
        "feridas": request.args.get("feridas", ""),
        "vacinado": request.args.get("vacinado", ""),
        "castrado": request.args.get("castrado", ""),
        "ambiente": request.args.get("ambiente", ""),
        "motivo_atencao": request.args.get("motivo_atencao", ""),
        "prioritarios": request.args.get("prioritarios", ""),
    }
    return jsonify(esporotricose_core.listar_animais(_db_path(), filtros))


@bp.route("/api/esporotricose/visitas/<id_visita>", methods=["PUT"])
@login_required
def api_atualizar_visita(id_visita):
    try:
        dados = request.get_json(silent=True) or {}
        resultado = esporotricose_core.atualizar_visita(_db_path(), id_visita, dados)
        return jsonify(resultado)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        import logging
        logging.exception("Erro ao atualizar visita esporotricose")
        return jsonify({"erro": "Erro interno do servidor."}), 500


@bp.route("/api/esporotricose/animais/<id_animal>", methods=["PUT"])
@login_required
def api_atualizar_animal(id_animal):
    try:
        dados = request.get_json(silent=True) or {}
        resultado = esporotricose_core.atualizar_animal(_db_path(), id_animal, dados)
        return jsonify(resultado)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    except Exception:
        import logging
        logging.exception("Erro ao atualizar animal esporotricose")
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
    return jsonify(esporotricose_core.resumo_localidades(_db_path(), filtros))


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
    return jsonify(esporotricose_core.dashboard(_db_path(), filtros))


@bp.route("/api/esporotricose/doentes")
@login_required
def api_doentes():
    filtros = {
        "busca": request.args.get("busca", ""),
        "status": request.args.get("status", ""),
        "localidade": request.args.get("localidade", ""),
        "bloqueio": request.args.get("bloqueio", ""),
        "pedido_zoomed": request.args.get("pedido_zoomed", ""),
        "baixa_zoomed": request.args.get("baixa_zoomed", ""),
    }
    return jsonify(esporotricose_core.listar_doentes(_db_path(), filtros))


@bp.route("/esporotricose/doentes/casos.csv")
@login_required
def download_doentes_csv():
    campos = [
        "id_animal_doente",
        "animal",
        "tutor",
        "telefone",
        "sexo",
        "status",
        "data_notificacao",
        "primeira_notificacao",
        "ultima_notificacao",
        "ultima_receita",
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
        "capsulas_entregues",
        "entregas",
        "anexos",
        "observacoes_entomologica",
    ]
    rows = esporotricose_core.listar_doentes_csv(_db_path(), {})
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


@bp.route("/api/esporotricose/doentes/status", methods=["GET", "POST"])
@login_required
def api_doentes_status():
    if request.method == "POST":
        nome = (request.json or {}).get("nome")
        if not nome:
            return jsonify({"erro": "Informe o status."}), 400
        esporotricose_core.salvar_status_doente(_db_path(), nome)
    return jsonify({"registros": esporotricose_core.status_doentes(_db_path())})


@bp.route("/api/esporotricose/doentes/<int:id_animal>", methods=["GET", "PUT"])
@login_required
def api_doente(id_animal):
    if request.method == "PUT":
        try:
            dados = dict(request.json or {})
            dados["id_animal_doente"] = id_animal
            esporotricose_core.salvar_doente(_db_path(), dados)
        except esporotricose_core.ValidationError as exc:
            return jsonify({"erro": str(exc)}), 400
    item = esporotricose_core.obter_doente(_db_path(), id_animal)
    if not item:
        return jsonify({"erro": "Animal não encontrado."}), 404
    return jsonify(item)


@bp.route("/api/esporotricose/doentes", methods=["POST"])
@login_required
def api_criar_doente():
    try:
        id_animal = esporotricose_core.salvar_doente(_db_path(), request.json or {})
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify(esporotricose_core.obter_doente(_db_path(), id_animal)), 201


@bp.route("/api/esporotricose/doentes/<int:id_animal>/receitas", methods=["POST"])
@login_required
def api_salvar_receita_doente(id_animal):
    try:
        id_receita = esporotricose_core.salvar_receita_doente(_db_path(), id_animal, request.json or {})
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "id_receita": id_receita, "animal": esporotricose_core.obter_doente(_db_path(), id_animal)}), 201


@bp.route("/api/esporotricose/doentes/receitas/<int:id_receita>", methods=["DELETE"])
@login_required
def api_excluir_receita_doente(id_receita):
    try:
        id_animal = esporotricose_core.excluir_receita_doente(_db_path(), id_receita)
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 404
    return jsonify({"ok": True, "id_animal_doente": id_animal})


@bp.route("/api/esporotricose/doentes/receitas/<int:id_receita>/entregas", methods=["POST"])
@login_required
def api_salvar_entrega_doente(id_receita):
    try:
        id_entrega = esporotricose_core.salvar_entrega_doente(_db_path(), id_receita, request.json or {})
    except esporotricose_core.ValidationError as exc:
        return jsonify({"erro": str(exc)}), 400
    return jsonify({"ok": True, "id_entrega": id_entrega}), 201


@bp.route("/api/esporotricose/doentes/entregas/<int:id_entrega>", methods=["PUT", "DELETE"])
@login_required
def api_excluir_entrega_doente(id_entrega):
    if request.method == "PUT":
        try:
            esporotricose_core.atualizar_entrega_doente(_db_path(), id_entrega, request.json or {})
        except esporotricose_core.ValidationError as exc:
            return jsonify({"erro": str(exc)}), 400
        return jsonify({"ok": True})
    esporotricose_core.excluir_entrega_doente(_db_path(), id_entrega)
    return jsonify({"ok": True})


@bp.route("/api/esporotricose/doentes/<int:id_animal>/anexos", methods=["GET", "POST"])
@login_required
def api_doente_anexos(id_animal):
    animal = esporotricose_core.obter_doente(_db_path(), id_animal)
    if not animal:
        return jsonify({"erro": "Animal não encontrado."}), 404
    if request.method == "GET":
        return jsonify({"anexos": animal.get("anexos", [])})
    arquivos = request.files.getlist("arquivos")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400
    destino_dir = _doente_anexos_dir(id_animal)
    usuario = auth_core.usuario_atual(lambda sql, params=(): db_core.query_one(_db_path(), sql, params)) or {}
    salvos = []
    conn = db_core.connect(_db_path())
    try:
        esporotricose_core.ensure_schema(conn)
        for arquivo in arquivos:
            meta, erro = _validar_upload_anexo(arquivo)
            if erro:
                return jsonify({"erro": erro}), 400
            nome_arquivo = f"{uuid.uuid4().hex}{meta['ext']}"
            caminho = destino_dir / nome_arquivo
            arquivo.save(caminho)
            mime_type = mimetypes.guess_type(meta["nome_seguro"])[0] or "application/octet-stream"
            caminho_rel = str(caminho.relative_to(_anexos_base_dir())).replace("\\", "/")
            cur = conn.execute(
                """INSERT INTO esporotricose_doentes_anexos
                   (id_animal_doente, id_receita, nome_original, nome_arquivo, caminho_rel,
                    mime_type, tamanho, criado_por, criado_em)
                   VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    id_animal, meta["nome_original"], nome_arquivo, caminho_rel, mime_type,
                    meta["tamanho"], usuario.get("nome") or "sistema",
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            salvos.append(cur.lastrowid)
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
        return jsonify({"erro": "Banco de dados ocupado. Tente novamente."}), 503
    finally:
        conn.close()
    return jsonify({"ok": True, "ids": salvos, "anexos": esporotricose_core.obter_doente(_db_path(), id_animal).get("anexos", [])}), 201


@bp.route("/api/esporotricose/doentes/anexos/<int:id_anexo>", methods=["DELETE"])
@login_required
def api_excluir_anexo_doente(id_anexo):
    conn = db_core.connect(_db_path())
    try:
        row = conn.execute("SELECT * FROM esporotricose_doentes_anexos WHERE id_anexo=?", (id_anexo,)).fetchone()
        if not row:
            return jsonify({"erro": "Anexo não encontrado."}), 404
        conn.execute("DELETE FROM esporotricose_doentes_anexos WHERE id_anexo=?", (id_anexo,))
        conn.commit()
    finally:
        conn.close()
    _remover_arquivos_anexos([row])
    return jsonify({"ok": True})


@bp.route("/esporotricose/doentes/anexos/<int:id_anexo>/download")
@login_required
def baixar_anexo_doente(id_anexo):
    conn = db_core.connect(_db_path())
    try:
        row = conn.execute("SELECT * FROM esporotricose_doentes_anexos WHERE id_anexo=?", (id_anexo,)).fetchone()
    finally:
        conn.close()
    if not row:
        abort(404)
    caminho = _path_anexo(row["caminho_rel"])
    if not caminho.exists() or not caminho.is_file():
        abort(404)
    inline = request.args.get("inline") == "1"
    return send_file(
        caminho,
        mimetype=row.get("mime_type") or None,
        as_attachment=not inline,
        download_name=row["nome_original"],
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


def _remover_arquivos_anexos(rows):
    for row in rows:
        try:
            caminho = _path_anexo(row["caminho_rel"])
            if caminho.exists() and caminho.is_file():
                caminho.unlink()
        except Exception:
            pass
