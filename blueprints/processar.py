import json
import logging
import os
import queue
import shutil
import threading
import time
import uuid

from flask import Blueprint, Response, current_app, jsonify, render_template, request, session, stream_with_context

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import import_history
from app_core import uploads


bp = Blueprint("processar", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


def _config_path():
    return current_app.config["CONFIG_PATH"]


def _upload_temp():
    return current_app.config["UPLOAD_TEMP"]


def limpar_uploads_antigos(max_age_hours=24):
    upload_root = os.path.abspath(_upload_temp())
    os.makedirs(upload_root, exist_ok=True)
    cutoff = time.time() - (max_age_hours * 3600)
    removidos = 0
    for entry in os.scandir(upload_root):
        if not entry.is_dir():
            continue
        try:
            uuid.UUID(entry.name)
        except ValueError:
            continue
        if entry.stat().st_mtime >= cutoff:
            continue
        job_path = os.path.abspath(entry.path)
        if os.path.commonpath([upload_root, job_path]) != upload_root:
            continue
        shutil.rmtree(job_path, ignore_errors=True)
        removidos += 1
    return removidos


def _job_dir(job_id):
    try:
        normalized = str(uuid.UUID(str(job_id)))
    except (ValueError, TypeError, AttributeError):
        return None
    if normalized != str(job_id).lower():
        return None

    upload_root = os.path.abspath(_upload_temp())
    job_path = os.path.abspath(os.path.join(upload_root, normalized))
    if os.path.commonpath([upload_root, job_path]) != upload_root:
        return None
    return job_path


def _cache_invalidator():
    return current_app.extensions.get("invalidar_cache_globals")


def get_db():
    return db_core.connect(_db_path())


def q1(sql, params=()):
    return db_core.query_one(_db_path(), sql, params)


def usuario_atual():
    return auth_core.usuario_atual(q1)


def nivel_min(nivel):
    return auth_core.nivel_min(nivel, usuario_atual)


def registrar_importacao(job_id, arquivos, status="upload", usuario=None):
    usuario = usuario or session.get("nome", "")
    return import_history.registrar_importacao(get_db, job_id, arquivos, status, usuario)


def atualizar_importacao(job_id, status, dry_run_ok=None, commit_ok=None, sumario=None, erro=None):
    return import_history.atualizar_importacao(
        get_db,
        job_id,
        status,
        dry_run_ok=dry_run_ok,
        commit_ok=commit_ok,
        sumario=sumario,
        erro=erro,
    )


def listar_importacoes_recentes(limite=8):
    return import_history.listar_importacoes_recentes(get_db, limite)


def _arquivos_do_job(job_dir):
    arquivos_trabalho = []
    arquivos_larvas = []
    for nome in os.listdir(job_dir):
        caminho = os.path.join(job_dir, nome)
        if nome.upper().startswith("LARVAS"):
            arquivos_larvas.append(caminho)
        else:
            arquivos_trabalho.append(caminho)
    return arquivos_trabalho, arquivos_larvas


def _sse_response(gerar):
    return Response(
        stream_with_context(gerar()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/processar")
@login_required
@nivel_min("admin")
def processar_page():
    try:
        limpar_uploads_antigos()
    except Exception:
        logging.exception("Falha ao limpar uploads temporarios antigos")
    importacoes = listar_importacoes_recentes(10)
    return render_template("processar.html", importacoes=importacoes)


@bp.route("/processar/iniciar", methods=["POST"])
@login_required
@nivel_min("admin")
def processar_iniciar():
    try:
        limpar_uploads_antigos()
    except Exception:
        logging.exception("Falha ao limpar uploads temporarios antigos")
    arquivos = request.files.getlist("arquivos")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    os.makedirs(job_dir, exist_ok=True)

    salvos = []
    rejeitados = []
    for arquivo in arquivos:
        valido, nome_seguro, motivo = uploads.validar_arquivo_xlsx(arquivo)
        if not valido:
            rejeitados.append(motivo)
            logging.warning("Upload rejeitado: %s | IP: %s", motivo, request.remote_addr)
            continue
        dest = os.path.join(job_dir, nome_seguro)
        arquivo.save(dest)
        salvos.append(nome_seguro)

    if not salvos:
        shutil.rmtree(job_dir, ignore_errors=True)
        msg = "Nenhum arquivo XLSX valido enviado."
        if rejeitados:
            msg += " Rejeitados: " + "; ".join(rejeitados)
        return jsonify({"erro": msg}), 400

    try:
        registrar_importacao(job_id, salvos, status="upload")
    except Exception:
        logging.exception("Falha ao registrar historico de importacao")

    return jsonify({"job_id": job_id, "arquivos": salvos})


@bp.route("/processar/stream/<job_id>", methods=["POST"])
@login_required
@nivel_min("admin")
def processar_stream(job_id):
    job_dir = _job_dir(job_id)
    if not job_dir or not os.path.isdir(job_dir):
        return "Job nao encontrado.", 404

    arquivos_trabalho, arquivos_larvas = _arquivos_do_job(job_dir)

    def gerar():
        from etl import Logger, processar_upload

        db_path = _db_path()
        config_path = _config_path()
        q_log = queue.Queue()
        done = threading.Event()
        result = [None]

        def cb(msg, tag):
            q_log.put((msg, tag))

        def worker():
            try:
                lg = Logger(callback=cb)
                result[0] = processar_upload(
                    arquivos_trabalho,
                    arquivos_larvas,
                    db_path,
                    config_path,
                    lg,
                    dry_run=True,
                )
            except Exception as exc:
                logging.exception("Falha no dry-run de importacao")
                q_log.put((f"Erro inesperado no processamento: {exc}", "erro"))
                result[0] = (False, [])
            finally:
                done.set()

        threading.Thread(target=worker, daemon=True).start()

        while not done.is_set() or not q_log.empty():
            try:
                msg, tag = q_log.get(timeout=0.2)
                payload = json.dumps({"msg": msg, "tag": tag}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            except Exception:
                pass

        ok, sumario = result[0] if isinstance(result[0], tuple) else (result[0], [])
        try:
            atualizar_importacao(
                job_id,
                "dry_run_ok" if ok else "dry_run_erro",
                dry_run_ok=ok,
                sumario=sumario,
            )
        except Exception:
            logging.exception("Falha ao atualizar historico de importacao")
        yield f"data: {json.dumps({'done': True, 'ok': ok, 'sumario': sumario, 'dry_run': True})}\n\n"

    return _sse_response(gerar)


@bp.route("/processar/confirmar/<job_id>", methods=["POST"])
@login_required
@nivel_min("admin")
def processar_confirmar(job_id):
    job_dir = _job_dir(job_id)
    if not job_dir or not os.path.isdir(job_dir):
        return jsonify({"erro": "Job nao encontrado ou expirado."}), 404

    arquivos_trabalho, arquivos_larvas = _arquivos_do_job(job_dir)

    def gerar():
        from etl import Logger, processar_upload

        db_path = _db_path()
        config_path = _config_path()
        cache_invalidator = _cache_invalidator()
        q_log = queue.Queue()
        done = threading.Event()
        result = [None]

        def cb(msg, tag):
            q_log.put((msg, tag))

        def worker():
            try:
                lg = Logger(callback=cb)
                result[0] = processar_upload(
                    arquivos_trabalho,
                    arquivos_larvas,
                    db_path,
                    config_path,
                    lg,
                    dry_run=False,
                )
            except Exception as exc:
                logging.exception("Falha na confirmacao de importacao")
                q_log.put((f"Erro inesperado ao gravar no banco: {exc}", "erro"))
                result[0] = (False, [])
            finally:
                done.set()

        threading.Thread(target=worker, daemon=True).start()

        while not done.is_set() or not q_log.empty():
            try:
                msg, tag = q_log.get(timeout=0.2)
                payload = json.dumps({"msg": msg, "tag": tag}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            except Exception:
                pass

        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass

        ok, sumario = result[0] if isinstance(result[0], tuple) else (result[0], [])
        if ok and cache_invalidator:
            cache_invalidator()
        try:
            atualizar_importacao(
                job_id,
                "confirmado" if ok else "erro_confirmacao",
                commit_ok=ok,
                sumario=sumario,
            )
        except Exception:
            logging.exception("Falha ao atualizar historico de importacao")
        yield f"data: {json.dumps({'done': True, 'ok': ok})}\n\n"

    return _sse_response(gerar)


@bp.route("/processar/cancelar/<job_id>", methods=["POST"])
@login_required
@nivel_min("admin")
def processar_cancelar(job_id):
    job_dir = _job_dir(job_id)
    if not job_dir:
        return jsonify({"erro": "Job nao encontrado ou expirado."}), 404
    try:
        shutil.rmtree(job_dir)
    except Exception:
        pass
    try:
        atualizar_importacao(job_id, "cancelado")
    except Exception:
        logging.exception("Falha ao atualizar historico de importacao")
    return jsonify({"ok": True})
