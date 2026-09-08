"""Diagnostico SOMENTE LEITURA da causa de ovitrampas com endereco em branco.

Hipotese a confirmar: em certas ovitrampas, o ovitrampa_id que enviamos via
/postcounting NAO coincide com o registro que o Conta Ovos usa como mestre (com
endereco). Quando o group_id nao casa, o Conta Ovos cria uma ovitrampa NOVA sem
endereco ao lado da original, deixando a contagem mais recente sem endereco.

Este script NAO altera nada: le no banco local (producao) o que temos em
ovitrampas_armadilhas (nosso id/endereco) e em contaovos_registro_ovitrampas
(espelho do cadastro publico do Conta Ovos: ids remotos, grupo/bloco, coords) e
cruza por chave de comparacao, apontando divergencias de codigo/coordenada.

Uso (console elevado que leia o pgpass; banco padrao endemias_teste):

    python scripts/diagnosticar_duplicata_cadastro_contaovos.py \
        --ids 131,137,138,140,142,145,148-A,149,151,154,156,157 \
        --database endemias --confirmar-banco endemias
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import ovitrampas  # noqa: E402

SAFE_DATABASE = "endemias_teste"
KNOWN_PGPASS = r"C:\ProgramData\Endemias\pgpass.conf"
LOCAL_CAMPOS = ("ovitrampa_id", "localidade", "rua", "numero", "quarteirao",
                "latitude", "longitude")


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
    p.add_argument("--ids", required=True,
                   help="ovitrampa_group_id separados por virgula.")
    p.add_argument("--database", default=SAFE_DATABASE)
    p.add_argument("--confirmar-banco", default="")
    return p


def _parse_ids(valor):
    ids = set()
    for pedaco in (valor or "").replace(";", ",").split(","):
        pedaco = pedaco.strip()
        if pedaco:
            ids.add(pedaco)
    return sorted(ids)


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
    conn = db_core.connect(target)
    try:
        placeholders = ",".join("?" for _ in ids)
        armadilhas = [db_core.serialize_row(r) for r in conn.execute(
            f"SELECT * FROM ovitrampas_armadilhas "
            f"WHERE ovitrampa_id IN ({placeholders})", ids)]
        tem_registro = db_core.table_exists(conn, "contaovos_registro_ovitrampas")
        remotos = []
        if tem_registro:
            remotos = [db_core.serialize_row(r) for r in conn.execute(
                f"SELECT * FROM contaovos_registro_ovitrampas "
                f"WHERE ovitrampa_id_remoto IN ({placeholders})", ids)]
    finally:
        conn.close()

    # Indices locais por chave de comparacao
    locais = {}
    for r in armadilhas:
        chave = ovitrampas.chave_comparacao_ovitrampa_id(r["ovitrampa_id"])
        if chave:
            locais[chave] = r

    print(f"== Cruzamento cadastro local x espelho remoto (somente leitura) ==")
    print(f"Banco: {args.database}")
    print(f"Existe espelho remoto contaovos_registro_ovitrampas: "
          f"{'sim' if tem_registro else 'NAO (ainda nao sincronizado)'}")
    if not tem_registro:
        print("\n[NOTA] Sem espelho do cadastro publico, nao da para comparar "
              "o codigo remoto. Considere sincronizar o cadastro remoto "
              "(sincronizar_registro_ovitrampas_contaovos) primeiro.")
        return 0

    remotos_por_chave = {}
    for r in remotos:
        chave = ovitrampas.chave_comparacao_ovitrampa_id(r["ovitrampa_id_remoto"])
        if chave:
            remotos_por_chave.setdefault(chave, []).append(r)

    for ident in ids:
        chave = ovitrampas.chave_comparacao_ovitrampa_id(ident)
        local = locais.get(chave)
        remoto_list = remotos_por_chave.get(chave, [])
        print(f"\n--- alvo {ident} (chave '{chave}') ---")
        if local:
            print("  LOCAL (ovitrampas_armadilhas):")
            for campo in LOCAL_CAMPOS:
                print(f"      {campo}: {_fmt(local.get(campo))}")
        else:
            print("  LOCAL: nao encontrado no cadastro local por essa chave.")
        if not remoto_list:
            print("  REMOTO (espelho cadastro publico): NENHUM registro "
                  "casando por essa chave.")
        else:
            for r in remoto_list:
                print("  REMOTO (espelho cadastro publico):")
                for campo, valor in r.items():
                    if campo in ("ovitrampa_id_remoto", "ovitrap_id",
                                 "ovitrap_block_id", "grupo_remoto_id",
                                 "latitude", "longitude",
                                 "ovitrap_eggs_mean", "atualizado_remoto_em"):
                        print(f"      {campo}: {_fmt(valor)}")

    print("\n[FIM] Somente leitura. Nenhum dado alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
