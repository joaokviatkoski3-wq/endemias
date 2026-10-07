"""PDFs operacionais A4 retrato, com referência RG e pendências explícitas."""

from html import escape
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from app_core import liraa, liraa_operacional as op, liraa_boletim


def _pdf(story):
    output = BytesIO()
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(30, 20, "Endemias — LIRAa | Almirante Tamandaré / PR")
        canvas.drawRightString(A4[0]-30, 20, f"Página {document.page}")
        canvas.restoreState()
    SimpleDocTemplate(output, pagesize=A4, rightMargin=30, leftMargin=30,
                      topMargin=30, bottomMargin=35).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def _p(value, style="BodyText"):
    return Paragraph(escape(str(value)), getSampleStyleSheet()[style])


def _table(rows, widths=None):
    table = Table([[_p(cell) for cell in row] for row in rows], colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#94a3b8")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table


def plano_pdf(target, id_ciclo, base_dir=None, id_estrato=None, id_localidade=None):
    data = op.plano(target, id_ciclo, base_dir, id_estrato, id_localidade)
    if not data["quarteiroes"]:
        raise liraa.LiraaError("Nenhum quarteirão sorteado neste filtro.")
    story = [_p("LIRAa — Plano de campo", "Title"), _p(f"{data['ciclo']['ano']} / {data['ciclo']['nome']}"), Spacer(1,12),
             _p("A meta por quarteirão é uma referência operacional do RG: 20% ou 50%, arredondados para cima. Não substitui a amostra estatística calculada do estrato. Sem RG não significa zero imóvel."), Spacer(1,12)]
    estratos = {e['id_estrato']:e for e in data['ciclo']['estratos']}
    for eid in dict.fromkeys(q['id_estrato'] for q in data['quarteiroes']):
        e=estratos[eid]
        chosen=[q for q in data['quarteiroes'] if q['id_estrato']==eid]
        known=sum(q['unidades_rg'] or 0 for q in chosen)
        meta=sum(q['meta_rg'] or 0 for q in chosen)
        absent=sum(q['unidades_rg'] is None for q in chosen)
        story += [_p(f"Estrato {e['numero']} — resumo", 'Heading2'),
                  _p(f"N confirmado (estrato inteiro): {e['imoveis_confirmados']} | Amostra programada: {e['sorteio']['n']} imóveis | Plano: {e['sorteio']['q']} quarteirões | Sorteados: {len(e['sorteio']['selecionados'])}"),
                  _p(f"Neste filtro: {len(chosen)} quarteirões; {known} imóveis RG conhecidos; referência a trabalhar: {meta}; {absent} quarteirões sem RG."),Spacer(1,8)]
    for g in data["grupos"]:
        story += [_p(f"Estrato {g['estrato']} — {g['localidade']}", "Heading2"),
                  _p(f"{g['quarteiroes']} quarteirões | Fração {g['fracao']:.0%} | {g['sem_rg']} sem RG")]
        rows = [["Quarteirão municipal", "Imóveis RG (sem PE)", f"Referência {g['fracao']:.0%}"]]
        for q in data["quarteiroes"]:
            if q["id_estrato"] == g["id_estrato"] and q["id_localidade"] == g["id_localidade"]:
                rows.append([q["quarteirao_exibicao"], q["unidades_rg"] if q["unidades_rg"] is not None else "Sem RG",
                             q["meta_rg"] if q["meta_rg"] is not None else "Não disponível"])
        rows.append(["TOTAL conhecido" if g["sem_rg"] else "TOTAL", g["unidades_rg"], g["meta_rg"]])
        story += [_table(rows, [180,180,175]), Spacer(1,12)]
    return _pdf(story)


def boletim_pdf(target, id_ciclo, base_dir=None, agrupar="estrato", id_estrato=None, id_localidade=None):
    data = liraa_boletim.resumir(target,id_ciclo,base_dir,agrupar,id_estrato,id_localidade)
    if not data["grupos"]:
        raise liraa.LiraaError("Nenhum estrato sorteado neste filtro.")
    story = []
    for g in data["grupos"]:
        if story:
            story.append(PageBreak())
        story += [_p("Resumo do Boletim de Campo e Laboratório — LIRAa", "Heading1"),
                  _p(f"Município: Almirante Tamandaré | Estado: PR | Estrato: {g['estrato']}"),
                  _p(f"{data['ciclo']['ano']} / {data['ciclo']['nome']} | {g['localidade']}"), Spacer(1,12)]
        if g["parcial"]:
            story.append(_p(f"PARCIAL: {g['pendentes']} tubitos sem leitura, {g['tipos_invalidos']} imóveis sem tipo válido e {g['depositos_invalidos']} recipientes aegypti sem classificação A1/A2/B/C/D1/D2/E. Pendência não é resultado negativo."))
        rows = [["Número de imóveis", "Quantidade"],
                ["Programados — amostra do estrato" if agrupar == "estrato" else "Programados no estrato (não é meta só desta localidade)", g["programados"]],
                ["Trabalhados (visitas abertas importadas)", g["trabalhados"]],
                ["Aedes aegypti — terrenos baldios positivos", g["aegypt_tb"]],
                ["Aedes aegypti — outros imóveis positivos", g["aegypt_outros"]],
                ["Aedes albopictus — terrenos baldios positivos", g["albopictus_tb"]],
                ["Aedes albopictus — outros imóveis positivos", g["albopictus_outros"]]]
        story += [_table(rows, [415,120]), Spacer(1,8),
                  _p(f"Referência operacional RG deste filtro: {g['referencia_rg']} imóveis conhecidos; {g['sem_rg']} quarteirões sem RG. Esta referência não substitui os programados do estrato."),
                  Spacer(1,8), _p("Recipientes positivos para Aedes aegypti", "Heading2")]
        deposits = [["Código / descrição", "Quantidade"]] + [[f"{code} — {label}", g["aegypt_recipientes"][code]] for code,label in op.DEPOSITOS.items()]
        deposits.append(["Total geral de recipientes positivos (inclui sem classificação)",g["aegypt_total"]])
        deposits.append(["Recipientes positivos para Aedes albopictus",g["albopictus_total"]])
        story += [_table(deposits, [415,120]), Spacer(1,12),
                  _p(f"Leituras: {g['leituras']} de {g['tubitos']} tubitos. Visitas fora do plano/período, não consolidadas no ciclo: {data['excluidas']}."),
                  _p("Cada visita aberta representa um imóvel trabalhado. Cada tubito representa um recipiente; vários tubitos positivos da mesma visita contam apenas um imóvel positivo por espécie. Confira retornos ou duplicações de visitas antes da digitação oficial."),
                  _p("Data: ____________________    Responsável: ______________________________")]
    return _pdf(story)
