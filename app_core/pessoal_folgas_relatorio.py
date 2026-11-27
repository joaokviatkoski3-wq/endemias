"""Consultas e exportações administrativas de folgas e ausências."""

from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from app_core import pessoal_folgas as folgas


ORIGENS = {
    "sabado": "Trabalho no sábado", "domingo_feriado": "Domingo ou feriado",
    "evento_campanha": "Evento ou campanha", "servico_extraordinario": "Serviço extraordinário",
    "ajuste_administrativo": "Ajuste administrativo", "outro": "Outro",
    "credito": "Crédito de folga", "ferias": "Férias", "dia_trabalhado": "Dia trabalhado",
}
STATUS = {
    "agendada": "Agendada", "aguardando_confirmacao": "A confirmar", "utilizada": "Utilizada",
    "pendente": "Aguardando justificativa", "justificada": "Justificada", "abonada": "Abonada",
    "injustificada": "Não justificada", "cancelada": "Cancelada", "cancelado": "Cancelado",
    "ativo": "Ativo", "esgotado": "Esgotado", "expirado": "Expirado",
}


def _data(valor):
    return date.fromisoformat(valor)


def _dias(unidades):
    return unidades / 2


def _tabela(titulo, colunas, pesos, linhas):
    return {"titulo": titulo, "colunas": colunas, "pesos": pesos, "linhas": list(linhas)}


def montar(conn, inicio, fim, fim_exclusivo, id_agente):
    hoje = folgas._agora().date()
    saldos, creditos = folgas._saldos(conn, hoje, id_agente)
    if id_agente is not None and not saldos:
        raise ValueError("Servidor não encontrado.")
    inicio_iso, fim_iso = inicio.isoformat(), fim_exclusivo.isoformat()
    nomes = {item["id_agente"]: item["nome"] for item in saldos}
    ocorrencias = folgas.listar_ocorrencias(conn, inicio, fim_exclusivo, id_agente)
    compensacoes = folgas.listar_compensacoes(conn, id_agente, inicio_iso, fim_iso)
    tabelas = (
        _tabela("Saldos atuais",
                ("Servidor", "Situação", "Saldo líquido (dias)", "Crédito vigente", "Crédito reservado",
                 "Crédito usado", "Crédito expirado", "Adiantado reservado", "Em débito"),
                (28, 10, 13, 12, 12, 12, 12, 13, 11),
                ((s["nome"], "Ativo" if s["ativo"] else "Inativo",
                  *(_dias(s[c]) for c in ("saldo_liquido", "disponivel", "reservado", "utilizado", "expirado",
                                         "adiantado_reservado", "em_debito"))) for s in saldos)),
        _tabela("Créditos concedidos",
                ("Servidor", "Aquisição", "Validade", "Origem", "Dias", "Disponível", "Situação", "Atividade ou referência"),
                (25, 12, 12, 22, 8, 10, 12, 30),
                ((nomes[c["id_agente"]], _data(c["data_aquisicao"]), _data(c["validade"]), ORIGENS[c["origem"]],
                  _dias(c["unidades"]), _dias(c["disponivel"]), STATUS[c["status"]],
                  " / ".join(x for x in (c["descricao"], c["referencia"]) if x))
                 for c in creditos if inicio_iso <= c["data_aquisicao"] < fim_iso)),
        _tabela("Folgas e faltas",
                ("Servidor", "Data", "Tipo", "Período", "Situação", "Adiantado (dias)", "Pendente (dias)", "Observação"),
                (24, 12, 9, 16, 21, 11, 11, 29),
                ((o["nome"], _data(o["data"]), "Folga" if o["tipo"] == "folga" else "Falta",
                  "Dia inteiro" if o["dia_inteiro"] else f'{o["hora_inicio"]} às {o["hora_fim"]}',
                  STATUS[o["classificacao"] if o["status"] == "registrada" else o["status"]],
                  _dias(o["unidades_adiantadas"]) if o["tipo"] == "folga" else None,
                  _dias(o["unidades_pendentes"]) if o["tipo"] == "folga" else None, o["observacao"])
                 for o in ocorrencias)),
        _tabela("Compensações",
                ("Servidor", "Data da baixa", "Data da folga", "Origem", "Dias", "Motivo ou referência"),
                (25, 13, 13, 21, 8, 45),
                ((c["nome"], _data(c["criado_em"][:10]), _data(c["data_folga"]), ORIGENS[c["origem"]],
                  _dias(c["unidades"]), c["motivo"]) for c in compensacoes)),
    )
    filtros = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "id_agente": id_agente}
    periodo = f"{exibir(inicio)} a {exibir(fim)}"
    identificacao = nomes[id_agente] if id_agente is not None else "Todos os servidores"
    return {"filtros": filtros, "tabelas": tabelas, "exibir": exibir,
            "periodo": periodo, "identificacao": identificacao, "data_saldo": exibir(hoje)}


def exibir(valor):
    if valor is None or valor == "":
        return "-"
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, float):
        return f"{valor:g}".replace(".", ",")
    return str(valor)


def exportar(dados, formato):
    arquivo = BytesIO()
    if formato == "xlsx":
        _excel(arquivo, dados)
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        _pdf(arquivo, dados)
        tipo = "application/pdf"
    arquivo.seek(0)
    return arquivo, tipo


def _excel(arquivo, dados):
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    livro = Workbook()
    livro.remove(livro.active)
    for tabela in dados["tabelas"]:
        planilha = livro.create_sheet(tabela["titulo"])
        planilha.sheet_view.showGridLines = False
        planilha.append([tabela["titulo"]])
        planilha.append([f'Servidor: {dados["identificacao"]}'])
        planilha.append([f'Saldo em {dados["data_saldo"]}' if tabela["titulo"] == "Saldos atuais"
                         else dados["periodo"]])
        planilha.append(tabela["colunas"])
        for linhas in tabela["linhas"]:
            planilha.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in linhas])
            altura = 1
            for celula, largura in zip(planilha[planilha.max_row], tabela["pesos"]):
                celula.alignment = Alignment(vertical="center", wrap_text=isinstance(celula.value, str))
                if isinstance(celula.value, str):
                    celula.data_type = "s"
                    altura = max(altura, sum(max(1, (len(parte) + largura - 1) // largura)
                                             for parte in celula.value.split("\n")))
                elif isinstance(celula.value, date):
                    celula.number_format = "dd/mm/yyyy"
                elif isinstance(celula.value, float):
                    celula.number_format = "0.0"
            planilha.row_dimensions[planilha.max_row].height = min(390, 16 * altura)
        for linha in (1, 2, 3):
            planilha.merge_cells(start_row=linha, end_row=linha, start_column=1, end_column=len(tabela["colunas"]))
        planilha["A1"].font = Font(bold=True, size=15, color="16345F")
        for celula in planilha[4]:
            celula.font = Font(color="FFFFFF", bold=True)
            celula.fill = PatternFill("solid", fgColor="16345F")
            celula.alignment = Alignment(wrap_text=True, vertical="center")
        planilha.row_dimensions[4].height = 32
        for idx, largura in enumerate(tabela["pesos"], 1):
            planilha.column_dimensions[get_column_letter(idx)].width = max(12, largura)
        planilha.freeze_panes = "B5"
        planilha.auto_filter.ref = f"A4:{get_column_letter(len(tabela['colunas']))}{planilha.max_row}"
    livro.save(arquivo)


def _pdf(arquivo, dados):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    doc = SimpleDocTemplate(arquivo, pagesize=landscape(A4), leftMargin=29, rightMargin=29,
                            topMargin=27, bottomMargin=34, title="Controle de Pessoal")
    estilos = getSampleStyleSheet()
    corpo = ParagraphStyle("Celula", fontName="Helvetica", fontSize=8, leading=11, splitLongWords=True)
    cab = ParagraphStyle("Cabeçalho", parent=corpo, fontName="Helvetica-Bold", textColor=colors.white)
    texto = [Paragraph("Controle de Pessoal", estilos["Title"]),
             Paragraph(escape(f'Servidor: {dados["identificacao"]}'), estilos["Normal"]),
             Paragraph(escape(f'Lançamentos de {dados["periodo"]}. Saldos em {dados["data_saldo"]}. Quantidades em dias.'),
                       estilos["Normal"]), Spacer(1, 9)]
    for tabela in dados["tabelas"]:
        texto.append(Paragraph(tabela["titulo"], estilos["Heading2"]))
        if not tabela["linhas"]:
            texto.append(Paragraph("Nenhum registro no recorte.", estilos["Normal"]))
            continue
        valores = [[Paragraph(escape(titulo), cab) for titulo in tabela["colunas"]]]
        for linha in tabela["linhas"]:
            valores.append([Paragraph(escape(exibir(v)).replace("\n", "<br/>"), corpo) for v in linha])
        pesos = tabela["pesos"]
        grade = LongTable(valores, colWidths=[(doc.width - 12) * p / sum(pesos) for p in pesos],
                          repeatRows=1, hAlign="LEFT")
        grade.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16345F")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F4FA")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ]))
        texto.extend([grade, Spacer(1, 9)])

    def rodape(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#445674"))
        canvas.drawString(doc.leftMargin, 18, "VSATT - Controle de Pessoal")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 18, str(doc.page))

    doc.build(texto, onFirstPage=rodape, onLaterPages=rodape)
