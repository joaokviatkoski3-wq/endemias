
"""Exportações de visitas ao imóvel e dos animais registrados no mesmo envio."""
import io
import json

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas


VISITA = (
    ("data", "Data da visita"), ("hora_inicio", "Hora inicial"), ("hora_fim", "Hora final"),
    ("situacao", "Situação"), ("localidade", "Localidade"), ("quarteirao", "Quarteirão"),
    ("logradouro", "Logradouro"), ("numero", "Número do imóvel"), ("tipo_imovel", "Tipo de imóvel"),
    ("morador", "Morador"), ("telefone", "Telefone"), ("agentes", "Agentes"),
    ("acs", "ACS acompanhantes"), ("acs_presente", "ACS presente"), ("observacoes", "Observações"),
    ("deseja_cadastrar_animal", "Desejou cadastrar animal"), ("inicio_registro", "Início do preenchimento"),
    ("fim_registro", "Fim do preenchimento"), ("submission_time", "Envio Kobo"),
    ("kobo_id", "Número do envio Kobo"), ("kobo_uuid", "UUID Kobo"),
    ("arquivo_origem", "Arquivo de origem"), ("origem_estrutura", "Estrutura"),
    ("processado_em", "Importado em"),
)
ANIMAL = (
    ("nome", "Nome"), ("especie", "Espécie"), ("outro_animal", "Qual outro animal"), ("raca", "Raça"),
    ("sexo", "Sexo"), ("ambiente", "Ambiente"), ("vacinado", "Vacinado"), ("castrado", "Castrado"),
    ("feridas", "Feridas"), ("regiao_ferida", "Região da ferida"),
    ("atendimento_veterinario", "Atendimento veterinário"), ("data_atendimento", "Data do atendimento"),
    ("evolucao_caso", "Evolução"), ("kobo_uuid", "Identificador de origem"),
)


def valores_visita(visita):
    valores = dict(visita)
    valores["situacao"] = visita.get("visita")
    valores["agentes"] = visita.get("agentes") or visita.get("agentes_texto")
    valores["acs"] = visita.get("acs") or visita.get("acs_nome")
    if isinstance(valores["acs"], list):
        valores["acs"] = ", ".join(
            str(item.get("nome", "") if isinstance(item, dict) else item) for item in valores["acs"]
        )
    if visita.get("acs_presente") in (0, 1):
        valores["acs_presente"] = "Sim" if visita["acs_presente"] else "Não"
    return valores


def texto(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    return ILLEGAL_CHARACTERS_RE.sub("", str(value))


def _respostas(valor, caminho=""):
    if isinstance(valor, dict) and valor:
        for chave, item in valor.items():
            prefixo = f"{caminho}/{chave}" if caminho else chave
            yield from _respostas(item, prefixo)
    elif isinstance(valor, list) and valor:
        for ordem, item in enumerate(valor, start=1):
            yield from _respostas(item, f"{caminho}[{ordem}]")
    else:
        yield caminho, valor


def campos_camadas(visita):
    origem = visita.get("origem_kobo")
    if not origem:
        return
    if "envio_api" in origem:
        for campo, valor in _respostas(origem["envio_api"]):
            yield "Envio Kobo", None, campo, valor
        return
    for campo, valor in origem["visita"].items():
        yield "Visita", None, campo, valor
    for ordem, animal in enumerate(origem["animais"], start=1):
        for campo, valor in animal.items():
            yield "Animal", ordem, campo, valor


def _inserir_linha(planilha, valores):
    planilha.append([texto(val) if not isinstance(val, (int, float)) else val for val in valores])
    # Texto vindo de formulário é texto literal, inclusive se começar por "=".
    for celula in planilha[planilha.max_row]:
        if isinstance(celula.value, str):
            celula.data_type = "s"


def _configurar_planilha(planilha):
    planilha.freeze_panes = "C2" if planilha.max_column > 5 else "B2"
    planilha.auto_filter.ref = planilha.dimensions
    for idx, celula in enumerate(planilha[1], start=1):
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="1A5145")
        planilha.column_dimensions[get_column_letter(idx)].width = max(16, min(36, len(celula.value) + 4))


def xlsx(registros):
    wb = Workbook()
    visitas, animais, originais = wb.active, wb.create_sheet("Animais"), wb.create_sheet("Campos de origem")
    visitas.title = "Visitas"
    visitas.append(["Identificador da visita", "Cópia de origem disponível", *[rotulo for _, rotulo in VISITA]])
    animais.append(["Identificador da visita", "Identificador do animal", *[rotulo for _, rotulo in ANIMAL]])
    originais.append(["Identificador da visita", "Grupo", "Ordem no Kobo", "Campo original", "Parte", "Valor original"])
    for visita in registros:
        identificador = visita["id_visita"]
        valores = valores_visita(visita)
        _inserir_linha(visitas, [identificador, "Sim" if visita.get("origem_kobo") else "Não",
                               *(valores.get(k) for k, _ in VISITA)])
        for animal in visita["animais_detalhes"]:
            _inserir_linha(animais, [identificador, animal["id_animal"], *(animal.get(k) for k, _ in ANIMAL)])
        for grupo, ordem, campo, valor in campos_camadas(visita):
            valor = texto(valor)
            partes = range(0, len(valor), 32000) if valor else (0,)
            for parte, inicio in enumerate(partes, start=1):
                _inserir_linha(originais, [identificador, grupo, ordem, campo, parte, valor[inicio:inicio+32000]])
    for aba in wb:
        _configurar_planilha(aba)
    for aba in (visitas, animais):
        aba.column_dimensions["A"].width = 42
    originais.column_dimensions["A"].width = 42
    originais.column_dimensions["D"].width = 46
    originais.column_dimensions["F"].width = 70
    saida = io.BytesIO()
    wb.save(saida)
    saida.seek(0)
    return saida


def pdf(registros):
    arquivo = io.BytesIO()
    papel = Canvas(arquivo, pagesize=A4, pageCompression=1)
    papel.setTitle("Visitas de vigilância da esporotricose")
    largura, altura = A4
    margem = 38
    y = 0

    def pagina():
        nonlocal y
        papel.setFillColor("#184C40")
        papel.setFont("Helvetica-Bold", 15)
        papel.drawString(margem, altura - 42, "Visitas de vigilância da esporotricose")
        papel.setFont("Helvetica", 9)
        papel.drawString(margem, altura - 59, f"Vigilância Ambiental   |   {len(registros)} visitas no recorte")
        papel.drawRightString(largura - margem, 26, f"Página {papel.getPageNumber()}")
        y = altura - 85

    def linha(conteudo, titulo=False, recuo=0):
        nonlocal y
        fonte, tamanho = ("Helvetica-Bold", 10) if titulo else ("Helvetica", 9)
        for trecho in texto(conteudo).splitlines() or [""]:
            for linha_visual in simpleSplit(trecho, fonte, tamanho, largura - 2*margem - recuo) or [""]:
                # simpleSplit não quebra identificadores longos sem espaços.
                while linha_visual:
                    limite = len(linha_visual)
                    espaco = largura - 2*margem - recuo
                    if papel.stringWidth(linha_visual, fonte, tamanho) > espaco:
                        limite = min(limite, 100)
                        while papel.stringWidth(linha_visual[:limite], fonte, tamanho) > espaco:
                            limite -= 1
                    if y < 46:
                        papel.showPage()
                        pagina()
                    papel.setFont(fonte, tamanho)
                    papel.setFillColor("#184C40" if titulo else "#182322")
                    papel.drawString(margem + recuo, y, linha_visual[:limite])
                    y -= 12
                    linha_visual = linha_visual[limite:]

    def campos(colunas, dados, recuo):
        for chave, rotulo in colunas:
            valor = dados.get(chave)
            if valor not in (None, ""):
                linha(f"{rotulo} · {texto(valor)}", recuo=recuo)

    pagina()
    if not registros:
        linha("Nenhuma visita corresponde aos filtros.")
    for ordem, visita in enumerate(registros, start=1):
        if y < 140:
            papel.showPage()
            pagina()
        linha(f"Visita {ordem} de {len(registros)} · {visita['data']} · {visita.get('localidade') or 'Localidade sem registro'}", True)
        linha(f"Identificador · {visita['id_visita']}", recuo=8)
        campos(VISITA, valores_visita(visita), 8)
        for n, animal in enumerate(visita["animais_detalhes"], start=1):
            linha(f"Animal {n} · {animal.get('nome') or animal.get('especie') or 'Sem identificação'}", True, 8)
            campos(ANIMAL, animal, 16)
        if visita.get("origem_kobo"):
            linha("Campos da origem Kobo", True, 8)
            for grupo, n, campo, valor in campos_camadas(visita):
                contexto = f"{grupo} {n}" if n else grupo
                linha(f"{contexto} · {campo} · {texto(valor)}", recuo=16)
        else:
            linha("Cópia de origem indisponível. A ficha contém os campos registrados no VSATT.", recuo=8)
        y -= 12
    papel.save()
    arquivo.seek(0)
    return arquivo
