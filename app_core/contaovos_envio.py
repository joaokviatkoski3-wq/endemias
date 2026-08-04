"""Envio unitario e supervisionado de contagens para o Conta Ovos."""

from datetime import datetime

from app_core import audit
from app_core import contaovos_client
from app_core import contaovos_credencial
from app_core import contaovos_fila
from app_core import db as db_core
from app_core import ovitrampas
from app_core import ovitrampas_laboratorio
from app_core import sispncd


MAX_RECONCILIATION_PAGES = 100
COORDINATE_TOLERANCE = 0.00001


class ContaOvosSendError(RuntimeError):
    def __init__(
        self,
        message,
        *,
        kind="send_error",
        outcome_uncertain=False,
        required_confirmation=None,
        details=None,
    ):
        super().__init__(message)
        self.kind = kind
        self.outcome_uncertain = bool(outcome_uncertain)
        self.required_confirmation = required_confirmation
        self.details = dict(details or {})


def _now_text(now=None):
    return (now or datetime.now()).isoformat(timespec="seconds")


def _queue_row(conn, queue_id):
    row = conn.execute(
        f"""SELECT q.*, i.id_lote, i.ovitrampa_id, i.ovos, i.ocorrencia,
                   l.data_movimento, a.latitude, a.longitude
              FROM {contaovos_fila.QUEUE_TABLE} q
              JOIN {ovitrampas_laboratorio.ITENS_TABLE} i
                ON i.id_item=q.id_item
              JOIN {ovitrampas_laboratorio.LOTES_TABLE} l
                ON l.id_lote=i.id_lote
              LEFT JOIN {ovitrampas.ARMADILHAS_TABLE} a
                ON a.ovitrampa_id=i.ovitrampa_id
             WHERE q.id_fila=?""",
        (int(queue_id),),
    ).fetchone()
    if not row:
        raise ContaOvosSendError(
            "Item da fila Conta Ovos nao encontrado.", kind="not_found"
        )
    payload = contaovos_fila._payload(row)
    digest = contaovos_fila.payload_hash(payload)
    if digest != row["payload_hash"]:
        raise ContaOvosSendError(
            "A leitura mudou depois da preparacao; prepare a fila novamente.",
            kind="payload_changed",
        )
    return row, payload, digest


def list_queue(conn, *, limit=20):
    limit = max(1, min(int(limit or 20), 100))
    rows = conn.execute(
        f"""SELECT q.id_fila, q.status, q.tentativas, i.id_item, i.id_lote,
                   i.ovitrampa_id, i.ovos, l.data_movimento
              FROM {contaovos_fila.QUEUE_TABLE} q
              JOIN {ovitrampas_laboratorio.ITENS_TABLE} i
                ON i.id_item=q.id_item
              JOIN {ovitrampas_laboratorio.LOTES_TABLE} l
                ON l.id_lote=i.id_lote
             WHERE q.status IN (?, ?)
             ORDER BY CASE q.status WHEN ? THEN 0 ELSE 1 END,
                      q.atualizado_em, q.id_fila
             LIMIT ?""",
        (
            contaovos_fila.STATUS_PENDING,
            contaovos_fila.STATUS_SENDING,
            contaovos_fila.STATUS_PENDING,
            limit,
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def _scope_ok(row):
    return (
        str(row.get("municipality_code") or "").strip()
        == contaovos_client.EXPECTED_MUNICIPALITY_CODE
        and str(row.get("state_code") or "").strip().upper()
        == contaovos_client.EXPECTED_STATE_CODE
    )


def _first(row, *fields):
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def _remote_week_rows(key, payload, *, page_fetcher=None):
    page_fetcher = page_fetcher or contaovos_client.private_counts_page
    year, week = sispncd.epidemiological_week_for_date(payload["date"])
    date_start, date_end = sispncd.epidemiological_week_range(year, week)
    found = []
    comparison_key = ovitrampas.chave_comparacao_ovitrampa_id(
        payload["ovitrap_group_id"]
    )
    for page in range(1, MAX_RECONCILIATION_PAGES + 1):
        rows = page_fetcher(
            key,
            page=page,
            date_start=date_start,
            date_end=date_end,
        )
        if not isinstance(rows, list):
            raise ContaOvosSendError(
                "A reconciliacao remota retornou um formato inesperado.",
                kind="unexpected_payload",
            )
        if not rows:
            return found
        for row in rows:
            if not isinstance(row, dict):
                raise ContaOvosSendError(
                    "A reconciliacao remota retornou uma contagem invalida.",
                    kind="unexpected_payload",
                )
            if not _scope_ok(row):
                raise ContaOvosSendError(
                    "A API retornou uma contagem fora do municipio esperado.",
                    kind="scope_mismatch",
                )
            remote_key = ovitrampas.chave_comparacao_ovitrampa_id(
                _first(row, "ovitrap_id", "ovitrap_group_id", "ovitrampa_id")
            )
            try:
                remote_year = int(row.get("year"))
                remote_week = int(row.get("week"))
            except (TypeError, ValueError):
                raise ContaOvosSendError(
                    "A API retornou ano ou semana invalidos.",
                    kind="unexpected_payload",
                ) from None
            if remote_key == comparison_key and (remote_year, remote_week) == (
                year,
                week,
            ):
                found.append(row)
    raise ContaOvosSendError(
        "A reconciliacao atingiu o limite de paginas.", kind="pagination_limit"
    )


def _optional_float_matches(remote_value, expected):
    if remote_value in (None, ""):
        return True
    try:
        return (
            abs(float(str(remote_value).replace(",", ".")) - float(expected))
            <= COORDINATE_TOLERANCE
        )
    except (TypeError, ValueError):
        return False


def _remote_ovitrap_position(payload, *, ovitrap_fetcher=None):
    ovitrap_fetcher = ovitrap_fetcher or contaovos_client.public_ovitraps_page
    comparison_key = ovitrampas.chave_comparacao_ovitrampa_id(
        payload["ovitrap_group_id"]
    )
    found = []
    for page in range(1, MAX_RECONCILIATION_PAGES + 1):
        rows = ovitrap_fetcher(page=page)
        if not isinstance(rows, list):
            raise ContaOvosSendError(
                "A consulta publica de ovitrampas retornou formato inesperado.",
                kind="unexpected_ovitrap_payload",
            )
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict) or not _scope_ok(row):
                raise ContaOvosSendError(
                    "A consulta publica retornou ovitrampa fora do municipio esperado.",
                    kind="ovitrap_scope_mismatch",
                )
            remote_id = str(row.get("ovitrap_group_id") or "").strip()
            if ovitrampas.chave_comparacao_ovitrampa_id(remote_id) == comparison_key:
                found.append(row)
    else:
        raise ContaOvosSendError(
            "A consulta publica de ovitrampas atingiu o limite de paginas.",
            kind="ovitrap_pagination_limit",
        )
    if not found:
        raise ContaOvosSendError(
            "A ovitrampa nao foi localizada no cadastro remoto; o envio foi bloqueado "
            "para impedir uma instalacao automatica incompleta.",
            kind="remote_ovitrap_not_found",
        )
    if len(found) > 1:
        raise ContaOvosSendError(
            "Mais de uma ovitrampa remota corresponde ao identificador local.",
            kind="ambiguous_remote_ovitrap",
        )
    row = found[0]
    remote_group_id = str(row.get("ovitrap_group_id") or "").strip()
    if remote_group_id != str(payload["ovitrap_group_id"]):
        raise ContaOvosSendError(
            "O identificador remoto da ovitrampa difere do payload preparado; "
            "alinhe o cadastro antes do envio.",
            kind="remote_ovitrap_id_mismatch",
            details={
                "identificador_local": str(payload["ovitrap_group_id"]),
                "identificador_remoto": remote_group_id,
            },
        )
    try:
        remote_lat = float(str(row["ovitrap_lat"]).replace(",", "."))
        remote_lng = float(str(row["ovitrap_lng"]).replace(",", "."))
    except (KeyError, TypeError, ValueError):
        raise ContaOvosSendError(
            "A ovitrampa remota nao possui coordenadas validas.",
            kind="invalid_remote_ovitrap_coordinates",
        ) from None
    local_lat = float(payload["ovitrap_lat"])
    local_lng = float(payload["ovitrap_lng"])
    return {
        "remote_lat": remote_lat,
        "remote_lng": remote_lng,
        "local_lat": local_lat,
        "local_lng": local_lng,
        "coordinates_match": (
            abs(remote_lat - local_lat) <= COORDINATE_TOLERANCE
            and abs(remote_lng - local_lng) <= COORDINATE_TOLERANCE
        ),
    }


def _coordinate_confirmation(queue_id, position):
    return (
        f"MOVER OVITRAMPA DA FILA {int(queue_id)} DE "
        f"{position['remote_lat']:.6f},{position['remote_lng']:.6f} PARA "
        f"{position['local_lat']:.6f},{position['local_lng']:.6f}"
    )


def _classify_remote(payload, rows):
    if not rows:
        return None, None
    if len(rows) > 1:
        return None, "Mais de uma contagem remota existe para a ovitrampa e semana."
    row = rows[0]
    try:
        eggs = int(_first(row, "eggs", "counting_eggs", "ovos") or 0)
    except (TypeError, ValueError):
        return None, "A contagem remota possui quantidade de ovos invalida."
    if eggs != payload["counting_eggs"]:
        return None, "A quantidade de ovos diverge da contagem remota."
    observation = _first(
        row,
        "counting_observation_id",
        "observation_id",
        "codigo_conta_ovos",
    )
    if observation not in (None, ""):
        try:
            if int(observation) != payload["counting_observation_id"]:
                return None, "A ocorrencia diverge da contagem remota."
        except (TypeError, ValueError):
            return None, "A contagem remota possui ocorrencia invalida."
    if not _optional_float_matches(
        _first(row, "latitude", "ovitrap_lat"), payload["ovitrap_lat"]
    ) or not _optional_float_matches(
        _first(row, "longitude", "ovitrap_lng"), payload["ovitrap_lng"]
    ):
        return None, "As coordenadas divergem da ovitrampa remota."
    remote_id = _first(row, "counting_id", "id_contagem")
    if remote_id in (None, ""):
        return None, "A contagem remota nao possui identificador."
    return str(remote_id), None


def _audit(conn, action, row, operator_name, details, now_text):
    audit.registrar_evento_operacional(
        conn,
        action,
        operador_nome=operator_name,
        entidade=contaovos_fila.QUEUE_TABLE,
        entidade_id=row["id_fila"],
        detalhes={
            "id_item": int(row["id_item"]),
            "id_lote": int(row["id_lote"]),
            "ovitrampa_id": row["ovitrampa_id"],
            **details,
        },
        criado_em=now_text,
    )


def _finish(
    conn,
    row,
    *,
    status,
    remote_id,
    error_message,
    operator_name,
    action,
    now_text,
):
    confirmed_at = now_text if status == contaovos_fila.STATUS_CONFIRMED else None
    conn.execute(
        f"""UPDATE {contaovos_fila.QUEUE_TABLE}
               SET status=?, id_remoto=?, erro_sanitizado=?, atualizado_em=?,
                   confirmado_em=?
             WHERE id_fila=?""",
        (
            status,
            remote_id,
            error_message,
            now_text,
            confirmed_at,
            row["id_fila"],
        ),
    )
    _audit(
        conn,
        action,
        row,
        operator_name,
        {"status": status, "id_remoto": remote_id, "erro": error_message},
        now_text,
    )
    conn.commit()


def send_one(
    target=None,
    *,
    queue_id,
    operator_name,
    key=None,
    allow_remote_write=False,
    page_fetcher=None,
    ovitrap_fetcher=None,
    poster=None,
    coordinate_authorization=None,
    connection=None,
    now=None,
):
    """Reconcilia, envia uma vez e confirma exclusivamente por GET."""
    if allow_remote_write is not True:
        raise ContaOvosSendError(
            "O envio remoto nao foi autorizado explicitamente.",
            kind="write_not_authorized",
        )
    operator_name = str(operator_name or "").strip()
    if not operator_name:
        raise ContaOvosSendError(
            "Informe o operador responsavel.", kind="operator_required"
        )
    key = key or contaovos_credencial.read_key()
    poster = poster or contaovos_client.post_counting
    owns_connection = connection is None
    conn = db_core.connect(target) if owns_connection else connection
    try:
        row, payload, digest = _queue_row(conn, queue_id)
        if row["status"] == contaovos_fila.STATUS_CONFIRMED:
            return {
                "ok": True,
                "sent": False,
                "status": contaovos_fila.STATUS_CONFIRMED,
                "id_remoto": row["id_remoto"],
            }
        if row["status"] == contaovos_fila.STATUS_ERROR:
            raise ContaOvosSendError(
                "O item esta em erro e exige nova preparacao/revisao humana.",
                kind="human_review_required",
            )

        before_rows = _remote_week_rows(key, payload, page_fetcher=page_fetcher)
        remote_id, conflict = _classify_remote(payload, before_rows)
        moment = _now_text(now)
        if conflict:
            _finish(
                conn,
                row,
                status=contaovos_fila.STATUS_ERROR,
                remote_id=None,
                error_message=conflict,
                operator_name=operator_name,
                action="conta_ovos_envio_contagem_conflito",
                now_text=moment,
            )
            raise ContaOvosSendError(conflict, kind="remote_conflict")
        if remote_id:
            _finish(
                conn,
                row,
                status=contaovos_fila.STATUS_CONFIRMED,
                remote_id=remote_id,
                error_message=None,
                operator_name=operator_name,
                action="conta_ovos_envio_contagem_reconciliada",
                now_text=moment,
            )
            return {
                "ok": True,
                "sent": False,
                "status": contaovos_fila.STATUS_CONFIRMED,
                "id_remoto": remote_id,
            }
        if row["status"] == contaovos_fila.STATUS_SENDING:
            message = (
                "Uma tentativa anterior nao foi localizada no Conta Ovos; "
                "reenvio automatico bloqueado para revisao humana."
            )
            _finish(
                conn,
                row,
                status=contaovos_fila.STATUS_ERROR,
                remote_id=None,
                error_message=message,
                operator_name=operator_name,
                action="conta_ovos_envio_contagem_incerta_nao_localizada",
                now_text=moment,
            )
            raise ContaOvosSendError(message, kind="uncertain_not_found")
        if row["status"] != contaovos_fila.STATUS_PENDING:
            raise ContaOvosSendError(
                "O estado atual da fila nao permite envio.", kind="invalid_state"
            )

        position = _remote_ovitrap_position(
            payload, ovitrap_fetcher=ovitrap_fetcher
        )
        coordinate_change = None
        if not position["coordinates_match"]:
            required_confirmation = _coordinate_confirmation(
                row["id_fila"], position
            )
            if coordinate_authorization != required_confirmation:
                raise ContaOvosSendError(
                    "As coordenadas locais divergem do cadastro Conta Ovos. "
                    "O envio so pode continuar com autorizacao humana explicita.",
                    kind="coordinate_change_confirmation_required",
                    required_confirmation=required_confirmation,
                    details=position,
                )
            coordinate_change = {
                "autorizada": True,
                "latitude_remota": position["remote_lat"],
                "longitude_remota": position["remote_lng"],
                "latitude_local": position["local_lat"],
                "longitude_local": position["local_lng"],
            }

        updated = conn.execute(
            f"""UPDATE {contaovos_fila.QUEUE_TABLE}
                   SET status=?, tentativas=tentativas+1, erro_sanitizado=NULL,
                       atualizado_em=?, ultima_tentativa_em=?
                 WHERE id_fila=? AND status=? AND payload_hash=?""",
            (
                contaovos_fila.STATUS_SENDING,
                moment,
                moment,
                row["id_fila"],
                contaovos_fila.STATUS_PENDING,
                digest,
            ),
        )
        if updated.rowcount != 1:
            conn.rollback()
            raise ContaOvosSendError(
                "O item foi alterado por outra operacao; nada foi enviado.",
                kind="concurrent_change",
            )
        _audit(
            conn,
            "conta_ovos_envio_contagem_iniciado",
            row,
            operator_name,
            {
                "status": contaovos_fila.STATUS_SENDING,
                "payload_hash": digest,
                "mudanca_coordenadas": coordinate_change,
            },
            moment,
        )
        conn.commit()

        post_error = None
        try:
            poster(
                key,
                payload,
                allow_remote_write=True,
            )
        except Exception as exc:
            post_error = exc

        try:
            after_rows = _remote_week_rows(key, payload, page_fetcher=page_fetcher)
            remote_id, conflict = _classify_remote(payload, after_rows)
        except Exception as exc:
            safe = contaovos_client.sanitize_message(exc, key)
            message = (
                "Resultado do envio incerto; a reconciliacao GET falhou. "
                "Nao reenvie automaticamente. " + safe
            )
            _finish(
                conn,
                row,
                status=contaovos_fila.STATUS_SENDING,
                remote_id=None,
                error_message=message,
                operator_name=operator_name,
                action="conta_ovos_envio_contagem_inconclusivo",
                now_text=_now_text(),
            )
            raise ContaOvosSendError(
                message, kind="reconciliation_failed", outcome_uncertain=True
            ) from None

        if remote_id:
            _finish(
                conn,
                row,
                status=contaovos_fila.STATUS_CONFIRMED,
                remote_id=remote_id,
                error_message=None,
                operator_name=operator_name,
                action="conta_ovos_envio_contagem_confirmado",
                now_text=_now_text(),
            )
            return {
                "ok": True,
                "sent": True,
                "status": contaovos_fila.STATUS_CONFIRMED,
                "id_remoto": remote_id,
            }

        safe_post_error = (
            contaovos_client.sanitize_message(post_error, key) if post_error else None
        )
        if conflict:
            final_message = conflict
            final_status = contaovos_fila.STATUS_ERROR
            final_kind = "remote_conflict"
        elif isinstance(post_error, contaovos_client.ContaOvosError) and (
            post_error.status_code in (400, 403, 404, 409)
        ):
            final_message = (
                (safe_post_error or "O envio foi recusado.")
                + " A leitura nao apareceu na reconciliacao; revisao humana obrigatoria."
            )
            final_status = contaovos_fila.STATUS_ERROR
            final_kind = "write_rejected"
        else:
            final_message = (
                "Resultado do envio incerto; a leitura nao apareceu na reconciliacao. "
                "Nao reenvie automaticamente."
            )
            if safe_post_error:
                final_message += " " + safe_post_error
            final_status = contaovos_fila.STATUS_SENDING
            final_kind = "write_outcome_uncertain"
        _finish(
            conn,
            row,
            status=final_status,
            remote_id=None,
            error_message=final_message,
            operator_name=operator_name,
            action="conta_ovos_envio_contagem_inconclusivo",
            now_text=_now_text(),
        )
        raise ContaOvosSendError(
            final_message,
            kind=final_kind,
            outcome_uncertain=final_status == contaovos_fila.STATUS_SENDING,
        )
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if owns_connection:
            conn.close()
