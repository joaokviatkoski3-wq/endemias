"""Confere o plano real e o formulário aprovado em transações somente leitura."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import db, liraa, liraa_modelo, liraa_operacional as op, liraa_kobo, liraa_boletim
from openpyxl import load_workbook


CONFIRMACAO = "CONFERIR LIRAA SEM ALTERAR DADOS"


def executar():
    # A opção libpq se aplica também às conexões internas abertas pelos módulos.
    os.environ["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=15000"
    os.environ.setdefault("PGPASSFILE", r"C:\ProgramData\Endemias\pgpass.conf")
    target = db.DatabaseTarget("postgresql", "endemias")
    contrato = liraa_modelo.contrato()
    cid = int(contrato["ciclo"])
    conn = db.connect(target)
    try:
        assert conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        result = {"somente_leitura": True, "ciclo": cid, "assinatura_confere": op.plano_hash_conn(conn, cid) == contrato["plano_hash"]}
        row = conn.execute("SELECT ano,nome,inicio,fim FROM liraa_ciclos WHERE id_ciclo=?", (cid,)).fetchone()
        if not row:
            raise RuntimeError("Ciclo do formulário aprovado não encontrado.")
        result["cadastro"] = db.serialize_row(row)
        result["visitas_existentes"] = conn.execute("SELECT COUNT(*) FROM liraa_visitas WHERE id_ciclo=?", (cid,)).fetchone()[0]
        result["sorteios"] = conn.execute("""SELECT COUNT(*) FROM liraa_sorteios s
            JOIN liraa_estratos e ON e.id_estrato=s.id_estrato WHERE e.id_ciclo=?""", (cid,)).fetchone()[0]
    finally:
        conn.close()
    plano = op.plano(target, cid, ROOT)
    w = load_workbook(liraa_modelo.APROVADO_XLSFORM, read_only=True)
    try:
        values = iter(w["choices"].values)
        headers = next(values)
        choices = [dict(zip(headers, row)) for row in values]
        quarteiroes = {(liraa_kobo._localidade(r["localidade"]), liraa_kobo._quarteirao(r["name"])) for r in choices
                   if r["list_name"] == "endemias_quarteiroes" and r["name"] != "outros"}
    finally:
        w.close()
    result.update(quarteiroes_sorteados=len(plano["quarteiroes"]), estratos_sem_sorteio=plano["sem_sorteio"],
                  quarteiroes_sem_rg=plano["sem_rg"], geometrias_ausentes=plano["geometrias_ausentes"],
                  quarteiroes_formulario_conferem=quarteiroes == {(q["localidade"], liraa_kobo._quarteirao(q["quarteirao"])) for q in plano["quarteiroes"]},
                  acs_definidos=bool(op.configuracao(target, cid)["acs_definidos"]))
    resumo = liraa_boletim.resumir(target, cid, ROOT)
    result["visitas_fora_plano_periodo"] = resumo["excluidas"]
    print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
    return 0 if result["assinatura_confere"] and result["quarteiroes_formulario_conferem"] and not (plano["sem_sorteio"] or plano["geometrias_ausentes"]) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirmar-leitura", required=True, choices=[CONFIRMACAO])
    parser.parse_args()
    try:
        raise SystemExit(executar())
    except Exception as exc:
        print(f"[ERRO] Conferência somente leitura: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
