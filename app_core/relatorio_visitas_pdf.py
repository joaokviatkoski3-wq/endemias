"""PDF de histórico individual de visitas, com todos os campos preenchidos."""

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape


ROTULOS = {
    "id_visita": "Identificador da visita", "kobo_uuid": "Kobo UUID",
    "kobo_id": "Kobo ID", "data": "Data", "hora_inicio": "Horário inicial",
    "hora_fim": "Horário final", "tipo": "Tipo de trabalho", "visita": "Resultado da visita",
    "localidade": "Localidade", "localidade_nome": "Localidade oficial",
    "quarteirao": "Quarteirão", "logradouro": "Logradouro", "numero": "Número",
    "tipo_imovel": "Tipo de imóvel", "morador": "Morador", "telefone": "Telefone",
    "agentes": "Agentes", "acs": "ACS acompanhantes", "acs_codigos": "Códigos ACS",
    "observacoes": "Observações", "num_tubo": "Número do tubo",
    "id_coleta": "Identificador da coleta", "id_resultado": "Identificador do resultado",
    "codigo_deposito": "Código do depósito", "tipo_deposito": "Tipo de depósito",
    "deposito_eliminado": "Depósito eliminado", "id_animal": "Identificador do animal",
    "especie": "Espécie", "nome": "Nome", "raca": "Raça",
    "feridas": "Feridas", "regiao_ferida": "Região da ferida",
    "data_leitura": "Data da leitura", "laboratorista": "Laboratorista",
}


def _texto(valor):
    return "".join(c if c in "\n\t" or ord(c) >= 32 else " " for c in str(valor)).strip()


def _campos(registro):
    for chave, valor in registro.items():
        if valor is None or valor == "":
            continue
        yield ROTULOS.get(chave, chave.replace("_", " ").capitalize()), _texto(valor)


def gerar(dados):
    """Gera PDF em memória; não cria arquivos nem escreve no banco."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    estilos = getSampleStyleSheet()
    estilos.add(ParagraphStyle(name="HistoricoTitulo", parent=estilos["Heading1"],
        fontName="Helvetica-Bold", fontSize=14, leading=17, spaceAfter=8))
    estilos.add(ParagraphStyle(name="HistoricoResumo", parent=estilos["Normal"],
        fontName="Helvetica", fontSize=9, leading=12, spaceAfter=4))
    estilos.add(ParagraphStyle(name="HistoricoVisita", parent=estilos["Heading2"],
        fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=12,
        spaceAfter=4, keepWithNext=True))
    estilos.add(ParagraphStyle(name="HistoricoSecao", parent=estilos["Heading3"],
        fontName="Helvetica-Bold", fontSize=8.5, leading=11, spaceBefore=6,
        spaceAfter=3, keepWithNext=True))
    estilos.add(ParagraphStyle(name="HistoricoCampo", parent=estilos["Normal"],
        fontName="Helvetica", fontSize=8, leading=10, spaceAfter=2,
        wordWrap="CJK"))

    historia = [Paragraph("Histórico completo de visitas", estilos["HistoricoTitulo"])]
    resumo = (f"Agente: {dados['agente_exibicao']} | Período: {dados['inicio']} a {dados['fim']} | "
              f"Vetores: {dados['totais']['vetores']} | "
              f"Esporotricose: {dados['totais']['esporotricose']} | "
              f"Total: {len(dados['visitas'])}")
    historia.append(Paragraph(escape(resumo), estilos["HistoricoResumo"]))
    historia.append(Paragraph("Inclui todas as visitas vinculadas ao agente no período. "
        "Campos sem preenchimento não são impressos; campos com valor zero são mantidos. "
        "As visitas com mais de um agente aparecem no relatório de cada participante.",
        estilos["HistoricoResumo"]))
    historia.append(HRFlowable(width="100%", thickness=.6, color=colors.grey))

    if not dados["visitas"]:
        historia.append(Spacer(1, 12))
        historia.append(Paragraph("Nenhuma visita encontrada para estes filtros.",
                                  estilos["HistoricoResumo"]))
    for numero, item in enumerate(dados["visitas"], 1):
        visita = item["visita"]
        titulo = (f"{numero}. {item['origem']} - {visita.get('data') or 'sem data'} "
                  f"{visita.get('hora_inicio') or ''} - "
                  f"{visita.get('logradouro') or 'endereço não informado'}, "
                  f"{visita.get('numero') or 's/n'}")
        historia.append(Paragraph(escape(_texto(titulo)), estilos["HistoricoVisita"]))
        for rotulo, valor in _campos(visita):
            historia.append(Paragraph(f"<b>{escape(rotulo)}:</b> "
                f"{escape(valor).replace(chr(10), '<br/>')}", estilos["HistoricoCampo"]))
        for secao in item["secoes"]:
            for indice, registro in enumerate(secao["registros"], 1):
                bloco = []
                if indice == 1:
                    bloco.append(Paragraph(f"{escape(secao['titulo'])} "
                        f"({len(secao['registros'])})", estilos["HistoricoSecao"]))
                bloco.append(Paragraph(f"Registro {indice}", estilos["HistoricoCampo"]))
                for rotulo, valor in _campos(registro):
                    bloco.append(Paragraph(f"<b>{escape(rotulo)}:</b> "
                        f"{escape(valor).replace(chr(10), '<br/>')}", estilos["HistoricoCampo"]))
                historia.append(KeepTogether(bloco))
        historia.append(Spacer(1, 6))
        historia.append(HRFlowable(width="100%", thickness=.4, color=colors.lightgrey))

    gerado_em = datetime.now().strftime("%d/%m/%Y %H:%M")
    def rodape(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        if documento.page > 1:
            canvas.drawString(15 * mm, 287 * mm,
                f"Histórico de visitas - {dados['agente_exibicao']} - continuação")
        canvas.drawString(15 * mm, 12 * mm, f"Endemias | Gerado em {gerado_em}")
        canvas.drawRightString(195 * mm, 12 * mm, f"Página {documento.page}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm,
                            rightMargin=15 * mm, topMargin=17 * mm,
                            bottomMargin=18 * mm, title="Histórico completo de visitas",
                            author="Sistema Endemias")
    pdf.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()
