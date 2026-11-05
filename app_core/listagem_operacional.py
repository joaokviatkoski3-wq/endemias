"""Paginação e exportação das listas operacionais com o mesmo recorte."""
import csv
import io
from flask import Response
from app_core import escopo_agente
from app_core.csv_seguranca import campo_csv


def paginacao(total, filtros, completo=False):
    def inteiro(valor, padrao):
        try:
            return int(valor)
        except (ValueError, TypeError):
            return padrao
    tamanho = max(1, min(500, inteiro(filtros.get("por_pagina"), 100)))
    paginas = max(1, (total + tamanho - 1) // tamanho)
    pagina = max(1, min(paginas, inteiro(filtros.get("pagina"), 1)))
    metadados = {"total": total, "pagina": pagina, "paginas": paginas, "por_pagina": tamanho}
    if completo:
        return "", [], metadados
    return " LIMIT ? OFFSET ?", [tamanho, (pagina - 1) * tamanho], metadados


def exportar_csv(registros, campos, nome, target, usuario):
    if escopo_agente.nivel_restrito(usuario):
        proprio = escopo_agente.agente_proprio(target, usuario)
        registros = escopo_agente.redigir_agentes(registros, (proprio or {}).get("chaves") or set())
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([titulo for _, titulo in campos])
    for registro in registros:
        writer.writerow([campo_csv(registro.get(chave), numerico=isinstance(registro.get(chave), (int, float))) for chave, _ in campos])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'})
