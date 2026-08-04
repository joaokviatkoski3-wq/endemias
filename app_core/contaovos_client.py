"""Cliente HTTP somente leitura para a API privada Conta Ovos."""

import json
import os
import re
import time
from urllib import error, parse, request


BASE_URL = "https://contaovos.com/en-us/api"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_ATTEMPTS = 3
MAX_PAGE = 100
# Codigo IBGE de Almirante Tamandare/PR, escopo territorial oficial do sistema.
EXPECTED_MUNICIPALITY_CODE = "4100400"
EXPECTED_STATE_CODE = "PR"
EXPECTED_MUNICIPALITY_NAME = "Almirante Tamandaré"
EXPECTED_COUNTRY = "Brasil"
TEST_NETWORK_GUARD = "ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK"


class ContaOvosError(RuntimeError):
    def __init__(self, message, *, status_code=None, retriable=False, kind="error"):
        super().__init__(message)
        self.status_code = status_code
        self.retriable = bool(retriable)
        self.kind = kind


def sanitize_message(value, key=None):
    text = str(value or "")
    if key:
        text = text.replace(str(key), "[CHAVE_REMOVIDA]")
    return re.sub(
        r"(?i)(key=)[^&\s\"']+",
        r"\1[CHAVE_REMOVIDA]",
        text,
    )


def _private_url(path, key, params=None):
    query = {"key": key}
    query.update(params or {})
    return f"{BASE_URL}/{path.lstrip('/')}?{parse.urlencode(query)}"


def _public_url(path, params=None):
    query = parse.urlencode(params or {})
    suffix = f"?{query}" if query else ""
    return f"{BASE_URL}/{path.lstrip('/')}{suffix}"


def _decode_json(body):
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ContaOvosError(
            "A API Conta Ovos retornou JSON invalido.", kind="invalid_json"
        ) from None


def _open_json(
    url,
    *,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    opener=None,
    sleep=None,
):
    if opener is None and os.environ.get(TEST_NETWORK_GUARD) == "1":
        raise ContaOvosError(
            "Chamadas reais ao Conta Ovos estao bloqueadas durante os testes.",
            kind="test_network_blocked",
        )
    opener = request.urlopen if opener is None else opener
    sleep = time.sleep if sleep is None else sleep
    attempts = max(1, min(int(max_attempts or 1), 5))
    req = request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Endemias/ContaOvos"},
        method="GET",
    )
    for attempt in range(1, attempts + 1):
        try:
            with opener(req, timeout=timeout) as response:
                return _decode_json(response.read())
        except error.HTTPError as exc:
            status_code = int(exc.code)
            exc.close()
            if status_code == 500 and attempt < attempts:
                sleep(min(2 ** (attempt - 1), 4))
                continue
            if status_code == 500:
                raise ContaOvosError(
                    "A API Conta Ovos apresentou erro interno apos novas tentativas.",
                    status_code=500,
                    retriable=True,
                    kind="http_error",
                ) from None
            raise ContaOvosError(
                f"A API Conta Ovos recusou a consulta (HTTP {status_code}).",
                status_code=status_code,
                retriable=False,
                kind="http_error",
            ) from None
        except (error.URLError, TimeoutError, OSError):
            if attempt < attempts:
                sleep(min(2 ** (attempt - 1), 4))
                continue
            raise ContaOvosError(
                "Nao foi possivel conectar a API Conta Ovos apos novas tentativas.",
                retriable=True,
                kind="network_error",
            ) from None


def private_counts_page(
    key,
    *,
    page=1,
    date_start=None,
    date_end=None,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    opener=None,
    sleep=None,
):
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    page = max(1, min(page, MAX_PAGE))
    params = {"page": page}
    if date_start:
        params["date_start"] = str(date_start)
    if date_end:
        params["date_end"] = str(date_end)
    data = _open_json(
        _private_url("lastcounting", key, params),
        timeout=timeout,
        max_attempts=max_attempts,
        opener=opener,
        sleep=sleep,
    )
    if not isinstance(data, list):
        raise ContaOvosError(
            "A API Conta Ovos respondeu HTTP 200 sem retornar uma lista.",
            kind="unexpected_payload",
        )
    return data


def public_ovitraps_page(
    *,
    page=1,
    country=EXPECTED_COUNTRY,
    state=EXPECTED_STATE_CODE,
    municipality=EXPECTED_MUNICIPALITY_NAME,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    opener=None,
    sleep=None,
):
    """Consulta o cadastro publico de ovitrampas (sem chave privada).

    Endpoint publico documentado: GET /getmunicipalityovitrapspublic.
    """
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    page = max(1, min(page, MAX_PAGE))
    params = {"page": page}
    if country:
        params["country"] = str(country)
    if state:
        params["state"] = str(state)
    if municipality:
        params["municipality"] = str(municipality)
    data = _open_json(
        _public_url("getmunicipalityovitrapspublic", params),
        timeout=timeout,
        max_attempts=max_attempts,
        opener=opener,
        sleep=sleep,
    )
    if not isinstance(data, list):
        raise ContaOvosError(
            "A API Conta Ovos respondeu sem retornar uma lista de ovitrampas.",
            kind="unexpected_payload",
        )
    return data


def validate_private_access(
    key,
    *,
    expected_municipality_code=EXPECTED_MUNICIPALITY_CODE,
    expected_state_code=EXPECTED_STATE_CODE,
    opener=None,
    sleep=None,
):
    rows = private_counts_page(
        key,
        page=1,
        opener=opener,
        sleep=sleep,
    )
    scopes = sorted(
        {
            (
                str(row.get("municipality") or "").strip(),
                str(row.get("municipality_code") or "").strip(),
                str(row.get("state_code") or "").strip().upper(),
            )
            for row in rows
            if isinstance(row, dict)
        }
    )
    scopes = [scope for scope in scopes if any(scope)]
    if not scopes:
        raise ContaOvosError(
            "A chave foi aceita, mas a primeira pagina nao permitiu confirmar o escopo.",
            kind="scope_not_confirmed",
        )
    unexpected = [
        scope
        for scope in scopes
        if scope[1] != str(expected_municipality_code)
        or scope[2] != str(expected_state_code).upper()
    ]
    if unexpected:
        raise ContaOvosError(
            "A chave privada retornou dados fora do municipio esperado.",
            kind="scope_mismatch",
        )
    return {
        "ok": True,
        "page_items": len(rows),
        "scopes": [
            {
                "municipality": municipality,
                "municipality_code": municipality_code,
                "state_code": state_code,
            }
            for municipality, municipality_code, state_code in scopes
        ],
        "credential_format": (
            "documented"
            if len(key) == 45 and key.isalpha()
            else "accepted_non_documented_format"
        ),
    }
