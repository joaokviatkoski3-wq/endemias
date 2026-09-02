"""Fila local e reconciliacao segura das leituras de ovitrampas.

Este modulo nao envia dados ao Conta Ovos. Ele prepara o payload futuro,
valida os dados locais e reconhece leituras que ja existem no historico GET.
"""

import hashlib
import json
from datetime import date, datetime

from app_core import db as db_core
from app_core import contaovos_client
from app_core import ovitrampas
from app_core import ovitrampas_laboratorio
from app_core import sispncd


QUEUE_TABLE = "contaovos_fila_contagens"
STATUS_PENDING = "pendente"
STATUS_SENDING = "enviando"
STATUS_CONFIRMED = "confirmado"
STATUS_ERROR = "erro"
ALLOWED_STATUSES = (
    STATUS_PENDING,
    STATUS_SENDING,
    STATUS_CONFIRMED,
    STATUS_ERROR,
)


class ContaOvosQueueError(ValueError):
    def __init__(self, message, *, kind="queue_error", issues=None):
        super().__init__(message)
        self.kind = kind
        self.issues = list(issues or ())


def ensure_schema(target):
    conn = db_core.connect(target)
    try:
        ensure_schema_connection(conn)
        conn.commit()
    finally:
        conn.close()


def ensure_schema_connection(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {QUEUE_TABLE} (
            id_fila INTEGER PRIMARY KEY AUTOINCREMENT,
            id_item INTEGER NOT NULL UNIQUE
                REFERENCES {ovitrampas_laboratorio.ITENS_TABLE}(id_item),
            status TEXT NOT NULL DEFAULT '{STATUS_PENDING}'
                CHECK(status IN ('pendente','enviando','confirmado','erro')),
            tentativas INTEGER NOT NULL DEFAULT 0 CHECK(tentativas >= 0),
            id_remoto TEXT,
            erro_sanitizado TEXT,
            payload_hash TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            ultima_tentativa_em TEXT,
            confirmado_em TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_contaovos_fila_contagens_status
            ON {QUEUE_TABLE}(status, atualizado_em, id_fila);
        """
    )


def occurrence_code_for_api(local_code):
    if local_code in (None, ""):
        return 1
    try:
        local_code = int(local_code)
    except (TypeError, ValueError):
        raise ContaOvosQueueError(
            "A ocorrencia local e invalida.", kind="invalid_occurrence"
        ) from None
    inverse = {local: remote for remote, local in ovitrampas.CONTA_OVOS_OCORRENCIAS.items()}
    remote = inverse.get(local_code)
    if remote is None or local_code not in ovitrampas_laboratorio.OCORRENCIAS:
        raise ContaOvosQueueError(
            "A ocorrencia local nao possui mapeamento seguro para o Conta Ovos.",
            kind="unsupported_occurrence",
        )
    return remote


def _number(value, field, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ContaOvosQueueError(
            f"{field} nao informada.", kind="missing_coordinates"
        ) from None
    if not minimum <= parsed <= maximum:
        raise ContaOvosQueueError(
            f"{field} fora da faixa valida.", kind="invalid_coordinates"
        )
    return parsed


def _iso_date(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        raise ContaOvosQueueError(
            "A data do movimento e invalida.", kind="invalid_date"
        ) from None


def _payload(row, data_instalacao=None):
    ovitrap_id = str(row["ovitrampa_id"] or "").strip()
    if not ovitrap_id:
        raise ContaOvosQueueError(
            "A ovitrampa nao possui identificador.", kind="invalid_ovitrap_id"
        )
    eggs = int(row["ovos"] or 0)
    if eggs < 0 or eggs > 100000:
        raise ContaOvosQueueError(
            "A quantidade de ovos e invalida.", kind="invalid_eggs"
        )
    # No Conta Ovos, 'date' e a data de instalacao (ancora da semana) e
    # 'counting_date_collect' e a data de coleta. No lote de laboratorio,
    # data_movimento e a COleta (troca/retirada); a instalacao vem do calendario
    # (derivada por _derivar_instalacao). Sem calendario/evento, mantemos o
    # comportamento antigo (usa data_movimento) por retrocompatibilidade.
    data_coleta = _iso_date(row["data_movimento"])
    data_inst = _iso_date(data_instalacao) if data_instalacao else data_coleta
    return {
        "ovitrap_group_id": ovitrap_id,
        "ovitrap_lat": _number(row["latitude"], "Latitude", -90, 90),
        "ovitrap_lng": _number(row["longitude"], "Longitude", -180, 180),
        "date": data_inst,
        "counting_date_collect": data_coleta,
        "counting_observation_id": occurrence_code_for_api(row["ocorrencia"]),
        "counting_observation": "",
        "counting_eggs": eggs,
    }


def _derivar_instalacao(conn, id_evento, data_coleta):
    """Data de instalacao das ovitrampas coletadas num lote (do calendario).

    O calendario e a fonte da verdade. Para um lote de troca/retirada na data
    ``data_coleta`` (do grupo do ``id_evento``), as ovitrampas coletadas foram
    instaladas no ultimo evento do mesmo grupo, antes dessa data, com movimento
    instalacao/troca. Retorna a data ou None (ex.: evento/calendario ausente).
    """
    if id_evento in (None, "") or not data_coleta:
        return None
    try:
        evento = conn.execute(
            "SELECT id_grupo, data FROM ovitrampas_calendario_eventos WHERE id_evento=?",
            (int(id_evento),),
        ).fetchone()
        if not evento or not evento["id_grupo"]:
            return None
        linha = conn.execute(
            """SELECT data FROM ovitrampas_calendario_eventos
                WHERE id_grupo=? AND data < ? AND movimento IN ('instalacao','troca')
                ORDER BY data DESC, id_evento DESC
                LIMIT 1""",
            (evento["id_grupo"], str(data_coleta)[:10]),
        ).fetchone()
        return linha["data"] if linha else None
    except Exception:
        return None


def payload_hash(payload):
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lot_rows(conn, lot_id):
    lot = conn.execute(
        f"SELECT * FROM {ovitrampas_laboratorio.LOTES_TABLE} WHERE id_lote=?",
        (int(lot_id),),
    ).fetchone()
    if not lot:
        raise ContaOvosQueueError("Lote de leitura nao encontrado.", kind="not_found")
    if lot["status"] not in ("concluido", "enviado_conta_ovos"):
        raise ContaOvosQueueError(
            "O lote precisa estar concluido pelo laboratorio.", kind="lot_not_completed"
        )
    rows = conn.execute(
        f"""SELECT i.id_item, i.ovitrampa_id, i.ovos, i.ocorrencia,
                   l.data_movimento, a.latitude, a.longitude
              FROM {ovitrampas_laboratorio.ITENS_TABLE} i
              JOIN {ovitrampas_laboratorio.LOTES_TABLE} l ON l.id_lote=i.id_lote
              LEFT JOIN {ovitrampas.ARMADILHAS_TABLE} a
                ON a.ovitrampa_id=i.ovitrampa_id
             WHERE i.id_lote=?
             ORDER BY i.id_item""",
        (int(lot_id),),
    ).fetchall()
    if not rows:
        raise ContaOvosQueueError("O lote nao possui leituras.", kind="empty_lot")
    return lot, rows


def _find_remote(conn, payload):
    rows = conn.execute(
        f"""SELECT id_contagem, ovos, ocorrencia_codigo
              FROM {ovitrampas.OCORRENCIAS_TABLE}
             WHERE ovitrampa_id=? AND data=?
             ORDER BY CAST(id_contagem AS TEXT)""",
        (payload["ovitrap_group_id"], payload["counting_date_collect"]),
    ).fetchall()
    if len(rows) > 1:
        return None, "Mais de uma contagem remota foi encontrada para a mesma data."
    if not rows:
        return None, None
    row = rows[0]
    local_occurrence = ovitrampas.CONTA_OVOS_OCORRENCIAS.get(
        payload["counting_observation_id"]
    )
    remote_occurrence = row["ocorrencia_codigo"]
    if int(row["ovos"] or 0) != payload["counting_eggs"]:
        return None, "A quantidade de ovos diverge da contagem remota."
    if (remote_occurrence or None) != (local_occurrence or None):
        return None, "A ocorrencia diverge da contagem remota."
    return str(row["id_contagem"]), None


def prepare_and_reconcile(conn, lot_id, *, now=None):
    """Prepara a fila e reconcilia somente contra o historico GET local."""
    ensure_schema_connection(conn)
    now_text = (now or datetime.now()).isoformat(timespec="seconds")
    lot, rows = _lot_rows(conn, lot_id)
    id_evento = None
    try:
        id_evento = lot["id_evento"]
    except (KeyError, IndexError):
        pass
    data_instalacao = _derivar_instalacao(conn, id_evento, lot["data_movimento"])
    prepared = []
    issues = []
    for row in rows:
        try:
            payload = _payload(row, data_instalacao=data_instalacao)
            prepared.append((row, payload, payload_hash(payload)))
        except ContaOvosQueueError as exc:
            issues.append(
                {
                    "id_item": row["id_item"],
                    "ovitrampa_id": row["ovitrampa_id"],
                    "tipo": exc.kind,
                    "erro": str(exc),
                }
            )
    if issues:
        raise ContaOvosQueueError(
            "O lote possui leituras que impedem a preparacao da fila.",
            kind="validation_failed",
            issues=issues,
        )

    summary = {
        "id_lote": int(lot["id_lote"]),
        "total": len(prepared),
        "pendentes": 0,
        "confirmados": 0,
        "erros": 0,
    }
    for row, payload, digest in prepared:
        current = conn.execute(
            f"SELECT * FROM {QUEUE_TABLE} WHERE id_item=?", (row["id_item"],)
        ).fetchone()
        if (
            current
            and current["status"] == STATUS_CONFIRMED
            and current["payload_hash"] != digest
        ):
            raise ContaOvosQueueError(
                "Uma leitura ja confirmada foi alterada localmente.",
                kind="confirmed_payload_changed",
                issues=[
                    {
                        "id_item": row["id_item"],
                        "ovitrampa_id": row["ovitrampa_id"],
                        "tipo": "confirmed_payload_changed",
                        "erro": "Revisao humana obrigatoria; nenhuma exclusao remota e automatica.",
                    }
                ],
            )
        remote_id, conflict = _find_remote(conn, payload)
        if (
            current
            and current["status"] == STATUS_SENDING
            and remote_id is None
            and conflict is None
        ):
            conflict = (
                "Uma tentativa anterior ficou em envio e nao foi localizada no "
                "historico sincronizado; revise antes de tentar novamente."
            )
        if conflict:
            status = STATUS_ERROR
            summary["erros"] += 1
        elif remote_id:
            status = STATUS_CONFIRMED
            summary["confirmados"] += 1
        else:
            status = STATUS_PENDING
            summary["pendentes"] += 1
        confirmed_at = now_text if status == STATUS_CONFIRMED else None
        conn.execute(
            f"""INSERT INTO {QUEUE_TABLE}
                    (id_item, status, tentativas, id_remoto, erro_sanitizado,
                     payload_hash, criado_em, atualizado_em, confirmado_em)
                VALUES (?,?,0,?,?,?,?,?,?)
                ON CONFLICT (id_item) DO UPDATE SET
                    status=excluded.status,
                    id_remoto=excluded.id_remoto,
                    erro_sanitizado=excluded.erro_sanitizado,
                    payload_hash=excluded.payload_hash,
                    atualizado_em=excluded.atualizado_em,
                    confirmado_em=excluded.confirmado_em""",
            (
                row["id_item"],
                status,
                remote_id,
                conflict,
                digest,
                now_text,
                now_text,
                confirmed_at,
            ),
        )
    return summary


def lot_queue_status(conn, lot_id):
    ensure_schema_connection(conn)
    rows = conn.execute(
        f"""SELECT q.status, COUNT(*) AS total
              FROM {QUEUE_TABLE} q
              JOIN {ovitrampas_laboratorio.ITENS_TABLE} i ON i.id_item=q.id_item
             WHERE i.id_lote=?
             GROUP BY q.status""",
        (int(lot_id),),
    ).fetchall()
    result = {status: 0 for status in ALLOWED_STATUSES}
    for row in rows:
        result[row["status"]] = int(row["total"] or 0)
    result["total"] = sum(result.values())
    return result


def check_epidemiological_weeks(conn, *, date_start=None, date_end=None, limit=20):
    """Compara semana/ano devolvidos pela API com o algoritmo local."""
    clauses = ["data IS NOT NULL", "ano IS NOT NULL", "semana IS NOT NULL"]
    params = []
    if date_start:
        clauses.append("data >= ?")
        params.append(_iso_date(date_start))
    if date_end:
        clauses.append("data <= ?")
        params.append(_iso_date(date_end))
    rows = conn.execute(
        f"""SELECT id_contagem, ovitrampa_id, data, ano, semana
              FROM {ovitrampas.OCORRENCIAS_TABLE}
             WHERE {' AND '.join(clauses)}
             ORDER BY data, id_contagem""",
        params,
    ).fetchall()
    divergences = []
    divergence_count = 0
    for row in rows:
        local_year, local_week = sispncd.epidemiological_week_for_date(row["data"])
        if int(row["ano"]) != local_year or int(row["semana"]) != local_week:
            divergence_count += 1
            if len(divergences) < max(1, min(int(limit or 20), 100)):
                divergences.append(
                    {
                        "id_contagem": str(row["id_contagem"]),
                        "ovitrampa_id": row["ovitrampa_id"],
                        "data": str(row["data"]),
                        "remoto": {"ano": int(row["ano"]), "semana": int(row["semana"])},
                        "local": {"ano": local_year, "semana": local_week},
                    }
                )
    return {
        "ok": divergence_count == 0,
        "comparados": len(rows),
        "divergencias": divergence_count,
        "exemplos": divergences,
    }


def check_remote_epidemiological_weeks(
    key,
    *,
    date_start,
    date_end,
    max_pages=100,
    page_fetcher=None,
    limit=20,
):
    """Compara ``date/year/week`` brutos da API, sem persistir nada."""
    page_fetcher = page_fetcher or contaovos_client.private_counts_page
    max_pages = max(1, min(int(max_pages or 1), contaovos_client.MAX_PAGE))
    examples = []
    compared = 0
    divergence_count = 0
    pages = 0
    for page in range(1, max_pages + 1):
        rows = page_fetcher(
            key,
            page=page,
            date_start=_iso_date(date_start),
            date_end=_iso_date(date_end),
        )
        pages = page
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                raise ContaOvosQueueError(
                    "A API retornou uma contagem invalida.", kind="invalid_payload"
                )
            if (
                str(row.get("municipality_code") or "").strip()
                != contaovos_client.EXPECTED_MUNICIPALITY_CODE
                or str(row.get("state_code") or "").strip().upper()
                != contaovos_client.EXPECTED_STATE_CODE
            ):
                raise ContaOvosQueueError(
                    "A API retornou dados fora do municipio esperado.",
                    kind="scope_mismatch",
                )
            try:
                remote_date = date.fromisoformat(str(row.get("date"))[:10])
                remote_year = int(row.get("year"))
                remote_week = int(row.get("week"))
            except (TypeError, ValueError):
                raise ContaOvosQueueError(
                    "A API retornou data, ano ou semana invalidos.",
                    kind="invalid_payload",
                ) from None
            local_year, local_week = sispncd.epidemiological_week_for_date(
                remote_date
            )
            compared += 1
            if (remote_year, remote_week) != (local_year, local_week):
                divergence_count += 1
                if len(examples) < max(1, min(int(limit or 20), 100)):
                    examples.append(
                        {
                            "id_contagem": str(row.get("counting_id") or ""),
                            "ovitrampa_id": str(row.get("ovitrap_id") or ""),
                            "data": remote_date.isoformat(),
                            "remoto": {"ano": remote_year, "semana": remote_week},
                            "local": {"ano": local_year, "semana": local_week},
                        }
                    )
    else:
        raise ContaOvosQueueError(
            "A validacao atingiu o limite de paginas; use um intervalo menor.",
            kind="pagination_limit",
        )
    return {
        "ok": divergence_count == 0,
        "comparados": compared,
        "divergencias": divergence_count,
        "paginas": pages,
        "exemplos": examples,
    }
