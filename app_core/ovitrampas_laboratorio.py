import re
import unicodedata
from datetime import date, datetime, timedelta

from app_core import db as db_core
from app_core import ovitrampas as ovitrampas_core


LOTES_TABLE = "ovitrampas_laboratorio_lotes"
ITENS_TABLE = "ovitrampas_laboratorio_itens"
ATIVO_DESDE = "2026-07-21"
STATUS_EDITAVEIS = ("pendente", "em_preenchimento", "concluido")


def ensure_schema(db_path):
    conn = db_core.connect(db_path)
    try:
        ovitrampas_core.ensure_schema(conn)
        _ensure_schema_conn(conn)
        conn.commit()
    finally:
        conn.close()


def gerar_lotes_pendentes(db_path, hoje=None):
    hoje = _data(hoje or date.today().isoformat())
    if hoje < ATIVO_DESDE:
        return 0
    conn = db_core.connect(db_path)
    try:
        ovitrampas_core.ensure_schema(conn)
        _ensure_schema_conn(conn)
        eventos = conn.execute(
            """SELECT e.id_evento, e.data, e.movimento, e.ciclo,
                      g.localidades AS grupo_localidades
                 FROM ovitrampas_calendario_eventos e
                 JOIN ovitrampas_calendario_grupos g ON g.id_grupo=e.id_grupo
                WHERE e.movimento IN ('troca','retirada')
                  AND date(e.data) BETWEEN date(?) AND date(?)
                ORDER BY e.data, e.id_evento""",
            (ATIVO_DESDE, hoje),
        ).fetchall()
        diarios = _diarios_com_armadilhas(conn)
        agora = datetime.now().isoformat(timespec="seconds")
        criados = 0
        for evento in eventos:
            localidades = _localidades(evento["grupo_localidades"])
            for diario in diarios:
                if not localidades.intersection(diario["localidades"]):
                    continue
                cur = conn.execute(
                    f"""INSERT OR IGNORE INTO {LOTES_TABLE}
                        (id_evento, id_diario, diario_nome, data_movimento, movimento,
                         ciclo, status, criado_em, atualizado_em)
                        VALUES (?,?,?,?,?,?,'pendente',?,?)""",
                    (
                        evento["id_evento"], diario["id_diario"], diario["nome"],
                        evento["data"], evento["movimento"], evento["ciclo"], agora, agora,
                    ),
                )
                if cur.rowcount:
                    criados += 1
                lote = conn.execute(
                    f"SELECT id_lote FROM {LOTES_TABLE} WHERE id_evento=? AND id_diario=?",
                    (evento["id_evento"], diario["id_diario"]),
                ).fetchone()
                for armadilha in diario["armadilhas"]:
                    conn.execute(
                        f"""INSERT OR IGNORE INTO {ITENS_TABLE}
                            (id_lote, ovitrampa_id, complemento, localidade, ovos)
                            VALUES (?,?,?,?,0)""",
                        (
                            lote["id_lote"], armadilha["ovitrampa_id"],
                            armadilha["complemento"], armadilha["localidade"],
                        ),
                    )
        conn.commit()
        return criados
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar_para_laboratorista(db_path, historico=False, hoje=None):
    gerar_lotes_pendentes(db_path, hoje=hoje)
    conn = db_core.connect(db_path)
    try:
        _ensure_schema_conn(conn)
        statuses = ("concluido", "enviado_conta_ovos") if historico else ("pendente", "em_preenchimento")
        placeholders = ",".join("?" for _ in statuses)
        rows = conn.execute(
            f"""SELECT l.*,
                       COUNT(i.id_item) AS armadilhas,
                       COALESCE(SUM(i.ovos),0) AS ovos,
                       CAST(julianday(?) - julianday(l.data_movimento) AS INTEGER) AS dias_desde_movimento
                  FROM {LOTES_TABLE} l
                  LEFT JOIN {ITENS_TABLE} i ON i.id_lote=l.id_lote
                 WHERE l.status IN ({placeholders})
                 GROUP BY l.id_lote
                 ORDER BY date(l.data_movimento) {'DESC' if historico else 'ASC'}, l.diario_nome COLLATE NOCASE""",
            (_data(hoje or date.today().isoformat()), *statuses),
        ).fetchall()
        registros = [_lote_dict(row) for row in rows]
        resultado = {"registros": registros, "total": len(registros)}
        if not historico:
            resultado["proximas"] = proximas_leituras_semana(db_path, hoje=hoje)
        return resultado
    finally:
        conn.close()


def proximas_leituras_semana(db_path, hoje=None):
    hoje_data = date.fromisoformat(_data(hoje or date.today().isoformat()))
    fim_semana = hoje_data + timedelta(days=6 - hoje_data.weekday())
    if fim_semana <= hoje_data:
        return []
    conn = db_core.connect(db_path)
    try:
        ovitrampas_core.ensure_schema(conn)
        eventos = conn.execute(
            """SELECT e.id_evento, e.data, e.movimento, e.ciclo,
                      g.localidades AS grupo_localidades
                 FROM ovitrampas_calendario_eventos e
                 JOIN ovitrampas_calendario_grupos g ON g.id_grupo=e.id_grupo
                WHERE e.movimento IN ('troca','retirada')
                  AND date(e.data) > date(?) AND date(e.data) <= date(?)
                ORDER BY e.data, e.id_evento""",
            (hoje_data.isoformat(), fim_semana.isoformat()),
        ).fetchall()
        diarios = _diarios_com_armadilhas(conn)
        proximas = []
        for evento in eventos:
            localidades = _localidades(evento["grupo_localidades"])
            for diario in diarios:
                if localidades.intersection(diario["localidades"]):
                    proximas.append({
                        "id_evento": evento["id_evento"],
                        "id_diario": diario["id_diario"],
                        "diario_nome": diario["nome"],
                        "data_movimento": evento["data"],
                        "movimento": evento["movimento"],
                        "movimento_label": "Troca" if evento["movimento"] == "troca" else "Retirada",
                        "ciclo": evento["ciclo"],
                        "armadilhas": len(diario["armadilhas"]),
                    })
        return proximas
    finally:
        conn.close()


def listar_para_administracao(db_path, status="pendente", hoje=None):
    gerar_lotes_pendentes(db_path, hoje=hoje)
    conn = db_core.connect(db_path)
    try:
        _ensure_schema_conn(conn)
        params = [_data(hoje or date.today().isoformat())]
        where = "l.status IN ('concluido','enviado_conta_ovos')"
        if status == "pendente":
            where = "l.status='concluido'"
        elif status == "enviado":
            where = "l.status='enviado_conta_ovos'"
        rows = conn.execute(
            f"""SELECT l.*,
                       COUNT(i.id_item) AS armadilhas,
                       COALESCE(SUM(i.ovos),0) AS ovos,
                       SUM(CASE WHEN i.ovos > 0 THEN 1 ELSE 0 END) AS positivas,
                       CAST(julianday(?) - julianday(l.data_movimento) AS INTEGER) AS dias_desde_movimento
                  FROM {LOTES_TABLE} l
                  LEFT JOIN {ITENS_TABLE} i ON i.id_lote=l.id_lote
                 WHERE {where}
                 GROUP BY l.id_lote
                 ORDER BY date(l.data_movimento) DESC, l.diario_nome COLLATE NOCASE""",
            params,
        ).fetchall()
        registros = [_lote_dict(row) for row in rows]
        return {"registros": registros, "total": len(registros)}
    finally:
        conn.close()


def obter_lote(db_path, id_lote):
    conn = db_core.connect(db_path)
    try:
        _ensure_schema_conn(conn)
        lote = conn.execute(
            f"SELECT * FROM {LOTES_TABLE} WHERE id_lote=?", (_int(id_lote),),
        ).fetchone()
        if not lote:
            raise ValueError("Lote de leitura não encontrado.")
        itens = [dict(row) for row in conn.execute(
            f"""SELECT id_item, ovitrampa_id, complemento, localidade, ovos
                  FROM {ITENS_TABLE}
                 WHERE id_lote=?
                 ORDER BY CAST(ovitrampa_id AS INTEGER), ovitrampa_id COLLATE NOCASE""",
            (lote["id_lote"],),
        ).fetchall()]
        registro = _lote_dict(lote)
        registro["itens"] = itens
        registro["armadilhas"] = len(itens)
        registro["ovos"] = sum(int(item["ovos"] or 0) for item in itens)
        registro["editavel"] = lote["status"] in STATUS_EDITAVEIS
        return registro
    finally:
        conn.close()


def salvar_rascunho(db_path, id_lote, leituras, usuario):
    conn = db_core.connect(db_path)
    try:
        _ensure_schema_conn(conn)
        lote = _lote_editavel(conn, id_lote)
        agora = datetime.now().isoformat(timespec="seconds")
        _salvar_itens(conn, lote["id_lote"], leituras, agora)
        novo_status = "em_preenchimento" if lote["status"] == "pendente" else lote["status"]
        conn.execute(
            f"""UPDATE {LOTES_TABLE}
                   SET status=?, id_laboratorista=?, laboratorista_nome=?,
                       iniciado_em=COALESCE(iniciado_em,?), atualizado_em=?
                 WHERE id_lote=?""",
            (
                novo_status, _usuario_id(usuario), _usuario_nome(usuario),
                agora, agora, lote["id_lote"],
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return obter_lote(db_path, id_lote)


def concluir_lote(db_path, id_lote, leituras, usuario):
    conn = db_core.connect(db_path)
    try:
        _ensure_schema_conn(conn)
        lote = _lote_editavel(conn, id_lote)
        agora = datetime.now().isoformat(timespec="seconds")
        _salvar_itens(conn, lote["id_lote"], leituras, agora)
        conn.execute(
            f"""UPDATE {LOTES_TABLE}
                   SET status='concluido', id_laboratorista=?, laboratorista_nome=?,
                       iniciado_em=COALESCE(iniciado_em,?), concluido_em=?, atualizado_em=?
                 WHERE id_lote=?""",
            (
                _usuario_id(usuario), _usuario_nome(usuario), agora, agora, agora,
                lote["id_lote"],
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return obter_lote(db_path, id_lote)


def marcar_enviado_conta_ovos(db_path, id_lote, usuario):
    conn = db_core.connect(db_path)
    try:
        _ensure_schema_conn(conn)
        lote = conn.execute(
            f"SELECT status FROM {LOTES_TABLE} WHERE id_lote=?", (_int(id_lote),),
        ).fetchone()
        if not lote:
            raise ValueError("Lote de leitura não encontrado.")
        if lote["status"] == "enviado_conta_ovos":
            return obter_lote(db_path, id_lote)
        if lote["status"] != "concluido":
            raise ValueError("O lote precisa estar concluído pelo laboratório.")
        agora = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            f"""UPDATE {LOTES_TABLE}
                   SET status='enviado_conta_ovos', enviado_conta_ovos_em=?,
                       enviado_conta_ovos_por=?, enviado_por_nome=?, atualizado_em=?
                 WHERE id_lote=?""",
            (agora, _usuario_id(usuario), _usuario_nome(usuario), agora, _int(id_lote)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return obter_lote(db_path, id_lote)


def _ensure_schema_conn(conn):
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {LOTES_TABLE} (
            id_lote INTEGER PRIMARY KEY AUTOINCREMENT,
            id_evento INTEGER NOT NULL REFERENCES ovitrampas_calendario_eventos(id_evento) ON DELETE CASCADE,
            id_diario INTEGER NOT NULL REFERENCES ovitrampas_diarios(id_diario),
            diario_nome TEXT NOT NULL,
            data_movimento DATE NOT NULL,
            movimento TEXT NOT NULL CHECK(movimento IN ('troca','retirada')),
            ciclo TEXT,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','em_preenchimento','concluido','enviado_conta_ovos')),
            id_laboratorista INTEGER REFERENCES usuarios(id_usuario),
            laboratorista_nome TEXT,
            iniciado_em TEXT,
            concluido_em TEXT,
            enviado_conta_ovos_em TEXT,
            enviado_conta_ovos_por INTEGER REFERENCES usuarios(id_usuario),
            enviado_por_nome TEXT,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            UNIQUE(id_evento, id_diario)
        );
        CREATE TABLE IF NOT EXISTS {ITENS_TABLE} (
            id_item INTEGER PRIMARY KEY AUTOINCREMENT,
            id_lote INTEGER NOT NULL REFERENCES {LOTES_TABLE}(id_lote) ON DELETE CASCADE,
            ovitrampa_id TEXT NOT NULL,
            complemento TEXT,
            localidade TEXT,
            ovos INTEGER NOT NULL DEFAULT 0 CHECK(ovos >= 0),
            atualizado_em TEXT,
            UNIQUE(id_lote, ovitrampa_id)
        );
        CREATE INDEX IF NOT EXISTS idx_ovi_lab_lotes_status ON {LOTES_TABLE}(status, data_movimento DESC);
        CREATE INDEX IF NOT EXISTS idx_ovi_lab_lotes_evento ON {LOTES_TABLE}(id_evento, id_diario);
        CREATE INDEX IF NOT EXISTS idx_ovi_lab_itens_lote ON {ITENS_TABLE}(id_lote, ovitrampa_id);
    """)


def _diarios_com_armadilhas(conn):
    rows = conn.execute(
        """SELECT d.id_diario, d.nome, a.ovitrampa_id, a.complemento, a.localidade,
                  a.rua, a.numero, a.localizacao, a.bairro, a.responsavel
             FROM ovitrampas_diarios d
             JOIN ovitrampas_diario_armadilhas da ON da.id_diario=d.id_diario
             JOIN ovitrampas_armadilhas a ON a.ovitrampa_id=da.ovitrampa_id
            WHERE d.ativo=1 AND COALESCE(a.ativo,1)=1
            ORDER BY d.nome COLLATE NOCASE, da.ordem,
                     CAST(a.ovitrampa_id AS INTEGER), a.ovitrampa_id COLLATE NOCASE"""
    ).fetchall()
    diarios = {}
    for raw in rows:
        row = dict(raw)
        if _realocar(row):
            continue
        diario = diarios.setdefault(row["id_diario"], {
            "id_diario": row["id_diario"], "nome": row["nome"],
            "localidades": set(), "armadilhas": [],
        })
        localidade = _chave(row["localidade"])
        if localidade:
            diario["localidades"].add(localidade)
        diario["armadilhas"].append({
            "ovitrampa_id": row["ovitrampa_id"],
            "complemento": row["complemento"],
            "localidade": row["localidade"],
        })
    return list(diarios.values())


def _salvar_itens(conn, id_lote, leituras, agora):
    if not isinstance(leituras, list):
        raise ValueError("Informe as leituras das armadilhas.")
    permitidos = {
        row["id_item"] for row in conn.execute(
            f"SELECT id_item FROM {ITENS_TABLE} WHERE id_lote=?", (id_lote,),
        ).fetchall()
    }
    vistos = set()
    for leitura in leituras:
        id_item = _int((leitura or {}).get("id_item"))
        if not id_item or id_item not in permitidos or id_item in vistos:
            raise ValueError("Leitura de armadilha inválida.")
        vistos.add(id_item)
        ovos = _int((leitura or {}).get("ovos"), default=None)
        if ovos is None or ovos < 0 or ovos > 100000:
            raise ValueError("A quantidade de ovos deve estar entre 0 e 100000.")
        conn.execute(
            f"UPDATE {ITENS_TABLE} SET ovos=?, atualizado_em=? WHERE id_item=? AND id_lote=?",
            (ovos, agora, id_item, id_lote),
        )


def _lote_editavel(conn, id_lote):
    lote = conn.execute(
        f"SELECT id_lote, status FROM {LOTES_TABLE} WHERE id_lote=?", (_int(id_lote),),
    ).fetchone()
    if not lote:
        raise ValueError("Lote de leitura não encontrado.")
    if lote["status"] not in STATUS_EDITAVEIS:
        raise ValueError("Este lote já foi enviado ao Conta Ovos e não pode mais ser alterado.")
    return lote


def _lote_dict(row):
    item = dict(row)
    item["movimento_label"] = "Troca" if item.get("movimento") == "troca" else "Retirada"
    dias = int(item.get("dias_desde_movimento") or 0)
    item["alerta"] = dias > 2 and item.get("status") in ("pendente", "em_preenchimento")
    item["editavel"] = item.get("status") in STATUS_EDITAVEIS
    return item


def _localidades(value):
    return {_chave(item) for item in re.split(r"\s*(?:,|;|/|\be\b)\s*", str(value or ""), flags=re.I) if _chave(item)}


def _chave(value):
    texto = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).casefold().split())


def _realocar(row):
    texto = " ".join(str(row.get(campo) or "") for campo in (
        "localidade", "rua", "numero", "complemento", "localizacao", "bairro", "responsavel",
    ))
    return "REALOCAR" in texto.upper()


def _data(value):
    texto = str(value or "")[:10]
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError as exc:
        raise ValueError("Data inválida.") from exc


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _usuario_id(usuario):
    return _int((usuario or {}).get("id_usuario")) or None


def _usuario_nome(usuario):
    return str((usuario or {}).get("nome") or "Sistema").strip() or "Sistema"
