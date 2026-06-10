import json
import logging
import os
import queue
import shutil
import threading
import time
import uuid

from flask import Blueprint, Response, current_app, jsonify, render_template, request, session, stream_with_context

from app_core import audit
from app_core import auth as auth_core
from app_core import backup as backup_core
from app_core import db as db_core
from app_core import import_history
from app_core import kobo_api
from app_core import uploads


bp = Blueprint("processar", __name__)
login_required = auth_core.login_required

KOBO_DUPLICATE_TABLES = {
    "PE": "visitas",
    "TB": "visitas",
    "TBO": "visitas",
    "PVE": "visitas",
    "LARVAS": "resultados_laboratorio",
    "ESPOROTRICOSE": "esporotricose_visitas",
    "BRI": "bri_registros",
    "AMOSTRA_ANIMAIS": "amostras_animais",
    "RECOLHIMENTO": "recolhimentos",
}


def _db_path():
    return current_app.config["DB_PATH"]


def _config_path():
    return current_app.config["CONFIG_PATH"]


def _kobo_config_path():
    return current_app.config["KOBO_CONFIG_PATH"]


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
    kobo_config = kobo_api.public_config(kobo_api.load_config(_kobo_config_path()))
    return render_template("processar.html", importacoes=importacoes, kobo_config=kobo_config)


@bp.route("/api/kobo/config", methods=["GET", "POST"])
@login_required
@nivel_min("admin")
def kobo_config():
    if request.method == "GET":
        return jsonify(kobo_api.public_config(kobo_api.load_config(_kobo_config_path())))
    data = request.json or {}
    cfg = kobo_api.save_config(_kobo_config_path(), data, keep_token=True)
    audit.registrar_evento(
        get_db,
        "kobo_config_atualizada",
        entidade="kobo",
        detalhes={"server_url": cfg.get("server_url"), "assets": cfg.get("assets")},
    )
    return jsonify({"ok": True, "config": cfg})


@bp.route("/api/kobo/testar", methods=["POST"])
@login_required
@nivel_min("admin")
def kobo_testar():
    cfg = kobo_api.load_config(_kobo_config_path())
    try:
        result = kobo_api.test_connection(cfg)
    except kobo_api.KoboError as exc:
        return jsonify({"ok": False, "erro": str(exc)}), 400
    return jsonify(result)


@bp.route("/api/kobo/previa", methods=["POST"])
@login_required
@nivel_min("admin")
def kobo_previa():
    data = request.json or {}
    tipo = (data.get("tipo") or "").strip().upper()
    cfg = kobo_api.load_config(_kobo_config_path())
    assets = cfg.get("assets") or {}
    asset_uid = (data.get("asset_uid") or assets.get(tipo) or "").strip()
    if tipo not in kobo_api.ALL_TYPES:
        return jsonify({"erro": "Tipo de formulário inválido."}), 400
    try:
        records, bruto = kobo_api.fetch_submissions(
            cfg,
            asset_uid,
            limit=data.get("limite") or 100,
            start=data.get("inicio") or None,
            end=data.get("fim") or None,
        )
    except kobo_api.KoboError as exc:
        return jsonify({"erro": str(exc)}), 400

    uuids = [kobo_api.record_uuid(r) for r in records if kobo_api.record_uuid(r)]
    existentes = set()
    larvas_links = {}
    if uuids:
        tabela = KOBO_DUPLICATE_TABLES.get(tipo, "visitas")
        campo = "kobo_uuid"
        placeholders = ",".join("?" for _ in uuids)
        try:
            conn = get_db()
            rows = conn.execute(
                f"SELECT DISTINCT {campo} FROM {tabela} WHERE {campo} IN ({placeholders})",
                uuids,
            ).fetchall()
            existentes = {row[0] for row in rows}
        except Exception:
            existentes = set()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    if tipo == "LARVAS":
        chaves = set()
        for record in records:
            detalhes = kobo_api.record_details(tipo, record)
            tubo = (detalhes.get("tubo") or "").strip()
            data_coleta = (detalhes.get("data_coleta") or "").strip()[:10]
            if tubo and data_coleta:
                chaves.add((tubo, data_coleta))
        if chaves:
            try:
                conn = get_db()
                for tubo, data_coleta in chaves:
                    row = conn.execute(
                        """SELECT 1
                             FROM coletas c
                             JOIN visitas v ON v.id_visita = c.id_visita
                            WHERE TRIM(COALESCE(c.num_tubo,'')) = ?
                              AND v.data = ?
                            LIMIT 1""",
                        (tubo, data_coleta),
                    ).fetchone()
                    larvas_links[(tubo, data_coleta)] = bool(row)
            except Exception:
                larvas_links = {}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    resumo = kobo_api.summarize_submissions(records, existentes, tipo=tipo, larvas_links=larvas_links)
    audit.registrar_evento(
        get_db,
        "kobo_previa",
        entidade="kobo",
        entidade_id=tipo,
        detalhes={"asset_uid": asset_uid, "total": resumo["total"], "novos": resumo["novos"]},
    )
    return jsonify({
        "ok": True,
        "tipo": tipo,
        "asset_uid": asset_uid,
        "resumo": resumo,
        "next": bruto.get("next") if isinstance(bruto, dict) else None,
    })


def _kobo_existing_uuids(tipo, records):
    uuids = [kobo_api.record_uuid(r) for r in records if kobo_api.record_uuid(r)]
    if not uuids:
        return set()
    tabela = KOBO_DUPLICATE_TABLES.get(tipo, "visitas")
    placeholders = ",".join("?" for _ in uuids)
    try:
        conn = get_db()
        rows = conn.execute(
            f"SELECT DISTINCT kobo_uuid FROM {tabela} WHERE kobo_uuid IN ({placeholders})",
            uuids,
        ).fetchall()
        return {row[0] for row in rows}
    except Exception:
        return set()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _larvas_links_banco(chaves):
    links = {}
    if not chaves:
        return links
    try:
        conn = get_db()
        for tubo, data_coleta in chaves:
            row = conn.execute(
                """SELECT 1
                     FROM coletas c
                     JOIN visitas v ON v.id_visita = c.id_visita
                    WHERE TRIM(COALESCE(c.num_tubo,'')) = ?
                      AND v.data = ?
                    LIMIT 1""",
                (tubo, data_coleta),
            ).fetchone()
            if row:
                links[(tubo, data_coleta)] = "banco"
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return links


@bp.route("/api/kobo/lote-vetores-larvas", methods=["POST"])
@login_required
@nivel_min("admin")
def kobo_lote_vetores_larvas():
    data = request.json or {}
    cfg = kobo_api.load_config(_kobo_config_path())
    assets = cfg.get("assets") or {}
    limite = data.get("limite") or 100
    inicio = data.get("inicio") or None
    fim = data.get("fim") or None

    registros_por_tipo = {}
    erros = []
    for tipo in list(kobo_api.VISIT_TYPES) + ["LARVAS"]:
        asset_uid = (assets.get(tipo) or "").strip()
        if not asset_uid:
            erros.append(f"{tipo}: UID não configurado")
            registros_por_tipo[tipo] = []
            continue
        try:
            registros_por_tipo[tipo], _ = kobo_api.fetch_submissions(
                cfg,
                asset_uid,
                limit=limite,
                start=inicio,
                end=fim,
            )
        except kobo_api.KoboError as exc:
            erros.append(f"{tipo}: {exc}")
            registros_por_tipo[tipo] = []

    tubos_lote = {}
    for tipo in kobo_api.VISIT_TYPES:
        for record in registros_por_tipo.get(tipo, []):
            data_visita = kobo_api.record_date(record)
            for tubo in kobo_api.record_tubes(record, fallback_date=data_visita):
                key = (tubo["tubo"], tubo["data"])
                tubos_lote.setdefault(key, []).append({
                    "tipo": tipo,
                    "data": data_visita or tubo["data"],
                    "uuid": kobo_api.record_uuid(record),
                })

    larvas_chaves = set()
    for record in registros_por_tipo.get("LARVAS", []):
        detalhes = kobo_api.record_details("LARVAS", record)
        tubo = (detalhes.get("tubo") or "").strip()
        data_coleta = (detalhes.get("data_coleta") or "").strip()[:10]
        if tubo and data_coleta:
            larvas_chaves.add((tubo, data_coleta))

    larvas_links = _larvas_links_banco(larvas_chaves)
    vinculadas_lote = 0
    for key in larvas_chaves:
        if key not in larvas_links and key in tubos_lote:
            larvas_links[key] = "lote"
            vinculadas_lote += 1

    resumos = {}
    for tipo, records in registros_por_tipo.items():
        links = larvas_links if tipo == "LARVAS" else None
        resumos[tipo] = kobo_api.summarize_submissions(
            records,
            _kobo_existing_uuids(tipo, records),
            tipo=tipo,
            larvas_links=links,
        )

    larvas_resumo = resumos.get("LARVAS", {})
    vinculadas_banco = sum(1 for value in larvas_links.values() if value == "banco")
    audit.registrar_evento(
        get_db,
        "kobo_lote_vetores_larvas",
        entidade="kobo",
        detalhes={
            "inicio": inicio,
            "fim": fim,
            "limite": limite,
            "tubos_lote": len(tubos_lote),
            "larvas": larvas_resumo.get("total", 0),
            "pendencias": larvas_resumo.get("pendencias", 0),
        },
    )
    return jsonify({
        "ok": not erros,
        "erros": erros,
        "periodo": {"inicio": inicio, "fim": fim},
        "resumos": resumos,
        "tubos_lote": len(tubos_lote),
        "larvas_vinculadas_banco": vinculadas_banco,
        "larvas_vinculadas_lote": vinculadas_lote,
        "larvas_pendentes": larvas_resumo.get("pendencias", 0),
    })


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
        audit.registrar_evento(
            get_db,
            "importacao_upload",
            entidade="importacoes",
            entidade_id=job_id,
            detalhes={"arquivos": salvos},
        )
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
            audit.registrar_evento(
                get_db,
                "importacao_verificada",
                entidade="importacoes",
                entidade_id=job_id,
                detalhes={"ok": ok, "itens": len(sumario or [])},
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
        backup_pre_import = [None]

        def cb(msg, tag):
            q_log.put((msg, tag))

        def worker():
            try:
                lg = Logger(callback=cb)
                with backup_core.operacao_exclusiva():
                    backup_info = backup_core.criar_backup_sqlite(
                        db_path,
                        destino_dir=os.path.join(os.path.dirname(db_path), "backups"),
                        prefixo="pre_import",
                        manter=20,
                    )
                    cb(
                        f"Backup de seguranca criado antes da importacao: {os.path.basename(backup_info['arquivo'])}",
                        "ok",
                    )
                    backup_pre_import[0] = os.path.basename(backup_info["arquivo"])
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
            audit.registrar_evento(
                get_db,
                "importacao_confirmada",
                entidade="importacoes",
                entidade_id=job_id,
                detalhes={
                    "ok": ok,
                    "itens": len(sumario or []),
                    "backup_pre_import": backup_pre_import[0],
                },
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
        audit.registrar_evento(get_db, "importacao_cancelada", entidade="importacoes", entidade_id=job_id)
    except Exception:
        logging.exception("Falha ao atualizar historico de importacao")
    return jsonify({"ok": True})
