"""Espelho local, somente GET, do cadastro publico de ovitrampas do Conta Ovos.

Este modulo nunca envia, altera nem exclui dados remotos. Ele consulta o
endpoint publico ``getmunicipalityovitrapspublic`` (sem chave privada),
valida tudo antes de gravar e mantem uma tabela de espelho separada de
``ovitrampas_armadilhas``: os campos remotos ficam aqui; responsavel,
telefone e demais complementos locais continuam exclusivos da tabela local
e nunca sao sobrescritos por este sincronizador.
"""

import json
from datetime import datetime

from app_core import contaovos_client
from app_core import contaovos_integracao
from app_core import db as db_core


TABLE = "contaovos_registro_ovitrampas"
EXECUTION_TYPE = "sincronizacao_registro_ovitrampas"
DEFAULT_MAX_PAGES = 100


class ContaOvosRegistroError(RuntimeError):
    def __init__(self, message, *, kind="registro_error"):
        super().__init__(message)
        self.kind = kind


def ensure_schema_connection(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            ovitrampa_id_remoto  TEXT PRIMARY KEY,
            ovitrap_id           TEXT,
            latitude             REAL,
            longitude            REAL,
            coordenada_erro      INTEGER,
            municipio            TEXT,
            municipio_codigo     TEXT,
            estado               TEXT,
            ovos_media           REAL,
            quarteirao_remoto_id TEXT,
            grupo_remoto_id      TEXT,
            usuario_remoto_id    TEXT,
            atualizado_remoto_em TEXT,
            sincronizado_em      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_contaovos_registro_ovitrampas_sincronizado
            ON {TABLE}(sincronizado_em DESC);
        """
    )


def _text(value):
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _real(value):
    text = _text(value)
    if text is None:
        return None
    try:
        return float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _normalize_row(row):
    """Valida e normaliza uma linha remota antes de qualquer escrita."""
    if not isinstance(row, dict):
        raise ContaOvosRegistroError(
            "A API retornou uma ovitrampa invalida.", kind="invalid_payload"
        )
    remote_id = _text(row.get("ovitrap_group_id"))
    if not remote_id:
        raise ContaOvosRegistroError(
            "Registro remoto sem ovitrap_group_id.", kind="invalid_payload"
        )
    municipality_code = _text(row.get("municipality_code"))
    state_code = (_text(row.get("state_code")) or "").upper()
    if (
        municipality_code != contaovos_client.EXPECTED_MUNICIPALITY_CODE
        or state_code != contaovos_client.EXPECTED_STATE_CODE
    ):
        raise ContaOvosRegistroError(
            "A API retornou ovitrampa fora do municipio esperado.",
            kind="scope_mismatch",
        )
    latitude = _real(row.get("ovitrap_lat"))
    longitude = _real(row.get("ovitrap_lng"))
    return {
        "ovitrampa_id_remoto": remote_id,
        "ovitrap_id": _text(row.get("ovitrap_id")),
        "latitude": latitude,
        "longitude": longitude,
        "coordenada_erro": (
            int(row["ovitrap_lat_lng_error"])
            if _text(row.get("ovitrap_lat_lng_error")) is not None
            else None
        ),
        "municipio": _text(row.get("municipality")),
        "municipio_codigo": municipality_code,
        "estado": state_code or None,
        "ovos_media": _real(row.get("ovitrap_eggs_mean")),
        "quarteirao_remoto_id": _text(row.get("ovitrap_block_id")),
        "grupo_remoto_id": _text(row.get("group_id")),
        "usuario_remoto_id": _text(row.get("user_id")),
        "atualizado_remoto_em": _text(row.get("ovitrap_datetime")),
    }


def fetch_registro(*, max_pages=DEFAULT_MAX_PAGES, page_fetcher=None):
    """Pagina o endpoint publico e normaliza tudo antes de qualquer escrita."""
    page_fetcher = page_fetcher or contaovos_client.public_ovitraps_page
    max_pages = max(1, min(int(max_pages or 1), contaovos_client.MAX_PAGE))
    by_id = {}
    pages = 0
    for page in range(1, max_pages + 1):
        rows = page_fetcher(page=page)
        pages = page
        if not rows:
            break
        for row in rows:
            normalized = _normalize_row(row)
            by_id[normalized["ovitrampa_id_remoto"]] = normalized
    else:
        raise ContaOvosRegistroError(
            "A consulta atingiu o limite de paginas do cadastro publico.",
            kind="pagination_limit",
        )
    return {"records": list(by_id.values()), "pages": pages}


def synchronize(target=None, *, max_pages=DEFAULT_MAX_PAGES, page_fetcher=None,
                 now=None, connection=None):
    """Busca via GET e substitui o espelho local de forma atomica."""
    now = now or datetime.now()
    now_text = now.isoformat(timespec="seconds")
    owns_connection = connection is None
    conn = db_core.connect(target) if owns_connection else connection
    execution_id = None
    try:
        ensure_schema_connection(conn)
        contaovos_integracao.ensure_schema(conn)

        statement = f"""INSERT INTO {contaovos_integracao.EXECUTIONS_TABLE}
            (tipo, iniciado_em, status, itens_ok, itens_erro)
            VALUES (?, ?, 'executando', 0, 0)"""
        execution_id = db_core.insert_and_get_id(
            conn, statement, (EXECUTION_TYPE, now_text), "id_execucao"
        )
        conn.commit()

        fetched = fetch_registro(max_pages=max_pages, page_fetcher=page_fetcher)

        counts = {"inseridos": 0, "atualizados": 0, "sem_alteracao": 0}
        for record in fetched["records"]:
            current = conn.execute(
                f"SELECT * FROM {TABLE} WHERE ovitrampa_id_remoto=?",
                (record["ovitrampa_id_remoto"],),
            ).fetchone()
            if not current:
                conn.execute(
                    f"""INSERT INTO {TABLE}
                        (ovitrampa_id_remoto, ovitrap_id, latitude, longitude,
                         coordenada_erro, municipio, municipio_codigo, estado,
                         ovos_media, quarteirao_remoto_id, grupo_remoto_id,
                         usuario_remoto_id, atualizado_remoto_em, sincronizado_em)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record["ovitrampa_id_remoto"], record["ovitrap_id"],
                        record["latitude"], record["longitude"],
                        record["coordenada_erro"], record["municipio"],
                        record["municipio_codigo"], record["estado"],
                        record["ovos_media"], record["quarteirao_remoto_id"],
                        record["grupo_remoto_id"], record["usuario_remoto_id"],
                        record["atualizado_remoto_em"], now_text,
                    ),
                )
                counts["inseridos"] += 1
                continue
            current = db_core.serialize_row(current)
            campos_comparaveis = (
                "ovitrap_id", "latitude", "longitude", "coordenada_erro",
                "municipio", "municipio_codigo", "estado", "ovos_media",
                "quarteirao_remoto_id", "grupo_remoto_id", "usuario_remoto_id",
                "atualizado_remoto_em",
            )
            mudou = any(
                current.get(campo) != record[campo] for campo in campos_comparaveis
            )
            if not mudou:
                counts["sem_alteracao"] += 1
                continue
            conn.execute(
                f"""UPDATE {TABLE}
                       SET ovitrap_id=?, latitude=?, longitude=?, coordenada_erro=?,
                           municipio=?, municipio_codigo=?, estado=?, ovos_media=?,
                           quarteirao_remoto_id=?, grupo_remoto_id=?,
                           usuario_remoto_id=?, atualizado_remoto_em=?,
                           sincronizado_em=?
                     WHERE ovitrampa_id_remoto=?""",
                (
                    record["ovitrap_id"], record["latitude"], record["longitude"],
                    record["coordenada_erro"], record["municipio"],
                    record["municipio_codigo"], record["estado"],
                    record["ovos_media"], record["quarteirao_remoto_id"],
                    record["grupo_remoto_id"], record["usuario_remoto_id"],
                    record["atualizado_remoto_em"], now_text,
                    record["ovitrampa_id_remoto"],
                ),
            )
            counts["atualizados"] += 1

        finished_at = datetime.now().isoformat(timespec="seconds")
        summary = {"paginas": fetched["pages"], "registros": len(fetched["records"]), **counts}
        conn.execute(
            f"""UPDATE {contaovos_integracao.EXECUTIONS_TABLE}
                   SET finalizado_em=?, status='concluido', itens_ok=?,
                       itens_erro=0, resumo_sanitizado=?
                 WHERE id_execucao=?""",
            (finished_at, len(fetched["records"]), json.dumps(summary, ensure_ascii=False), execution_id),
        )
        conn.commit()
        return {"ok": True, "id_execucao": execution_id, **summary}
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        if execution_id is not None:
            try:
                finished_at = datetime.now().isoformat(timespec="seconds")
                conn.execute(
                    f"""UPDATE {contaovos_integracao.EXECUTIONS_TABLE}
                           SET finalizado_em=?, status='erro', itens_erro=1,
                               resumo_sanitizado=?
                         WHERE id_execucao=?""",
                    (
                        finished_at,
                        json.dumps(
                            {"tipo_erro": getattr(exc, "kind", "error"), "erro": str(exc)},
                            ensure_ascii=False,
                        ),
                        execution_id,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()
