# Estado atual e passagem de contexto do projeto

Atualizado em 27/11/2026. Consulte [o contexto](../CONTEXTO_PARA_IA.md) para
regras de trabalho e isolamento de testes.

## Produção confirmada

- **2.30.2**, release `cd2c297`, ativa desde 27/11/2026. A ativação confirmou
  os backups, a preservação das 110 tabelas e os três logins na origem do
  Tunnel. A migração `0050_geovsatt_posicoes_coletas.sql` foi aplicada na
  release `f8477c3` da 2.30.0. O relatório atual está em
  `C:/ProgramData/EndemiasWeb/ativacao-geovsatt2302-resultado.json`.
  A primeira leitura do Sheets, feita na 2.29.0, consta em
  `C:/ProgramData/EndemiasWeb/ativacao-geovsatt2290-sincronizacao.json`.
  A busca Nominatim usa o maps.co, configurado em 27/11/2026.
- O portal `vsatt.com.br` apresenta Endemias, Ambiental e GeoVSATT. O Tunnel
  encaminha para Waitress em
  `127.0.0.1:5001`. O acesso local usa as portas 5000 (Endemias) e
  5004 (Ambiental). A tarefa `Endemias - Servidor` inicia o servidor Windows.
- Contas comuns entram nos setores autorizados. Admin e superadmin acessam
  os dois setores. Pilotos incluem o superadmin para teste próprio.
- PostgreSQL `endemias` é produção. PostgreSQL `endemias_teste` e SQLite
  temporário servem a ensaios. Os backups operacionais ficam em
  `D:/BackupsEndemias`.

## Homologação do GeoVSATT

- O ZIP CNEFE do município 4100400 está configurado no serviço e carrega
  26.238 chaves de logradouro e número. O Google Sheets de dengue está
  conectado por conta de serviço leitora. A primeira sincronização registrou
  442 notificações, sendo 317 de 2025 e 125 de 2026, com 14 conflitos.
- **Gerenciar camadas** reúne abas de estilos, dengue e coletas de tubo
  exclusivas do superadmin. A camada de tubos considera 2026 em diante.
  Tubos vinculados a PEs seguem as coordenadas do ponto no cadastro.
  Em **Coletas de tubo**, o CSV para Google Earth e o retorno por KML
  foram validados de ponta a ponta com dois endereços públicos.
  O acompanhamento da localização foi validado com duas posições no Brave.
  O teste em modo avião ainda será feito em aparelho. O redirecionamento
  dos mapas antigos aguarda a conferência de Endemias e Ambiental.
  [Operação no GeoVSATT](GEOVSATT_IMPLEMENTACAO.md#operação-de-campo-a-partir-da-2300)
- **Pacientes de dengue**, no Endemias, abre no ano corrente, mantém 2025
  para consulta histórica e imprime o bloqueio de 200 m a partir de 2026.
  Na conferência de 27/11, 113 de 125 notificações de 2026 foram localizadas.
  Das 12 pendentes, sete têm conflito e cinco carecem de coordenadas utilizáveis.
- Em 27/11, havia 469 coletas desde janeiro, das quais 467 tinham resultado.
  Na 2.30.2, há 229 localizadas, sendo 169 pelo cadastro de PE, 55 pelo CNEFE
  e cinco pela coincidência de endereço com uma ovitrampa no quarteirão.
  Restaram 190 coletas em 115 endereços, 39 vinculadas a nove PEs que precisam
  de coordenadas e 11 de PE sem vínculo. Em coletas já localizadas sem vínculo
  com PE, o superadmin pode corrigir a posição visualmente no mapa.
- As folhas de bloqueio de dengue, esporotricose e ovitrampa usam nomes de ruas
  sobre seus eixos. No ensaio em A4 com a malha de Tanguá, couberam 16 etiquetas
  sobre o mapa e 11 quarteirões na lista de duas colunas.

## Continuidade por módulo

- **Esporotricose.** Ambiental reúne visitas, animais, casos humanos e estoque.
  O Dashboard abre em Visitas. Excel e PDF administrativos seguem os filtros
  e abrangem o recorte completo. A migração `0045` arquiva os campos de origem
  disponíveis. Foram recuperadas 910 de 2.312 visitas do Kobo. As outras
  1.402 seguem com os dados presentes no VSATT. A rotina de recuperação pode
  conferir um XLSX histórico sem reimportar visitas.
  [Casos humanos](ESPOROTRICOSE_CASOS_HUMANOS.md) ·
  [Imóveis e histórico](ESPOROTRICOSE_IMOVEIS_HISTORICO.md) ·
  [Estoque e entregas](ESTOQUE_292.md)
- **LIRAa.** O ciclo de 2026 foi encerrado pelo usuário. O superadmin gerencia
  os ciclos e o resumo conserva as visitas, leituras e índices. Use os guias
  para interpretar inclusões, metas, sequências e resultados.
  [Operação do ciclo](LIRAA_OPERACAO_CICLO.md) ·
  [Integração Kobo](LIRAA_INTEGRACAO_OPERACIONAL.md) ·
  [Notificações](NOTIFICACOES_LABORATORIO.md)
- **Formulários.** Kobo e formulários internos convivem durante o piloto.
  O agente envia e o admin ou superadmin revisa antes da gravação definitiva.
  O aplicativo de campo oferece preparação offline para as contas do piloto,
  com atualização em conexão. Avisos Web Push têm fluxo de teste no sininho.
  [Formulários internos](FORMULARIOS_INTERNOS_KOBO.md) ·
  [Piloto RG](PILOTO_PWA_RG.md)
- **Ovitrampas e Conta Ovos.** Consultas e indicadores usam o espelho local
  da API. A sincronização GET e o envio remoto de leituras são ações distintas.
  O envio remoto é explícito e exige confirmação. Armadilhas oferece KML.
  [Interface](CONTA_OVOS_INTERFACE.md) · [API](CONTA_OVOS_API.md)
- **Territorialização.** O GeoJSON ativo contém os quarteirões. A cartografia
  local e as bases de mapa sustentam a consulta RG e a impressão.
  [GeoJSON de quarteirões](REGISTRO_GEOGRAFICO_GEOJSON.md) ·
  [Mapas-base](MAPAS_BASE_CARTOGRAFICA.md)

## Pendências operacionais

- Conferir a tarefa automática do Kobo após a retomada de 26/11. A consulta
  exige permissão de administrador do Windows.
- Retomar o exercício de restauração integral em VM isolada. Para guardar
  backups fora do servidor, siga a rotina de cópia protegida.
  [Rotina de backup](ROTINA_BACKUP_GOOGLE_DRIVE.md)
- Homologar os formulários offline e a entrega de Web Push com o aplicativo
  fechado em aparelhos reais do piloto.
- O Windows do servidor está fora de suporte e o acesso local segue em HTTP.
  Esses pontos ficaram para uma etapa de infraestrutura.
  [Infraestrutura](CLOUDFLARE_INFRAESTRUTURA.md) ·
  [Segurança](CORRECOES_SEGURANCA_180.md)

## Projetos futuros

- **GeoVSATT** (`geo.vsatt.com.br`). Na 2.20.0, a composição A4 permite escolher
  o recorte, o layout, as camadas e a base. A folha inclui legenda, escala,
  norte e nota. A população por área usa as residências do RG e informa a
  cobertura de quarteirões. A exportação CSV, GeoJSON e KML exige autorização
  por conta e camada e gera registro de auditoria.
  O acervo QGIS fornece os quarteirões e polígonos de localidades. O limite
  municipal aparece na abertura e o Esri pode ser escolhido no seletor.
  O catálogo administra importações, versões, metadados, permissões, estilos
  e etiquetas por camada. O mapa respeita os filtros aplicados na composição.
  A busca de endereço oferece sugestões do RG. Ovitrampas, pontos estratégicos
  e ações com coordenadas estão disponíveis conforme a permissão do setor.
  Entre 64 cadastros de Esporotricose animal, 60 têm coordenadas e quatro não
  têm. A apresentação anterior deslocava 36 dos 60 em mais de 100 m, com
  máximo de 177,1 m e um centro de célula além da divisa. Admin e superadmin
  agora veem a posição cadastrada. A publicação não alterou esses cadastros.
  O modo CEP / BrasilAPI e a imagem Sentinel‑2 continuam disponíveis.
  O acervo importado tem 12 camadas e 3.862 feições. Consulte
  [a continuidade do GeoVSATT](GEOVSATT_IMPLEMENTACAO.md).
  A versão 2.23.0 acrescentou os raios de 150 m do mapa de Esporotricose do
  Ambiental. O mapa cruza os raios com a malha ativa, mostra a situação e
  a data do bloqueio e oferece acesso ao RG e à folha do caso no Ambiental.
  A camada de execução por quarteirão depende do registro de campo.
  A versão 2.24.0 acrescentou os quarteirões trabalhados do Endemias e
  LIRAa, com filtros por período, tipo e localidade, impressão e exportação.
  A versão 2.25.0 acrescentou ortofotos MBTiles com publicação por versão,
  permissões e uso em composições. O acervo fornecido até aqui é vetorial.
  A versão 2.26.0 acrescentou classificação por faixas numéricas, prévia de
  simbologia e etiquetas compostas configuráveis.
  A versão 2.27.3 acrescenta painel de feições, símbolos na legenda
  lateral, calor e busca Nominatim pelo maps.co. A cópia offline reúne
  camadas e ortofotos autorizadas, o recorte OpenFreeMap, busca, RG, medições,
  impressão, configuração de calor em composições e filtros das visitas
  dentro do período baixado. A busca offline aceita endereços completos do
  RG e a interface retoma a cópia se o servidor ficar indisponível.
- **Biblioteca VSATT** (`biblioteca.vsatt.com.br`, nome provisório). Acervo
  interno de referências de Vigilância em Saúde, com documentos, links,
  vídeos e imagens.

## Referências de operação

- [Divisão por setor](DIVISAO_SETORES_200.md)
- [Inicialização automática](INICIALIZACAO_AUTOMATICA.md)
- [Importação automática do Kobo](KOBO_IMPORTACAO_AUTOMATICA.md)
- [Ambiente e configuração](configuracao_ambiente.md)
- [Auditoria e logs](AUDITORIA_E_LOGS.md)
- [Permissões do superadmin](SUPERADMIN_PERMISSOES.md)
- [Migração PostgreSQL](MIGRACAO_POSTGRESQL.md)

Atalhos de execução pontual ficam em `C:/VSATT-Temporarios`. O histórico das
implantações e notas detalhadas anteriores está no commit `de21b05`, nos dois
arquivos de contexto, e nos guias de cada módulo.
