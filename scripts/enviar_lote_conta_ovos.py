"""Envio supervisionado de um lote (diario) de leituras de ovitrampas ao Conta Ovos.

Para um lote concluido pelo laboratorio, deriva do calendario a data de
instalacao de cada ovitrampa, monta o payload /postcounting (date=instalacao,
counting_date_collect=coleta) e envia via API, marcando a fila e o lote.

SEGURANCA:
  - Requer console elevado que leia a chave (C:\\ProgramData\\Endemias\\contaovos.key)
    e o pgpass.
  - Por padrao apenas lista (dry-run). Para gravar: --aplicar + confirmacao digitada.
  - Processa UM lote por execucao (piloto). Nao ha lote automatico/silencioso.
  - Itens ja presentes no historico local GET (ovitrampas_ocorrencias_conta_ovos)
    sao considerados ja enviados (confirmados) e NAO reenviados.

Uso (Administrador):
  python scripts/enviar_lote_conta_ovos.py --lote <id> --banco endemias --confirmar-banco endemias
  python scripts/enviar_lote_conta_ovos.py --lote <id> --banco endemias --confirmar-banco endemias --aplicar
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_credencial  # noqa: E402
from app_core import contaovos_fila  # noqa: E402
from app_core import db as db_core  # noqa: E402

SAFE_DATABASE = "endemias_teste"
KNOWN_PGPASS = r"C:\ProgramData\Endemias\pgpass.conf"
BASE_URL = "https://contaovos.com/en-us/api"
CONFIRMACAO = "ENVIAR LOTE CONTA OVOS"


def _apontar_pgpass():
    if not os.environ.get("PGPASSFILE") and os.path.exists(KNOWN_PGPASS):
        try:
            with open(KNOWN_PGPASS, "rb") as fh:
                fh.read(1)
            os.environ["PGPASSFILE"] = KNOWN_PGPASS
        except OSError:
            pass


def _parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lote", type=int, required=True, help="id_lote do diario a enviar.")
    p.add_argument("--banco", default=SAFE_DATABASE)
    p.add_argument("--confirmar-banco", default="")
    p.add_argument("--aplicar", action="store_true")
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
    if args.banco != SAFE_DATABASE and args.confirmar_banco != args.banco:
        print(f"[ERRO] Banco {args.banco} nao autorizado. "
              f"Informe --confirmar-banco {args.banco}")
        return 2
    if not contaovos_credencial.configured():
        print("[ERRO] Credencial Conta Ovos nao configurada.")
        return 2
    _apontar_pgpass()
    key = contaovos_credencial.read_key()

    target = db_core.DatabaseTarget("postgresql", args.banco)
    conn = db_core.connect(target)
    try:
        lot, rows = contaovos_fila._lot_rows(conn, args.lote)
        if lot["status"] != "concluido":
            print("[ERRO] Lote nao esta concluido para envio. "
                  f"Status atual: {lot['status']}")
            return 2
        id_evento = None
        try:
            id_evento = lot["id_evento"]
        except (KeyError, IndexError):
            pass
        data_instalacao = contaovos_fila._derivar_instalacao(
            conn, id_evento, lot["data_movimento"]
        )
        if not data_instalacao:
            print("[ERRO] Nao foi possivel derivar a data de instalacao do "
                  "calendario para este lote. Revise o calendario.")
            return 2

        a_enviar = []
        ja_enviados = 0
        for row in rows:
            payload = contaovos_fila._payload(row, data_instalacao=data_instalacao)
            remote_id, _conf = contaovos_fila._find_remote(conn, payload)
            if remote_id:
                ja_enviados += 1
                continue
            a_enviar.append(payload)

        print(f"Lote {args.lote} | data coleta {lot['data_movimento']} | "
              f"movimento {lot.get('movimento')} | instalacao derivada "
              f"{data_instalacao}")
        print(f"Total itens: {len(rows)} | ja no Conta Ovos (nao reenviar): "
              f"{ja_enviados} | a enviar: {len(a_enviar)}")
        for p in a_enviar:
            print("  -> ovitrampa", p["ovitrap_group_id"],
                  "| date(inst)", p["date"],
                  "| coleta", p["counting_date_collect"],
                  "| ovos", p["counting_eggs"],
                  "| obs", p["counting_observation_id"])

        if not a_enviar:
            print("\nNada a enviar (todas as leituras ja existem no historico).")
            return 0

        if not args.aplicar:
            print("\n[Dry-run] Nada foi enviado. Rode com --aplicar para gravar.")
            return 0

        digitado = input(f"Confirmar envio de {len(a_enviar)} leitura(s) do lote "
                         f"{args.lote} ao Conta Ovos? Digite: {CONFIRMACAO}\n> ").strip()
        if digitado != CONFIRMACAO:
            print("Cancelado. Nenhum envio realizado.")
            return 3

        agora = datetime.now().isoformat(timespec="seconds")
        ok = falhas = 0
        for payload in a_enviar:
            ovitrap = payload["ovitrap_group_id"]
            print(f">> enviando ovitrampa {ovitrap} "
                  f"(date={payload['date']}, coleta={payload['counting_date_collect']})...")
            st, body = _post(BASE_URL, key, "postcounting", payload)
            print(f"   POST -> HTTP {st} | {body.strip()[:200]}")
            if st == 200:
                ok += 1
            else:
                falhas += 1

        print(f"\nEnviados com sucesso: {ok} | falhas: {falhas}")
        if falhas == 0:
            conn.execute(
                "UPDATE ovitrampas_laboratorio_lotes "
                "SET status='enviado_conta_ovos', enviado_conta_ovos_em=?, "
                "enviado_por_nome='script' WHERE id_lote=?",
                (agora, args.lote),
            )
            conn.commit()
            print("Lote marcado como enviado_conta_ovos.")
        else:
            conn.rollback()
            print("Houve falhas. O lote NAO foi marcado como enviado. "
                  "Confira cada falha no Conta Ovos antes de repetir.")
            return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
