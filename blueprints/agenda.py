from calendar import monthrange
from datetime import datetime, timedelta
import sqlite3

from flask import Blueprint, jsonify, render_template, request

from app_core import auth as auth_core
from app_core import blueprint_helpers as bh
from app_core import work_types


bp = Blueprint("agenda", __name__)
login_required = auth_core.login_required
nivel_min = bh.nivel_min

AGENDA_AUTO_FONTES = {
    "VETORES": {"label": "Vetores", "cor": "#2563eb"},
    "BRI": {"label": "BRI", "cor": "#0f766e"},
    "ESPOROTRICOSE": {"label": "Esporotricose", "cor": "#be123c"},
    "RECOLHIMENTO": {"label": "Recolhimento", "cor": "#92400e"},
    "AMOSTRA_ANIMAIS": {"label": "Amostra de animais", "cor": "#0891b2"},
}

RECORRENCIAS = {
    "nenhuma": {"label": "Não repetir", "days": None, "months": None},
    "diaria": {"label": "Diária", "days": 1, "months": None},
    "semanal": {"label": "Semanal", "days": 7, "months": None},
    "quinzenal": {"label": "Quinzenal", "days": 14, "months": None},
    "mensal": {"label": "Mensal", "days": None, "months": 1},
    "bimestral": {"label": "Bimestral", "days": None, "months": 2},
    "trimestral": {"label": "Trimestral", "days": None, "months": 3},
    "semestral": {"label": "Semestral", "days": None, "months": 6},
    "anual": {"label": "Anual", "days": None, "months": 12},
}


def ensure_schema():
    conn = bh.get_db()
    try:
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(agenda_eventos)").fetchall()
        }
        if "recorrencia" not in cols:
            conn.execute("ALTER TABLE agenda_eventos ADD COLUMN recorrencia TEXT NOT NULL DEFAULT 'nenhuma'")
        if "recorrencia_fim" not in cols:
            conn.execute("ALTER TABLE agenda_eventos ADD COLUMN recorrencia_fim TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agenda_recorrencia ON agenda_eventos(recorrencia, recorrencia_fim)")
        conn.commit()
    finally:
        conn.close()


def _admin_required_json():
    u = bh.usuario_atual()
    ordem = {"admin": 3, "operador": 2, "visualizador": 1}
    if not u or ordem.get(u["nivel"], 0) < ordem.get("admin", 999):
        return None, (jsonify({"erro": "Sem permissao"}), 403)
    return u, None


def _int_json(value, default):
    try:
        return int(value if value is not None and value != "" else default)
    except (TypeError, ValueError):
        raise ValueError("Valor numerico invalido")


def _erro_banco_agenda(exc):
    mensagem = str(exc).lower()
    if "database is locked" in mensagem:
        return jsonify({
            "erro": "Banco de dados ocupado. Feche outras operacoes em andamento e tente novamente.",
        }), 503
    return jsonify({"erro": "Erro ao gravar evento na agenda."}), 500


def _tipo_evento_json(value):
    tipo = value or "outro"
    if tipo not in work_types.AGENDA_TYPE_COLORS:
        raise ValueError("Tipo de evento invalido")
    return tipo


def _recorrencia_json(value):
    recorrencia = value or "nenhuma"
    if recorrencia not in RECORRENCIAS:
        raise ValueError("Recorrência inválida")
    return recorrencia


def _parse_data_evento(value, dia_inteiro=False):
    if not value:
        return None
    texto = str(value)
    formatos = ("%Y-%m-%d",) if dia_inteiro else ("%Y-%m-%dT%H:%M", "%Y-%m-%d")
    for formato in formatos:
        try:
            return datetime.strptime(texto[:16] if "T" in texto else texto[:10], formato)
        except ValueError:
            continue
    raise ValueError("Data inválida")


def _erro_intervalo(data_inicio, data_fim, dia_inteiro, recorrencia="nenhuma", recorrencia_fim=None):
    try:
        inicio = _parse_data_evento(data_inicio, bool(dia_inteiro))
        fim = _parse_data_evento(data_fim, bool(dia_inteiro)) if data_fim else None
        fim_recorrencia = _parse_data_evento(recorrencia_fim, True) if recorrencia_fim else None
    except ValueError:
        return "Data inválida"
    if not inicio:
        return "Título e data são obrigatórios"
    if fim and fim < inicio:
        return "Data fim não pode ser anterior ao início"
    if recorrencia != "nenhuma" and fim_recorrencia and fim_recorrencia.date() < inicio.date():
        return "Fim da recorrência não pode ser anterior ao início"
    return None


def _iso_evento(dt, dia_inteiro):
    return dt.date().isoformat() if dia_inteiro else dt.isoformat(timespec="minutes")


def _fim_fullcalendar(dt, dia_inteiro):
    if dia_inteiro:
        return (dt.date() + timedelta(days=1)).isoformat()
    return dt.isoformat(timespec="minutes")


def _add_months(dt, months):
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _proxima_ocorrencia(dt, recorrencia):
    cfg = RECORRENCIAS[recorrencia]
    if cfg["days"]:
        return dt + timedelta(days=cfg["days"])
    return _add_months(dt, cfg["months"])


def _evento_manual_dict(row, inicio_dt, fim_dt, ocorrencia=0):
    cor = row["cor"] or work_types.AGENDA_TYPE_COLORS.get(row["tipo"], "#64748b")
    recorrencia = row["recorrencia"] or "nenhuma"
    sufixo = "" if recorrencia == "nenhuma" else f"_{inicio_dt.date().isoformat()}"
    return {
        "id": f"manual_{row['id_evento']}{sufixo}",
        "title": row["titulo"],
        "start": _iso_evento(inicio_dt, bool(row["dia_inteiro"])),
        "end": _fim_fullcalendar(fim_dt, bool(row["dia_inteiro"])),
        "allDay": bool(row["dia_inteiro"]),
        "color": cor,
        "backgroundColor": cor,
        "borderColor": cor,
        "textColor": "#ffffff",
        "display": "block",
        "extendedProps": {
            "tipo": row["tipo"],
            "tipoLabel": work_types.AGENDA_TYPE_LABELS.get(row["tipo"], "Outro"),
            "descricao": row["descricao"] or "",
            "lembrete_min": row["lembrete_min"],
            "criado_por": row["criado_por"] or "",
            "origem": "manual",
            "id_evento": row["id_evento"],
            "data_inicio": row["data_inicio"],
            "data_fim": row["data_fim"] or "",
            "recorrencia": recorrencia,
            "recorrenciaLabel": RECORRENCIAS.get(recorrencia, RECORRENCIAS["nenhuma"])["label"],
            "recorrencia_fim": row["recorrencia_fim"] or "",
            "ocorrencia": ocorrencia,
        },
    }


def _eventos_manuais_expandido(row, range_inicio, range_fim):
    recorrencia = row["recorrencia"] or "nenhuma"
    inicio_base = _parse_data_evento(row["data_inicio"], bool(row["dia_inteiro"]))
    fim_base = _parse_data_evento(row["data_fim"], bool(row["dia_inteiro"])) if row["data_fim"] else inicio_base
    if fim_base < inicio_base:
        fim_base = inicio_base
    duracao = fim_base - inicio_base

    if recorrencia == "nenhuma":
        if fim_base.date() < range_inicio.date() or inicio_base.date() > range_fim.date():
            return []
        return [_evento_manual_dict(row, inicio_base, fim_base)]

    fim_recorrencia = _parse_data_evento(row["recorrencia_fim"], True).date() if row["recorrencia_fim"] else None
    eventos = []
    atual = inicio_base
    ocorrencia = 0
    while atual.date() <= range_fim.date():
        fim_atual = atual + duracao
        if fim_recorrencia and atual.date() > fim_recorrencia:
            break
        if fim_atual.date() >= range_inicio.date():
            eventos.append(_evento_manual_dict(row, atual, fim_atual, ocorrencia=ocorrencia))
        ocorrencia += 1
        if ocorrencia > 1500:
            break
        proxima = _proxima_ocorrencia(atual, recorrencia)
        if proxima <= atual:
            break
        atual = proxima
    return eventos


def _table_exists(table):
    return bool(bh.q(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ))


def _localidades_lista(value):
    return sorted({item.strip() for item in (value or "-").split(",") if item and item.strip()})


def _auto_evento(data, fonte_codigo, titulo, total, resumo="", localidades="", agentes="-", tipo=None):
    fonte = AGENDA_AUTO_FONTES[fonte_codigo]
    cor = fonte["cor"]
    data_dt = _parse_data_evento(data, True)
    return {
        "id": f"auto_{fonte_codigo}_{data}_{tipo or fonte_codigo}",
        "title": titulo,
        "start": data,
        "end": _fim_fullcalendar(data_dt, True),
        "allDay": True,
        "color": cor + "dd",
        "backgroundColor": cor + "dd",
        "borderColor": cor,
        "textColor": "#ffffff",
        "display": "block",
        "classNames": ["agenda-auto-importado", f"agenda-auto-{fonte_codigo.lower()}"],
        "extendedProps": {
            "tipo": tipo or fonte_codigo,
            "tipoLabel": fonte["label"],
            "fonte": fonte_codigo,
            "fonteLabel": fonte["label"],
            "resumo": resumo,
            "localidades": _localidades_lista(localidades),
            "total": total,
            "agentes": agentes or "-",
            "origem": "auto",
        },
    }


@bp.route("/agenda")
@login_required
def page():
    ensure_schema()
    return render_template(
        "agenda.html",
        agenda_auto_fontes=tuple(
            {"codigo": codigo, **dados} for codigo, dados in AGENDA_AUTO_FONTES.items()
        ),
    )


@bp.route("/api/agenda/eventos", methods=["GET", "POST"])
@login_required
def api_eventos():
    """GET: lista eventos. POST: cria evento (admin)."""
    ensure_schema()
    if request.method == "POST":
        u, erro = _admin_required_json()
        if erro:
            return erro

        d = request.json or {}
        titulo = (d.get("titulo") or "").strip()
        try:
            tipo = _tipo_evento_json(d.get("tipo", "outro"))
        except ValueError:
            return jsonify({"erro": "Tipo de evento inválido"}), 400
        data_inicio = d.get("data_inicio", "")
        data_fim = d.get("data_fim") or None
        dia_inteiro = int(bool(d.get("dia_inteiro", False)))
        try:
            lembrete_min = _int_json(d.get("lembrete_min"), 60)
        except ValueError:
            return jsonify({"erro": "Lembrete inválido"}), 400
        try:
            recorrencia = _recorrencia_json(d.get("recorrencia"))
        except ValueError:
            return jsonify({"erro": "Recorrência inválida"}), 400
        recorrencia_fim = d.get("recorrencia_fim") or None
        if recorrencia == "nenhuma":
            recorrencia_fim = None
        descricao = (d.get("descricao") or "").strip() or None
        cor = work_types.AGENDA_TYPE_COLORS.get(tipo, "#64748b")
        if not titulo or not data_inicio:
            return jsonify({"erro": "Título e data são obrigatórios"}), 400
        erro_intervalo = _erro_intervalo(data_inicio, data_fim, dia_inteiro, recorrencia, recorrencia_fim)
        if erro_intervalo:
            return jsonify({"erro": erro_intervalo}), 400

        conn = None
        try:
            conn = bh.get_db()
            cur = conn.execute(
                """INSERT INTO agenda_eventos
                (titulo, descricao, tipo, data_inicio, data_fim, dia_inteiro, lembrete_min,
                 cor, criado_por, criado_em, recorrencia, recorrencia_fim)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    recorrencia,
                    recorrencia_fim,
                ),
            )
            conn.commit()
            novo_id = cur.lastrowid
        except sqlite3.OperationalError as exc:
            if conn:
                conn.rollback()
            return _erro_banco_agenda(exc)
        finally:
            if conn:
                conn.close()
        return jsonify({"ok": True, "id_evento": novo_id}), 201

    inicio = request.args.get("start", "")
    fim = request.args.get("end", "")
    eventos = []

    range_inicio = _parse_data_evento(inicio[:10], True)
    range_fim = _parse_data_evento(fim[:10], True)
    rows = bh.q(
        """SELECT * FROM agenda_eventos
           WHERE (
               date(data_inicio) <= date(?)
               AND (data_fim IS NULL OR date(data_fim) >= date(?))
           ) OR (
               COALESCE(recorrencia,'nenhuma') <> 'nenhuma'
               AND date(data_inicio) <= date(?)
               AND (recorrencia_fim IS NULL OR date(recorrencia_fim) >= date(?))
           )
           ORDER BY data_inicio""",
        (fim, inicio, fim, inicio),
    )
    for r in rows:
        eventos.extend(_eventos_manuais_expandido(r, range_inicio, range_fim))

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
        eventos.append(_auto_evento(
            r["data"],
            "VETORES",
            titulo,
            total,
            resumo=" | ".join(desc_partes),
            localidades=r["localidades"],
            agentes=r["agentes"] or "-",
            tipo=tipo,
        ))

    if _table_exists("bri_registros") and _table_exists("bri_agentes"):
        bri_rows = bh.q(
            """
            SELECT b.data,
                   COUNT(DISTINCT b.id_bri) AS total,
                   GROUP_CONCAT(DISTINCT COALESCE(b.localidade, '-')) AS localidades,
                   SUM(COALESCE(b.quantidade_carga,0) + COALESCE(b.quantidade_carga_extra,0)) AS carga,
                   (SELECT GROUP_CONCAT(a2.nome, ', ')
                      FROM (SELECT DISTINCT ag.nome
                              FROM agentes ag
                              JOIN bri_agentes ba ON ba.id_agente=ag.id_agente
                              JOIN bri_registros b2 ON b2.id_bri=ba.id_bri
                             WHERE b2.data=b.data
                             ORDER BY ag.nome) a2) AS agentes
              FROM bri_registros b
             WHERE b.data BETWEEN ? AND ?
             GROUP BY b.data
             ORDER BY b.data
            """,
            (inicio[:10], fim[:10]),
        )
        for r in bri_rows:
            total = r["total"] or 0
            carga = r["carga"] or 0
            eventos.append(_auto_evento(
                r["data"],
                "BRI",
                f"BRI - {total} registro{'s' if total != 1 else ''}",
                total,
                resumo=f"Carga total: {carga:g}",
                localidades=r["localidades"],
                agentes=r["agentes"] or "-",
            ))

    if _table_exists("esporotricose_visitas") and _table_exists("esporotricose_visita_agentes"):
        esporo_rows = bh.q(
            """
            SELECT v.data,
                   COUNT(DISTINCT v.id_visita) AS total,
                   COUNT(DISTINCT a.id_animal) AS animais,
                   COUNT(DISTINCT CASE WHEN LOWER(COALESCE(a.feridas,''))='sim' THEN a.id_animal END) AS feridas,
                   GROUP_CONCAT(DISTINCT COALESCE(v.localidade, '-')) AS localidades,
                   (SELECT GROUP_CONCAT(a2.nome, ', ')
                      FROM (SELECT DISTINCT ag.nome
                              FROM agentes ag
                              JOIN esporotricose_visita_agentes va ON va.id_agente=ag.id_agente
                              JOIN esporotricose_visitas v2 ON v2.id_visita=va.id_visita
                             WHERE v2.data=v.data
                             ORDER BY ag.nome) a2) AS agentes
              FROM esporotricose_visitas v
              LEFT JOIN esporotricose_animais a ON a.id_visita=v.id_visita
             WHERE v.data BETWEEN ? AND ?
             GROUP BY v.data
             ORDER BY v.data
            """,
            (inicio[:10], fim[:10]),
        )
        for r in esporo_rows:
            total = r["total"] or 0
            eventos.append(_auto_evento(
                r["data"],
                "ESPOROTRICOSE",
                f"Esporotricose - {total} visita{'s' if total != 1 else ''}",
                total,
                resumo=f"Animais: {r['animais'] or 0} | Com feridas: {r['feridas'] or 0}",
                localidades=r["localidades"],
                agentes=r["agentes"] or "-",
            ))

    if _table_exists("recolhimentos") and _table_exists("recolhimento_agentes"):
        recolhimento_rows = bh.q(
            """
            SELECT r.data,
                   COUNT(DISTINCT r.id_recolhimento) AS total,
                   COALESCE(SUM(r.total_materiais),0) AS materiais,
                   COALESCE(SUM(r.pneu),0) AS pneus,
                   GROUP_CONCAT(DISTINCT COALESCE(r.localidade, '-')) AS localidades,
                   (SELECT GROUP_CONCAT(a2.nome, ', ')
                      FROM (SELECT DISTINCT ag.nome
                              FROM agentes ag
                              JOIN recolhimento_agentes ra ON ra.id_agente=ag.id_agente
                              JOIN recolhimentos r2 ON r2.id_recolhimento=ra.id_recolhimento
                             WHERE r2.data=r.data
                             ORDER BY ag.nome) a2) AS agentes
              FROM recolhimentos r
             WHERE r.data BETWEEN ? AND ?
             GROUP BY r.data
             ORDER BY r.data
            """,
            (inicio[:10], fim[:10]),
        )
        for r in recolhimento_rows:
            total = r["total"] or 0
            eventos.append(_auto_evento(
                r["data"],
                "RECOLHIMENTO",
                f"Recolhimento - {total} registro{'s' if total != 1 else ''}",
                total,
                resumo=f"Materiais: {r['materiais'] or 0} | Pneus: {r['pneus'] or 0}",
                localidades=r["localidades"],
                agentes=r["agentes"] or "-",
            ))

    if _table_exists("amostras_animais") and _table_exists("amostra_animais_agentes"):
        amostra_rows = bh.q(
            """
            SELECT am.data,
                   COUNT(DISTINCT am.id_amostra) AS total,
                   COALESCE(SUM(am.quantidade),0) AS animais,
                   SUM(CASE WHEN LOWER(COALESCE(am.houve_acidente,''))='sim' THEN 1 ELSE 0 END) AS acidentes,
                   SUM(CASE WHEN LOWER(COALESCE(am.houve_captura,''))='sim' THEN 1 ELSE 0 END) AS capturas,
                   GROUP_CONCAT(DISTINCT COALESCE(am.localidade, '-')) AS localidades,
                   (SELECT GROUP_CONCAT(a2.nome, ', ')
                      FROM (SELECT DISTINCT ag.nome
                              FROM agentes ag
                              JOIN amostra_animais_agentes aa ON aa.id_agente=ag.id_agente
                              JOIN amostras_animais am2 ON am2.id_amostra=aa.id_amostra
                             WHERE am2.data=am.data
                             ORDER BY ag.nome) a2) AS agentes
              FROM amostras_animais am
             WHERE am.data BETWEEN ? AND ?
             GROUP BY am.data
             ORDER BY am.data
            """,
            (inicio[:10], fim[:10]),
        )
        for r in amostra_rows:
            total = r["total"] or 0
            eventos.append(_auto_evento(
                r["data"],
                "AMOSTRA_ANIMAIS",
                f"Amostras animais - {total} registro{'s' if total != 1 else ''}",
                total,
                resumo=f"Animais: {r['animais'] or 0} | Acidentes: {r['acidentes'] or 0} | Capturas: {r['capturas'] or 0}",
                localidades=r["localidades"],
                agentes=r["agentes"] or "-",
            ))

    return jsonify(eventos)


@bp.route("/api/agenda/eventos/<int:id_evento>", methods=["PUT", "DELETE"])
@login_required
@nivel_min("admin")
def api_evento(id_evento):
    ensure_schema()
    if request.method == "DELETE":
        conn = None
        try:
            conn = bh.get_db()
            conn.execute("DELETE FROM agenda_eventos WHERE id_evento=?", (id_evento,))
            conn.commit()
        except sqlite3.OperationalError as exc:
            if conn:
                conn.rollback()
            return _erro_banco_agenda(exc)
        finally:
            if conn:
                conn.close()
        return jsonify({"ok": True})

    d = request.json or {}
    titulo = (d.get("titulo") or "").strip()
    try:
        tipo = _tipo_evento_json(d.get("tipo", "outro"))
    except ValueError:
        return jsonify({"erro": "Tipo de evento inválido"}), 400
    data_inicio = d.get("data_inicio", "")
    data_fim = d.get("data_fim") or None
    dia_inteiro = int(bool(d.get("dia_inteiro", False)))
    try:
        lembrete_min = _int_json(d.get("lembrete_min"), 60)
    except ValueError:
        return jsonify({"erro": "Lembrete inválido"}), 400
    try:
        recorrencia = _recorrencia_json(d.get("recorrencia"))
    except ValueError:
        return jsonify({"erro": "Recorrência inválida"}), 400
    recorrencia_fim = d.get("recorrencia_fim") or None
    if recorrencia == "nenhuma":
        recorrencia_fim = None
    descricao = (d.get("descricao") or "").strip() or None
    cor = work_types.AGENDA_TYPE_COLORS.get(tipo, "#64748b")
    if not titulo or not data_inicio:
        return jsonify({"erro": "Título e data são obrigatórios"}), 400
    erro_intervalo = _erro_intervalo(data_inicio, data_fim, dia_inteiro, recorrencia, recorrencia_fim)
    if erro_intervalo:
        return jsonify({"erro": erro_intervalo}), 400

    conn = None
    try:
        conn = bh.get_db()
        conn.execute(
            """UPDATE agenda_eventos SET titulo=?, descricao=?, tipo=?, data_inicio=?,
               data_fim=?, dia_inteiro=?, lembrete_min=?, cor=?, recorrencia=?, recorrencia_fim=?
               WHERE id_evento=?""",
            (
                titulo,
                descricao,
                tipo,
                data_inicio,
                data_fim,
                dia_inteiro,
                lembrete_min,
                cor,
                recorrencia,
                recorrencia_fim,
                id_evento,
            ),
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        if conn:
            conn.rollback()
        return _erro_banco_agenda(exc)
    finally:
        if conn:
            conn.close()
    return jsonify({"ok": True})


@bp.route("/api/agenda/lembretes")
@login_required
def api_lembretes():
    """Retorna eventos manuais nas proximas 24h para notificacoes do browser."""
    ensure_schema()
    agora = datetime.now()
    limite = agora + timedelta(hours=24)
    rows = bh.q(
        """SELECT *
           FROM agenda_eventos
           WHERE (
               data_inicio BETWEEN ? AND ?
           ) OR (
               COALESCE(recorrencia,'nenhuma') <> 'nenhuma'
               AND date(data_inicio) <= date(?)
               AND (recorrencia_fim IS NULL OR date(recorrencia_fim) >= date(?))
           )
           ORDER BY data_inicio""",
        (agora.isoformat(), limite.isoformat(), limite.isoformat(), agora.isoformat()),
    )
    eventos = []
    for row in rows:
        for evento in _eventos_manuais_expandido(row, agora, limite):
            inicio = evento["start"]
            if evento["allDay"]:
                inicio = inicio + "T00:00"
            eventos.append({
                "id_evento": evento["extendedProps"]["id_evento"],
                "titulo": evento["title"],
                "tipo": evento["extendedProps"]["tipo"],
                "data_inicio": inicio,
                "dia_inteiro": int(evento["allDay"]),
                "lembrete_min": evento["extendedProps"]["lembrete_min"],
            })
    return jsonify(eventos)
