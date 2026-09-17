"""Atualizacao supervisionada do cadastro de ovitrampas no Conta Ovos.

Cada alteracao nasce no Endemias, fica registrada no historico local e entra
numa fila propria antes de qualquer POST remoto.  A fila nao e reutilizada para
contagens: o cadastro precisa ser confirmado antes de a leitura do mesmo item
ser enviada.
"""

import hashlib
import json
from datetime import date, datetime

from app_core import contaovos_client
from app_core import db as db_core
from app_core import ovitrampas
from app_core import ovitrampas_laboratorio


QUEUE_TABLE = "contaovos_fila_cadastro_ovitrampas"
STATUS_PENDING = "pendente"
STATUS_SENDING = "enviando"
STATUS_CONFIRMED = "confirmado"
STATUS_ERROR = "erro"
STATUS_UNCERTAIN = "incerto"
ALLOWED_STATUSES = (
    STATUS_PENDING, STATUS_SENDING, STATUS_CONFIRMED, STATUS_ERROR, STATUS_UNCERTAIN,
)

LOCAL_FIELDS = (
    "rua", "numero", "complemento", "localizacao", "localidade", "responsavel",
    "telefone_responsavel", "quarteirao", "latitude", "longitude",
)


class ContaOvosCadastroError(ValueError):
    pass


def ensure_schema_connection(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {QUEUE_TABLE} (
            id_fila INTEGER PRIMARY KEY AUTOINCREMENT,
            id_item INTEGER NOT NULL UNIQUE
                REFERENCES {ovitrampas_laboratorio.ITENS_TABLE}(id_item),
            ovitrampa_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '{STATUS_PENDING}'
                CHECK(status IN ('pendente','enviando','confirmado','erro','incerto')),
            tentativas INTEGER NOT NULL DEFAULT 0 CHECK(tentativas >= 0),
            payload_json TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            atualizar_desde TEXT,
            erro_sanitizado TEXT,
            resposta_sanitizada TEXT,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            ultima_tentativa_em TEXT,
            confirmado_em TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_contaovos_fila_cadastro_status
            ON {QUEUE_TABLE}(status, atualizado_em, id_fila);
        """
    )


def _text(value):
    return str(value or "").strip()


def _number(value, label, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ContaOvosCadastroError(f"{label} invalida.") from None
    if not minimum <= parsed <= maximum:
        raise ContaOvosCadastroError(f"{label} fora da faixa valida.")
    return parsed


def _date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        raise ContaOvosCadastroError("A data para atualizar historico e invalida.") from None


def payload_hash(payload):
    value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload(ovitrampa_id, values, atualizar_desde=None):
    localidade = _text(values.get("localidade"))
    if not localidade:
        raise ContaOvosCadastroError("Informe a localidade da ovitrampa.")
    payload = {
        "ovitrap_group_id": _text(ovitrampa_id),
        # Regra operacional municipal: os dois campos remotos representam a
        # mesma Localidade. Nunca mapear o bairro local para estes campos.
        "ovitrap_address_district": localidade,
        "ovitrap_address_sector": localidade,
        "ovitrap_address_street": _text(values.get("rua")),
        "ovitrap_address_number": _text(values.get("numero")),
        "ovitrap_address_complement": _text(values.get("complemento")),
        "ovitrap_address_loc_inst": _text(values.get("localizacao")),
        "ovitrap_responsable": _text(values.get("responsavel")),
        "ovitrap_block_id": _text(values.get("quarteirao")),
        "ovitrap_lat": _number(values.get("latitude"), "Latitude", -90, 90),
        "ovitrap_lng": _number(values.get("longitude"), "Longitude", -180, 180),
    }
    if not payload["ovitrap_group_id"]:
        raise ContaOvosCadastroError("A ovitrampa nao possui identificador.")
    since = _date(atualizar_desde)
    if since:
        payload["atualizar_desde"] = since
    return payload


def _row_values(row, submitted):
    values = {}
    for field in LOCAL_FIELDS:
        raw = submitted.get(field) if field in submitted else row[field]
        values[field] = raw if field in ("latitude", "longitude") else _text(raw)
    return values


def prepare_lot_updates(conn, lot_id, updates, *, user_name="sistema", now=None):
    """Persiste alteracoes locais e enfileira o POST cadastral por item.

    O lote precisa estar concluido. Uma fila `incerto` so e liberada por uma
    nova gravacao explicita do administrador, nunca por nova tentativa muda.
    """
    ensure_schema_connection(conn)
    if not isinstance(updates, list):
        raise ContaOvosCadastroError("Informe as alteracoes cadastrais do lote.")
    lot = conn.execute(
        f"SELECT status FROM {ovitrampas_laboratorio.LOTES_TABLE} WHERE id_lote=?", (int(lot_id),)
    ).fetchone()
    if not lot or lot["status"] != "concluido":
        raise ContaOvosCadastroError("O lote precisa estar concluido e ainda nao enviado.")
    now_text = (now or datetime.now()).isoformat(timespec="seconds")
    changed = queued = 0
    seen = set()
    for submitted in updates:
        if not isinstance(submitted, dict):
            raise ContaOvosCadastroError("Alteracao cadastral invalida.")
        try:
            item_id = int(submitted.get("id_item"))
        except (TypeError, ValueError):
            raise ContaOvosCadastroError("Item de leitura invalido.") from None
        if item_id in seen:
            raise ContaOvosCadastroError("Uma ovitrampa foi informada mais de uma vez.")
        seen.add(item_id)
        row = conn.execute(
            f"""SELECT i.id_item, i.ovitrampa_id, a.*
                  FROM {ovitrampas_laboratorio.ITENS_TABLE} i
                  JOIN {ovitrampas.ARMADILHAS_TABLE} a ON a.ovitrampa_id=i.ovitrampa_id
                 WHERE i.id_item=? AND i.id_lote=?""",
            (item_id, int(lot_id)),
        ).fetchone()
        if not row:
            raise ContaOvosCadastroError("A ovitrampa nao pertence a este lote ou nao esta cadastrada.")
        values = _row_values(row, submitted)
        payload = _payload(row["ovitrampa_id"], values, submitted.get("atualizar_desde"))
        local_changed = any(str(row[field] or "") != str(values[field] or "") for field in LOCAL_FIELDS)
        remote_changed = any(
            str(row[field] or "") != str(values[field] or "")
            for field in LOCAL_FIELDS if field != "telefone_responsavel"
        ) or bool(submitted.get("atualizar_desde"))
        if not local_changed and not remote_changed:
            continue
        changed += 1
        context = {
            "motivo": "Atualizacao cadastral preparada para o Conta Ovos",
            "agentes": "", "usuario": user_name, "arquivo_origem": None, "criado_em": now_text,
        }
        for field in LOCAL_FIELDS:
            old, new = row[field], values[field]
            if str(old or "") != str(new or ""):
                conn.execute(
                    f"UPDATE {ovitrampas.ARMADILHAS_TABLE} SET {field}=?, atualizado_em=? WHERE ovitrampa_id=?",
                    (new, now_text, row["ovitrampa_id"]),
                )
                ovitrampas._registrar_alteracao_armadilha(
                    conn, row["ovitrampa_id"], field, old, new, context
                )
        if remote_changed:
            digest = payload_hash(payload)
            conn.execute(
                f"""INSERT INTO {QUEUE_TABLE}
                     (id_item,ovitrampa_id,status,tentativas,payload_json,payload_hash,
                      atualizar_desde,erro_sanitizado,resposta_sanitizada,criado_em,atualizado_em)
                    VALUES (?,?,?,0,?,?,?,?,?,?,?)
                    ON CONFLICT (id_item) DO UPDATE SET
                      ovitrampa_id=excluded.ovitrampa_id,status=excluded.status,tentativas=0,
                      payload_json=excluded.payload_json,payload_hash=excluded.payload_hash,
                      atualizar_desde=excluded.atualizar_desde,erro_sanitizado=NULL,
                      resposta_sanitizada=NULL,atualizado_em=excluded.atualizado_em,
                      ultima_tentativa_em=NULL,confirmado_em=NULL""",
                (item_id, row["ovitrampa_id"], STATUS_PENDING, json.dumps(payload, ensure_ascii=False),
                 digest, payload.get("atualizar_desde"), None, None, now_text, now_text),
            )
            queued += 1
    return {"id_lote": int(lot_id), "alterados_localmente": changed, "enfileirados": queued}


def lot_queue_status(conn, lot_id):
    ensure_schema_connection(conn)
    result = {status: 0 for status in ALLOWED_STATUSES}
    rows = conn.execute(
        f"""SELECT q.status, COUNT(*) total FROM {QUEUE_TABLE} q
              JOIN {ovitrampas_laboratorio.ITENS_TABLE} i ON i.id_item=q.id_item
             WHERE i.id_lote=? GROUP BY q.status""", (int(lot_id),)
    ).fetchall()
    for row in rows:
        result[row["status"]] = int(row["total"] or 0)
    result["total"] = sum(result.values())
    return result


def lot_has_unconfirmed(conn, lot_id):
    status = lot_queue_status(conn, lot_id)
    return any(status[name] for name in (STATUS_PENDING, STATUS_SENDING, STATUS_ERROR, STATUS_UNCERTAIN))


def process_item(conn, item_id, key, *, now=None):
    """Envia uma unica atualizacao cadastral, sem retentativa automatica."""
    ensure_schema_connection(conn)
    row = conn.execute(f"SELECT * FROM {QUEUE_TABLE} WHERE id_item=?", (int(item_id),)).fetchone()
    if not row or row["status"] == STATUS_CONFIRMED:
        return {"ok": True, "changed": False}
    if row["status"] in (STATUS_SENDING, STATUS_UNCERTAIN):
        return {"ok": False, "changed": True, "uncertain": True,
                "message": "Atualizacao cadastral com resultado incerto; revise antes de preparar nova alteracao."}
    now_text = (now or datetime.now()).isoformat(timespec="seconds")
    conn.execute(
        f"UPDATE {QUEUE_TABLE} SET status=?,tentativas=tentativas+1,ultima_tentativa_em=?,atualizado_em=? WHERE id_item=?",
        (STATUS_SENDING, now_text, now_text, int(item_id)),
    )
    # Persiste o estado antes da escrita externa: queda do processo nao provoca
    # um segundo POST silencioso; a proxima tentativa fica marcada como incerta.
    conn.commit()
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        raise ContaOvosCadastroError("A fila cadastral possui payload invalido.") from None
    result = contaovos_client.send_ovitrap_edit(key, payload)
    message = contaovos_client.sanitize_message(result.get("message"), key)
    if result["ok"]:
        conn.execute(
            f"UPDATE {QUEUE_TABLE} SET status=?,erro_sanitizado=NULL,resposta_sanitizada=?,confirmado_em=?,atualizado_em=? WHERE id_item=?",
            (STATUS_CONFIRMED, message, now_text, now_text, int(item_id)),
        )
        return {"ok": True, "changed": True, "message": message}
    status = STATUS_UNCERTAIN if int(result.get("status_code", -1)) < 0 else STATUS_ERROR
    conn.execute(
        f"UPDATE {QUEUE_TABLE} SET status=?,erro_sanitizado=?,resposta_sanitizada=?,atualizado_em=? WHERE id_item=?",
        (status, message, message, now_text, int(item_id)),
    )
    return {"ok": False, "changed": True, "uncertain": status == STATUS_UNCERTAIN, "message": message}
