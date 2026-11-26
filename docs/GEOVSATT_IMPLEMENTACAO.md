# GeoVSATT - implementação e continuidade

Atualizado em 26/11/2026.

## Estado deste incremento

A versão `2.24.0` reúne as alterações descritas a seguir. Consulte
`ESTADO_ATUAL_PROJETO.md` para confirmar qual versão está em produção.

Implementado:

- terceiro domínio lógico `geo.vsatt.com.br`, com sessão isolada e o login atual;
- auditoria identificada como setor `geo`, com ampliação compatível em SQLite e PostgreSQL;
- entrada do GeoVSATT no portal `vsatt.com.br`;
- mapa próprio, sem reaproveitar o desenho da página Mapa antiga e sem imagem-base;
- menu de camadas à esquerda, aberto pelo botão de menu;
- quarteirões do QGIS com resumo e detalhe dos imóveis do RG ao clicar;
- polígonos de localidades e áreas dispersas do lote;
- logradouros da base cartográfica municipal já existente;
- busca por localidade e quarteirão;
- pop-up de boas-vindas e novidades em Endemias, Ambiental e GeoVSATT;
- uso dos arquivos SVG e PNG oficiais anexados para a nova marca;
- catálogo persistente com administração exclusiva do superadmin no menu do mapa;
- importação de vetores como rascunho, histórico, edição dos metadados, publicação e
  restauração de uma versão anterior;
- níveis e setores permitidos, concessões por conta, visibilidade inicial, rótulo e
  cores por valor de um atributo. O servidor aplica a regra tanto ao catálogo quanto
  à URL direta da camada.

Limites explícitos:

- a camada Localidades deste incremento é representativa; não declara limites oficiais;
- Bairros, hidrografia, satélite e ortofotos permanecem sem geometria até entrada de fonte
  oficial e metadados;
- as camadas operacionais sensíveis ainda não foram expostas;
- as três camadas do sistema aceitam configuração de acesso e visualização. O RG
  continua sendo a fonte dos quarteirões e o acesso aos seus detalhes exige acesso
  a Endemias. A publicação de vetores via catálogo usa camadas de importação;
- a configuração do endereço público e do Tunnel é administrada separadamente.

## Contratos iniciais

As rotas privadas usam o prefixo `/api/geovsatt` e nunca devem devolver uma camada
somente porque ela existe no banco. Cada camada operacional deve declarar fonte,
permissão, precisão da localização, filtros, retenção e forma de agregação antes de
ser habilitada.

As camadas vetoriais preparadas no QGIS entram preferencialmente como GeoJSON. O
armazenamento e a publicação podem ganhar formatos complementares quando volume,
imagem raster ou desempenho exigirem, sem mudar o formato de entrega preferido pelo
usuário para vetores.

## Operação do catálogo

1. No menu do mapa, como superadmin, abra **Gerenciar camadas** e crie a camada.
   Use o código `bairros` ou `hidrografia` para ocupar a respectiva entrada
   reservada no mapa.
2. Exporte o vetor no QGIS como *GeoJSON*, em WGS 84 (EPSG:4326), UTF-8,
   até 8 MiB e 50 mil feições. São aceitos pontos, linhas e polígonos
   (simples ou múltiplos), com atributos escalares.
3. Importe com a fonte e, quando disponíveis, data de referência, licença e
   observações. O histórico mostra quantidade, arquivo, data, conta responsável
   e SHA-256 do arquivo recebido. É possível baixar a coleção validada.
4. Use **Publicar no mapa** para trocar a versão ativa ou **Restaurar no mapa**
   em uma versão anterior. Os metadados podem ser corrigidos no histórico.
5. Marque os níveis e os setores para liberar acesso geral. Conceda acesso
   diretamente a contas específicas para exceções. O superadmin sempre tem acesso
   às versões publicadas e ao painel. Ao atualizar a página do mapa, carregam-se
   a versão e as permissões vigentes.
6. Para cor por localidade, indique o nome exato do atributo (por exemplo,
   `Localidade` no quarteirão) e escreva uma regra por linha, como
   `1 = #008c30`. A cor padrão cobre os demais valores.

A migração PostgreSQL `0047_geovsatt_catalogo` armazena o JSON validado e os
metadados no banco do VSATT, junto ao backup existente. Mudanças de configuração,
importação, publicação e edição de metadados geram eventos de auditoria.

## Busca, etiquetas e ferramentas

- Pesquise por rua e número, localidade ou quarteirão. É possível incluir
  localidade, município, UF e CEP no texto do endereço. Os resultados do RG
  exigem acesso ao RG e à camada de quarteirões no GeoVSATT.
- Selecionar um endereço destaca o quarteirão que consta no cadastro e a linha
  correspondente no painel. A ausência de um polígono na malha não impede a
  leitura do cadastro, que é exibido sem inventar uma posição.
- Informar apenas oito dígitos ou um CEP com hífen consulta a
  [BrasilAPI CEP v2](https://brasilapi.com.br/docs#tag/CEP-V2). Somente o CEP é
  enviado externamente. O logradouro retornado é usado para buscar
  correspondências no RG local. A BrasilAPI não estabelece o quarteirão.
- As etiquetas de quarteirões aparecem a partir do zoom 16. Os nomes de rua
  acompanham os trechos visíveis a partir do zoom 17. A tela limita e
  espaça as etiquetas, removendo-as enquanto a vista se move.
- Use as ferramentas de distância e área para marcar pontos, desfazer o último
  ponto e concluir. As medidas são aproximadas. O mapa aceita até zoom 22.
- Como superadmin, **Gerenciar camadas** fica no topo do mapa ou no começo
  do menu lateral. Na 2.18.0, **Nova camada GeoJSON** abre o formulário com
  seletor de arquivo. **Atualizar camada existente** abre a lista de camadas
  importadas com o botão **Importar versão**. O arquivo importado é rascunho
  até **Publicar no mapa**. A busca oferece o modo **CEP / BrasilAPI**.

## Cartografia e vigilância na 2.18.0

- O lote assistido `scripts/importar_cartografia_geovsatt.py` prepara as camadas
  da pasta de origem sem editar os arquivos. A prévia informa contagens, SRC,
  correções e hashes. A publicação é transacional e reutiliza versões
  idênticas em nova execução. Um cadastro divergente interrompe o lote.
- Em 26/11/2026, foram publicadas 3.862 feições em 12 camadas:
  bairros, limite municipal, localidades e áreas dispersas, quarteirões QGIS,
  equipamentos públicos (111), ferrovias, cursos e massas d’água, geologia,
  áreas de risco e suscetibilidades à inundação e a movimentos de massa.
  Duas camadas foram reprojetadas, 14 geometrias foram reparadas e quatro
  registros de ferrovia estavam sem geometria. Os originais foram preservados.
- Quarteirões do QGIS entram como uma camada de referência. O RG conserva
  a malha ativa que vincula os imóveis. As propriedades importadas são
  selecionadas por camada. Os QMD recebidos não especificam licença.
- **Imagem-base** no menu permite ativar Sentinel‑2 (2025) por
  [EOxCloudless](https://cloudless.eox.at/license-non-commercial), com
  atribuição no mapa. A abertura padrão segue sem imagem-base.
- A opção Esri World Imagery aparece quando a instalação tiver cobertura
  de uso confirmada e `ENDEMIAS_GEO_ESRI_LICENSED=1`. Consulte os
  [termos da Esri para mapas e camadas](https://doc.arcgis.com/en/arcgis-online/reference/access-use-constraints.htm).
- **Esporotricose animal** apresenta contagens de animais do cadastro
  em células de aproximadamente 250 metros. O acesso padrão é admin e
  superadmin. Concessões a outros perfis também exigem acesso ao Ambiental.
  O mapa exibe centros das células e não inclui a ficha ou o ponto individual.

## Cartografia, busca e vigilância na 2.19.0

- O menu **Imagens e bases** oferece **Satélite Esri World Imagery** com a
  mesma fonte usada no Ambiental e em outros mapas do VSATT. O mapa abre
  sem imagem-base. A instalação pode ocultar o Esri com
  `ENDEMIAS_GEO_ESRI_LICENSED=0`.
- Os vetores `quarteiroes-qgis` e `localidades-areas-dispersas` continuam
  versionados no catálogo administrativo. Suas versões publicadas alimentam
  **Quarteirões** e **Localidades** no mapa. Atualize as versões nessas fontes
  e ajuste o estilo nas camadas com os nomes exibidos no mapa. A troca da
  malha no GeoVSATT preserva a malha utilizada pelos outros mapas do RG.
- O limite municipal liga por padrão. As localidades recebem cores distintas.
  Hidrografia nomeada recebe etiquetas azuis pelo eixo e ferrovias recebem
  traço com dormentes. Etiquetas respeitam zoom, recorte e colisões.
- Cada camada carregada pode ser filtrada por atributos presentes na versão
  exibida. No catálogo, o superadmin pode escolher cores por categoria,
  traços, símbolos de ponto, preenchimento e aparência das etiquetas.
- A busca de endereço oferece até sete sugestões de imóveis e ruas do RG
  quando o perfil tem acesso aos dados. O quarteirão continua sendo o vínculo
  para consultar as informações dos imóveis.
- Ovitrampas usam a leitura mais recente entre as fontes válidas do VSATT.
  Pontos estratégicos e ações e atendimentos usam coordenadas dos cadastros.
  O GeoVSATT respeita a permissão da camada e do setor de origem.
- Admin e superadmin veem as coordenadas cadastradas dos animais da
  Esporotricose e a indicação de que o ponto está dentro ou fora do limite
  oficial, quando disponível. Outros perfis autorizados veem contagens por
  célula e o centro de cada célula. Nenhum ponto cadastrado é reposicionado
  automaticamente pelo GeoVSATT.

## Composição, população e exportação na 2.20.0

- Abra **Compor e imprimir mapa** e ajuste o recorte na própria folha.
  Selecione camadas e imagem-base, orientação A4, título e nota. A legenda
  pode ficar acima, abaixo ou ao lado do mapa e mostra as categorias no
  recorte. A folha inclui seta norte, escala gráfica, data e créditos da
  base escolhida. A opção **Imprimir / salvar PDF** abre a impressão do
  navegador. Ao fechar a composição, o mapa anterior recupera seu recorte,
  camadas e imagem-base.
- Use **Estimar população por área**, desenhe o contorno e selecione
  **Concluir**. O cálculo usa as residências do RG, o fator de 2,93 pessoas
  por residência do Censo 2022 e a proporção de área dos quarteirões
  cortados pelo contorno. A cobertura do RG é indicada à parte. É possível
  excluir residências em condomínios. A estimativa pode acompanhar a folha.
- Em **Gerenciar camadas → camada → Exportação da camada**, o superadmin
  escolhe as contas autorizadas. A autorização de exportação exige acesso
  à camada e às permissões de seu setor. O botão **Exportar** no menu
  oferece CSV com coluna WKT em WGS 84, GeoJSON e KML para a versão ativa.
  O arquivo inclui todas as feições acessíveis da camada. O VSATT registra
  formato, conta, camada, versão quando importada e quantidade na auditoria.

## Equipamentos, filtros e composições salvas na 2.21.0

- O superadmin pode abrir **Gerenciar camadas → Cadastro de equipamentos**
  ou usar **Marcar novo equipamento** na barra do mapa. Ao clicar em um
  equipamento, o superadmin também encontra **Editar equipamento**. Salvar
  publica uma versão da camada `predios_publicos`, com histórico e auditoria.
  Se outra versão for publicada durante a edição, o sistema pede para reabrir
  o cadastro. Os formulários de Endemias usam seu próprio catálogo.
- A camada mantém o acervo carregado. O código, os serviços, o horário e a
  gestão são complementados pelo cadastro institucional quando há uma única
  correspondência por nome e coordenadas. O superadmin pode preencher ou
  corrigir esses campos no GeoVSATT. O detalhe e os formatos de exportação
  usam os mesmos atributos, conforme as permissões da camada.
- Os filtros de atributos aceitam igualdade, diferença, busca por trecho,
  vazio ou preenchido. Campos de data e numéricos oferecem limites que podem
  ser combinados para formar um intervalo.
- Na prévia, **Salvar como nova** guarda a composição na conta. Em **Minhas
  composições**, use **Abrir** para recuperar título, nota, recorte, layout,
  orientação, imagem-base, legenda, camadas e filtros. **Atualizar composição**
  grava uma revisão. Camadas e imagem-base passam pela permissão vigente a
  cada abertura. Medições pertencem à sessão aberta.

## Busca postal e base vetorial na 2.22.0

- **Rua → CEP** consulta o [ViaCEP](https://viacep.com.br/) com o logradouro e
  o município do RG, Almirante Tamandaré–PR. Mostra todos os CEPs retornados,
  com bairro e descrição do trecho quando informados. A consulta é executada
  ao acionar **Buscar**. **Procurar no RG** busca os quarteirões para as contas
  autorizadas. **CEP / BrasilAPI** atende à consulta a partir dos oito dígitos.
- As sugestões usam o RG enquanto a pessoa digita, inclusive com início do
  número do imóvel. A busca enviada no modo **Endereço / RG** continua usando
  o número completo. As setas navegam pelas sugestões e Enter escolhe o item.
- **OpenStreetMap · OpenFreeMap** usa a base Positron com MapLibre GL JS e
  atribuição à cartografia na tela e na prévia. A opção pode ser escolhida e
  salva em composições. O mapa abre sem base. As camadas institucionais mantêm
  o controle de acesso e a busca continua disponível durante a troca de base.

## Bloqueios de esporotricose na 2.23.0

- **Esporotricose · Raios de bloqueio** representa os 150 m do mapa de
  bloqueio do Ambiental, centrados na coordenada cadastrada do caso animal.
  O contorno abre os detalhes com situação e data do bloqueio, classificação
  da posição e quantidade de quarteirões inteiros ou parcialmente no raio.
  O ponto ou o contorno também abre a página de impressão do caso no Ambiental.
- **Esporotricose · Quarteirões nos raios** cruza os raios com a malha
  territorial ativa. Mostra a parcela coberta pelos raios combinados e os casos
  correspondentes por situação de bloqueio. Sobreposições contam uma vez
  no cálculo de área. Abra os detalhes do RG pelo balão do quarteirão.
- Os resultados indicam abrangência geométrica. A situação de bloqueio vem
  do cadastro do caso. A comprovação da execução em cada quarteirão exige
  dados próprios de campo. Ambas as camadas exigem permissão para as posições
  exatas da Esporotricose animal. O acesso aos quarteirões libera a cobertura
  e suas contagens. As autorizações de exportação são configuradas por camada.

## Quarteirões trabalhados na 2.24.0

- A camada **Quarteirões trabalhados** cruza os registros de visita do
  Endemias e do LIRAa com a malha ativa, usando localidade e número do
  quarteirão. O filtro começa em 1º de janeiro do ano corrente e aceita
  outros períodos, tipos de trabalho e localidades. O painel informa
  o total do recorte e quantos registros ficaram sem geometria.
- O balão mostra a contagem por tipo, o último registro no período e as
  quantidades de visitas normais, fechadas, recuperadas e de registros
  com outra situação ou sem situação. Os valores contam registros de
  visita. Um mesmo imóvel pode aparecer em várias visitas.
- Composições reaplicam o recorte ao abrir e imprimem o período na legenda.
  Os links de CSV, GeoJSON e KML exportam o recorte aplicado para as contas
  autorizadas. O catálogo administra a visibilidade e os estilos da camada.
  O acesso também exige o setor Endemias e a camada Quarteirões.

## Próximos incrementos

1. Usar a camada nativa `heatmap` do MapLibre para futuros mapas de densidade,
   com filtros por período e respeito às permissões e à agregação de cada fonte.
   [Documentação OpenFreeMap](https://openfreemap.org/quick_start/) ·
   [Estilos MapLibre](https://maplibre.org/maplibre-style-spec/layers/#heatmap)
2. Adicionar ortofotos com atribuição, metadados e regras de exportação.
3. Nominatim como geocodificação complementar para vias e lugares públicos.
   Priorizar instância própria ou provedor contratado no uso recorrente.
   A instância pública exige atribuição, identificação da aplicação, limite
   agregado de uma consulta por segundo, provedor substituível e ausência de
   autocomplete ou dados confidenciais. O resultado externo deve indicar a
   fonte e a precisão. O vínculo oficial com o quarteirão vem do RG.
   [Política do Nominatim público](https://operations.osmfoundation.org/policies/nominatim/)
4. Camadas de suspeitas de dengue e coletas de tubos com coordenadas. Evoluir
   consultas temporais e incorporar raios de ovitrampas positivas com a regra
   operacional definida pelo setor.

## Histórico de implantação e próximas validações

Para a transição de `2.15.2` para `2.16.0`, foi usado
`scripts/ativar_geovsatt_2160_windows.py`, em uma sessão elevada do Windows.
O instalador verifica os commits completos passados em
`--release` e `--expected-current`, faz os backups, integra por fast-forward,
aplica somente as migrações previstas `0046` e `0047` e valida os logins nas
entradas locais e na origem do Tunnel. Em caso de falha, volta ao código e à
configuração anteriores e preserva as migrações aditivas.

A revisão `9346ba9` da 2.17.0 foi instalada sem novas migrações. A primeira
tentativa retornou à 2.16.0 porque `requests` não fazia parte do Python do
serviço. A consulta de CEP foi corrigida para usar a biblioteca padrão.
A regressão de 70 testes e uma consulta de CEP público foram executadas
com o próprio runtime do serviço antes da segunda tentativa.

A origem do hostname `geo.vsatt.com.br` no Tunnel é
`http://127.0.0.1:5001`, com o cabeçalho Host original. A porta `5005` é para
acesso local. Configure o Access para as contas de teste e valide o login
do novo hostname na origem antes de criar a rota publicada.

Para próximas versões:

- executar a suíte completa em banco isolado;
- homologar o mapa e os detalhes do RG com superadmin e contas comuns;
- validar desempenho em computador e celular com as três camadas iniciais;
- confirmar backup, reinício e retorno dos logins após a atualização.
