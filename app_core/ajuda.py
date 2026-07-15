"""Base local de ajuda orientada ao uso do sistema."""
import unicodedata


ARTIGOS = (
    {
        "id": "inicio",
        "titulo": "Conhecendo a tela inicial",
        "categoria": "Geral",
        "rotas": ("/",),
        "tags": ("inicio", "painel", "dashboard", "indicadores", "atalhos"),
        "resumo": "A tela inicial reúne os indicadores do setor, alertas e atalhos para as rotinas mais frequentes.",
        "passos": (
            "Use os cards para abrir diretamente a área relacionada ao indicador.",
            "Confira os alertas antes de iniciar as rotinas do dia.",
            "Use o menu lateral para acessar os módulos do sistema.",
        ),
        "link": "/",
        "link_label": "Abrir início",
    },
    {
        "id": "importacao-kobo",
        "titulo": "Importar dados do Kobo",
        "categoria": "Dados",
        "rotas": ("/processar",),
        "tags": ("kobo", "importacao", "api", "pendencias", "planilha", "visitas", "laboratorio"),
        "resumo": "Use a Importação Kobo para conferir pendências, buscar uma prévia e gravar os registros no sistema.",
        "passos": (
            "Abra Pendências por formulário para identificar registros novos.",
            "Escolha o formulário e, se necessário, o período desejado.",
            "Busque a prévia, confira os avisos e prepare a importação.",
            "A importação por planilhas fica disponível como recurso emergencial.",
        ),
        "link": "/processar",
        "link_label": "Abrir Importação Kobo",
    },
    {
        "id": "registro-geografico-consulta",
        "titulo": "Consultar o Registro Geográfico",
        "categoria": "Registro Geográfico",
        "rotas": ("/registro-geografico",),
        "tags": ("rg", "consulta", "imoveis", "populacao", "filtro", "quarteirao", "localidade"),
        "resumo": "A aba Consulta permite localizar imóveis e resumir os dados por localidade, quarteirão, tipo, atualização e agente.",
        "passos": (
            "Selecione uma ou mais localidades nos filtros.",
            "Refine por quarteirão, tipo de imóvel, atualização ou agente.",
            "Use a pesquisa para encontrar rua, número ou observação.",
        ),
        "link": "/registro-geografico",
        "link_label": "Abrir Registro Geográfico",
    },
    {
        "id": "registro-geografico-edicao",
        "titulo": "Editar um quarteirão",
        "categoria": "Registro Geográfico",
        "rotas": ("/registro-geografico",),
        "tags": ("rg", "edicao", "quarteirao", "logradouro", "imovel", "referencia", "ref", "setas"),
        "resumo": "Na aba Edição, altere as linhas de imóveis de um quarteirão ou comece um registro novo do zero.",
        "passos": (
            "Escolha a localidade e o quarteirão na aba Edição.",
            "Use as setas do teclado para avançar entre as células da grade.",
            "Linhas do tipo REF servem apenas como referência de lado ou acesso e não entram na contagem de imóveis.",
            "Salve a grade ao terminar as alterações.",
        ),
        "link": "/registro-geografico",
        "link_label": "Abrir edição do RG",
    },
    {
        "id": "registro-geografico-impressao",
        "titulo": "Imprimir fichas do Registro Geográfico",
        "categoria": "Registro Geográfico",
        "rotas": ("/registro-geografico",),
        "tags": ("rg", "impressao", "imprimir", "mapa", "satelite", "osm", "quarteiroes", "selecionar tudo"),
        "resumo": "A aba Impressão gera as fichas de campo com a relação de imóveis e, quando escolhido, os mapas do quarteirão.",
        "passos": (
            "Escolha a localidade e marque os quarteirões desejados ou use Selecionar tudo.",
            "Defina se a ficha deve incluir os mapas de satélite e ruas.",
            "Abra a impressão e use a visualização do navegador antes de enviar para a impressora.",
        ),
        "link": "/registro-geografico",
        "link_label": "Abrir impressão do RG",
    },
    {
        "id": "registro-geografico-mapa",
        "titulo": "Analisar áreas no mapa do RG",
        "categoria": "Registro Geográfico",
        "rotas": ("/registro-geografico",),
        "tags": ("rg", "mapa", "analise", "area", "selecao", "cores", "localidade", "satelite"),
        "resumo": "Na aba Mapa / Análise, clique em um ou mais quarteirões para somar imóveis, tipos e população aproximada.",
        "passos": (
            "Filtre as localidades que deseja visualizar.",
            "Clique nos quarteirões para montar uma seleção de área.",
            "Confira os totais e a lista de quarteirões selecionados no painel lateral.",
        ),
        "link": "/registro-geografico",
        "link_label": "Abrir mapa do RG",
    },
    {
        "id": "ovitrampas-diarios",
        "titulo": "Gerar diários de ovitrampas",
        "categoria": "Ovitrampas",
        "rotas": ("/ovitrampas",),
        "tags": ("ovitrampas", "diario", "rota", "armadilha", "impressao", "conta ovos", "realocar"),
        "resumo": "Os Diários organizam as armadilhas por rota para impressão e uso no campo durante o ciclo.",
        "passos": (
            "Importe o cadastro exportado do Conta Ovos quando houver alterações.",
            "Defina o diário e ajuste a ordem das armadilhas arrastando os itens.",
            "Armadilhas marcadas como REALOCAR permanecem fora do diário até serem definidas.",
            "Abra a impressão do diário ao finalizar a rota.",
        ),
        "link": "/ovitrampas",
        "link_label": "Abrir Ovitrampas",
    },
    {
        "id": "ovitrampas-leituras",
        "titulo": "Lançar e corrigir leituras de ovitrampas",
        "categoria": "Ovitrampas",
        "rotas": ("/ovitrampas",),
        "tags": ("ovitrampas", "leituras", "laboratorista", "lote", "editar", "palhetas", "ovos"),
        "resumo": "Use as leituras para registrar os resultados das ovitrampas, inclusive em lote quando várias leituras recebem a mesma informação.",
        "passos": (
            "Filtre o grupo ou a data de leitura desejada.",
            "Selecione os registros que devem receber a mesma informação.",
            "Informe o laboratorista e a data no lançamento em lote.",
        ),
        "link": "/ovitrampas",
        "link_label": "Abrir leituras",
    },
    {
        "id": "laboratorio-lancamentos",
        "titulo": "Lançar resultados de laboratório",
        "categoria": "Laboratório",
        "rotas": ("/laboratorio",),
        "tags": ("laboratorio", "tubo", "larvas", "pupas", "aegypti", "resultado", "historico", "negativo"),
        "resumo": "Em Lançamentos Laboratório, os tubos pendentes são preenchidos a partir das coletas registradas nas visitas.",
        "passos": (
            "Abra um tubo pendente e confira a origem da coleta, o agente e o tipo de trabalho.",
            "Registre as quantidades por espécie e forma encontrada.",
            "Resultado negativo significa ausência de Aedes aegypti em todas as formas informadas.",
            "Os registros recentes podem ser corrigidos no histórico dentro do prazo permitido.",
        ),
        "link": "/laboratorio",
        "link_label": "Abrir Laboratório",
    },
    {
        "id": "esporotricose-visitas",
        "titulo": "Consultar visitas de esporotricose",
        "categoria": "Esporotricose",
        "rotas": ("/esporotricose",),
        "tags": ("esporotricose", "visitas", "animais", "ferido", "kobo", "agente", "localidade", "imprimir"),
        "resumo": "A área Visitas reúne os dados importados do Kobo, com filtros, detalhes dos animais e acompanhamento de busca de animal ferido.",
        "passos": (
            "Use os filtros para combinar localidades, agentes, situações e outros critérios.",
            "Abra Detalhes de um animal para ver a visita relacionada.",
            "Registre a data e o agente quando houver busca de animal ferido.",
        ),
        "link": "/esporotricose",
        "link_label": "Abrir Esporotricose",
    },
    {
        "id": "esporotricose-doentes",
        "titulo": "Acompanhar animais doentes e medicação",
        "categoria": "Esporotricose",
        "rotas": ("/esporotricose",),
        "tags": ("esporotricose", "doentes", "receita", "capsulas", "entrega", "estoque", "zoomed", "proxima entrega"),
        "resumo": "A área Doentes controla receitas, entregas, próxima dispensação e o estoque de medicação.",
        "passos": (
            "Cadastre ou edite a receita com quantidade total e posologia.",
            "Registre cada entrega com a quantidade efetivamente dispensada.",
            "A próxima entrega é calculada conforme a última dispensação e a posologia.",
            "Confira o estoque para entradas, saídas, sobras e baixas no Zoomed.",
        ),
        "link": "/esporotricose",
        "link_label": "Abrir Doentes",
    },
    {
        "id": "agenda",
        "titulo": "Planejar atividades na Agenda",
        "categoria": "Planejamento",
        "rotas": ("/agenda",),
        "tags": ("agenda", "evento", "campo", "atividade externa", "recorrencia", "clima", "lembrete"),
        "resumo": "A Agenda reúne compromissos manuais e atividades registradas automaticamente pelo sistema.",
        "passos": (
            "Crie eventos manuais com data, horário, lembrete e recorrência quando necessário.",
            "Marque Atividade externa para receber o alerta meteorológico correspondente.",
            "Use o painel de condições para campo para acompanhar chuva, vento e temperatura no expediente.",
        ),
        "link": "/agenda",
        "link_label": "Abrir Agenda",
    },
    {
        "id": "meteorologia",
        "titulo": "Consultar dados meteorológicos",
        "categoria": "Planejamento",
        "rotas": ("/meteorologia",),
        "tags": ("meteorologia", "inmet", "clima", "chuva", "temperatura", "umidade", "previsao", "atualizar"),
        "resumo": "A Meteorologia apresenta condições atuais estimadas e resumos diários de referência para apoiar o planejamento do setor.",
        "passos": (
            "Atualize os dados quando precisar de uma previsão nova.",
            "Consulte as temperaturas, umidade e precipitação nos resumos diários.",
            "Para trabalho externo, use também os alertas da Agenda dentro do horário de expediente.",
        ),
        "link": "/meteorologia",
        "link_label": "Abrir Meteorologia",
    },
    {
        "id": "acoes-setor",
        "titulo": "Registrar ações do setor e anexos",
        "categoria": "Ações do Setor",
        "rotas": ("/acoes-setor",),
        "tags": ("acoes", "palestra", "limpeza", "educativa", "anexos", "galeria", "video", "publico"),
        "resumo": "Registre ações educativas ou de limpeza, seus dados de execução e os arquivos que comprovam a atividade.",
        "passos": (
            "Escolha o tipo de ação e informe o período obrigatório.",
            "Em ações educativas, preencha atividade realizada, público-alvo e recursos utilizados.",
            "Inclua imagens, documentos ou vídeos como anexos.",
            "Use a aba Anexos para localizar os arquivos em formato de galeria.",
        ),
        "link": "/acoes-setor",
        "link_label": "Abrir Ações do Setor",
    },
    {
        "id": "pontos-estrategicos",
        "titulo": "Acompanhar Pontos Estratégicos",
        "categoria": "Campo",
        "rotas": ("/pontos-estrategicos",),
        "tags": ("pe", "ponto estrategico", "atraso", "visita", "situacao", "prazo"),
        "resumo": "A tela de Pontos Estratégicos ajuda a identificar locais que precisam de visita e acompanhar suas situações.",
        "passos": (
            "Use os filtros para localizar pontos por situação, localidade ou responsável.",
            "Confira os atrasos antes de organizar a rota de campo.",
            "Após importar a visita correta, atualize a página para conferir a nova situação.",
        ),
        "link": "/pontos-estrategicos",
        "link_label": "Abrir Pontos Estratégicos",
    },
    {
        "id": "backups",
        "titulo": "Fazer e localizar backups",
        "categoria": "Administração",
        "rotas": ("/admin/sistema",),
        "tags": ("backup", "copia", "seguranca", "central do sistema", "banco", "restaurar"),
        "resumo": "A Central do Sistema reúne os controles de backup do banco e dos arquivos importantes do setor.",
        "passos": (
            "Abra a Central do Sistema para gerar um backup manual quando necessário.",
            "Os backups são organizados em D:\\BackupsEndemias conforme a configuração do sistema.",
            "Mantenha cópias adicionais em outro local para proteção contra falhas do computador.",
        ),
        "link": "/admin/sistema",
        "link_label": "Abrir Central do Sistema",
    },
)


def _normalizar(value):
    texto = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in texto if unicodedata.category(char) != "Mn").casefold()


def _texto_artigo(artigo):
    return " ".join((
        artigo["titulo"],
        artigo["categoria"],
        artigo["resumo"],
        " ".join(artigo["tags"]),
        " ".join(artigo["passos"]),
    ))


def _publico(artigo):
    return {
        "id": artigo["id"],
        "titulo": artigo["titulo"],
        "categoria": artigo["categoria"],
        "resumo": artigo["resumo"],
        "passos": artigo["passos"],
        "link": artigo["link"],
        "link_label": artigo["link_label"],
    }


def consultar(consulta="", rota="", limite=12):
    consulta_normalizada = _normalizar(consulta)
    termos = tuple(term for term in consulta_normalizada.split() if len(term) >= 2)
    rota = str(rota or "/").rstrip("/") or "/"
    resultados = []
    for artigo in ARTIGOS:
        score = 0
        corresponde_contexto = any(
            rota == prefixo or (prefixo != "/" and rota.startswith(prefixo + "/"))
            for prefixo in artigo["rotas"]
        )
        if corresponde_contexto:
            score += 100
        texto = _normalizar(_texto_artigo(artigo))
        titulo = _normalizar(artigo["titulo"])
        corresponde_busca = not termos
        for termo in termos:
            if termo in titulo:
                score += 30
                corresponde_busca = True
            elif termo in texto:
                score += 10
                corresponde_busca = True
        if not corresponde_busca:
            continue
        resultados.append((score, artigo))
    resultados.sort(key=lambda item: (-item[0], item[1]["titulo"]))
    contexto = [_publico(artigo) for score, artigo in resultados if score >= 100]
    return {
        "contexto": contexto[:3],
        "artigos": [_publico(artigo) for _, artigo in resultados[:max(1, min(int(limite or 12), 30))]],
    }
