import logging

from flask import Blueprint, current_app, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import db as db_core
from app_core import work_types


bp = Blueprint("mapa", __name__)
login_required = auth_core.login_required


def _db_path():
    return current_app.config["DB_PATH"]


def get_db():
    return db_core.connect(_db_path())


@bp.route("/mapa")
@login_required
def page():
    return render_template("mapa.html")


@bp.route("/api/mapa")
@login_required
def api_mapa():
    """
    Retorna estatisticas por quarteirao para colorir o mapa.
    Filtros: localidade[] (nomes), tipo[], d_ini, d_fim.
    """
    try:
        locs = request.args.getlist("localidade")
        tipos = request.args.getlist("tipo")
        d_ini = request.args.get("d_ini", "")
        d_fim = request.args.get("d_fim", "")

        where_v = "WHERE v.quarteirao IS NOT NULL AND v.id_localidade IS NOT NULL"
        params_v = []

        if locs:
            where_v += f" AND l.nome IN ({','.join('?' * len(locs))})"
            params_v += locs
        if tipos:
            where_v += f" AND v.tipo IN ({','.join('?' * len(tipos))})"
            params_v += tipos
        if d_ini:
            where_v += " AND v.data>=?"
            params_v.append(d_ini)
        if d_fim:
            where_v += " AND v.data<=?"
            params_v.append(d_fim)

        conn = get_db()
        try:
            rows_v = conn.execute(
                f"""
                SELECT
                    v.id_localidade,
                    v.quarteirao,
                    v.tipo,
                    COUNT(DISTINCT v.id_visita) AS total_tipo,
                    COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal' THEN v.id_visita END) AS normais,
                    COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado' THEN v.id_visita END) AS fechados,
                    COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) AS recuperados,
                    MAX(v.data) AS ultimo_trabalho
                FROM visitas v
                LEFT JOIN localidades l ON l.id_localidade = v.id_localidade
                {where_v}
                GROUP BY v.id_localidade, v.quarteirao, v.tipo
                """,
                params_v,
            ).fetchall()

            where_f = "WHERE f.quarteirao IS NOT NULL AND f.id_localidade IS NOT NULL AND f.gera_notificacao=1"
            params_f = []
            if locs:
                where_f += f" AND l2.nome IN ({','.join('?' * len(locs))})"
                params_f += locs
            if d_ini:
                where_f += " AND f.data>=?"
                params_f.append(d_ini)
            if d_fim:
                where_f += " AND f.data<=?"
                params_f.append(d_fim)
            if tipos:
                where_f += f" AND f.tipo_trabalho IN ({','.join('?' * len(tipos))})"
                params_f += tipos

            rows_f = conn.execute(
                f"""
                SELECT f.id_localidade, f.quarteirao,
                       COUNT(*) AS total_focos,
                       COUNT(CASE WHEN f.status_notificacao='pendente' THEN 1 END) AS focos_pendentes
                FROM focos_positivos f
                LEFT JOIN localidades l2 ON l2.id_localidade = f.id_localidade
                {where_f}
                GROUP BY f.id_localidade, f.quarteirao
                """,
                params_f,
            ).fetchall()
        finally:
            conn.close()

        dados = {}

        def mapa_entry_vazio():
            entry = {
                "total": 0,
                "tipos": {},
                "normais": 0,
                "fechados": 0,
                "recuperados": 0,
                "ultimo_trabalho": None,
                "focos": 0,
                "focos_pendentes": 0,
            }
            for codigo in work_types.WORK_TYPE_COLORS:
                entry[codigo.lower()] = 0
            return entry

        for r in rows_v:
            chave = f"{r['id_localidade']}:{r['quarteirao']}"
            if chave not in dados:
                dados[chave] = mapa_entry_vazio()
            tipo = r["tipo"] or ""
            total_tipo = r["total_tipo"] or 0
            dados[chave]["total"] += total_tipo
            dados[chave]["tipos"][tipo] = total_tipo
            dados[chave][tipo.lower()] = total_tipo
            dados[chave]["normais"] += r["normais"] or 0
            dados[chave]["fechados"] += r["fechados"] or 0
            dados[chave]["recuperados"] += r["recuperados"] or 0
            ultimo = r["ultimo_trabalho"]
            if ultimo and (not dados[chave]["ultimo_trabalho"] or ultimo > dados[chave]["ultimo_trabalho"]):
                dados[chave]["ultimo_trabalho"] = ultimo

        for r in rows_f:
            chave = f"{r['id_localidade']}:{r['quarteirao']}"
            if chave not in dados:
                dados[chave] = mapa_entry_vazio()
            dados[chave]["focos"] = r["total_focos"]
            dados[chave]["focos_pendentes"] = r["focos_pendentes"]

        return jsonify(dados)
    except Exception:
        logging.exception("Erro em api_mapa")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500
