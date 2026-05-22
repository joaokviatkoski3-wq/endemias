from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import work_types


bp = Blueprint("agenda", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min


def _admin_required_json():
    u = bh.usuario_atual()
    ordem = {"admin": 3, "operador": 2, "visualizador": 1}
    if not u or ordem.get(u["nivel"], 0) < ordem.get("admin", 999):
        return None, (jsonify({"erro": "Sem permissao"}), 403)
    return u, None


@bp.route("/agenda")
@login_required
def page():
    return render_template("agenda.html")


@bp.route("/api/agenda/eventos", methods=["GET", "POST"])
@login_required
def api_eventos():
    """GET: lista eventos. POST: cria evento (admin)."""
    if request.method == "POST":
        u, erro = _admin_required_json()
        if erro:
            return erro

        d = request.json or {}
        titulo = (d.get("titulo") or "").strip()
        tipo = d.get("tipo", "outro")
        data_inicio = d.get("data_inicio", "")
        data_fim = d.get("data_fim") or None
        dia_inteiro = int(bool(d.get("dia_inteiro", False)))
        lembrete_min = int(d.get("lembrete_min") or 60)
        descricao = (d.get("descricao") or "").strip() or None
        cor = work_types.AGENDA_TYPE_COLORS.get(tipo, "#64748b")
        if not titulo or not data_inicio:
            return jsonify({"erro": "Titulo e data sao obrigatorios"}), 400

        conn = bh.get_db()
        cur = conn.execute(
            """INSERT INTO agenda_eventos
            (titulo, descricao, tipo, data_inicio, data_fim, dia_inteiro, lembrete_min, cor, criado_por, criado_em)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                titulo,
                descricao,
                tipo,
                data_inicio,
                data_fim,
                dia_inteiro,
                lembrete_min,
                cor,
                u["nome"] if u else "admin",
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        novo_id = cur.lastrowid
        conn.close()
        return jsonify({"ok": True, "id_evento": novo_id}), 201

    inicio = request.args.get("start", "")
    fim = request.args.get("end", "")
    eventos = []

    rows = bh.q(
        """SELECT * FROM agenda_eventos
           WHERE date(data_inicio) <= date(?) AND (data_fim IS NULL OR date(data_fim) >= date(?))
           ORDER BY data_inicio""",
        (fim, inicio),
    )
    for r in rows:
        cor = r["cor"] or work_types.AGENDA_TYPE_COLORS.get(r["tipo"], "#64748b")
        eventos.append({
            "id": f"manual_{r['id_evento']}",
            "title": r["titulo"],
            "start": r["data_inicio"],
            "end": r["data_fim"] or r["data_inicio"],
            "allDay": bool(r["dia_inteiro"]),
            "color": cor,
            "backgroundColor": cor,
            "borderColor": cor,
            "textColor": "#ffffff",
            "display": "block",
            "extendedProps": {
                "tipo": r["tipo"],
                "tipoLabel": work_types.AGENDA_TYPE_LABELS.get(r["tipo"], "Outro"),
                "descricao": r["descricao"] or "",
                "lembrete_min": r["lembrete_min"],
                "criado_por": r["criado_por"] or "",
                "origem": "manual",
                "id_evento": r["id_evento"],
            },
        })

    auto_rows = bh.q(
        """
        SELECT
            v.data,
            v.tipo,
            COUNT(DISTINCT v.id_visita) as total,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='normal'     THEN v.id_visita END) as normais,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='fechado'    THEN v.id_visita END) as fechados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recuperado' THEN v.id_visita END) as recuperados,
            COUNT(DISTINCT CASE WHEN LOWER(v.visita)='recusa'     THEN v.id_visita END) as recusados,
            GROUP_CONCAT(DISTINCT COALESCE(v.localidade, '-')) as localidades,
            (SELECT GROUP_CONCAT(a2.nome, ', ')
             FROM (SELECT DISTINCT a2.nome FROM agentes a2
                   JOIN visita_agentes va2 ON va2.id_agente = a2.id_agente
                   WHERE va2.id_visita IN (
                       SELECT id_visita FROM visitas v2
                       WHERE v2.data = v.data AND v2.tipo = v.tipo
                   ) ORDER BY a2.nome) a2
            ) as agentes
        FROM visitas v
        WHERE v.data BETWEEN ? AND ?
        GROUP BY v.data, v.tipo
        ORDER BY v.data, v.tipo
        """,
        (inicio[:10], fim[:10]),
    )

    for r in auto_rows:
        tipo = r["tipo"]
        total = r["total"]
        titulo = f"{tipo} - {total} visita{'s' if total != 1 else ''}"
        desc_partes = []
        if r["normais"]:
            desc_partes.append(f"Normais: {r['normais']}")
        if r["fechados"]:
            desc_partes.append(f"Fechados: {r['fechados']}")
        if r["recuperados"]:
            desc_partes.append(f"Recuperados: {r['recuperados']}")
        if r["recusados"]:
            desc_partes.append(f"Recusas: {r['recusados']}")
        localidades_lista = sorted(set((r["localidades"] or "-").split(",")))
        eventos.append({
            "id": f"auto_{r['data']}_{tipo}",
            "title": titulo,
            "start": r["data"],
            "end": r["data"],
            "allDay": True,
            "color": work_types.WORK_TYPE_COLORS.get(tipo, "#64748b") + "cc",
            "backgroundColor": work_types.WORK_TYPE_COLORS.get(tipo, "#64748b") + "cc",
            "borderColor": work_types.WORK_TYPE_COLORS.get(tipo, "#64748b"),
            "textColor": "#ffffff",
            "display": "block",
            "extendedProps": {
                "tipo": tipo,
                "tipoLabel": work_types.WORK_TYPE_LABELS.get(tipo, tipo),
                "resumo": " | ".join(desc_partes),
                "localidades": localidades_lista,
                "total": total,
                "agentes": r["agentes"] or "-",
                "origem": "auto",
            },
        })

    return jsonify(eventos)


@bp.route("/api/agenda/eventos/<int:id_evento>", methods=["PUT", "DELETE"])
@login_required
@nivel_min("admin")
def api_evento(id_evento):
    if request.method == "DELETE":
        conn = bh.get_db()
        conn.execute("DELETE FROM agenda_eventos WHERE id_evento=?", (id_evento,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    d = request.json or {}
    titulo = (d.get("titulo") or "").strip()
    tipo = d.get("tipo", "outro")
    data_inicio = d.get("data_inicio", "")
    data_fim = d.get("data_fim") or None
    dia_inteiro = int(bool(d.get("dia_inteiro", False)))
    lembrete_min = int(d.get("lembrete_min") or 60)
    descricao = (d.get("descricao") or "").strip() or None
    cor = work_types.AGENDA_TYPE_COLORS.get(tipo, "#64748b")
    if not titulo or not data_inicio:
        return jsonify({"erro": "Titulo e data sao obrigatorios"}), 400

    conn = bh.get_db()
    conn.execute(
        """UPDATE agenda_eventos SET titulo=?, descricao=?, tipo=?, data_inicio=?,
           data_fim=?, dia_inteiro=?, lembrete_min=?, cor=? WHERE id_evento=?""",
        (titulo, descricao, tipo, data_inicio, data_fim, dia_inteiro, lembrete_min, cor, id_evento),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/api/agenda/lembretes")
@login_required
def api_lembretes():
    """Retorna eventos manuais nas proximas 24h para notificacoes do browser."""
    agora = datetime.now()
    limite = agora + timedelta(hours=24)
    rows = bh.q(
        """SELECT id_evento, titulo, tipo, data_inicio, dia_inteiro, lembrete_min
           FROM agenda_eventos
           WHERE data_inicio BETWEEN ? AND ?
           ORDER BY data_inicio""",
        (agora.isoformat(), limite.isoformat()),
    )
    return jsonify(rows)
