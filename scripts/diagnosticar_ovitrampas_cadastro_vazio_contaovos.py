"""Diagnostico SOMENTE LEITURA das ovitrampas cujo cadastro ficou em branco.

Apos envios de /postcounting (formato de instalacao sem endereco), algumas
ovitrampas tiveram a leitura mais recente gravada sem Distrito/Rua/Numero/
Complemento/Localizacao/Setor/Responsavel no Conta Ovos, enquanto o historico
antigo ainda traz o endereco. Este script NAO altera nada no Conta Ovos nem no
banco local: apenas imprime o cadastro local e as leituras remotas das
ovitrampas indicadas, para decidir a correcao.

Uso (console elevado que leia a chave e o pgpass):

    python scripts/diagnosticar_ovitrampas_cadastro_vazio_contaovos.py \
        --ids 131,137,138,140,142,145,148-A,149,151,154,156,157

Opcoes:
    --database endemias_teste|endemias   banco do cadastro local
    --confirmar-banco <nome>             obrigatorio p/ banco != endemias_teste
    --date-ini / --date-fim              janela de leituras remotas (GET)
    --sem-remoto                         nao consulta a API (so cadastro local)
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import contaovos_client  # noqa: E402
from app_core import contaovos_credencial  # noqa: E402
from app_core import db as db_core  # noqa: E402
from app_core import ovitrampas  # noqa: E402

SAFE_DATABASE = "endemias_teste"
KNOWN_PGPASS = r"C:\ProgramData\Endemias\pgpass.conf"
DEFAULT_FIM = date.today().isoformat()
DEFAULT_INI = (date.today() - timedelta(days=180)).isoformat()

# Campos de endereco do cadastro local (ovitrampas_armadilhas)
LOCAL_ADDR_FIELDS = (
    "ovitrampa_id", "localidade", "rua", "numero", "complemento", "bairro",
    "localizacao", "quarteirao", "responsavel", "telefone_responsavel",
    "latitude", "longitude", "ativo", "atualizado_em",
)
# Campos de endereco que a API /lastcounting devolve por leitura
REMOTE_ADDR_FIELDS = (
    "district", "street", "number", "complement", "sector", "loc_inst",
    "ovitrap_block_id", "ovitrap_responsable",
)


def _apontar_pgpass():
    if not os.environ.get("PGPASSFILE") and os.path.exists(KNOWN_PGPASS):
        try:
            with open(KNOWN_PGPASS, "rb") as fh:
                fh.read(1)
            os.environ["PGPASSFILE"] = KNOWN_PGPASS
        except OSError:
            pass


def _parse_ids(valor):
    ids = set()
    for pedaco in (valor or "").replace(";", ",").split(","):
        pedaco = pedaco.strip()
        if pedaco:
            ids.add(pedaco)
    return sorted(ids)


def _parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ids", required=True,
                   help="ovitrampa_group_id separados por virgula.")
    p.add_argument("--database", default=SAFE_DATABASE)
    p.add_argument("--confirmar-banco", default="")
    p.add_argument("--date-ini", default=DEFAULT_INI)
    p.add_argument("--date-fim", default=DEFAULT_FIM)
    p.add_argument("--sem-remoto", action="store_true",
                   help="Nao consulta a API (somente cadastro local).")
    return p


def _ler_cadastro_local(target, ids):
    conn = db_core.connect(target)
    try:
        placeholders = ",".join("?" for _ in ids)
        rows = [db_core.serialize_row(r) for r in conn.execute(
            f"SELECT * FROM ovitrampas_armadilhas "
            f"WHERE ovitrampa_id IN ({placeholders})",
            ids,
        )]
    finally:
        conn.close()
    return rows


def _leituras_remotas(key, ids_alvo, date_ini, date_fim):
    """Pagina /lastcounting no periodo e devolve so as ovitrampas do alvo."""
    alvo_norm = set()
    for ident in ids_alvo:
        norm = ovitrampas.normalizar_ovitrampa_id(ident)
        if norm:
            alvo_norm.add(norm)
    resultado = []
    for pagina in range(1, contaovos_client.MAX_PAGE + 1):
        linha = contaovos_client.private_counts_page(
            key, page=pagina, date_start=date_ini, date_end=date_fim
        )
        if not linha:
            break
        for rec in linha:
            if not isinstance(rec, dict):
                continue
            ovi = ovitrampas.normalizar_ovitrampa_id(
                rec.get("ovitrap_id") or rec.get("ovitrap_group_id")
            )
            if ovi and ovi in alvo_norm:
                rec["_ovi_norm"] = ovi
                resultado.append(rec)
    resultado.sort(key=lambda r: (
        str(r.get("_ovi_norm") or ""),
        str(r.get("date_collect") or r.get("date") or ""),
    ))
    return resultado


def _fmt(value):
    if value in (None, ""):
        return "-"
    return str(value).strip()


def main(argv=None):
    args = _parser().parse_args(argv)
    ids = _parse_ids(args.ids)
    if not ids:
        print("[ERRO] Informe ao menos um id.")
        return 2
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print(f"[ERRO] Para ler de {args.database}, informe "
              f"--confirmar-banco {args.database}")
        return 2
    _apontar_pgpass()
    target = db_core.DatabaseTarget("postgresql", args.database)

    print(f"== Cadastro local em {args.database} ==")
    local = _ler_cadastro_local(target, ids)
    locais_por_chave = {}
    for r in local:
        locais_por_chave[_chave(str(r["ovitrampa_id"]))] = r
    for ident in ids:
        r = locais_por_chave.get(_chave(ident))
        if not r:
            print(f"  [AVISO] {ident}: sem cadastro local exato em "
                  f"ovitrampas_armadilhas.")
            continue
        print(f"  --- ovitrampa {r['ovitrampa_id']} (alvo {ident}) ---")
        for campo in LOCAL_ADDR_FIELDS:
            print(f"      {campo}: {_fmt(r.get(campo))}")
    if not local:
        print("  Nenhum cadastro local encontrado para os ids informados.")

    if args.sem_remoto:
        print("\n[FIM] Somente leitura local (--sem-remoto).")
        return 0

    if not contaovos_credencial.configured():
        print("[ERRO] Credencial Conta Ovos nao configurada "
              "(rode como administrador).")
        return 2
    key = contaovos_credencial.read_key()
    print(f"\n== Leituras remotas /lastcounting "
          f"{args.date_ini}..{args.date_fim} (somente leitura) ==")
    remotas = _leituras_remotas(key, ids, args.date_ini, args.date_fim)
    print(f"  Total de leituras remotas no periodo p/ o alvo: {len(remotas)}")
    por_ovi = {}
    for rec in remotas:
        por_ovi.setdefault(rec["_ovi_norm"], []).append(rec)
    for ovi in sorted(por_ovi):
        leituras = por_ovi[ovi]
        print(f"\n  --- ovitrampa {ovi} ({len(leituras)} leitura(s)) ---")
        for rec in leituras:
            data = _fmt(rec.get("date_collect") or rec.get("date"))
            coleta = _fmt(rec.get("counting_date_collect")
                          or rec.get("date_collect") or rec.get("date"))
            print(f"    data={data} coleta={coleta} "
                  f"counting_id={_fmt(rec.get('counting_id'))} "
                  f"eggs={_fmt(rec.get('eggs'))}")
            for campo in REMOTE_ADDR_FIELDS:
                print(f"        {campo}: {_fmt(rec.get(campo))}")

    print("\n[FIM] Somente leitura. Nenhum dado do Conta Ovos foi alterado.")
    return 0


def _chave(value):
    import unicodedata
    texto = unicodedata.normalize("NFKD", str(value or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return "".join(texto.split()).upper()


if __name__ == "__main__":
    raise SystemExit(main())
