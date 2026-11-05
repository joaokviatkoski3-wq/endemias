import io
import json
import secrets
import string
from datetime import datetime, date
from pathlib import Path

import openpyxl
from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from openpyxl.styles import Font, PatternFill

from app_core import audit
from app_core import logging_rastreamento
from app_core import setores
from app_core import agentes as agentes_core
from app_core import auth as auth_core
from app_core import backup as backup_core
from app_core import backup_completo as backup_completo_core
from app_core import backup_exportacao
from app_core import blueprint_helpers as bh
from app_core import backup_health
from app_core import contaovos_health
from app_core import diagnostico as diagnostico_core
from app_core import dbml as dbml_core
from app_core import db as db_core
from app_core import import_history
from app_core import postgresql_backup
from app_core import sqlite_maintenance
from app_core import usuarios as usuarios_core
from app_core import version as version_core


bp = Blueprint("admin", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


def _filtros_auditoria():
    filtros = {
        "acao": request.args.get("acao", "").strip(),
        "usuario": request.args.get("usuario", "").strip(),
        "entidade": request.args.get("entidade", "").strip(),
        "d_ini": request.args.get("d_ini", "").strip(),
        "d_fim": request.args.get("d_fim", "").strip(),
    }
    filtros.update({k: request.args.get(k, "").strip()[:200] for k in
                    ("correlacao", "entidade_id", "rota", "metodo", "status", "resultado")})
    for key in ("d_ini", "d_fim"):
        if filtros[key]:
            try:
                filtros[key] = date.fromisoformat(filtros[key]).isoformat()
            except ValueError:
                abort(400, "Data inválida no filtro de logs.")
    if filtros["d_ini"] and filtros["d_fim"] and filtros["d_ini"] > filtros["d_fim"]:
        abort(400, "Período de logs fora de ordem.")
    return filtros


def _fonte_logs():
    origem = request.args.get("origem", "auditoria")
    if origem not in {"auditoria", "tecnico"}:
        abort(400)
    superadmin = (bh.usuario_atual() or {}).get("nivel") == "superadmin"
    if origem == "tecnico" and not superadmin:
        abort(403)
    atual = setores.atual() or "sistema"
    area = request.args.get("area", atual)
    if area not in {atual, "portal", "sistema"} or area != atual and not superadmin:
        abort(403)
    return origem, superadmin, area


def _consultar_logs(origem, filtros, area, pagina=1, por_pagina=50, limite=None):
    if origem == "tecnico":
        return logging_rastreamento.trilha(current_app.config, area).consultar(filtros, pagina, por_pagina, limite)
    return audit.consultar_eventos(bh.get_db, filtros, pagina, por_pagina, limite)


def _excel_safe(value):
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _bytes_label(value):
    value = int(value or 0)
    unidades = ("B", "KB", "MB", "GB")
    tamanho = float(value)
    for unidade in unidades:
        if tamanho < 1024 or unidade == unidades[-1]:
            return f"{tamanho:.1f} {unidade}" if unidade != "B" else f"{value} B"
        tamanho /= 1024


def _db_target():
    return db_core.configured_target(current_app.config)


def _sqlite_only_message(operacao):
    if _db_target().backend == "sqlite":
        return None
    return redirect(url_for(
        "admin.admin_sistema",
        backup_erro=(
            f"{operacao} indisponível com PostgreSQL: use o procedimento "
            "operacional homologado para esse banco."
        ),
    ))


def _saude_backups(target, backup_dir, backup_completo_dir, modo):
    """Avalia a saude dos backups PostgreSQL sem interromper a Central."""
    if target.backend != "postgresql":
        return None
    try:
        return backup_health.avaliar(
            backup_dir,
            backup_completo_dir,
            database=target.location,
            modo=modo,
        )
    except Exception:
        current_app.logger.exception("Falha ao avaliar a saude dos backups")
        motivo = "Nao foi possivel avaliar os backups nesta consulta."
        return {
            "backend": "postgresql",
            "modo": modo,
            "nivel": backup_health.NIVEL_DESCONHECIDO,
            "dump": {
                "nivel": backup_health.NIVEL_DESCONHECIDO,
                "titulo": "Dump diario nao verificado",
                "detalhe": motivo,
            },
            "completo": {
                "nivel": backup_health.NIVEL_DESCONHECIDO,
                "titulo": "Backup completo nao verificado",
                "detalhe": motivo,
            },
            "tarefas": [],
        }


def _listar_backups_ativos(destino, limite=20):
    if _db_target().backend == "postgresql":
        return postgresql_backup.listar_backups(destino, limite=limite)
    return backup_core.listar_backups(destino, limite=limite)


def _resolver_backup_ativo(destino, nome):
    if _db_target().backend == "postgresql":
        return postgresql_backup.resolver_backup(destino, nome)
    return backup_core.resolver_backup(destino, nome)


def _db_status():
    target = _db_target()
    if target.backend == "postgresql":
        status = {
            "backend": "postgresql",
            "path": target.location,
            "nome": target.location,
            "existe": True,
            "tamanho": "0 B",
            "wal": False,
            "wal_tamanho": "N/A",
            "shm": False,
            "shm_tamanho": "N/A",
            "integridade": "nao verificado",
            "tabelas": 0,
            "journal_mode": "PostgreSQL WAL",
            "synchronous": "Servidor",
            "busy_timeout_ms": 0,
            "wal_autocheckpoint": 0,
            "indices": 0,
            "indices_essenciais": {"total": 0, "presentes": 0, "faltantes": [], "ok": True},
            "metricas": db_core.connection_metrics(),
        }
        conn = None
        try:
            conn = bh.get_db()
            row = conn.execute(
                """SELECT current_database(), pg_database_size(current_database()),
                          current_setting('server_version')"""
            ).fetchone()
            status["nome"] = row[0]
            status["path"] = f"PostgreSQL: {row[0]} (servidor {row[2]})"
            status["tamanho"] = _bytes_label(row[1])
            status["tabelas"] = conn.execute(
                """SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema=current_schema() AND table_type='BASE TABLE'"""
            ).fetchone()[0]
            status["indices"] = conn.execute(
                "SELECT COUNT(*) FROM pg_indexes WHERE schemaname=current_schema()"
            ).fetchone()[0]
            status["integridade"] = "ok"
        except Exception as exc:
            status["existe"] = False
            status["integridade"] = "erro"
            status["erro"] = str(exc)
        finally:
            if conn is not None:
                conn.close()
        return status

    db_path = Path(current_app.config["DB_PATH"])
    wal_path = Path(str(db_path) + "-wal")
    shm_path = Path(str(db_path) + "-shm")
    status = {
        "backend": "sqlite",
        "path": str(db_path),
        "nome": db_path.name,
        "existe": db_path.exists(),
        "tamanho": _bytes_label(db_path.stat().st_size) if db_path.exists() else "0 B",
        "wal": wal_path.exists(),
        "wal_tamanho": _bytes_label(wal_path.stat().st_size) if wal_path.exists() else "0 B",
        "shm": shm_path.exists(),
        "shm_tamanho": _bytes_label(shm_path.stat().st_size) if shm_path.exists() else "0 B",
        "integridade": "nao verificado",
        "tabelas": 0,
        "journal_mode": "-",
        "synchronous": "-",
        "busy_timeout_ms": 0,
        "wal_autocheckpoint": 0,
        "indices": 0,
        "indices_essenciais": {"total": 0, "presentes": 0, "faltantes": [], "ok": False},
        "metricas": db_core.connection_metrics(),
    }
    if not db_path.exists():
        return status

    conn = bh.get_db()
    try:
        status["integridade"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        status["tabelas"] = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
        status["journal_mode"] = conn.execute("PRAGMA journal_mode").fetchone()[0].upper()
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
        status["synchronous"] = {0: "OFF", 1: "NORMAL", 2: "FULL", 3: "EXTRA"}.get(
            synchronous, str(synchronous)
        )
        status["busy_timeout_ms"] = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        status["wal_autocheckpoint"] = conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
        status["indices"] = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index'"
        ).fetchone()[0]
        status["indices_essenciais"] = sqlite_maintenance.performance_index_status(conn)
    finally:
        conn.close()
    return status


def _contagens_sistema():
    conn = bh.get_db()
    try:
        return {
            "usuarios_ativos": conn.execute("SELECT COUNT(*) FROM usuarios WHERE ativo=1").fetchone()[0],
            "visitas_total": conn.execute("SELECT COUNT(*) FROM visitas").fetchone()[0],
            "focos_pendentes": conn.execute(
                "SELECT COUNT(*) FROM focos_positivos WHERE status_notificacao='pendente' AND gera_notificacao=1"
            ).fetchone()[0],
            "eventos_auditoria": conn.execute(
                "SELECT COUNT(*) FROM auditoria_eventos"
            ).fetchone()[0] if db_core.table_exists(conn, "auditoria_eventos") else 0,
        }
    finally:
        conn.close()


@bp.route("/admin/usuarios")
@login_required
@nivel_min("admin")
def admin_usuarios():
    usuarios = usuarios_core.listar(bh.db_target())
    agentes = agentes_core.listar(bh.db_target(), {"status": "ativos"})
    return render_template(
        "admin_usuarios.html", usuarios=usuarios, agentes=agentes
    )


@bp.route("/admin/sistema")
@login_required
@nivel_min("superadmin")
def admin_sistema():
    target = _db_target()
    db_path = Path(target.location) if target.backend == "sqlite" else target.location
    backup_dir = Path(current_app.config["BACKUP_DIR"])
    backup_completo_dir = Path(current_app.config["BACKUP_COMPLETO_DIR"])
    backups = _listar_backups_ativos(backup_dir, limite=20)
    backups_completos = backup_completo_core.listar_backups_completos(backup_completo_dir, limite=20)
    importacoes = import_history.listar_importacoes_recentes(bh.get_db, limite=5)
    eventos = audit.listar_eventos(bh.get_db, limite=8, todos_setores=True)
    saude_backups = _saude_backups(
        target,
        backup_dir,
        backup_completo_dir,
        backup_health.MODO_RAPIDO,
    )
    contaovos_status = contaovos_health.read_status()
    conn = bh.get_db()
    try:
        diagnostico = diagnostico_core.gerar(
            conn,
            db_path=db_path,
            backup_dir=backup_dir,
            backup_completo_dir=backup_completo_dir,
            database=target.location,
            saude_backups=saude_backups,
            contaovos_status=contaovos_status,
        )
    finally:
        conn.close()
    return render_template(
        "admin_sistema.html",
        saude_backups=saude_backups,
        contaovos_status=contaovos_status,
        db_status=_db_status(),
        contagens=_contagens_sistema(),
        backups=backups,
        backups_completos=backups_completos,
        diagnostico=diagnostico,
        backup_dir=str(backup_dir),
        backup_completo_dir=str(backup_completo_dir),
        importacoes=importacoes,
        eventos=eventos,
        app_version=version_core.APP_VERSION_LABEL,
        instance_dir=current_app.config["INSTANCE_DIR"],
        upload_temp=current_app.config["UPLOAD_TEMP"],
        log_path=current_app.config["LOG_PATH"],
        backup_ok=request.args.get("backup_ok", "").strip(),
        backup_erro=request.args.get("backup_erro", "").strip(),
        format_bytes=_bytes_label,
        sqlite_operations=target.backend == "sqlite",
        postgresql_operations=target.backend == "postgresql",
        database_name=target.location,
    )


@bp.route("/api/admin/sistema/diagnostico")
@login_required
@nivel_min("superadmin")
def api_admin_diagnostico():
    target = _db_target()
    db_path = Path(target.location) if target.backend == "sqlite" else target.location
    backup_dir = Path(current_app.config["BACKUP_DIR"])
    backup_completo_dir = Path(current_app.config["BACKUP_COMPLETO_DIR"])
    completo = request.args.get("completo", "").strip().lower() in {"1", "sim", "true", "completo"}
    saude_backups = _saude_backups(
        target,
        backup_dir,
        backup_completo_dir,
        backup_health.MODO_COMPLETO if completo else backup_health.MODO_RAPIDO,
    )
    contaovos_status = contaovos_health.read_status()
    conn = bh.get_db()
    try:
        return jsonify(
            diagnostico_core.gerar(
                conn,
                db_path=db_path,
                backup_dir=backup_dir,
                completo=completo,
                backup_completo_dir=backup_completo_dir,
                database=target.location,
                saude_backups=saude_backups,
                contaovos_status=contaovos_status,
            )
        )
    finally:
        conn.close()


@bp.route("/admin/sistema/backups/criar", methods=["POST"])
@login_required
@nivel_min("superadmin")
def admin_criar_backup():
    target = _db_target()
    backup_dir = Path(current_app.config["BACKUP_DIR"])
    try:
        with backup_core.operacao_exclusiva():
            if target.backend == "postgresql":
                info = postgresql_backup.criar_backup_postgresql(
                    target.location,
                    destino_dir=backup_dir,
                    prefixo="endemias",
                    manter=20,
                )
            else:
                info = backup_core.criar_backup_sqlite(
                    Path(target.location),
                    destino_dir=backup_dir,
                    prefixo="endemias",
                    manter=20,
                )
        audit.registrar_evento(
            bh.get_db,
            "backup_criado",
            entidade="backups",
            entidade_id=Path(info["arquivo"]).name,
            detalhes={
                "arquivo": Path(info["arquivo"]).name,
                "tamanho_bytes": info["tamanho_bytes"],
                "integridade": info["integridade"],
                "backend": target.backend,
            },
        )
        msg = f"Backup criado: {Path(info['arquivo']).name}"
        return redirect(url_for("admin.admin_sistema", backup_ok=msg))
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao criar backup: {exc}"))


@bp.route("/admin/sistema/backups/restaurar", methods=["POST"])
@login_required
@nivel_min("superadmin")
def admin_restaurar_backup():
    target = _db_target()
    backup_dir = Path(current_app.config["BACKUP_DIR"])
    nome_backup = request.form.get("backup", "").strip()
    try:
        with backup_core.operacao_exclusiva():
            backup_path = _resolver_backup_ativo(backup_dir, nome_backup)
            if target.backend == "postgresql":
                info = postgresql_backup.restaurar_backup_postgresql(
                    target.location,
                    backup_path,
                    confirmacao=request.form.get("confirmacao", ""),
                    backup_dir=backup_dir,
                    manter=20,
                )
                seguranca_nome = info["backup_seguranca"]
            else:
                seguranca = backup_core.criar_backup_sqlite(
                    Path(target.location),
                    destino_dir=backup_dir,
                    prefixo="pre_restore",
                    manter=20,
                )
                info = backup_core.restaurar_backup_sqlite(
                    Path(target.location),
                    backup_path,
                )
                seguranca_nome = Path(seguranca["arquivo"]).name
        audit.registrar_evento(
            bh.get_db,
            "backup_restaurado",
            entidade="backups",
            entidade_id=backup_path.name,
            detalhes={
                "backup_restaurado": backup_path.name,
                "backup_seguranca": seguranca_nome,
                "integridade": info["integridade"],
                "backend": target.backend,
            },
        )
        msg = f"Backup restaurado: {backup_path.name}. Copia de seguranca criada: {seguranca_nome}"
        return redirect(url_for("admin.admin_sistema", backup_ok=msg))
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao restaurar backup: {exc}"))


@bp.route("/admin/sistema/backups/baixar/<nome_backup>", methods=['GET','POST'])
@login_required
@nivel_min("superadmin")
def admin_baixar_backup(nome_backup):
    backup_dir = Path(current_app.config["BACKUP_DIR"])
    try:
        backup_path = _resolver_backup_ativo(backup_dir, nome_backup)
        return backup_exportacao.resposta_download(backup_path)
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao baixar backup: {exc}"))


@bp.route("/admin/sistema/dbml")
@login_required
@nivel_min("superadmin")
def admin_baixar_dbml():
    bloqueio = _sqlite_only_message("Exportação DBML SQLite")
    if bloqueio:
        return bloqueio
    try:
        db_path = Path(current_app.config["DB_PATH"])
        conteudo = dbml_core.gerar_dbml(db_path)
        nome = f"{db_path.stem}_schema.dbml"
        audit.registrar_evento(
            bh.get_db,
            "dbml_baixado",
            entidade="banco",
            entidade_id=db_path.name,
            detalhes={"arquivo": nome},
        )
        return send_file(
            io.BytesIO(conteudo.encode("utf-8")),
            as_attachment=True,
            download_name=nome,
            mimetype="text/plain; charset=utf-8",
        )
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao gerar DBML: {exc}"))


@bp.route("/admin/sistema/backups/excluir", methods=["POST"])
@login_required
@nivel_min("superadmin")
def admin_excluir_backup():
    backup_dir = Path(current_app.config["BACKUP_DIR"])
    nome_backup = request.form.get("backup", "").strip()
    try:
        with backup_core.operacao_exclusiva():
            backup_path = _resolver_backup_ativo(backup_dir, nome_backup)
            backup_core.excluir_backup(backup_path)
        audit.registrar_evento(
            bh.get_db,
            "backup_excluido",
            entidade="backups",
            entidade_id=backup_path.name,
            detalhes={"arquivo": backup_path.name},
        )
        return redirect(url_for("admin.admin_sistema", backup_ok=f"Backup excluido: {backup_path.name}"))
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao excluir backup: {exc}"))


@bp.route("/admin/sistema/backups-completos/criar", methods=["POST"])
@login_required
@nivel_min("superadmin")
def admin_criar_backup_completo():
    target = _db_target()
    try:
        with backup_core.operacao_exclusiva():
            info = backup_completo_core.criar_backup_completo(
                destino_dir=current_app.config["BACKUP_COMPLETO_DIR"],
                manter=10,
                db_path=current_app.config["DB_PATH"],
                raiz=current_app.config["INSTANCE_DIR"],
                anexos_dir=current_app.config["ANEXOS_DIR"],
                kobo_config_path=current_app.config["KOBO_CONFIG_PATH"],
                secret_key_path=current_app.config["SECRET_KEY_PATH"],
                db_target=target,
            )
        audit.registrar_evento(
            bh.get_db,
            "backup_completo_criado",
            entidade="backups_completos",
            entidade_id=info["nome"],
            detalhes={
                "arquivo": info["nome"],
                "tamanho_bytes": info["tamanho_bytes"],
                "integridade_banco": info["integridade_banco"],
                "destino": current_app.config["BACKUP_COMPLETO_DIR"],
                "backend": target.backend,
            },
        )
        return redirect(url_for("admin.admin_sistema", backup_ok=f"Backup completo criado: {info['nome']}"))
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao criar backup completo: {exc}"))


@bp.route("/admin/sistema/backups-completos/baixar/<nome_backup>", methods=['GET','POST'])
@login_required
@nivel_min("superadmin")
def admin_baixar_backup_completo(nome_backup):
    try:
        backup_path = backup_completo_core.resolver_backup_completo(
            current_app.config["BACKUP_COMPLETO_DIR"],
            nome_backup,
        )
        return backup_exportacao.resposta_download(backup_path)
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao baixar backup completo: {exc}"))


@bp.route("/admin/sistema/backups-completos/excluir", methods=["POST"])
@login_required
@nivel_min("superadmin")
def admin_excluir_backup_completo():
    nome_backup = request.form.get("backup", "").strip()
    try:
        with backup_core.operacao_exclusiva():
            backup_path = backup_completo_core.resolver_backup_completo(
                current_app.config["BACKUP_COMPLETO_DIR"],
                nome_backup,
            )
            backup_completo_core.excluir_backup_completo(backup_path)
        audit.registrar_evento(
            bh.get_db,
            "backup_completo_excluido",
            entidade="backups_completos",
            entidade_id=backup_path.name,
            detalhes={"arquivo": backup_path.name},
        )
        return redirect(url_for("admin.admin_sistema", backup_ok=f"Backup completo excluido: {backup_path.name}"))
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao excluir backup completo: {exc}"))


@bp.route("/admin/auditoria")
@login_required
@nivel_min("admin")
def admin_auditoria():
    origem, superadmin, area = _fonte_logs()
    filtros = _filtros_auditoria()
    pagina = bh.request_int_arg("pagina", 1, minimo=1, maximo=100000)
    por_pagina = bh.request_int_arg("por_pagina", 50, minimo=25, maximo=100)
    if por_pagina not in {25, 50, 100}:
        por_pagina = 50
    result = _consultar_logs(origem, filtros, area, pagina, por_pagina)
    total = result["total"]
    paginas = max(1, (total+por_pagina-1)//por_pagina)
    if pagina > paginas:
        pagina = paginas
        result = _consultar_logs(origem, filtros, area, pagina, por_pagina)
    writer = logging_rastreamento.trilha(current_app.config, area)
    args = {k:v for k,v in filtros.items() if v}
    args.update(origem=origem, area=area, por_pagina=por_pagina)
    return render_template("admin_auditoria.html", eventos=result["registros"], filtros=filtros,
        origem=origem, superadmin=superadmin, area=area, total=total, pagina=pagina, paginas=paginas,
        por_pagina=por_pagina, inicio=(pagina-1)*por_pagina+1 if total else 0,
        fim=min(pagina*por_pagina,total), incompleto=result.get("incompleto",False),
        falhas=writer.falhas if origem=="tecnico" else 0,
        anterior=url_for("admin.admin_auditoria", **args, pagina=pagina-1),
        proxima=url_for("admin.admin_auditoria", **args, pagina=pagina+1),
        exportar=url_for("admin.admin_auditoria_exportar", **args),
        limite_exportacao=logging_rastreamento.MAX_EXPORTACAO)


@bp.route("/admin/auditoria/exportar")
@login_required
@nivel_min("admin")
def admin_auditoria_exportar():
    origem, _, area = _fonte_logs()
    filtros = _filtros_auditoria()
    result = _consultar_logs(origem, filtros, area, limite=logging_rastreamento.MAX_EXPORTACAO)
    if result.get("incompleto"):
        return "Não foi possível ler todos os arquivos. A exportação não foi gerada.", 503
    if result["total"] > logging_rastreamento.MAX_EXPORTACAO:
        return f"O filtro encontrou {result['total']} registros. Reduza o período ou use mais filtros; o limite por exportação é {logging_rastreamento.MAX_EXPORTACAO}. Nenhum arquivo parcial foi gerado.", 400
    eventos = result["registros"]
    if sum(len(json.dumps(ev, ensure_ascii=False,default=str).encode('utf-8')) for ev in eventos) > 16*1024*1024:
        return "O conteúdo excede 16 MiB por exportação. Reduza o período; nenhum arquivo parcial foi gerado.", 400
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Auditoria"
    headers = ["Data", "Acao", "Usuario", "IP", "Entidade", "Entidade ID", "Detalhes", "Setor", "Correlacao", "Rota", "Metodo", "Status", "Duracao ms"]
    fill = PatternFill("solid", fgColor="1A4FBA")
    for col, title in enumerate(headers, 1):
        cell = ws.cell(1, col, title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
    for row_idx, ev in enumerate(eventos, 2):
        detalhes = json.dumps(ev if origem=="tecnico" else ev.get("detalhes") or {}, ensure_ascii=False, sort_keys=True)
        if len(detalhes)>32000:
            return "Um detalhe excede o tamanho seguro de uma célula. Restrinja o filtro; nenhum arquivo parcial foi gerado.", 400
        rastro = ev.get("rastro") or ev
        values = [
            ev.get("criado_em", ev.get("instante", "")),
            ev.get("acao", ev.get("tipo", "")),
            ev.get("usuario_nome", ev.get("ator", "")),
            ev.get("ip", ""),
            ev.get("entidade", ""),
            ev.get("entidade_id", ""),
            detalhes,
            ev.get("setor", ""), rastro.get("correlacao", ""), rastro.get("rota", ""),
            rastro.get("metodo", ""), ev.get("status", ""), ev.get("duracao_ms", ""),
        ]
        for col, value in enumerate(values, 1):
            ws.cell(row_idx, col, _excel_safe(value))
    for col in ws.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"auditoria_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.route("/admin/usuarios/presenca")
@login_required
@nivel_min("admin")
def presencas():
    from app_core import presenca
    return jsonify(presenca.resumo(bh.db_target()))


@bp.route("/admin/usuarios/criar", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_criar_usuario():
    dados = request.form.to_dict()
    erro = None
    try:
        novo_id = usuarios_core.criar(bh.db_target(), dados, actor_id=session["uid"])
        somente_laboratorio = (
            1 if dados.get("somente_laboratorio") == "1" else 0
        )
        acesso_laboratorio = (
            1
            if somente_laboratorio
            or dados.get("acesso_laboratorio") == "1"
            else 0
        )
        audit.registrar_evento(
            bh.get_db,
            "usuario_criado",
            entidade="usuarios",
            entidade_id=novo_id,
            detalhes={
                "usuario": dados.get("usuario", "").strip().lower(),
                "nome": dados.get("nome", "").strip(),
                "nivel": dados.get("nivel", "visualizador"),
                "acesso_laboratorio": acesso_laboratorio,
                "somente_laboratorio": somente_laboratorio,
                "id_agente": dados.get("id_agente") or None,
            },
        )
    except Exception as exc:
        erro = f"Erro: {exc}"
    if erro:
        usuarios = usuarios_core.listar(bh.db_target())
        agentes = agentes_core.listar(bh.db_target(), {"status": "ativos"})
        return render_template(
            "admin_usuarios.html", usuarios=usuarios, agentes=agentes, erro=erro
        )
    return redirect(url_for("admin.admin_usuarios"))


@bp.route("/admin/usuarios/<int:uid>/editar", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_editar_usuario(uid):
    campo = request.form.get("campo")
    valor = request.form.get("valor", "").strip()
    try:
        anterior, novo = usuarios_core.editar(
            bh.db_target(),
            uid,
            campo,
            valor,
            usuario_atual_id=session.get("uid"),
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    detalhes = {"campo": campo}
    detalhes.update({
        "usuario": anterior["usuario"],
        "valor_antigo": anterior.get(campo),
        "valor_novo": novo,
    })
    audit.registrar_evento(
        bh.get_db,
        "usuario_editado",
        entidade="usuarios",
        entidade_id=uid,
        detalhes=detalhes,
    )
    return jsonify({"ok": True})


@bp.route("/admin/usuarios/<int:uid>/recuperacao-senha", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_gerar_recuperacao(uid):
    from flask import current_app
    from app_core import recuperacao_senha

    chave = "gerar-recuperacao:" + str(session["uid"])
    if auth_core.login_bloqueado_db(bh.get_db, chave, limite=20):
        return jsonify({"erro": "Limite de links atingido. Aguarde 15 minutos."}), 429
    base = current_app.config.get("RECOVERY_BASE_URL", "https://endemias.vsatt.com.br")
    if current_app.config.get('SETORES_ENABLED'):
        from app_core import setores
        target_user=bh.q1('SELECT * FROM usuarios WHERE id_usuario=?',(uid,))
        sector=(target_user or {}).get('setor','endemias') if (target_user or {}).get('nivel') not in {'admin','superadmin'} else setores.atual()
        base='https://'+sector+'.'+current_app.config['DOMINIO_BASE']
    try:
        recuperacao_senha.url_publica("", base)

        def registrar(conn, usuario):
            audit.registrar_evento(bh.get_db, "usuario_recuperacao_gerada", entidade="usuarios",
                entidade_id=uid, detalhes={"usuario": usuario["usuario"], "validade_minutos": 15}, conn=conn)

        token = recuperacao_senha.gerar(bh.db_target(), uid, session["uid"], auditar=registrar)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    auth_core.registrar_login_falha_db(bh.get_db, chave)
    return jsonify({"ok": True, "url": recuperacao_senha.url_publica(token, base), "validade_minutos": 15})


@bp.route("/admin/usuarios/<int:uid>/resetar-senha", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_resetar_senha(uid):
    tamanho = max(auth_core.PASSWORD_MIN_LENGTH, 12)
    nova = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(tamanho))
    try:
        alvo = usuarios_core.resetar_senha(bh.db_target(), uid, nova, actor_id=session["uid"])
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    audit.registrar_evento(
        bh.get_db,
        "usuario_senha_resetada",
        entidade="usuarios",
        entidade_id=uid,
        detalhes={"usuario": alvo["usuario"], "nome": alvo["nome"]},
    )
    return jsonify({"ok": True, "senha": nova})
