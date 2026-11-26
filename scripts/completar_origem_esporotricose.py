
"""Completa o arquivo de origem de visitas já cadastradas pelo UUID do Kobo."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import db, esporotricose, kobo_api
from scripts.ativar_acesso_externo_windows import connect


def completar(conn, visitas, aplicar=False):
    existentes = {
        row["kobo_uuid"]: (row["kobo_id"], bool(row["tem_origem"]))
        for row in conn.execute("SELECT kobo_uuid,kobo_id,dados_kobo_json IS NOT NULL AS tem_origem FROM esporotricose_visitas")
    }
    repeticoes = Counter(v["kobo_uuid"] for v in visitas)
    resultado = Counter({"já recuperadas": sum(flag for _, flag in existentes.values())})
    for visita in visitas:
        uuid = visita["kobo_uuid"]
        if uuid not in existentes or existentes[uuid][1]:
            continue
        kobo_id = existentes[uuid][0]
        if repeticoes[uuid] > 1 or (kobo_id and visita.get("kobo_id") and kobo_id != visita["kobo_id"]):
            resultado["identidade divergente ou repetida"] += 1
            continue
        if visita.get("dados_kobo"):
            resultado["origens localizadas"] += 1
            if aplicar:
                resultado["origens preenchidas"] += esporotricose.armazenar_dados_kobo(
                    conn, visita, somente_ausentes=True
                )
    resultado["visitas cadastradas"] = len(existentes)
    resultado["ainda sem cópia"] = len(existentes) - resultado["já recuperadas"] - resultado["origens preenchidas"]
    return resultado


def obter_visitas(planilha, config, dir_temporario):
    if planilha:
        _, visitas, _ = esporotricose.preparar_arquivo(planilha, aceitar_legado=True)
        return visitas
    caminho_kobo = config["env"].get("ENDEMIAS_KOBO_CONFIG_PATH") or str(Path(config["root"]) / "kobo_config.json")
    configuracao = Path(caminho_kobo).with_name("kobo_ambiental.json")
    origem = kobo_api.load_config(configuracao)
    registros = kobo_api.fetch_complete_submissions(origem, origem["assets"].get("ESPOROTRICOSE"), limit=5000)
    if not registros:
        return []
    caminho, = kobo_api.write_etl_workbooks({"ESPOROTRICOSE": registros}, configuracao, dir_temporario)
    _, visitas, _ = esporotricose.preparar_arquivo(caminho, aceitar_legado=True)
    return visitas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--planilha", help="XLSX completo do Kobo em substituição à consulta da API")
    parser.add_argument("--aplicar", action="store_true", help="Preenche somente cópias de origem ausentes")
    args = parser.parse_args()
    home = Path("C:/ProgramData/EndemiasWeb")
    config = json.loads((home / "config.json").read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="esporo-origem-", dir=home) as temp:
        visitas = obter_visitas(args.planilha, config, temp)
    with closing(connect(config, readonly=not args.aplicar)) as pg:
        conn = db.PostgreSQLConnection(pg)
        try:
            resultado = completar(conn, visitas, aplicar=args.aplicar)
            if args.aplicar:
                conn.commit()
        except BaseException:
            conn.rollback()
            raise
    for chave, valor in resultado.items():
        print(f"{chave}: {valor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
