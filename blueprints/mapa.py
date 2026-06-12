import logging

from flask import Blueprint, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import esporotricose as esporotricose_core
from app_core import ovitrampas as ovitrampas_core
from app_core import pontos_estrategicos as pe_core
from app_core import work_types


bp = Blueprint("mapa", __name__)
login_required = auth_core.login_required


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

        conn = bh.get_db()
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

            esporotricose_core.ensure_schema(conn)
            where_e = "WHERE v.quarteirao IS NOT NULL AND v.id_localidade IS NOT NULL"
            params_e = []
            if locs:
                where_e += f" AND l3.nome IN ({','.join('?' * len(locs))})"
                params_e += locs
            if d_ini:
                where_e += " AND v.data>=?"
                params_e.append(d_ini)
            if d_fim:
                where_e += " AND v.data<=?"
                params_e.append(d_fim)

            rows_e = conn.execute(
                f"""
                SELECT
                    v.id_localidade,
                    v.quarteirao,
                    COUNT(DISTINCT v.id_visita) AS esporo_visitas,
                    COUNT(DISTINCT a.id_animal) AS esporo_animais,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(a.feridas,''))='sim' THEN a.id_animal END) AS esporo_feridas,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='fechado' THEN v.id_visita END) AS esporo_fechadas,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,''))='recusa' THEN v.id_visita END) AS esporo_recusas,
                    MAX(v.data) AS ultimo_esporotricose
                FROM esporotricose_visitas v
                LEFT JOIN localidades l3 ON l3.id_localidade = v.id_localidade
                LEFT JOIN esporotricose_animais a ON a.id_visita = v.id_visita
                {where_e}
                GROUP BY v.id_localidade, v.quarteirao
                """,
                params_e,
            ).fetchall()

            pe_core.ensure_schema(conn)
            where_pe = "WHERE pe.id_localidade IS NOT NULL AND pe.quarteirao IS NOT NULL"
            params_pe = []
            if locs:
                where_pe += f" AND pe.localidade IN ({','.join('?' * len(locs))})"
                params_pe += locs
            rows_pe = conn.execute(
                f"""
                SELECT
                    pe.id_localidade,
                    pe.quarteirao,
                    COUNT(*) AS pes_total,
                    SUM(CASE WHEN pe.situacao=1 THEN 1 ELSE 0 END) AS pes_ativos,
                    SUM(CASE WHEN pe.situacao=0 THEN 1 ELSE 0 END) AS pes_inativos,
                    SUM(CASE WHEN pe.situacao=1 AND (pe.latitude IS NULL OR pe.longitude IS NULL) THEN 1 ELSE 0 END) AS pes_sem_coordenada,
                    SUM(CASE WHEN pe.situacao=1 AND (
                        (
                            SELECT MAX(v.data)
                              FROM visitas v
                             WHERE v.tipo='PE'
                               AND v.id_localidade=pe.id_localidade
                               AND v.quarteirao=pe.quarteirao
                        ) IS NULL
                        OR julianday('now') - julianday((
                            SELECT MAX(v2.data)
                              FROM visitas v2
                             WHERE v2.tipo='PE'
                               AND v2.id_localidade=pe.id_localidade
                               AND v2.quarteirao=pe.quarteirao
                        )) > 20
                    ) THEN 1 ELSE 0 END) AS pes_atrasados
                FROM pontos_estrategicos pe
                {where_pe}
                GROUP BY pe.id_localidade, pe.quarteirao
                """,
                params_pe,
            ).fetchall()

            ovitrampas_core.ensure_schema(conn)
            join_ovi = "LEFT JOIN ovitrampas_leituras o ON o.ovitrampa_id=a.ovitrampa_id"
            params_o = []
            if d_ini or d_fim:
                on_filters = ["o.ovitrampa_id=a.ovitrampa_id"]
                if d_ini:
                    on_filters.append("COALESCE(o.data_coleta, o.data_leitura, o.data_envio_contagem)>=?")
                    params_o.append(d_ini)
                if d_fim:
                    on_filters.append("COALESCE(o.data_coleta, o.data_leitura, o.data_envio_contagem)<=?")
                    params_o.append(d_fim)
                join_ovi = "LEFT JOIN ovitrampas_leituras o ON " + " AND ".join(on_filters)

            where_o = "WHERE a.quarteirao IS NOT NULL AND l4.id_localidade IS NOT NULL"
            if locs:
                where_o += f" AND l4.nome IN ({','.join('?' * len(locs))})"
                params_o += locs

            rows_o = conn.execute(
                f"""
                SELECT
                    l4.id_localidade,
                    a.quarteirao,
                    COUNT(DISTINCT a.ovitrampa_id) AS ovi_armadilhas,
                    COUNT(DISTINCT CASE
                        WHEN a.latitude IS NOT NULL AND a.longitude IS NOT NULL THEN a.ovitrampa_id
                    END) AS ovi_com_coordenada,
                    COUNT(DISTINCT o.id_leitura) AS ovi_leituras,
                    COUNT(DISTINCT CASE WHEN o.ovos > 0 THEN o.id_leitura END) AS ovi_positivas,
                    COALESCE(SUM(o.ovos), 0) AS ovi_ovos,
                    MAX(COALESCE(o.data_coleta, o.data_leitura, o.data_envio_contagem)) AS ultimo_ovitrampa
                FROM ovitrampas_armadilhas a
                LEFT JOIN localidades l4 ON l4.nome = a.localidade
                {join_ovi}
                {where_o}
                GROUP BY l4.id_localidade, a.quarteirao
                """,
                params_o,
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
                "esporo_visitas": 0,
                "esporo_animais": 0,
                "esporo_feridas": 0,
                "esporo_fechadas": 0,
                "esporo_recusas": 0,
                "ultimo_esporotricose": None,
                "pes_total": 0,
                "pes_ativos": 0,
                "pes_inativos": 0,
                "pes_sem_coordenada": 0,
                "pes_atrasados": 0,
                "ovi_armadilhas": 0,
                "ovi_com_coordenada": 0,
                "ovi_leituras": 0,
                "ovi_positivas": 0,
                "ovi_ovos": 0,
                "ultimo_ovitrampa": None,
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

        for r in rows_e:
            chave = f"{r['id_localidade']}:{r['quarteirao']}"
            if chave not in dados:
                dados[chave] = mapa_entry_vazio()
            dados[chave]["esporo_visitas"] = r["esporo_visitas"] or 0
            dados[chave]["esporo_animais"] = r["esporo_animais"] or 0
            dados[chave]["esporo_feridas"] = r["esporo_feridas"] or 0
            dados[chave]["esporo_fechadas"] = r["esporo_fechadas"] or 0
            dados[chave]["esporo_recusas"] = r["esporo_recusas"] or 0
            dados[chave]["ultimo_esporotricose"] = r["ultimo_esporotricose"]

        for r in rows_pe:
            chave = f"{r['id_localidade']}:{r['quarteirao']}"
            if chave not in dados:
                dados[chave] = mapa_entry_vazio()
            dados[chave]["pes_total"] = r["pes_total"] or 0
            dados[chave]["pes_ativos"] = r["pes_ativos"] or 0
            dados[chave]["pes_inativos"] = r["pes_inativos"] or 0
            dados[chave]["pes_sem_coordenada"] = r["pes_sem_coordenada"] or 0
            dados[chave]["pes_atrasados"] = r["pes_atrasados"] or 0

        for r in rows_o:
            chave = f"{r['id_localidade']}:{r['quarteirao']}"
            if chave not in dados:
                dados[chave] = mapa_entry_vazio()
            dados[chave]["ovi_armadilhas"] = r["ovi_armadilhas"] or 0
            dados[chave]["ovi_com_coordenada"] = r["ovi_com_coordenada"] or 0
            dados[chave]["ovi_leituras"] = r["ovi_leituras"] or 0
            dados[chave]["ovi_positivas"] = r["ovi_positivas"] or 0
            dados[chave]["ovi_ovos"] = r["ovi_ovos"] or 0
            dados[chave]["ultimo_ovitrampa"] = r["ultimo_ovitrampa"]

        return jsonify(dados)
    except Exception:
        logging.exception("Erro em api_mapa")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


@bp.route("/api/mapa/ovitrampas")
@login_required
def api_mapa_ovitrampas():
    try:
        locs = request.args.getlist("localidade")
        d_ini = request.args.get("d_ini", "")
        d_fim = request.args.get("d_fim", "")
        busca = (request.args.get("busca") or "").strip()
        somente_positivas = request.args.get("positivas") == "1"
        min_ovos = _int(request.args.get("min_ovos"))

        conn = bh.get_db()
        try:
            ovitrampas_core.ensure_schema(conn)
            join = "LEFT JOIN ovitrampas_leituras l ON l.ovitrampa_id=a.ovitrampa_id"
            params = []
            if d_ini or d_fim:
                filtros_join = ["l.ovitrampa_id=a.ovitrampa_id"]
                if d_ini:
                    filtros_join.append("COALESCE(l.data_coleta, l.data_leitura, l.data_envio_contagem)>=?")
                    params.append(d_ini)
                if d_fim:
                    filtros_join.append("COALESCE(l.data_coleta, l.data_leitura, l.data_envio_contagem)<=?")
                    params.append(d_fim)
                join = "LEFT JOIN ovitrampas_leituras l ON " + " AND ".join(filtros_join)

            where = ["a.latitude IS NOT NULL", "a.longitude IS NOT NULL"]
            if locs:
                where.append(f"a.localidade IN ({','.join('?' * len(locs))})")
                params.extend(locs)
            if busca:
                termo = f"%{busca}%"
                where.append(
                    "(a.ovitrampa_id LIKE ? OR COALESCE(a.rua,'') LIKE ? OR COALESCE(a.localidade,'') LIKE ? "
                    "OR COALESCE(a.responsavel,'') LIKE ? OR COALESCE(a.quarteirao,'') LIKE ?)"
                )
                params.extend([termo] * 5)

            having = []
            if somente_positivas:
                having.append("positivas > 0")
            if min_ovos is not None:
                having.append("ovos >= ?")
                params.append(min_ovos)

            sql = f"""
                SELECT
                    a.ovitrampa_id,
                    a.rua,
                    a.numero,
                    a.complemento,
                    a.localidade,
                    a.bairro,
                    a.quarteirao,
                    a.responsavel,
                    a.latitude,
                    a.longitude,
                    COUNT(DISTINCT l.id_leitura) AS leituras,
                    COUNT(DISTINCT CASE WHEN l.ovos > 0 THEN l.id_leitura END) AS positivas,
                    COALESCE(SUM(l.ovos), 0) AS ovos,
                    MAX(COALESCE(l.data_coleta, l.data_leitura, l.data_envio_contagem)) AS ultima_coleta
                  FROM ovitrampas_armadilhas a
                  {join}
                 WHERE {' AND '.join(where)}
                 GROUP BY a.ovitrampa_id
            """
            if having:
                sql += " HAVING " + " AND ".join(having)
            sql += " ORDER BY ovos DESC, positivas DESC, CAST(a.ovitrampa_id AS INTEGER), a.ovitrampa_id COLLATE NOCASE"
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

        resumo = {
            "armadilhas": len(rows),
            "leituras": sum(row["leituras"] or 0 for row in rows),
            "positivas": sum(row["positivas"] or 0 for row in rows),
            "ovos": sum(row["ovos"] or 0 for row in rows),
            "localidades": len({row["localidade"] for row in rows if row["localidade"]}),
        }
        return jsonify({"resumo": resumo, "pontos": rows})
    except Exception:
        logging.exception("Erro em api_mapa_ovitrampas")
        return jsonify({"erro": "Erro interno. Verifique endemias.log"}), 500


def _int(value):
    try:
        if value in (None, ""):
            return None
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None
