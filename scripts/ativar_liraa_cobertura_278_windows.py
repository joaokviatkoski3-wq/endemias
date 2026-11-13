"""Ativa e confere o acompanhamento do ciclo 4 do LIRAa."""

from datetime import date, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_core import db, liraa_acompanhamento, liraa_operacional
from scripts.ativar_acesso_externo_windows import connect
from scripts.ativar_interface_setores_windows import HOME, main


MARKER = "ativacao-liraa-cobertura278"


def conferir():
    config = json.loads((HOME / "config.json").read_text(encoding="utf-8"))
    connection = connect(config, readonly=True)
    connection.close()
    target = db.DatabaseTarget("postgresql", config["env"]["ENDEMIAS_PG_DATABASE"])
    plano = liraa_operacional.plano(target, 4, Path(config["root"]))
    painel = liraa_acompanhamento.resumir(target, 4, date.today())
    chaves = ("meta", "faltam", "percentual", "percentual_sorteadas", "sorteadas", "adicionais",
              "estratos", "total_quarteiroes", "quarteiroes_visitados", "quarteiroes_pendentes")
    report = {key: painel[key] for key in chaves}
    report.update(
        conferido_em=datetime.now().isoformat(timespec="seconds"),
        santa_maria_0323_fora_do_plano=not any(
            (q["localidade"], q["quarteirao"]) == ("Santa Maria", "0323") for q in plano["quarteiroes"]
        ),
    )
    (HOME / f"{MARKER}-painel.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    status = main(origin="2.7.7", target="2.7.8", marker=MARKER)
    if status == 0:
        try:
            conferir()
            print("Indicadores do LIRAa conferidos.")
        except Exception as error:
            print(f"Conferencia do painel pendente ({type(error).__name__}).")
    raise SystemExit(status)
