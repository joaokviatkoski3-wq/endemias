"""Orquestra os ensaios homologados de todos os modulos no banco migrado."""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAFE_DATABASE = "endemias_migracao"
MODULE_SCRIPTS = (
    "testar_app_postgresql.py",
    "testar_auth_postgresql.py",
    "testar_usuarios_postgresql.py",
    "testar_servidores_postgresql.py",
    "testar_importacoes_postgresql.py",
    "testar_importacao_kobo_postgresql.py",
    "testar_campo_operacional_postgresql.py",
    "testar_bri_pe_postgresql.py",
    "testar_visitas_postgresql.py",
    "testar_dashboard_laboratorio_postgresql.py",
    "testar_esporotricose_visitas_postgresql.py",
    "testar_esporotricose_clinica_postgresql.py",
    "testar_ovitrampas_postgresql.py",
    "testar_conta_ovos_sispncd_postgresql.py",
    "testar_registro_geografico_postgresql.py",
    "testar_agenda_home_postgresql.py",
    "testar_acoes_setor_postgresql.py",
    "testar_boletim_mensal_postgresql.py",
    "testar_mapa_notificacoes_relatorio_postgresql.py",
    "testar_exportacoes_admin_postgresql.py",
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Executa o smoke integrado em endemias_migracao."
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument("--confirmar-banco")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE:
        print(f"[ERRO] Este smoke so pode usar {SAFE_DATABASE}.")
        return 2
    if args.confirmar_banco != args.database:
        print(
            "[ERRO] Informe --confirmar-banco endemias_migracao para executar "
            "os ensaios temporarios."
        )
        return 2

    for position, script_name in enumerate(MODULE_SCRIPTS, start=1):
        print(
            f"\n[{position:02d}/{len(MODULE_SCRIPTS):02d}] {script_name}",
            flush=True,
        )
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / script_name),
                "--database",
                args.database,
                "--confirmar-banco",
                args.database,
            ],
            cwd=ROOT,
            check=False,
        )
        if result.returncode:
            print(
                f"[ERRO] {script_name} terminou com codigo {result.returncode}."
            )
            return result.returncode

    print(
        "\n[OK] Smoke integrado: todos os 20 ensaios passaram no banco migrado."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
