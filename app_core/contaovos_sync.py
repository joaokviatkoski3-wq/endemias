"""Sincronizacao local, somente GET, das contagens privadas do Conta Ovos."""

import json
import math
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from app_core import contaovos_client
from app_core import contaovos_credencial
from app_core import contaovos_integracao
from app_core import db as db_core
from app_core import ovitrampas


FLOW_COUNTS = "contagens"
EXECUTION_TYPE = "sincronizacao_contagens"
DEFAULT_MAX_PAGES = 100
LOCK_STALE_MINUTES = 30
SOURCE_LABEL = "API privada Conta Ovos"


class ContaOvosSyncError(RuntimeError):
    def __init__(self, message, *, kind="sync_error"):
        super().__init__(message)
        self.kind = kind


class ContaOvosSyncAlreadyRunning(ContaOvosSyncError):
    def __init__(self):
        super().__init__(
            "Ja existe uma sincronizacao de contagens Conta Ovos em andamento.",
            kind="already_running",
        )


def _text(value):
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _integer(value, field, *, minimum=None, maximum=None):
    text = _text(value)
    if text is None:
        raise ContaOvosSyncError(
            f"Registro remoto sem {field} valido.", kind="invalid_payload"
        )
    try:
        parsed_decimal = Decimal(text)
        if not parsed_decimal.is_finite():
            raise InvalidOperation
        parsed = int(parsed_decimal)
    except (InvalidOperation, ValueError, OverflowError):
        raise ContaOvosSyncError(
            f"Registro remoto com {field} invalido.", kind="invalid_payload"
        ) from None
    if parsed_decimal != parsed:
        raise ContaOvosSyncError(
            f"Registro remoto com {field} fracionario.", kind="invalid_payload"
        )
    if minimum is not None and parsed < minimum:
        raise ContaOvosSyncError(
            f"Registro remoto com {field} abaixo do limite.", kind="invalid_payload"
        )
    if maximum is not None and parsed > maximum:
        raise ContaOvosSyncError(
            f"Registro remoto com {field} acima do limite.", kind="invalid_payload"
        )
    return parsed


def _real(value, field):
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = float(text.replace(",", "."))
    except ValueError:
        raise ContaOvosSyncError(
            f"Registro remoto com {field} invalido.", kind="invalid_payload"
        ) from None
    if not math.isfinite(parsed):
        raise ContaOvosSyncError(
            f"Registro remoto com {field} invalido.", kind="invalid_payload"
        )
    return parsed


def _date(value, field):
    text = _text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        raise ContaOvosSyncError(
            f"Registro remoto com {field} invalido.", kind="invalid_payload"
        ) from None


def _datetime_text(value):
    text = _text(value)
    if text is None:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).isoformat(sep=" ")
    except ValueError:
        return text


def _date_filter(value, field):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip()[:10]).date().isoformat()
    except ValueError:
        raise ContaOvosSyncError(
            f"Informe {field}.", kind="invalid_date_filter"
        ) from None
    return parsed


def _first(row, *names):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def normalize_counting(row, *, imported_at=None):
    """Converte uma linha remota no formato historico ja usado pelo CSV."""
    if not isinstance(row, dict):
        raise ContaOvosSyncError(
            "A API retornou um item de contagem invalido.", kind="invalid_payload"
        )
    municipality_code = _text(row.get("municipality_code"))
    state_code = (_text(row.get("state_code")) or "").upper()
    if (
        municipality_code != contaovos_client.EXPECTED_MUNICIPALITY_CODE
        or state_code != contaovos_client.EXPECTED_STATE_CODE
    ):
        raise ContaOvosSyncError(
            "A API retornou contagem fora do municipio esperado.",
            kind="scope_mismatch",
        )

    counting_id = _integer(
        _first(row, "counting_id", "id_contagem"),
        "counting_id",
        minimum=1,
    )
    ovitrap_id = ovitrampas.normalizar_ovitrampa_id(
        _first(row, "ovitrap_id", "ovitrap_group_id", "ovitrampa_id")
    )
    if not ovitrap_id:
        raise ContaOvosSyncError(
            "Registro remoto sem identificador de ovitrampa valido.",
            kind="invalid_payload",
        )
    year = _integer(_first(row, "year", "ano"), "ano", minimum=2000, maximum=2100)
    week = _integer(_first(row, "week", "semana"), "semana", minimum=1, maximum=53)
    eggs = _integer(_first(row, "eggs", "ovos") or 0, "ovos", minimum=0)
    observation_code_raw = _first(
        row,
        "counting_observation_id",
        "observation_id",
        "codigo_conta_ovos",
    )
    observation_code = (
        _integer(observation_code_raw, "codigo de observacao", minimum=1, maximum=10)
        if observation_code_raw not in (None, "")
        else None
    )
    latitude = _real(_first(row, "latitude", "ovitrap_lat"), "latitude")
    longitude = _real(_first(row, "longitude", "ovitrap_lng"), "longitude")
    collected_date = _date(
        _first(row, "date_collect", "date", "data"), "data da contagem"
    )
    sent_at = _datetime_text(
        _first(row, "time", "counting_time", "data_envio_contagem")
    )
    imported_at = imported_at or datetime.now().isoformat(timespec="seconds")
    return {
        "id_contagem": str(counting_id),
        "ovitrampa_id": ovitrap_id,
        "ano": year,
        "semana": week,
        "data": collected_date,
        "data_envio_contagem": sent_at,
        "ovos": eggs,
        "resultado": _text(_first(row, "result", "resultado"))
        or ("Positiva" if eggs > 0 else "Negativa"),
        "codigo_conta_ovos": observation_code,
        "observacao_conta_ovos": _text(
            _first(row, "counting_observation", "observation", "observacao")
        ),
        "ocorrencia_codigo": ovitrampas.CONTA_OVOS_OCORRENCIAS.get(
            observation_code
        ),
        "latitude": latitude,
        "longitude": longitude,
        "lat_lng": (
            f"{latitude},{longitude}"
            if latitude is not None and longitude is not None
            else None
        ),
        "arquivo_origem": SOURCE_LABEL,
        "importado_em": imported_at,
    }


def fetch_countings(
    key,
    *,
    date_start=None,
    date_end=None,
    max_pages=DEFAULT_MAX_PAGES,
    page_fetcher=None,
    imported_at=None,
):
    """Pagina e normaliza tudo antes de permitir qualquer escrita local."""
    page_fetcher = page_fetcher or contaovos_client.private_counts_page
    try:
        max_pages = int(max_pages or 1)
    except (TypeError, ValueError):
        raise ContaOvosSyncError(
            "O limite de paginas e invalido.", kind="invalid_pagination"
        ) from None
    max_pages = max(1, min(max_pages, contaovos_client.MAX_PAGE))
    date_start = _date_filter(date_start, "uma data inicial valida")
    date_end = _date_filter(date_end, "uma data final valida")
    if date_start and date_end and date_start > date_end:
        raise ContaOvosSyncError(
            "A data inicial nao pode ser posterior a data final.",
            kind="invalid_date_filter",
        )
    imported_at = imported_at or datetime.now().isoformat(timespec="seconds")
    by_id = {}
    pages = 0
    for page in range(1, max_pages + 1):
        rows = page_fetcher(
            key,
            page=page,
            date_start=date_start,
            date_end=date_end,
        )
        pages = page
        if not rows:
            break
        for row in rows:
            normalized = normalize_counting(row, imported_at=imported_at)
            remote_id = normalized["id_contagem"]
            previous = by_id.get(remote_id)
            if previous is not None and previous != normalized:
                raise ContaOvosSyncError(
                    "A API retornou o mesmo counting_id com dados divergentes.",
                    kind="conflicting_duplicate",
                )
            by_id[remote_id] = normalized
    else:
        raise ContaOvosSyncError(
            "A consulta atingiu o limite de paginas; informe um intervalo de datas menor.",
            kind="pagination_limit",
        )
    records = sorted(by_id.values(), key=lambda item: int(item["id_contagem"]))
    return {"records": records, "pages": pages}


def _acquire_lock(conn, *, now, token):
    cutoff = (now - timedelta(minutes=LOCK_STALE_MINUTES)).isoformat(
        timespec="seconds"
    )
    now_text = now.isoformat(timespec="seconds")
    conn.execute(
        f"""INSERT INTO {contaovos_integracao.CURSOR_TABLE}
                (fluxo, ultimo_id_remoto, atualizado_em)
            VALUES (?, NULL, ?)
            ON CONFLICT (fluxo) DO NOTHING""",
        (FLOW_COUNTS, now_text),
    )
    cursor = conn.execute(
        f"""UPDATE {contaovos_integracao.CURSOR_TABLE}
               SET execucao_token=?, em_execucao_desde=?
             WHERE fluxo=?
               AND (
                    execucao_token IS NULL
                    OR em_execucao_desde IS NULL
                    OR em_execucao_desde < ?
               )""",
        (token, now_text, FLOW_COUNTS, cutoff),
    )
    if cursor.rowcount != 1:
        conn.rollback()
        raise ContaOvosSyncAlreadyRunning()
    conn.execute(
        f"""UPDATE {contaovos_integracao.EXECUTIONS_TABLE}
               SET status='erro', finalizado_em=?, itens_erro=itens_erro + 1,
                   resumo_sanitizado=?
             WHERE tipo=? AND status='executando' AND iniciado_em < ?""",
        (
            now_text,
            json.dumps(
                {"erro": "Execucao anterior interrompida antes da conclusao."},
                ensure_ascii=False,
            ),
            EXECUTION_TYPE,
            cutoff,
        ),
    )


def _create_execution(conn, now):
    statement = f"""INSERT INTO {contaovos_integracao.EXECUTIONS_TABLE}
        (tipo, iniciado_em, status, itens_ok, itens_erro)
        VALUES (?, ?, 'executando', 0, 0)"""
    return db_core.insert_and_get_id(
        conn,
        statement,
        (EXECUTION_TYPE, now.isoformat(timespec="seconds")),
        "id_execucao",
    )


def _cursor_value(conn):
    row = conn.execute(
        f"SELECT ultimo_id_remoto FROM {contaovos_integracao.CURSOR_TABLE} WHERE fluxo=?",
        (FLOW_COUNTS,),
    ).fetchone()
    if not row or row[0] in (None, ""):
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        raise ContaOvosSyncError(
            "O cursor local de contagens esta invalido.", kind="invalid_cursor"
        ) from None


def _finish_with_error(conn, execution_id, token, exc, key):
    try:
        conn.rollback()
        finished_at = datetime.now().isoformat(timespec="seconds")
        safe_error = contaovos_client.sanitize_message(exc, key)
        conn.execute(
            f"""UPDATE {contaovos_integracao.EXECUTIONS_TABLE}
                   SET finalizado_em=?, status='erro', itens_erro=1,
                       resumo_sanitizado=?
                 WHERE id_execucao=?""",
            (
                finished_at,
                json.dumps(
                    {
                        "tipo_erro": getattr(exc, "kind", "error"),
                        "erro": safe_error,
                    },
                    ensure_ascii=False,
                ),
                execution_id,
            ),
        )
        conn.execute(
            f"""UPDATE {contaovos_integracao.CURSOR_TABLE}
                   SET execucao_token=NULL, em_execucao_desde=NULL
                 WHERE fluxo=? AND execucao_token=?""",
            (FLOW_COUNTS, token),
        )
        conn.commit()
    except Exception:
        conn.rollback()


def synchronize_countings(
    target=None,
    *,
    key=None,
    date_start=None,
    date_end=None,
    max_pages=DEFAULT_MAX_PAGES,
    page_fetcher=None,
    now=None,
    connection=None,
):
    """Busca via GET e persiste localmente de modo atomico e idempotente."""
    key = key or contaovos_credencial.read_key()
    now = now or datetime.now()
    token = uuid.uuid4().hex
    owns_connection = connection is None
    conn = db_core.connect(target) if owns_connection else connection
    execution_id = None
    lock_acquired = False
    try:
        ovitrampas.ensure_schema(conn)
        contaovos_integracao.ensure_schema(conn)
        required_columns = ("em_execucao_desde", "execucao_token")
        if not all(
            db_core.column_exists(
                conn, contaovos_integracao.CURSOR_TABLE, column
            )
            for column in required_columns
        ):
            raise ContaOvosSyncError(
                "O schema Conta Ovos nao esta atualizado; aplique as migracoes pendentes.",
                kind="schema_outdated",
            )
        _acquire_lock(conn, now=now, token=token)
        lock_acquired = True
        cursor_before = _cursor_value(conn)
        execution_id = _create_execution(conn, now)
        conn.commit()

        fetched = fetch_countings(
            key,
            date_start=date_start,
            date_end=date_end,
            max_pages=max_pages,
            page_fetcher=page_fetcher,
            imported_at=now.isoformat(timespec="seconds"),
        )
        counts = {"inseridos": 0, "atualizados": 0, "sem_alteracao": 0}
        missing_ovitraps = set()
        for record in fetched["records"]:
            exists = conn.execute(
                f"SELECT 1 FROM {ovitrampas.ARMADILHAS_TABLE} WHERE ovitrampa_id=?",
                (record["ovitrampa_id"],),
            ).fetchone()
            if not exists:
                missing_ovitraps.add(record["ovitrampa_id"])
            status = ovitrampas.upsert_ocorrencia_conta_ovos(conn, record)
            counts[status] += 1

        remote_ids = [int(item["id_contagem"]) for item in fetched["records"]]
        cursor_after = max(
            [value for value in (cursor_before, *remote_ids) if value is not None],
            default=None,
        )
        finished_at = datetime.now().isoformat(timespec="seconds")
        summary = {
            "paginas": fetched["pages"],
            "registros": len(fetched["records"]),
            **counts,
            "ovitrampas_nao_cadastradas": len(missing_ovitraps),
            "cursor_anterior": str(cursor_before) if cursor_before is not None else None,
            "cursor_atual": str(cursor_after) if cursor_after is not None else None,
            "data_inicial": date_start,
            "data_final": date_end,
        }
        cursor_update = conn.execute(
            f"""UPDATE {contaovos_integracao.CURSOR_TABLE}
                   SET ultimo_id_remoto=?, atualizado_em=?,
                       execucao_token=NULL, em_execucao_desde=NULL
                 WHERE fluxo=? AND execucao_token=?""",
            (
                str(cursor_after) if cursor_after is not None else None,
                finished_at,
                FLOW_COUNTS,
                token,
            ),
        )
        if cursor_update.rowcount != 1:
            raise ContaOvosSyncError(
                "A sincronizacao perdeu a trava antes de concluir.",
                kind="lock_lost",
            )
        conn.execute(
            f"""UPDATE {contaovos_integracao.EXECUTIONS_TABLE}
                   SET finalizado_em=?, status='concluido', itens_ok=?,
                       itens_erro=0, resumo_sanitizado=?
                 WHERE id_execucao=?""",
            (
                finished_at,
                len(fetched["records"]),
                json.dumps(summary, ensure_ascii=False),
                execution_id,
            ),
        )
        conn.commit()
        return {"ok": True, "id_execucao": execution_id, **summary}
    except Exception as exc:
        if execution_id is not None and lock_acquired:
            _finish_with_error(conn, execution_id, token, exc, key)
        elif lock_acquired:
            try:
                conn.rollback()
                conn.execute(
                    f"""UPDATE {contaovos_integracao.CURSOR_TABLE}
                           SET execucao_token=NULL, em_execucao_desde=NULL
                         WHERE fluxo=? AND execucao_token=?""",
                    (FLOW_COUNTS, token),
                )
                conn.commit()
            except Exception:
                conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()
