"""Geocodificacao supervisionada de enderecos normalizados.

O cliente usa a busca estruturada do Nominatim e limita as requisicoes para
respeitar o servico publico. A decisao de aceitar ou revisar um resultado fica
na camada de dominio de ``logradouros``.
"""

import json
import os
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NOMINATIM_URL = os.environ.get(
    "ENDEMIAS_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"
)
USER_AGENT = os.environ.get(
    "ENDEMIAS_GEOCODER_USER_AGENT",
    "Endemias-Almirante-Tamandare/1.0 (https://github.com/joaokviatkoski3-wq/endemias)",
)
MIN_INTERVAL_SECONDS = 1.1
_request_lock = threading.Lock()
_last_request_at = 0.0


class GeocodificacaoErro(RuntimeError):
    """Falha temporaria ou resposta invalida do servico externo."""


def buscar_nominatim(logradouro, numero, timeout=15):
    """Retorna candidatos brutos do Nominatim para Almirante Tamandare."""
    params = {
        "street": f"{numero} {logradouro}",
        "city": "Almirante Tamandaré",
        "state": "Paraná",
        "country": "Brasil",
        "countrycodes": "br",
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "5",
        "accept-language": "pt-BR",
    }
    request = Request(
        f"{NOMINATIM_URL}?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    global _last_request_at
    try:
        with _request_lock:
            espera = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
            if espera > 0:
                time.sleep(espera)
            try:
                with urlopen(request, timeout=timeout) as response:
                    payload = response.read(2 * 1024 * 1024)
            finally:
                _last_request_at = time.monotonic()
        data = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise GeocodificacaoErro(
            "O serviço de coordenadas não respondeu. Tente novamente mais tarde."
        ) from exc
    if not isinstance(data, list):
        raise GeocodificacaoErro("O serviço de coordenadas retornou uma resposta inválida.")
    return data
