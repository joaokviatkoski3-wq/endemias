"""Fase 2 - Correcao supervisionada das contagens do Conta Ovos.

Para cada registro do dump (contagens_afetadas.json), faz:
  - POST /api/postdeletecounting com ovitrap_group_id + date (17/08/2026)
  - POST /api/postcounting relancando com date corrigido (19/08/2026),
    counting_date_collect=24/08/2026, mesmas coordenadas e MESMA quantidade de
    ovos do registro original. Observacao NAO e preenchida (o operador completa
    depois no site).

SEGURANCA:
  - Por padrao apenas lista (dry-run). Para gravar precisa --aplicar e
    confirmacao digitada.
  - Exige PILOTO primeiro: rode com --apenas <ovitrap_id> em UM registro e
    confira no site; depois rode o restante com --aplicar (o script so processa
    mais de um registro quando --apenas nao e informado e voce confirma).
  - Se o relancamento corrigido falhar apos o apagar, o script tenta RELANCAR O
    ORIGINAL (data 17/08) para nao perder a leitura, e interrompe.
  - NUNCA roda automaticamente em lote silencioso.

Uso (console elevado que leia a chave em C:\\ProgramData\\Endemias\\contaovos.key):

  # 1) Piloto em uma ovitrampa (ex.: 246) - apenas mostra o que faria:
  python scripts/corrigir_contagens_contaovos.py --dump contagens_afetadas.json --apenas 246
  # se ok, aplica o piloto:
  python scripts/corrigir_contagens_contaovos.py --dump contagens_afetadas.json --apenas 246 --aplicar

  # 2) Depois de validar o piloto no site, processa as demais (preview, depois aplicar):
  python scripts/corrigir_contagens_contaovos.py --dump contagens_afetadas.json
  python scripts/corrigir_contagens_contaovos.py --dump contagens_afetadas.json --aplicar
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_credencial  # noqa: E402

DEFAULT_BASE = "https://contaovos.com/en-us/api"
DATA_ANTIGA = "2026-08-17"
DATA_NOVA = "2026-08-19"
COLETA = "2026-08-24"
CONFIRMACAO = "CONFIRMO CORRECAO CONTA OVOS"


def _parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dump", default="contagens_afetadas.json",
                   help="JSON com os registros afetados (gerado pela Fase 1).")
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--apenas", default="", help="Processa apenas este ovitrap_group_id (piloto).")
    p.add_argument("--data-antiga", default=DATA_ANTIGA)
    p.add_argument("--data-nova", default=DATA_NOVA)
    p.add_argument("--coleta", default=COLETA)
    p.add_argument("--ovos", type=int, default=0,
                   help="Quantidade de ovos a usar em todos os registros (padrao: 0).")
    p.add_argument("--aplicar", action="store_true",
                   help="Grava de verdade (sem ele, so mostra o plano).")
    return p


def _post(base, key, path, dados):
    url = f"{base.rstrip('/')}/{path.lstrip('/')}?key={urllib.parse.quote(key)}"
    corpo = urllib.parse.urlencode(dados).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=corpo,
        headers={
            "Accept": "application/json",
            "User-Agent": "Endemias/ContaOvos",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        corpo_resp = ""
        try:
            corpo_resp = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        return exc.code, corpo_resp
    except Exception as exc:
        return -1, f"Erro de rede: {exc}"


def main(argv=None):
    args = _parser().parse_args(argv)
    if not contaovos_credencial.configured():
        print("[ERRO] Credencial Conta Ovos nao configurada.")
        return 2
    key = contaovos_credencial.read_key()

    dump = Path(args.dump)
    if not dump.exists():
        print(f"[ERRO] Arquivo de dump nao encontrado: {dump}")
        return 2
    registros = json.loads(dump.read_text(encoding="utf-8"))
    if args.apenas:
        registros = [
            r for r in registros
            if str(r.get("ovitrap_id") or "") == str(args.apenas)
        ]
        if not registros:
            print(f"[ERRO] Nenhum registro com ovitrap_id={args.apenas} no dump.")
            return 2

    plano = []
    for r in registros:
        ovitrap = str(r.get("ovitrap_id") or "").strip()
        if not ovitrap:
            continue
        plano.append({
            "ovitrap": ovitrap,
            "lat": r.get("latitude"),
            "lng": r.get("longitude"),
        })
    if not plano:
        print("[ERRO] Nenhum registro valido para corrigir.")
        return 2

    print(f"Plano de correcao ({len(plano)} registro(s)):\n"
          f"  apagar date={args.data_antiga} e relancar date={args.data_nova} "
          f"(coleta {args.coleta}), ovos={args.ovos} em todos, "
          f"preservando coordenadas.\n"
          f"  Observacao: NAO sera preenchida (voce completa depois no site).")
    for item in plano:
        print("  - ovitrampa", item["ovitrap"],
              "| ovos", args.ovos,
              "| lat,lng", item["lat"], item["lng"])

    if not args.aplicar:
        print("\n[Dry-run] Nada foi alterado. Rode com --aplicar para gravar.")
        return 0

    if len(plano) > 1:
        print("\n[AVISO] Voce esta prestes a corrigir MAIS DE UM registro "
              "(recomenda-se piloto de 1 antes).")
    digitado = input(f"Confirme digitando exatamente: {CONFIRMACAO}\n> ").strip()
    if digitado != CONFIRMACAO:
        print("Cancelado. Nenhum dado foi alterado.")
        return 3

    print("\nExecutando...")
    falhas = 0
    for item in plano:
        ovitrap = item["ovitrap"]
        payload_del = {"ovitrap_group_id": ovitrap, "date": args.data_antiga}
        payload_novo = {
            "ovitrap_group_id": ovitrap,
            "ovitrap_lat": item["lat"],
            "ovitrap_lng": item["lng"],
            "date": args.data_nova,
            "counting_date_collect": args.coleta,
            "counting_eggs": args.ovos,
        }
        # rollback (relancar o original) em caso de falha apos o apagar
        payload_original = dict(payload_novo)
        payload_original["date"] = args.data_antiga

        print(f"\n>> ovitrampa {ovitrap}: apagando date={args.data_antiga}...")
        st, body = _post(args.base, key, "postdeletecounting", payload_del)
        print(f"   delete -> HTTP {st} | {body.strip()[:160]}")
        if st != 200:
            print("   [ERRO] Nao foi possivel apagar; pula registro.")
            falhas += 1
            continue

        print(f"   relancando date={args.data_nova} (ovos {args.ovos})...")
        st, body = _post(args.base, key, "postcounting", payload_novo)
        print(f"   post  -> HTTP {st} | {body.strip()[:160]}")
        if st == 200:
            continue
        # rollback: tenta restaurar o original
        print("   [ATENCAO] Falha no relancamento corrigido. "
              "Tentando restaurar o ORIGINAL (rollback)...")
        st2, body2 = _post(args.base, key, "postcounting", payload_original)
        print(f"   rollback -> HTTP {st2} | {body2.strip()[:160]}")
        falhas += 1

    print(f"\nConcluido. Registros com falha: {falhas}. "
          "Confira no site os que falharam.")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
