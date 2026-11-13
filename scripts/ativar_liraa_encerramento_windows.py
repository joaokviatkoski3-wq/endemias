"""Instala o espelho e o encerramento LIRAa sem encerrar ciclos na implantação."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import db, liraa_resumo
from scripts.ativar_acesso_externo_windows import connect
from scripts.ativar_interface_setores_windows import HOME, main


MARKER = "ativacao-liraa-resumo280"


def conferir():
    config = json.loads((HOME / "config.json").read_text(encoding="utf-8"))
    connect(config, readonly=True).close()
    target = db.DatabaseTarget("postgresql", config["env"]["ENDEMIAS_PG_DATABASE"])
    resumo = liraa_resumo.resumir(target, 4)
    dados = {campo: resumo[campo] for campo in ("ciclo", "pendentes_laboratorio", "quarteiroes_pendentes", "progresso", "excluidas")}
    dados.update(encerrado=bool(resumo.get("encerramento")), total=resumo["total"])
    (HOME / f"{MARKER}-painel.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    status = main(origin="2.7.8", target="2.8.0", marker=MARKER, migration="0036_liraa_encerramentos.sql")
    if status == 0:
        try:
            conferir()
            print("Resumo LIRAa conferido em modo somente leitura.")
        except Exception as error:
            print(f"Conferencia do resumo pendente ({type(error).__name__}).")
    raise SystemExit(status)
