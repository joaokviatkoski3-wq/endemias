"""Contrato do formulário aprovado: preserva o plano já distribuído em campo."""

from pathlib import Path
import json
from openpyxl import load_workbook


APROVADO_XLSFORM = Path(__file__).parent / "data" / "liraa_ciclo_aprovado.xlsx"
ADICIONAIS_JSON = Path(__file__).parent / "data" / "liraa_adicionais.json"


def adicionais():
    return json.loads(ADICIONAIS_JSON.read_text(encoding="utf-8"))


def contrato():
    workbook = load_workbook(APROVADO_XLSFORM, read_only=True)
    try:
        values = iter(workbook["survey"].values)
        headers = next(values)
        fields = {}
        for cells in values:
            row = dict(zip(headers, cells))
            if row.get("name"):
                fields[row["name"]] = row
        return {"ciclo": str(fields["endemias_ciclo"]["default"]),
                "plano_hash": str(fields["endemias_plano"]["default"])}
    finally:
        workbook.close()
