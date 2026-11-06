"""Orientacoes do sistema, autorizadas por area e capacidade antes da busca."""
import unicodedata
from urllib.parse import urlsplit

from app_core import permissoes

ENDEMIAS = ("endemias",)
AMBIENTAL = ("ambiental",)
COMUNS = ENDEMIAS + AMBIENTAL


def _artigo(ident, titulo, categoria, rota, resumo, passos, *, areas, nivel="visualizador",
             capacidade=None, contextos=(), tags=(), atencao=(), laboratorio=False):
    return dict(id=ident, titulo=titulo, categoria=categoria, rotas=(urlsplit(rota).path,),
        link=rota, link_label="Abrir página", resumo=resumo, passos=tuple(passos),
        areas=tuple(areas), nivel_minimo=nivel, capacidade=capacidade,
        contextos=tuple(contextos), tags=tuple(tags), atencao=tuple(atencao), laboratorio=laboratorio)


ARTIGOS = (
    _artigo("inicio", "Começar pelo início de Endemias", "Geral", "/",
        "A tela inicial de Endemias reúne atalhos e indicadores das rotinas deste setor.",
        ("Abra o módulo desejado pelo menu ou pelos atalhos.", "Confira o período dos indicadores antes de comparar valores."), areas=ENDEMIAS),
    _artigo("ambiental-inicio", "Começar pelo início Ambiental", "Geral", "/",
        "A tela inicial da Vigilância Ambiental oferece atalhos diretos para suas rotinas.",
        ("Escolha uma rotina no menu ou nos atalhos.", "Abra Dashboard para indicadores e Agenda para compromissos desta área."), areas=AMBIENTAL),
    _artigo("navegacao", "Usar o menu e o Portal VSATT", "Geral", "/",
        "O menu apresenta os módulos liberados para sua conta na área atual.",
        ("No celular, abra o menu pelo botão de três linhas.", "Portal VSATT retorna à entrada geral. O atalho de outra área só aparece quando sua conta está autorizada."), areas=COMUNS),
    _artigo("filtros-multiplos", "Filtrar e pesquisar registros", "Geral", "/",
        "Os filtros refinam as informações que sua conta pode consultar.",
        ("Comece pelo período e pela localidade; depois refine a busca.", "Em filtros múltiplos, marque as opções disponíveis. Use Limpar para recomeçar."), areas=COMUNS, tags=("busca", "consulta", "tabela")),
    _artigo("ajuda-como-usar", "Encontrar uma orientação nesta ajuda", "Geral", "/",
        "A ajuda acompanha a página e mostra somente assuntos da sua área e do seu acesso.",
        ("Abra um tópico para ver as orientações.", "Pesquise uma palavra ou escolha uma categoria para encontrar outros assuntos."), areas=COMUNS),
    _artigo("senha-pessoal", "Cuidar da própria conta e senha", "Minha conta", "/minha-senha",
        "Cada pessoa deve usar sua própria conta e manter a senha em segredo.",
        ("Use Minha senha para trocar sua senha atual.", "Se esquecer a senha, peça ao gestor um link individual de recuperação. Ao terminar em computador compartilhado, use Sair."), areas=COMUNS, laboratorio=True),
    _artigo("privacidade", "Consultar o compromisso de uso dos dados", "Minha conta", "/termos",
        "As informações do sistema devem ser usadas apenas na rotina autorizada de trabalho.",
        ("Consulte os termos de uso e as orientações sobre dados pessoais.", "Compartilhe arquivos somente pelos meios autorizados pelo setor."), areas=COMUNS, laboratorio=True),
    _artigo("meteorologia", "Consultar a Meteorologia", "Planejamento", "/meteorologia",
        "A Meteorologia apoia o planejamento com condições e previsões disponíveis.",
        ("Confira a data e o horário da atualização e as métricas apresentadas.", "Na Agenda, consulte também Condições para trabalho de campo; ausência de informação não significa condição favorável."), areas=COMUNS, tags=("clima", "chuva", "vento", "temperatura")),
    _artigo("meteorologia-atualizar", "Atualizar os dados meteorológicos", "Planejamento", "/meteorologia",
        "Gestores podem solicitar uma atualização dos dados usados no planejamento.",
        ("Use Atualizar e aguarde a conclusão.", "Confira o horário resultante antes de interpretar os indicadores."), areas=COMUNS, capacidade="gestao"),
    _artigo("agenda", "Consultar a Agenda de Endemias", "Planejamento", "/agenda",
        "O calendário reúne os compromissos e atividades de Endemias.",
        ("Use as setas para mudar o mês e abra o evento para consultar seus detalhes.", "Confira Condições para trabalho de campo antes de atividades externas."), areas=ENDEMIAS, contextos=("Mês", "Agenda")),
    _artigo("ambiental-agenda", "Consultar a Agenda Ambiental", "Planejamento", "/agenda",
        "O calendário Ambiental possui compromissos e atividades próprios desta área.",
        ("Mude o mês pelas setas e abra o evento para consultar os detalhes.", "O painel Condições para trabalho de campo também fica disponível nesta agenda."), areas=AMBIENTAL, contextos=("Mês", "Agenda")),
    _artigo("agenda-eventos", "Criar e ajustar compromissos", "Planejamento", "/agenda",
        "Gestores administram os eventos manuais da agenda da área atual.",
        ("Informe título, data, horário e demais opções do evento.", "Marque atividade externa quando aplicável e confira lembrete e recorrência antes de salvar."), areas=COMUNS, capacidade="gestao"),
    _artigo("dashboard-visitas", "Interpretar o Dashboard de Endemias", "Análise", "/dashboard",
        "Os gráficos resumem os registros já disponíveis em Endemias.",
        ("Defina o período e aplique os filtros disponíveis.", "Use as listas de visitas para conferir o detalhe de um indicador."), areas=ENDEMIAS, tags=("produção", "gráfico")),
    _artigo("visitas-arboviroses", "Consultar Visitas Arboviroses", "Campo", "/visitas",
        "A consulta reúne visitas, depósitos, tratamentos, coletas e resultados relacionados.",
        ("Combine período, tipo de trabalho, localidade e demais filtros disponíveis.", "Abra Ver mais para conferir os dados relacionados à visita."), areas=ENDEMIAS),
    _artigo("visitas-edicao", "Corrigir uma visita e seus vínculos", "Campo", "/visitas",
        "A edição permite corrigir os dados de campo conforme seu acesso operacional.",
        ("Confira a visita e os dados relacionados antes de salvar.", "Ao alterar um endereço de PE, verifique o vínculo resultante. Visitas LIRAa seguem o fluxo do levantamento."), areas=ENDEMIAS, nivel="operador", contextos=("Edição",)),
    _artigo("registro-geografico-consulta", "Consultar o Registro Geográfico", "Territorialização", "/territorializacao",
        "O RG organiza imóveis e informações dos quarteirões cadastrados.",
        ("Selecione localidade e quarteirão para localizar o registro.", "Use os filtros e a pesquisa para consultar rua, número e demais informações disponíveis."), areas=ENDEMIAS, contextos=("Consulta",), tags=("registro geográfico", "rg")),
    _artigo("registro-geografico-impressao", "Imprimir um quarteirão do RG", "Territorialização", "/territorializacao",
        "A impressão apresenta o recorte escolhido do Registro Geográfico.",
        ("Escolha a localidade e o quarteirão antes de abrir a impressão.", "Revise a prévia, a orientação e as páginas antes de imprimir ou salvar em PDF."), areas=ENDEMIAS, tags=("impressão", "quarteirão")),
    _artigo("registro-geografico-edicao", "Editar um quarteirão", "Territorialização", "/territorializacao",
        "A edição altera o cadastro territorial do quarteirão selecionado.",
        ("Escolha a localidade e o quarteirão na aba Edição.", "Confira as linhas e salve somente após revisar os imóveis informados."), areas=ENDEMIAS, nivel="operador", contextos=("Edição",)),
    _artigo("registro-geografico-logradouros", "Ajustar logradouros em lote", "Territorialização", "/territorializacao",
        "A edição em lotes permite revisar alterações de logradouro antes da aplicação.",
        ("Confira o recorte e a prévia das alterações.", "Aplique apenas o conjunto conferido e verifique o resultado no cadastro."), areas=ENDEMIAS, nivel="operador", contextos=("Edição em lotes",)),
    _artigo("territorializacao-microareas", "Gerenciar microáreas dos ACS", "Territorialização", "/territorializacao#microareas",
        "Microáreas agrupam quarteirões de uma localidade e podem ter ACS responsável.",
        ("Escolha a localidade e confira os quarteirões no mapa ou na lista.", "Revise número, responsável e composição antes de salvar ou exportar."), areas=ENDEMIAS, capacidade="gestao", contextos=("Microáreas",)),
    _artigo("formularios-proprios", "Acompanhar os próprios formulários", "Formulários", "/formularios",
        "Formulários reúne os envios da sua conta e a situação de cada um.",
        ("Confira se o envio está como rascunho, enviado ou já revisado.", "Abra seus formulários para consultar os dados e os retornos da revisão."), areas=ENDEMIAS),
    _artigo("formulario-rg", "Enviar uma atualização de RG em campo", "Formulários", "/formularios/rg-campo",
        "O formulário registra uma proposta de atualização; ela passa por revisão antes de alterar o RG oficial.",
        ("No piloto, abra o endereço HTTPS oficial, prepare os quarteirões e teste a abertura sem internet. O Android deve ter bloqueio de tela; os rascunhos não têm criptografia adicional do aplicativo.", "O preenchimento é salvo automaticamente neste navegador. Confira a indicação de gravação antes de fechar. Em Envios, diferencie pendências de registros recebidos; use Sincronizar agora quando a conexão voltar.", "Rascunho recebido ainda não foi aplicado ao RG. Envie para revisão e aguarde aprovação e oficialização do gestor. Se a sessão expirar, entre novamente na mesma conta para sincronizar.", "Renove a preparação online a cada 24 horas. Não limpe dados do navegador nem troque de aparelho com pendências. Sair bloqueia a página offline, preservando os rascunhos separados por conta."), areas=ENDEMIAS, tags=("offline", "celular", "próprio", "pwa", "piloto")),
    _artigo("formularios-revisao", "Revisar e oficializar formulários", "Formulários", "/formularios",
        "Gestores revisam os envios antes da aplicação ao cadastro oficial.",
        ("Abra o envio e confira o quarteirão e as linhas propostas.", "Aprove ou devolva para correção; oficialize somente o formulário aprovado e conferido."), areas=ENDEMIAS, capacidade="gestao"),
    _artigo("ovitrampas-diarios", "Consultar os diários de ovitrampas", "Ovitrampas", "/ovitrampas",
        "Os diários apresentam as armadilhas organizadas para a rotina de campo.",
        ("Escolha o diário e confira grupo, data e armadilhas.", "Use a impressão quando precisar levar o roteiro a campo."), areas=ENDEMIAS, contextos=("Diários",)),
    _artigo("ovitrampas-monitoramento", "Consultar o monitoramento de ovitrampas", "Ovitrampas", "/ovitrampas",
        "O monitoramento apresenta as leituras disponíveis no período escolhido.",
        ("Filtre período e armadilhas antes de comparar resultados.", "Confira data de coleta e leitura ao interpretar os gráficos e o histórico."), areas=ENDEMIAS, contextos=("Monitoramento", "Histórico")),
    _artigo("ovitrampas-organizacao", "Organizar diários e armadilhas", "Ovitrampas", "/ovitrampas",
        "A organização dos diários e do calendário faz parte do acesso operacional.",
        ("Revise grupo, armadilhas, datas e ordem do roteiro.", "Confirme a organização antes de imprimir e confira armadilhas que precisam de realocação."), areas=ENDEMIAS, nivel="operador", contextos=("Diários", "Calendário", "Cadastro")),
    _artigo("ovitrampas-laboratorio", "Trabalhar com lotes de ovitrampas", "Ovitrampas", "/ovitrampas",
        "O lote organiza a conferência das palhetas e suas leituras.",
        ("Confira os itens e preencha as leituras correspondentes.", "Conclua somente após informar o conjunto exigido; zero é uma leitura e difere de não preenchido."), areas=ENDEMIAS, nivel="operador", contextos=("Laboratório",)),
    _artigo("laboratorio-consulta", "Consultar resultados laboratoriais", "Laboratório", "/laboratorio",
        "Resultados Lab permite consultar leituras e sua evolução.",
        ("Use os filtros para localizar o período e a coleta.", "Confira espécie, formas encontradas e vínculo com a visita."), areas=ENDEMIAS, contextos=("Tabela", "Evolução", "Localidades")),
    _artigo("positividade", "Consultar focos positivos", "Análise", "/positividade",
        "A consulta reúne os focos positivos disponíveis e seu histórico.",
        ("Defina período e localidade e confira os filtros aplicados.", "Abra os detalhes para conferir a coleta ou a origem do registro."), areas=ENDEMIAS),
    _artigo("laboratorio-lancamentos", "Preencher resultados do laboratório", "Laboratório", "/laboratorio/lancamentos",
        "A fila reúne coletas disponíveis para o lançamento autorizado.",
        ("Confira o tubo, a origem e a coleta antes de informar o resultado.", "Preencha as contagens e revise antes de salvar. Não transforme uma leitura ausente em zero."), areas=ENDEMIAS, capacidade="laboratorio", laboratorio=True, contextos=("Tubos", "Pendentes")),
    _artigo("laboratorio-historico", "Consultar e corrigir lançamentos recentes", "Laboratório", "/laboratorio/lancamentos",
        "O histórico apresenta os lançamentos e as correções liberadas para sua conta.",
        ("Localize a coleta pelo código e pela data.", "Resultados lançados no sistema podem permitir correção por até três dias. Correções de leituras LIRAa são exclusivas de gestores; solicite avaliação quando o comando não estiver disponível."), areas=ENDEMIAS, capacidade="laboratorio", laboratorio=True, contextos=("Histórico",)),
    _artigo("conta-ovos", "Consultar Conta Ovos e SisPNCD", "Análise", "/conta-ovos-sispncd",
        "As abas apresentam o boletim TBO e o consolidado operacional SisPNCD.",
        ("Escolha a aba e confira ano, semana epidemiológica, localidade e frentes de trabalho disponíveis.", "Pesquise o recorte e confira os indicadores e pendências antes de utilizá-los no relatório."), areas=ENDEMIAS, contextos=("Conta Ovos", "SisPNCD")),
    _artigo("sispncd-registro", "Conferir e registrar o consolidado SisPNCD", "Análise", "/conta-ovos-sispncd",
        "O acesso operacional permite registrar a referência SisPNCD do recorte conferido.",
        ("Pesquise a semana, a localidade e as frentes de trabalho e confira a produção.", "Informe a referência somente depois da conferência. Quarteirões de localidades diferentes permanecem distintos no consolidado."), areas=ENDEMIAS, nivel="operador", contextos=("SisPNCD",)),
    _artigo("liraa-consulta", "Consultar o levantamento LIRAa", "LIRAa", "/liraa",
        "O levantamento mantém ciclo, estratos, quarteirões sorteados, visitas e resultados relacionados.",
        ("Selecione o ciclo e confira o plano e a situação das visitas.", "Use os relatórios disponíveis para acompanhar o levantamento selecionado."), areas=ENDEMIAS),
    _artigo("liraa-planejamento", "Planejar e acompanhar um ciclo LIRAa", "LIRAa", "/liraa",
        "Gestores administram ciclos, estratos, sorteios e a conferência dos envios do levantamento.",
        ("Revise configuração e estratos antes do sorteio.", "Confira visitas e pendências laboratoriais do ciclo antes de emitir o boletim."), areas=ENDEMIAS, capacidade="gestao"),
    _artigo("liraa-leitura", "Registrar leituras do LIRAa", "Laboratório", "/laboratorio/lancamentos?tipo=LIRAA",
        "As leituras permanecem vinculadas aos tubitos e ao ciclo de origem.",
        ("Filtre o tipo LIRAa e confira o ciclo e o tubito.", "Registre a leitura correspondente; ausência de leitura permanece pendência."), areas=ENDEMIAS, capacidade="laboratorio", laboratorio=True, contextos=("LIRAa",)),
    _artigo("pontos-estrategicos", "Consultar Pontos Estratégicos", "Campo", "/pontos-estrategicos",
        "O painel apresenta os pontos, as visitas e os prazos de acompanhamento.",
        ("Filtre por localidade e situação para organizar a consulta.", "Confira o ponto e a data da última visita ao avaliar atrasos."), areas=ENDEMIAS),
    _artigo("pe-semana-feitos", "Conferir os PEs realizados na semana", "Campo", "/pontos-estrategicos",
        "O recorte semanal facilita conferir os pontos já visitados.",
        ("Escolha a semana e a localidade desejadas.", "Abra os registros para conferir ponto, data e visita relacionada."), areas=ENDEMIAS, contextos=("Semana", "Feitos")),
    _artigo("pe-cadastro", "Manter o cadastro de Pontos Estratégicos", "Campo", "/pontos-estrategicos",
        "Gestores mantêm a identificação, a localização e a situação dos pontos.",
        ("Confira se o ponto já existe antes de cadastrar.", "Revise endereço, quarteirão e identificação antes de salvar; preserve o histórico ao alterar a situação."), areas=ENDEMIAS, capacidade="gestao", contextos=("Cadastro",)),
    _artigo("bri", "Consultar BRI, carga e local tratado", "Campo", "/bri",
        "BRI apresenta destino do tratamento, local tratado e carga informada.",
        ("Filtre o período, a localidade e o destino para localizar o registro.", "Abra os detalhes para conferir carga principal, adicional e estabelecimento. Rua não informada permanece indicada como ausente."), areas=ENDEMIAS, tags=("borrifamento", "carga", "local")),
    _artigo("recolhimentos", "Consultar Recolhimentos", "Campo", "/recolhimentos",
        "A consulta apresenta os materiais recolhidos e os totais do período.",
        ("Aplique os filtros e avance pelas páginas da lista.", "Confira os materiais de cada registro nos detalhes antes de usar o total."), areas=ENDEMIAS),
    _artigo("mapa-geral", "Explorar o mapa de Endemias", "Análise", "/mapa",
        "O mapa reúne camadas territoriais e informações de Endemias.",
        ("Escolha a localidade, o período e as camadas desejadas.", "Alterne ruas e satélite. Ative etiquetas ao aproximar e confira o detalhe do quarteirão."), areas=ENDEMIAS),
    _artigo("relatorio-agente", "Consultar o relatório por agente", "Análise", "/relatorio-agente",
        "O relatório resume as atividades disponíveis para sua consulta no período.",
        ("Use os filtros liberados para sua conta.", "Confira os detalhes das atividades antes de imprimir ou exportar."), areas=ENDEMIAS),
    _artigo("boletim-mensal", "Consultar o Boletim Mensal", "Análise", "/boletim-mensal",
        "O boletim reúne os indicadores e informações do mês escolhido.",
        ("Escolha um mês válido e confira os indicadores.", "Use a exportação ou a impressão disponíveis para o recorte selecionado."), areas=ENDEMIAS),
    _artigo("boletim-edicao", "Conferir os campos manuais do boletim", "Análise", "/boletim-mensal",
        "Gestores completam os campos manuais do mês sem substituir os indicadores automáticos.",
        ("Confira o mês e a produção já calculada antes de preencher os campos liberados.", "Revise e salve as informações e confira a exportação do mesmo mês."), areas=ENDEMIAS, capacidade="gestao"),
    _artigo("notificacoes", "Consultar Notificações", "Campo", "/notificacoes",
        "A consulta permite localizar notificações e acompanhar suas situações.",
        ("Refine por período, localidade e situação.", "Confira os detalhes e utilize apenas os comandos disponíveis para sua conta."), areas=ENDEMIAS),
    _artigo("acoes-setor", "Registrar ações e atendimentos", "Ações e Atendimentos", "/acoes-setor",
        "O registro organiza atividades e seus arquivos relacionados.",
        ("Informe tipo, situação, período e equipe; o término deve ser posterior ao início.", "Revise os dados antes de salvar e consulte apenas os anexos liberados para sua conta."), areas=ENDEMIAS, nivel="operador"),
    _artigo("ambiental-dashboard", "Interpretar o Dashboard Ambiental", "Análise", "/dashboard",
        "O painel consolida indicadores próprios da Vigilância Ambiental.",
        ("Escolha período, fonte e demais filtros para atualizar os indicadores e gráficos.", "Confira o detalhe nos módulos de origem antes de interpretar uma diferença."), areas=AMBIENTAL),
    _artigo("ambiental-relatorios", "Filtrar e exportar relatórios ambientais", "Análise", "/relatorios",
        "Os relatórios usam os registros das rotinas ambientais e o recorte selecionado.",
        ("Escolha período, fonte, localidade e os filtros específicos da consulta.", "Defina o agrupamento e confira a tabela antes de exportar XLSX ou PDF."), areas=AMBIENTAL),
    _artigo("ambiental-mapa", "Explorar o mapa Ambiental", "Análise", "/mapa",
        "O mapa apresenta as camadas e registros da Vigilância Ambiental.",
        ("Use os filtros de localidade, período e fonte para ajustar a visualização.", "Alterne ruas e satélite; aproxime para usar etiquetas de quarteirões e abrir seus detalhes."), areas=AMBIENTAL),
    _artigo("esporotricose-visitas", "Consultar visitas e animais de Esporotricose", "Esporotricose", "/esporotricose",
        "A consulta apresenta visitas e animais relacionados aos registros recebidos.",
        ("Combine os filtros disponíveis e abra os detalhes do animal ou da visita.", "Confira endereço e dados relacionados ao acompanhar o histórico."), areas=AMBIENTAL, contextos=("Visitas", "Animais", "Resumo")),
    _artigo("esporotricose-doentes", "Consultar animais doentes e entregas", "Esporotricose", "/esporotricose#doentes",
        "A área Doentes reúne casos, receitas e entregas disponíveis para consulta.",
        ("Abra Doentes e localize o animal pelos filtros.", "Confira a situação, a receita e o histórico de entregas antes de interpretar a próxima dispensação."), areas=AMBIENTAL, contextos=("Doentes", "Lista")),
    _artigo("esporo-data-notificacao", "Entender a data de notificação do animal", "Esporotricose", "/esporotricose#doentes",
        "A data de notificação é uma referência do caso e deve ser conferida na ficha.",
        ("Consulte a ficha do animal e o histórico disponível.", "Se identificar divergência, encaminhe a conferência ao responsável pelo cadastro."), areas=AMBIENTAL, contextos=("Doentes", "Lista")),
    _artigo("esporo-gestao-visitas", "Corrigir visitas e registrar busca de animal", "Esporotricose", "/esporotricose#animais",
        "O acesso operacional permite corrigir dados e registrar as buscas realizadas.",
        ("Confira o registro original antes de editar endereço, equipe ou dados do animal.", "Registre data e responsável pela busca e confira o histórico resultante."), areas=AMBIENTAL, nivel="operador", contextos=("Visitas", "Animais")),
    _artigo("esporo-doentes-cadastro", "Cadastrar um animal doente", "Esporotricose", "/esporotricose/doentes/novo",
        "O cadastro reúne a identificação do animal, tutor e informações do caso.",
        ("Confira se já existe uma ficha antes de cadastrar.", "Preencha os dados exigidos, revise os vínculos e salve o cadastro."), areas=AMBIENTAL, nivel="operador", contextos=("Doentes",)),
    _artigo("esporo-receitas-entregas", "Registrar receitas e entregas de medicação", "Esporotricose", "/esporotricose#doentes",
        "Receitas e entregas mantêm o acompanhamento da dispensação para cada animal.",
        ("Confira receita, quantidade e posologia antes de registrar a entrega.", "Registre somente o que foi dispensado e confira o histórico e a próxima entrega."), areas=AMBIENTAL, nivel="operador", contextos=("Doentes", "Receitas", "Entregas")),
    _artigo("esporo-estoque", "Conferir movimentações de medicação", "Esporotricose", "/esporotricose#doentes",
        "As movimentações explicam entradas, saídas e saldo da medicação.",
        ("Confira o saldo e o histórico antes de acrescentar um movimento.", "Registre a quantidade e o motivo correspondentes à movimentação realizada."), areas=AMBIENTAL, nivel="operador", contextos=("Estoque", "Doentes")),
    _artigo("esporo-anexos-arrastar", "Anexar documentos do animal doente", "Esporotricose", "/esporotricose#doentes",
        "Os anexos ficam vinculados à ficha do animal.",
        ("Abra a ficha e escolha ou arraste arquivos legíveis para Anexos.", "Confira os arquivos selecionados e use Enviar anexos para gravá-los."), areas=AMBIENTAL, nivel="operador", contextos=("Doentes", "Anexos")),
    _artigo("esporo-humanos", "Acompanhar casos humanos", "Esporotricose", "/esporotricose/humanos",
        "Gestores acompanham os casos humanos e seus registros de atendimento.",
        ("Confira o caso e os vínculos antes de lançar um acompanhamento.", "A situação considera o acompanhamento mais recente por data; um registro retroativo acrescenta histórico. Na mesma data, prevalece o último incluído."), areas=AMBIENTAL, capacidade="gestao", contextos=("Casos humanos",)),
    _artigo("amostras-animais", "Consultar Amostras de Animais", "Campo", "/amostras-animais",
        "Amostras registra motivo da visita, captura e identificação do animal.",
        ("Filtre período, localidade, animal e demais critérios disponíveis.", "Abra os detalhes e diferencie o animal que motivou a visita daquele que foi capturado."), areas=AMBIENTAL),
    _artigo("vigiagua", "Conhecer a área Vigiágua", "Campo", "/vigiagua",
        "Vigiágua é uma área reservada para desenvolvimento posterior.",
        ("A página informa a situação atual da implantação.", "Ainda não há cadastro, importação ou relatório operacional de Vigiágua nesta área."), areas=AMBIENTAL),
    _artigo("importacao-kobo", "Importar registros de Endemias pela API", "Dados", "/processar",
        "A API Kobo é a entrada principal dos formulários de Endemias.",
        ("Consulte pendências, escolha formulário e período e confira a prévia.", "Prepare e confirme os registros novos após revisar os avisos. XLSX é um recurso emergencial."), areas=ENDEMIAS, capacidade="gestao", tags=("importação", "api", "kobo")),
    _artigo("ambiental-importacao-kobo", "Importar registros ambientais pela API", "Dados", "/processar",
        "Esta importação usa apenas os formulários de Esporotricose e Amostras de Animais da área Ambiental.",
        ("Consulte as pendências e confira a prévia do formulário e período escolhidos.", "Prepare e confirme os registros novos somente após revisar os avisos. XLSX é emergencial."), areas=AMBIENTAL, capacidade="gestao", tags=("importação", "api", "kobo")),
    _artigo("bri-conferencia", "Conferir correções de BRI e Recolhimentos", "Dados", "/processar",
        "A conferência compara registros já importados com o Kobo sem substituir tudo automaticamente.",
        ("Escolha formulário e período de envio para gerar a prévia das diferenças.", "Marque somente os campos conferidos e confirme as alterações selecionadas. Campos não selecionados são preservados; se houver conflito ou expiração, gere outra prévia."), areas=ENDEMIAS, capacidade="gestao", contextos=("Conferir correções",), tags=("bri", "carga", "correção")),
    _artigo("kobo-configuracao", "Configurar a conexão Kobo desta área", "Administração técnica", "/processar",
        "A configuração técnica define a conexão e os formulários usados na área atual.",
        ("Confira a área e o formulário antes de alterar a conexão.", "Mantenha o token em segredo e teste a conexão após uma alteração autorizada."), areas=COMUNS, capacidade="tecnica"),
    _artigo("usuarios-permissoes", "Gerenciar acessos e recuperação de senha", "Gestão", "/admin/usuarios",
        "Gestores administram as contas dentro dos limites do próprio acesso.",
        ("Confira pessoa, nível e área antes de criar ou alterar uma conta.", "Para senha esquecida, gere o link individual e entregue ao titular pelo meio autorizado. A conta técnica e os acessos superiores possuem proteção própria."), areas=COMUNS, capacidade="gestao"),
    _artigo("agentes-cadastro", "Manter o Controle de Pessoal", "Gestão", "/admin/agentes",
        "O Controle de Pessoal mantém cadastro, situação e informações funcionais dos agentes.",
        ("Localize o agente e confira os dados antes de editar.", "Preserve o histórico e confira os vínculos ao alterar a situação funcional."), areas=COMUNS, capacidade="gestao"),
    _artigo("auditoria", "Conferir o histórico de operações", "Gestão", "/admin/auditoria",
        "A auditoria registra operações relevantes e ajuda na conferência de alterações.",
        ("Filtre período, pessoa e operação e avance pelas páginas para conferir os eventos.", "Use a exportação XLSX para baixar o resultado completo filtrado. Acima de 10.000 eventos, reduza o período ou refine os filtros."), areas=COMUNS, capacidade="gestao"),
    _artigo("registros-tecnicos", "Consultar registros técnicos", "Administração técnica", "/admin/auditoria?origem=tecnico",
        "Os registros técnicos ajudam a localizar requisições, negações, erros e downloads da área atual.",
        ("Filtre o período e use a identificação da requisição para relacionar os eventos. Portal e sistema têm áreas próprias de consulta técnica.", "A retenção é limitada a 30 dias e a 30 MiB por área. Para exportar, respeite o limite de 10.000 eventos e refine o recorte quando necessário."), areas=COMUNS, capacidade="tecnica"),
    _artigo("presenca", "Consultar presença e último acesso", "Gestão", "/admin/usuarios",
        "A presença ajuda a identificar sessões com atividade recente.",
        ("Na Gestão de Usuários, consulte quem aparece com atividade e o último acesso registrado.", "A indicação depende da comunicação do navegador e pode demorar a refletir uma desconexão."), areas=COMUNS, capacidade="gestao", contextos=("Presença",)),
    _artigo("central-backup", "Gerenciar cópias de segurança", "Administração técnica", "/admin/sistema",
        "A Central do Sistema reúne as funções técnicas de backup.",
        ("Confira a conclusão e a integridade da cópia gerada.", "Para guardar fora do computador, use a cópia criptografada e mantenha a frase de proteção separada."), areas=COMUNS, capacidade="tecnica", atencao=("Restauração exige planejamento e conferência; não é uma forma de corrigir um registro isolado.",)),
    _artigo("central-diagnostico", "Consultar a Central do Sistema", "Administração técnica", "/admin/sistema",
        "A Central apresenta informações técnicas e controles de manutenção.",
        ("Confira a situação e os registros antes de executar uma intervenção.", "Use os procedimentos aprovados e preserve cópias de segurança antes de mudanças operacionais."), areas=COMUNS, capacidade="tecnica"),
    _artigo("nada-aparece", "Quando uma consulta não mostra registros", "Geral", "/",
        "Um recorte vazio pode resultar dos filtros ou dos limites de acesso da conta.",
        ("Confira período e localidade e limpe os filtros antes de repetir a consulta.", "Se a divergência persistir, informe ao gestor a página e o período, sem criar registros repetidos para testar."), areas=COMUNS, tags=("duplicidade", "vazio", "faltando")),
)

ARTIGOS_BASE = ARTIGOS


def _normalizar(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").casefold()


def _publico(article):
    return {key: article.get(key, ()) for key in ("id", "titulo", "categoria", "resumo", "passos", "atencao", "link", "link_label")}


def _permitido(article, user, setor):
    if setor not in article.get("areas", ()) or not permissoes.tem_nivel(user, article.get("nivel_minimo")):
        return False
    capability = article.get("capacidade")
    if capability == "laboratorio":
        from app_core.laboratorio_lancamentos import pode_lancar
        if not pode_lancar(user):
            return False
    elif capability and not permissoes.permite(user, capability):
        return False
    if user.get("somente_laboratorio") and not permissoes.gerencia(user) and not article.get("laboratorio"):
        return False
    return True


def consultar(consulta="", rota="", limite=12, contexto="", nivel="visualizador", somente_laboratorio=False,
              rota_permitida=None, setor=None, usuario=None):
    # A instalacao anterior sem divisao assume Endemias; nunca libera a uniao.
    setor = setor or "endemias"
    user = dict(usuario) if usuario is not None else {"nivel": nivel, "somente_laboratorio": somente_laboratorio}
    terms = tuple(t for t in _normalizar(consulta).split() if len(t) >= 2)
    contexts = tuple(_normalizar(t).strip() for t in str(contexto or "").replace("|", ">").split(">") if t.strip())
    try:
        parsed = urlsplit(str(rota or "/"))
        path = parsed.path.rstrip("/") or "/"
        if parsed.scheme or parsed.netloc or not path.startswith("/"):
            path = "/"
    except ValueError:
        path = "/"
    if path == "/registro-geografico":
        path = "/territorializacao"
    results = []
    for article in ARTIGOS:
        if not _permitido(article, user, setor) or rota_permitida and not rota_permitida(article["link"]):
            continue
        contextual = any(path == prefix or prefix != "/" and path.startswith(prefix + "/") for prefix in article["rotas"])
        score = 100 if contextual else 0
        if contextual:
            matches = tuple(_normalizar(c) for c in article["contextos"])
            score += sum(100 if c in matches else 20 if any(c in m or m in c for m in matches) else 0 for c in contexts)
        text = _normalizar(" ".join((article["titulo"], article["categoria"], article["resumo"], *article["passos"], *article["tags"], *article["atencao"])))
        if not all(term in text for term in terms):
            continue
        score += sum(30 if term in _normalizar(article["titulo"]) else 10 for term in terms)
        results.append((score, contextual, article))
    results.sort(key=lambda item: (-item[0], _normalizar(item[2]["titulo"])))
    try:
        limite = max(1, min(int(limite or 12), 120))
    except (TypeError, ValueError):
        limite = 12
    categories = {}
    for _, _, article in results:
        categories[article["categoria"]] = categories.get(article["categoria"], 0) + 1
    return {"setor": setor, "contexto": [_publico(a) for _, contextual, a in results if contextual][:3],
        "artigos": [_publico(a) for _, _, a in results[:limite]], "total": len(results),
        "categorias": [{"nome": name, "total": count} for name, count in sorted(categories.items(), key=lambda item: _normalizar(item[0]))]}
