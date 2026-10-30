"""Contrato do formulário aprovado: preserva o plano já distribuído em campo."""

from pathlib import Path
from openpyxl import load_workbook


APROVADO_XLSFORM = Path(__file__).parent / "data" / "liraa_ciclo_aprovado.xlsx"


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
