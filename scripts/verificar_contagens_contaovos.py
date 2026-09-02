"""Fase 1 - Verificacao (somente leitura) das contagens do Conta Ovos.

Consulta /lastcounting e lista as contagens que correspondem ao alvo da
correcao: data de instalacao 17/08/2026 e data de coleta 24/08/2026 (as
enviadas em 02/09/2026 com instalacao errada). NAO altera nada no Conta Ovos:
apenas GET e escrita de um arquivo local opcional.

Uso (console elevado que leia C:\\ProgramData\\Endemias\\contaovos.key):

    python scripts/verificar_contagens_contaovos.py
    python scripts/verificar_contagens_contaovos.py --ids 123,456,789
    python scripts/verificar_contagens_contaovos.py --salvar contagens_afetadas.json

Para ver TODOS os campos brutos (nomes exatos) de cada registro, use --bruto.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_client  # noqa: E402
from app_core import contaovos_credencial  # noqa: E402
from app_core import ovitrampas  # noqa: E402

DEFAULT_BASE = contaovos_client.BASE_URL
INSTALACAO_ESPERADA = "2026-08-17"
COLETA_ESPERADA = "2026-08-24"


def _parse_ids(valor):
    ids = set()
    for pedaco in (valor or "").replace(";", ",").split(","):
        pedaco = pedaco.strip()
        if pedaco:
            ids.add(pedaco)
    return ids


def _parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=DEFAULT_BASE, help="Base da API Conta Ovos.")
    p.add_argument("--ids", default="", help="Filtro opcional por ovitrampa_group_id (separado por virgula).")
    p.add_argument("--date-ini", default=INSTALACAO_ESPERADA)
    p.add_argument("--date-fim", default="2026-08-24")
    p.add_argument("--salvar", default="", help="Caminho para salvar os registros brutos em JSON.")
    p.add_argument("--bruto", action="store_true", help="Exibir todos os campos de cada registro.")
    return p


def _todas_paginas(key, date_ini, date_fim):
    resultados = []
    for pagina in range(1, contaovos_client.MAX_PAGE + 1):
        linha = contaovos_client.private_counts_page(
            key,
            page=pagina,
            date_start=date_ini,
            date_end=date_fim,
        )
        if not linha:
            break
        resultados.extend(linha)
    return resultados


def main(argv=None):
    args = _parser().parse_args(argv)
    if not contaovos_credencial.configured():
        print("[ERRO] Credencial Conta Ovos nao configurada "
              "(rode configurar_contaovos.bat como administrador).")
        return 2
    key = contaovos_credencial.read_key()
    ids_alvo = _parse_ids(args.ids)

    print(f"Consultando /lastcounting ({args.base}) "
          f"{args.date_ini}..{args.date_fim} (somente leitura)...")
    registros = _todas_paginas(key, args.date_ini, args.date_fim)

    afetados = []
    for rec in registros:
        if not isinstance(rec, dict):
            continue
        ovitrap = ovitrampas.normalizar_ovitrampa_id(
            contaovos_sync_first(rec, "ovitrap_id", "ovitrap_group_id", "ovitrampa_id")
        )
        if not ovitrap:
            continue
        if ids_alvo and ovitrap not in ids_alvo:
            continue
        data = str(rec.get("date") or rec.get("data") or "")
        coleta = str(rec.get("date_collect")
                     or rec.get("counting_date_collect")
                     or rec.get("data_coleta") or "")
        if data[:10] != INSTALACAO_ESPERADA:
            continue
        if coleta[:10] != COLETA_ESPERADA:
            continue
        afetados.append({**rec, "_ovitrap_normalizado": ovitrap})

    print(f"\nRegistros encontrados com instalacao={INSTALACAO_ESPERADA} e "
          f"coleta={COLETA_ESPERADA}: {len(afetados)}")
    for rec in afetados:
        ovitrap = rec["_ovitrap_normalizado"]
        print(f"  ovitrampa={ovitrap}")
        if args.bruto:
            for chave, valor in rec.items():
                print(f"      {chave!r}: {valor!r}")
        else:
            for chave in ("date", "data", "date_collect", "counting_date_collect",
                          "eggs", "ovos", "counting_observation_id",
                          "ovitrap_lat", "ovitrap_lng", "latitude", "longitude",
                          "counting_id", "id_contagem"):
                if chave in rec:
                    print(f"      {chave}: {rec[chave]}")

    if args.salvar:
        caminho = Path(args.salvar)
        payload = [r for r in afetados]
        caminho.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nRegistros brutos salvos em: {caminho}")

    print("\n[FIM] Somente leitura. Nenhum dado do Conta Ovos foi alterado.")
    return 0


def contaovos_sync_first(rec, *chaves):
    for chave in chaves:
        valor = rec.get(chave)
        if valor not in (None, ""):
            return valor
    return None


if __name__ == "__main__":
    raise SystemExit(main())
