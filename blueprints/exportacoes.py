import io
import logging
import os
from datetime import datetime

import openpyxl
from flask import Blueprint, abort, current_app, jsonify, request, send_file
from openpyxl.styles import Alignment, Font, PatternFill

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import utils as utils_core
from app_core import work_types


bp = Blueprint("exportacoes", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


def q(sql, params=()):
    return db_core.query(_db_path(), sql, params)


def _base_dir():
    return current_app.root_path


def build_where(params_dict, alias_v="v", alias_l="l"):
    where, params = "WHERE 1=1", []
    d_ini = params_dict.get("d_ini") or utils_core.data_n_dias(365)
    d_fim = params_dict.get("d_fim") or utils_core.hoje()
    where += f" AND {alias_v}.data BETWEEN ? AND ?"
    params += [d_ini, d_fim]

    tipos = params_dict.getlist("tipo")
    locs = params_dict.getlist("localidade")
    ags = params_dict.getlist("agente")

    if tipos:
        where += f" AND {alias_v}.tipo IN ({','.join('?' * len(tipos))})"
        params += tipos
    if locs:
        where += f" AND {alias_l}.nome IN ({','.join('?' * len(locs))})"
        params += locs
    if ags:
        cond = " OR ".join([
            f"EXISTS(SELECT 1 FROM visita_agentes va2 JOIN agentes a2 ON a2.id_agente=va2.id_agente "
            f"WHERE va2.id_visita={alias_v}.id_visita AND a2.nome=?)"
            for _ in ags
        ])
        where += f" AND ({cond})"
        params += ags

    return where, params


@bp.route("/api/visitas/exportar")
@login_required
def exportar_visitas():
    try:
        where, params = build_where(request.args)
        busca = request.args.get("busca", "").strip()
        if busca:
            where += " AND (v.logradouro LIKE ? OR CAST(v.quarteirao AS TEXT) LIKE ?)"
            b = f"%{busca}%"
            params += [b, b]
        rows = q(f"""
            SELECT DISTINCT v.data, v.tipo, l.nome as localidade, v.quarteirao,
                   v.logradouro, v.numero, v.visita, v.morador, v.tipo_imovel,
                   v.ciclo, v.sequencia, v.hora_inicio, v.hora_fim, v.observacoes,
                   GROUP_CONCAT(DISTINCT a.nome) as agentes
            FROM visitas v
            LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
            LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
            LEFT JOIN agentes a ON a.id_agente=va.id_agente
            {where} GROUP BY v.id_visita ORDER BY v.data DESC, v.hora_inicio
        """, params)
        cabecalho = ["Data", "Tipo", "Localidade", "Quarteirao", "Logradouro", "Numero",
                     "Visita", "Morador", "Tipo Imovel", "Ciclo", "Sequencia",
                     "Hora Inicio", "Hora Fim", "Observacoes", "Agentes"]
        return _gerar_xlsx(cabecalho, rows, "visitas")
    except Exception:
        logging.exception("Erro em exportar_visitas")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@bp.route("/api/notificacoes/exportar")
@login_required
def exportar_notificacoes():
    try:
        fs = request.args.getlist("status")
        ft = request.args.getlist("tipo")
        fl = request.args.getlist("localidade")
        d_ini = request.args.get("d_ini", "")
        d_fim = request.args.get("d_fim", "")
        busca = request.args.get("busca", "").strip()
        where, params = "WHERE f.gera_notificacao=1", []
        if d_ini:
            where += " AND f.data>=?"
            params.append(d_ini)
        if d_fim:
            where += " AND f.data<=?"
            params.append(d_fim)
        if fs:
            where += f" AND COALESCE(f.status_notificacao,'pendente') IN ({','.join('?' * len(fs))})"
            params += fs
        if ft:
            where += f" AND f.tipo_trabalho IN ({','.join('?' * len(ft))})"
            params += ft
        if fl:
            where += f" AND l.nome IN ({','.join('?' * len(fl))})"
            params += fl
        if busca:
            where += " AND (f.logradouro LIKE ? OR f.num_tubo LIKE ? OR f.nome_morador LIKE ? OR f.codigo LIKE ?)"
            b = f"%{busca}%"
            params += [b, b, b, b]
        rows = q(f"""
            SELECT f.codigo, f.data, f.tipo_trabalho, l.nome as localidade,
                   f.quarteirao, f.logradouro, f.numero, f.nome_morador,
                   f.num_tubo, f.depositos, f.agentes,
                   COALESCE(f.status_notificacao,'pendente') as status,
                   f.tentativa_1, f.tentativa_2, f.tentativa_3,
                   f.data_entrega, f.observacoes
            FROM focos_positivos f
            LEFT JOIN localidades l ON l.id_localidade=f.id_localidade
            {where} ORDER BY f.data DESC
        """, params)
        cabecalho = ["Codigo", "Data", "Tipo", "Localidade", "Quarteirao", "Logradouro",
                     "Numero", "Morador", "Tubo(s)", "Deposito(s)", "Agentes", "Status",
                     "Tentativa 1", "Tentativa 2", "Tentativa 3", "Data Entrega", "Observacoes"]
        return _gerar_xlsx(cabecalho, rows, "notificacoes")
    except Exception:
        logging.exception("Erro em exportar_notificacoes")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@bp.route("/api/laboratorio/exportar")
@login_required
def exportar_laboratorio():
    try:
        d_ini = request.args.get("d_ini", utils_core.data_n_dias(365))
        d_fim = request.args.get("d_fim", utils_core.hoje())
        tipos = request.args.getlist("tipo")
        locs = request.args.getlist("localidade")
        tubo = request.args.get("tubo", "").strip()
        where = "WHERE v.data BETWEEN ? AND ?"
        params = [d_ini, d_fim]
        if tipos:
            where += f" AND v.tipo IN ({','.join('?' * len(tipos))})"
            params += tipos
        if locs:
            where += f" AND l.nome IN ({','.join('?' * len(locs))})"
            params += locs
        if tubo:
            where += " AND c.num_tubo LIKE ?"
            params.append(f"%{tubo}%")
        rows = q(f"""
            SELECT DISTINCT v.data, v.tipo, l.nome as localidade, v.quarteirao,
                   v.logradouro, v.numero, c.num_tubo, c.tipo_deposito,
                   rl.data_leitura, rl.laboratorista,
                   rl.aegypt_larvas, rl.aegypt_pupas, rl.aegypt_exuvias, rl.aegypt_adulto,
                   rl.albopictus_larvas, rl.albopictus_pupas, rl.albopictus_exuvias, rl.albopictus_adulto,
                   rl.outra_larvas, rl.outra_pupas, rl.outra_exuvias, rl.outra_adulto,
                   GROUP_CONCAT(DISTINCT a.nome) as agentes
            FROM resultados_laboratorio rl
            JOIN coletas c ON c.id_coleta=rl.id_coleta
            JOIN visitas v ON v.id_visita=c.id_visita
            LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
            LEFT JOIN visita_agentes va ON va.id_visita=v.id_visita
            LEFT JOIN agentes a ON a.id_agente=va.id_agente
            {where} GROUP BY rl.id_resultado ORDER BY v.data DESC
        """, params)
        cabecalho = ["Data", "Tipo", "Localidade", "Quarteirao", "Logradouro", "Numero",
                     "Tubo", "Deposito", "Data Leitura", "Laboratorista",
                     "Ae. Larvas", "Ae. Pupas", "Ae. Exuvias", "Ae. Adulto",
                     "Alb. Larvas", "Alb. Pupas", "Alb. Exuvias", "Alb. Adulto",
                     "Outra Larvas", "Outra Pupas", "Outra Exuvias", "Outra Adulto", "Agentes"]
        return _gerar_xlsx(cabecalho, rows, "laboratorio")
    except Exception:
        logging.exception("Erro em exportar_laboratorio")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


def _gerar_xlsx(cabecalho, rows, nome):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = nome[:31]
    fill = PatternFill("solid", fgColor="1A4FBA")
    for ci, col in enumerate(cabecalho, 1):
        cell = ws.cell(1, ci, col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")
    for ri, row in enumerate(rows, 2):
        vals = list(row.values()) if isinstance(row, dict) else list(row)
        for ci, value in enumerate(vals, 1):
            ws.cell(ri, ci, value)
    for col in ws.columns:
        width = max((len(str(cell.value or "")) for cell in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 40)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"{nome}_{ts}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.route("/saida/download/<tipo>")
@login_required
def saida_download(tipo):
    tipo = (tipo or "").upper()
    if tipo not in work_types.WORK_TYPE_CODES:
        abort(404)
    caminho = os.path.join(_base_dir(), "saida", f"{tipo}_consolidado.xlsx")
    if not os.path.exists(caminho):
        return f"Arquivo {tipo}_consolidado.xlsx ainda nao gerado. Execute um processamento primeiro.", 404
    return send_file(
        caminho,
        as_attachment=True,
        download_name=f"{tipo}_consolidado_{datetime.now().strftime('%Y%m%d')}.xlsx",
    )
