"""Preenche retroativamente os ACS das PVE ja existentes a partir do Kobo.

Consulta o formulario PVE e cruza as submissões exclusivamente por ``kobo_uuid``.
Somente ``visitas.acs_presente``, ``visitas.acs_nome`` e ``visita_acs`` podem ser
alterados. Por padrao e uma previa; fora de ``endemias_teste``, a escrita exige
confirmacao do banco e da aplicacao.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import kobo_api  # noqa: E402
import etl  # noqa: E402


SAFE_DATABASE = "endemias_teste"
CONFIRMACAO_APLICACAO = "RECONCILIAR ACS PVE"
KNOWN_PGPASS = r"C:\ProgramData\Endemias\pgpass.conf"


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--config", default=str(ROOT / "kobo_config.json"))
    parser.add_argument("--confirmar-banco", default="")
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--confirmar-aplicacao", default="")
    return parser


def _apontar_pgpass():
    if os.environ.get("PGPASSFILE") or not os.path.exists(KNOWN_PGPASS):
        return
    try:
        with open(KNOWN_PGPASS, "rb") as arquivo:
            arquivo.read(1)
        os.environ["PGPASSFILE"] = KNOWN_PGPASS
    except OSError:
        pass


def _preparar_registros(records):
    preparados = []
    for record in records:
        uuid = kobo_api.record_uuid(record)
        presente, nomes = kobo_api.pve_acs_values(record)
        if not uuid or not presente:
            continue
        preparados.append((uuid, presente, nomes))
    return preparados


def _auditar(conn, database, resumo):
    detalhes = dict(resumo)
    detalhes.update({
        "database": database,
        "origem": "kobo_pve_acs_reconciliacao_autorizada",
    })
    conn.execute(
        """INSERT INTO auditoria_eventos
               (acao, entidade, entidade_id, usuario_nome, detalhes_json, criado_em)
           VALUES (?,?,?,?,?,?)""",
        (
            "visitas_acs_reconciliadas",
            "visitas",
            None,
            "Sistema - reconciliacao ACS autorizada",
            json.dumps(detalhes, ensure_ascii=False, sort_keys=True),
            datetime.now().isoformat(),
        ),
    )


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        print(f"[ERRO] Informe --confirmar-banco {args.database} para este banco.")
        return 2
    if args.aplicar and args.confirmar_aplicacao != CONFIRMACAO_APLICACAO:
        print(
            "[ERRO] Para aplicar, informe --confirmar-aplicacao "
            f'"{CONFIRMACAO_APLICACAO}".'
        )
        return 2

    config_path = Path(args.config)
    config = kobo_api.load_config(config_path)
    asset = (config.get("assets") or {}).get("PVE")
    records, resposta = kobo_api.fetch_submissions(config, asset, limit=5000)
    total_kobo = resposta.get("count") if isinstance(resposta, dict) else None
    if total_kobo is not None and int(total_kobo) > len(records):
        print(
            "[ERRO] A consulta retornou somente parte das PVE do Kobo; "
            "nenhum dado foi alterado."
        )
        return 1
    preparados = _preparar_registros(records)
    print(
        f"Kobo: {len(records)} PVE recebidas; "
        f"{len(preparados)} com resposta ACS."
    )

    _apontar_pgpass()
    target = db_core.DatabaseTarget("postgresql", args.database)
    conn = db_core.connect(target)
    try:
        resumo = etl.reconciliar_acs_pve_registros(conn, preparados)
        resumo["pve_kobo"] = len(records)

        print("Resumo: " + ", ".join(f"{chave}={valor}" for chave, valor in resumo.items()))
        if not args.aplicar:
            conn.rollback()
            print("[Dry-run] Nenhum dado foi alterado.")
            return 0
        _auditar(conn, args.database, resumo)
        conn.commit()
        print(f"[OK] {resumo['alteradas']} PVE atualizada(s) somente nos dados ACS.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
