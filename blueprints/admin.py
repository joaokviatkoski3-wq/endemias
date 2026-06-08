import io
import json
import secrets
import string
from datetime import datetime
from pathlib import Path

import openpyxl
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from openpyxl.styles import Font, PatternFill

from app_core import audit
from app_core import auth as auth_core
from app_core import backup as backup_core
from app_core import blueprint_helpers as bh
from app_core import dbml as dbml_core
from app_core import import_history
from app_core import version as version_core


bp = Blueprint("admin", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


def _filtros_auditoria():
    return {
        "acao": request.args.get("acao", "").strip(),
        "usuario": request.args.get("usuario", "").strip(),
        "entidade": request.args.get("entidade", "").strip(),
        "d_ini": request.args.get("d_ini", "").strip(),
        "d_fim": request.args.get("d_fim", "").strip(),
    }


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


def _db_status():
    db_path = Path(current_app.config["DB_PATH"])
    wal_path = Path(str(db_path) + "-wal")
    shm_path = Path(str(db_path) + "-shm")
    status = {
        "path": str(db_path),
        "nome": db_path.name,
        "existe": db_path.exists(),
        "tamanho": _bytes_label(db_path.stat().st_size) if db_path.exists() else "0 B",
        "wal": wal_path.exists(),
        "shm": shm_path.exists(),
        "integridade": "nao verificado",
        "tabelas": 0,
    }
    if not db_path.exists():
        return status

    conn = bh.get_db()
    try:
        status["integridade"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        status["tabelas"] = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
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
            ).fetchone()[0] if conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='auditoria_eventos'"
            ).fetchone() else 0,
        }
    finally:
        conn.close()


@bp.route("/admin/usuarios")
@login_required
@nivel_min("admin")
def admin_usuarios():
    usuarios = bh.q("SELECT * FROM usuarios ORDER BY nivel, nome")
    return render_template("admin_usuarios.html", usuarios=usuarios)


@bp.route("/admin/sistema")
@login_required
@nivel_min("admin")
def admin_sistema():
    db_path = Path(current_app.config["DB_PATH"])
    backup_dir = db_path.parent / "backups"
    backups = backup_core.listar_backups(backup_dir, limite=20)
    importacoes = import_history.listar_importacoes_recentes(bh.get_db, limite=5)
    eventos = audit.listar_eventos(bh.get_db, limite=8)
    return render_template(
        "admin_sistema.html",
        db_status=_db_status(),
        contagens=_contagens_sistema(),
        backups=backups,
        backup_dir=str(backup_dir),
        importacoes=importacoes,
        eventos=eventos,
        app_version=version_core.APP_VERSION_LABEL,
        instance_dir=current_app.config["INSTANCE_DIR"],
        upload_temp=current_app.config["UPLOAD_TEMP"],
        log_path=current_app.config["LOG_PATH"],
        backup_ok=request.args.get("backup_ok", "").strip(),
        backup_erro=request.args.get("backup_erro", "").strip(),
        format_bytes=_bytes_label,
    )


@bp.route("/admin/sistema/backups/criar", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_criar_backup():
    db_path = Path(current_app.config["DB_PATH"])
    backup_dir = db_path.parent / "backups"
    try:
        with backup_core.operacao_exclusiva():
            info = backup_core.criar_backup_sqlite(db_path, destino_dir=backup_dir, prefixo="endemias", manter=20)
        audit.registrar_evento(
            bh.get_db,
            "backup_criado",
            entidade="backups",
            entidade_id=Path(info["arquivo"]).name,
            detalhes={
                "arquivo": Path(info["arquivo"]).name,
                "tamanho_bytes": info["tamanho_bytes"],
                "integridade": info["integridade"],
            },
        )
        msg = f"Backup criado: {Path(info['arquivo']).name}"
        return redirect(url_for("admin.admin_sistema", backup_ok=msg))
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao criar backup: {exc}"))


@bp.route("/admin/sistema/backups/restaurar", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_restaurar_backup():
    db_path = Path(current_app.config["DB_PATH"])
    backup_dir = db_path.parent / "backups"
    nome_backup = request.form.get("backup", "").strip()
    try:
        with backup_core.operacao_exclusiva():
            backup_path = backup_core.resolver_backup(backup_dir, nome_backup)
            seguranca = backup_core.criar_backup_sqlite(
                db_path,
                destino_dir=backup_dir,
                prefixo="pre_restore",
                manter=20,
            )
            info = backup_core.restaurar_backup_sqlite(db_path, backup_path)
        audit.registrar_evento(
            bh.get_db,
            "backup_restaurado",
            entidade="backups",
            entidade_id=backup_path.name,
            detalhes={
                "backup_restaurado": backup_path.name,
                "backup_seguranca": Path(seguranca["arquivo"]).name,
                "integridade": info["integridade"],
            },
        )
        msg = f"Backup restaurado: {backup_path.name}. Copia de seguranca criada: {Path(seguranca['arquivo']).name}"
        return redirect(url_for("admin.admin_sistema", backup_ok=msg))
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao restaurar backup: {exc}"))


@bp.route("/admin/sistema/backups/baixar/<nome_backup>")
@login_required
@nivel_min("admin")
def admin_baixar_backup(nome_backup):
    db_path = Path(current_app.config["DB_PATH"])
    backup_dir = db_path.parent / "backups"
    try:
        backup_path = backup_core.resolver_backup(backup_dir, nome_backup)
        return send_file(backup_path, as_attachment=True, download_name=backup_path.name)
    except Exception as exc:
        return redirect(url_for("admin.admin_sistema", backup_erro=f"Erro ao baixar backup: {exc}"))


@bp.route("/admin/sistema/dbml")
@login_required
@nivel_min("admin")
def admin_baixar_dbml():
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
@nivel_min("admin")
def admin_excluir_backup():
    db_path = Path(current_app.config["DB_PATH"])
    backup_dir = db_path.parent / "backups"
    nome_backup = request.form.get("backup", "").strip()
    try:
        with backup_core.operacao_exclusiva():
            backup_path = backup_core.resolver_backup(backup_dir, nome_backup)
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


@bp.route("/admin/auditoria")
@login_required
@nivel_min("admin")
def admin_auditoria():
    filtros = _filtros_auditoria()
    eventos = audit.listar_eventos(bh.get_db, filtros, limite=200)
    return render_template("admin_auditoria.html", eventos=eventos, filtros=filtros)


@bp.route("/admin/auditoria/exportar")
@login_required
@nivel_min("admin")
def admin_auditoria_exportar():
    filtros = _filtros_auditoria()
    eventos = audit.listar_eventos(bh.get_db, filtros, limite=500)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Auditoria"
    headers = ["Data", "Acao", "Usuario", "IP", "Entidade", "Entidade ID", "Detalhes"]
    fill = PatternFill("solid", fgColor="1A4FBA")
    for col, title in enumerate(headers, 1):
        cell = ws.cell(1, col, title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
    for row_idx, ev in enumerate(eventos, 2):
        detalhes = json.dumps(ev.get("detalhes") or {}, ensure_ascii=False, sort_keys=True)
        values = [
            ev.get("criado_em", ""),
            ev.get("acao", ""),
            ev.get("usuario_nome", ""),
            ev.get("ip", ""),
            ev.get("entidade", ""),
            ev.get("entidade_id", ""),
            detalhes,
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


@bp.route("/admin/usuarios/criar", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_criar_usuario():
    usuario = request.form.get("usuario", "").strip().lower()
    nome = request.form.get("nome", "").strip()
    nivel = request.form.get("nivel", "visualizador")
    senha = request.form.get("senha", "").strip()
    erro = None
    if not usuario or not nome or not senha:
        erro = "Preencha todos os campos."
    elif not auth_core.senha_valida(senha):
        erro = auth_core.mensagem_senha_invalida()
    elif nivel not in ("admin", "operador", "visualizador"):
        erro = "Nivel invalido."
    else:
        try:
            conn = bh.get_db()
            cur = conn.execute("""INSERT INTO usuarios (usuario,nome,senha_hash,nivel,ativo,criado_em)
                                  VALUES (?,?,?,?,1,?)""",
                               (usuario, nome, auth_core.hash_senha(senha), nivel, datetime.now().isoformat()))
            conn.commit()
            novo_id = cur.lastrowid
            conn.close()
            audit.registrar_evento(
                bh.get_db,
                "usuario_criado",
                entidade="usuarios",
                entidade_id=novo_id,
                detalhes={"usuario": usuario, "nome": nome, "nivel": nivel},
            )
        except Exception as e:
            erro = f"Erro: {e}"
    if erro:
        usuarios = bh.q("SELECT * FROM usuarios ORDER BY nivel, nome")
        return render_template("admin_usuarios.html", usuarios=usuarios, erro=erro)
    return redirect(url_for("admin.admin_usuarios"))


@bp.route("/admin/usuarios/<int:uid>/editar", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_editar_usuario(uid):
    campo = request.form.get("campo")
    valor = request.form.get("valor", "").strip()
    conn = bh.get_db()
    anterior = conn.execute("SELECT usuario,nome,nivel,ativo FROM usuarios WHERE id_usuario=?", (uid,)).fetchone()
    if campo == "nivel" and valor in ("admin", "operador", "visualizador"):
        conn.execute("UPDATE usuarios SET nivel=? WHERE id_usuario=?", (valor, uid))
    elif campo == "ativo" and valor in ("0", "1"):
        if uid == session.get("uid"):
            conn.close()
            return jsonify({"erro": "Voce nao pode desativar sua propria conta."}), 400
        conn.execute("UPDATE usuarios SET ativo=? WHERE id_usuario=?", (int(valor), uid))
    elif campo == "senha" and auth_core.senha_valida(valor):
        conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=?", (auth_core.hash_senha(valor), uid))
    else:
        conn.close()
        return jsonify({"erro": "Parametro invalido."}), 400
    conn.commit()
    conn.close()
    detalhes = {"campo": campo}
    if anterior:
        detalhes.update({
            "usuario": anterior["usuario"],
            "valor_antigo": anterior[campo] if campo in anterior.keys() else None,
        })
    detalhes["valor_novo"] = "***" if campo == "senha" else valor
    audit.registrar_evento(
        bh.get_db,
        "usuario_editado",
        entidade="usuarios",
        entidade_id=uid,
        detalhes=detalhes,
    )
    return jsonify({"ok": True})


@bp.route("/admin/usuarios/<int:uid>/resetar-senha", methods=["POST"])
@login_required
@nivel_min("admin")
def admin_resetar_senha(uid):
    tamanho = max(auth_core.PASSWORD_MIN_LENGTH, 12)
    nova = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(tamanho))
    conn = bh.get_db()
    alvo = conn.execute("SELECT usuario,nome FROM usuarios WHERE id_usuario=?", (uid,)).fetchone()
    conn.execute("UPDATE usuarios SET senha_hash=? WHERE id_usuario=?", (auth_core.hash_senha(nova), uid))
    conn.commit()
    conn.close()
    audit.registrar_evento(
        bh.get_db,
        "usuario_senha_resetada",
        entidade="usuarios",
        entidade_id=uid,
        detalhes={"usuario": alvo["usuario"] if alvo else None, "nome": alvo["nome"] if alvo else None},
    )
    return jsonify({"ok": True, "senha": nova})
