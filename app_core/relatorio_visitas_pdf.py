"""PDF compacto do histórico de visitas: até cinco linhas por visita."""

from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape


def _valor(valor):
    if valor is None:
        return ""
    return " ".join("".join(c if ord(c) >= 32 else " " for c in str(valor)).split())


def _data(valor):
    bruto = _valor(valor)
    try:
        return date.fromisoformat(bruto[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return bruto


def _secoes(item):
    return {secao["titulo"]: secao["registros"] for secao in item["secoes"]}


def _depositos(registros):
    if not registros:
        return ""
    totais = []
    for campo, abreviacao in (("inspecionado", "insp."), ("eliminado", "elim."),
                              ("tratado", "trat.")):
        valores = [r[campo] for r in registros if r.get(campo) is not None]
        if valores:
            totais.append(f"{sum(valores):g} {abreviacao}")
    tipos = ", ".join(_valor(r.get("tipo_deposito")) for r in registros
                      if _valor(r.get("tipo_deposito")))
    return "Depósitos: " + ", ".join(totais) + (f" ({tipos})" if tipos else "")


def _tratamentos(registros):
    if not registros:
        return ""
    partes = []
    for registro in registros:
        tipo = _valor(registro.get("tipo")) or "sem tipo"
        carga = registro.get("quantidade_carga")
        quantidade = registro.get("qtd_depositos_tratados")
        if carga is not None:
            tipo += f" {carga:g} carga(s)"
        if quantidade is not None:
            tipo += f" {quantidade:g} dep."
        partes.append(tipo)
    return "Tratamentos: " + "; ".join(partes)


def _coletas(registros):
    if not registros:
        return ""
    tubos = ", ".join(_valor(r.get("num_tubo")) for r in registros
                     if _valor(r.get("num_tubo")))
    return f"Coletas: {len(registros)}" + (f"; tubos {tubos}" if tubos else "")


def _laboratorio(registros, existem_coletas):
    if not registros:
        return "Lab: pendente" if existem_coletas else ""
    formas = []
    for prefixo, especie in (("aegypt", "Ae. aegypti"),
                             ("albopictus", "Ae. albopictus"), ("outra", "Outras")):
        for sufixo, nome in (("larvas", "larvas"), ("pupas", "pupas"),
                             ("exuvias", "exúvias"), ("adulto", "adultos")):
            total = sum(r.get(f"{prefixo}_{sufixo}") or 0 for r in registros)
            if total:
                formas.append(f"{especie} {total} {nome}")
    return f"Lab: {len(registros)} leitura(s)" + ("; " + "; ".join(formas) if formas else "; sem formas")


def _focos(registros):
    if not registros:
        return ""
    situacoes = sorted({_valor(r.get("status_notificacao")) for r in registros
                        if _valor(r.get("status_notificacao"))})
    return f"Focos positivos: {len(registros)}" + (
        "; notificação " + ", ".join(situacoes) if situacoes else "")


def _animais(registros):
    if not registros:
        return ""
    partes = []
    for animal in registros:
        nome = _valor(animal.get("nome")) or "sem nome"
        detalhes = [_valor(animal.get("especie") or animal.get("outro_animal"))]
        for campo, rotulo in (("feridas", "feridas"), ("regiao_ferida", "região"),
                              ("atendimento_veterinario", "atend. vet."),
                              ("evolucao_caso", "evolução")):
            valor = _valor(animal.get(campo))
            if valor:
                detalhes.append(f"{rotulo}: {valor}")
        partes.append(nome + (" (" + "; ".join(d for d in detalhes if d) + ")"
                               if any(detalhes) else ""))
    return f"Animais ({len(registros)}): " + ", ".join(partes)


def _linhas_visita(item, numero):
    """Cada elemento é uma linha física da tabela, sem campos técnicos/IDs."""
    visita = item["visita"]
    secoes = _secoes(item)
    periodo = _data(visita.get("data"))
    horas = [_valor(visita.get(chave)) for chave in ("hora_inicio", "hora_fim")]
    if horas[0]:
        periodo += " " + horas[0] + ("-" + horas[1] if horas[1] else "")
    tipo = " / ".join(parte for parte in (item["origem"], _valor(visita.get("tipo")),
                                       _valor(visita.get("visita"))) if parte)
    local = _valor(visita.get("localidade"))
    quarteirao = _valor(visita.get("quarteirao"))
    if quarteirao:
        local += f" / Q. {quarteirao}"
    endereco = ", ".join(parte for parte in (_valor(visita.get("logradouro")),
                                            _valor(visita.get("numero"))) if parte)
    linhas = [[f"{numero}. {periodo}", tipo, local or "Localidade não informada",
               endereco or "Endereço não informado"]]

    morador = _valor(visita.get("morador"))
    telefone = _valor(visita.get("telefone"))
    pessoa = "; ".join(parte for parte in ((f"Morador: {morador}" if morador else ""),
                                          (f"Tel.: {telefone}" if telefone else "")) if parte)
    imovel = "; ".join(parte for parte in (
        (f"Imóvel: {_valor(visita.get('tipo_imovel'))}" if visita.get("tipo_imovel") else ""),
        (f"Lado: {_valor(visita.get('lado'))}" if visita.get("lado") else ""),
        (f"Ciclo: {_valor(visita.get('ciclo'))}" if visita.get("ciclo") is not None else ""),
        (f"Água Sanepar: {'sim' if visita['agua_sanepar'] else 'não'}"
         if visita.get("agua_sanepar") is not None else "")) if parte)
    agentes = _valor(visita.get("agentes"))
    acs = _valor(visita.get("acs"))
    linhas.append([pessoa, imovel, f"Agentes: {agentes}" if agentes else "",
                   f"ACS: {acs}" if acs else ""])

    if item["origem"] == "Vetores":
        depositos = secoes.get("Depósitos inspecionados", [])
        tratamentos = secoes.get("Tratamentos", [])
        coletas = secoes.get("Coletas", [])
        resultados = secoes.get("Resultados laboratoriais", [])
        atividades = [_depositos(depositos), _tratamentos(tratamentos),
                      _coletas(coletas), _laboratorio(resultados, bool(coletas))]
        if any(atividades):
            linhas.append(atividades)
        focos = _focos(secoes.get("Focos positivos e notificações", []))
        if focos:
            linhas.append([focos, "", "", ""])
    else:
        animais = _animais(secoes.get("Animais registrados na visita", []))
        if animais:
            linhas.append([animais, "", "", ""])

    observacoes = _valor(visita.get("observacoes"))
    if observacoes:
        linhas.append([f"Observações: {observacoes}", "", "", ""])
    return linhas


def _limitar(texto, largura, fonte, tamanho):
    from reportlab.pdfbase import pdfmetrics

    texto = _valor(texto)
    if pdfmetrics.stringWidth(texto, fonte, tamanho) <= largura:
        return texto
    reticencias = "..."
    minimo, maximo = 0, len(texto)
    while minimo < maximo:
        meio = (minimo + maximo + 1) // 2
        if pdfmetrics.stringWidth(texto[:meio] + reticencias, fonte, tamanho) <= largura:
            minimo = meio
        else:
            maximo = meio - 1
    return texto[:minimo].rstrip() + reticencias


def gerar(dados):
    """Gera PDF paisagem, em memória, com até cinco linhas por visita."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    largura, altura = landscape(A4)
    margem = 12 * mm
    largura_util = largura - 2 * margem
    colunas = [180, 160, 175, largura_util - 515]
    fonte, tamanho = "Helvetica", 7.2
    estilos = getSampleStyleSheet()
    estilos.add(ParagraphStyle(name="HistoricoTitulo", parent=estilos["Heading1"],
        fontName="Helvetica-Bold", fontSize=13, leading=16, spaceAfter=6))
    estilos.add(ParagraphStyle(name="HistoricoResumo", parent=estilos["Normal"],
        fontName="Helvetica", fontSize=8, leading=10, spaceAfter=4))
    historia = [Paragraph("Histórico de visitas - resumo", estilos["HistoricoTitulo"])]
    resumo = (f"Agente: {dados['agente_exibicao']} | Período: {_data(dados['inicio'])} a "
              f"{_data(dados['fim'])} | Vetores: {dados['totais']['vetores']} | "
              f"Esporotricose: {dados['totais']['esporotricose']} | Total: {len(dados['visitas'])}")
    historia.append(Paragraph(escape(resumo), estilos["HistoricoResumo"]))
    if not dados["visitas"]:
        historia.append(Paragraph("Nenhuma visita encontrada para estes filtros.",
                                  estilos["HistoricoResumo"]))
    for numero, item in enumerate(dados["visitas"], 1):
        linhas = _linhas_visita(item, numero)
        if len(linhas) > 5:
            raise ValueError("O resumo excedeu cinco linhas por visita.")
        celulas = []
        estilos_tabela = [
            ("FONTNAME", (0, 0), (-1, -1), fonte),
            ("FONTSIZE", (0, 0), (-1, -1), tamanho),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eff8")),
            ("LINEBELOW", (0, -1), (-1, -1), .4, colors.HexColor("#b9c8d9")),
        ]
        for indice, linha in enumerate(linhas):
            linha_longa = indice >= 2 and linha[1:] == ["", "", ""]
            if linha_longa:
                celulas.append([_limitar(linha[0], largura_util - 8, fonte, tamanho), "", "", ""])
                estilos_tabela.append(("SPAN", (0, indice), (3, indice)))
            else:
                celulas.append([_limitar(valor, largura - 8, fonte, tamanho)
                                for valor, largura in zip(linha, colunas)])
        tabela = Table(celulas, colWidths=colunas, rowHeights=[15] * len(celulas),
                       splitByRow=0, hAlign="LEFT")
        tabela.setStyle(TableStyle(estilos_tabela))
        historia.append(KeepTogether([tabela, Spacer(1, 5)]))

    gerado_em = datetime.now().strftime("%d/%m/%Y %H:%M")
    def rodape(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(margem, 10 * mm, f"Endemias | Gerado em {gerado_em}")
        canvas.drawRightString(largura - margem, 10 * mm, f"Página {documento.page}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(buffer, pagesize=(largura, altura), leftMargin=margem,
                            rightMargin=margem, topMargin=12 * mm,
                            bottomMargin=15 * mm, title="Histórico de visitas - resumo",
                            author="Sistema Endemias")
    pdf.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()
