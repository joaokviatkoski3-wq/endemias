# GeoVSATT - implementação e continuidade

Atualizado em 26/11/2026.

## Estado deste incremento

O GeoVSATT está instalado na versão `2.17.0`, com busca de endereços,
etiquetas e medições. O login respondeu em `https://geo.vsatt.com.br/login`.
Consulte `ESTADO_ATUAL_PROJETO.md` para acompanhar a instalação oficial.

Implementado:

- terceiro domínio lógico `geo.vsatt.com.br`, com sessão isolada e o login atual;
- auditoria identificada como setor `geo`, com ampliação compatível em SQLite e PostgreSQL;
- entrada do GeoVSATT no portal `vsatt.com.br`;
- mapa próprio, sem reaproveitar o desenho da página Mapa antiga e sem imagem-base;
- menu de camadas à esquerda, aberto pelo botão de menu;
- quarteirões ativos do Registro Geográfico, com resumo e detalhe dos imóveis ao clicar;
- localidades como pontos de referência derivados da extensão dos quarteirões;
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
  do menu lateral. Para publicar um novo arquivo em uma camada importada,
  escolha **Importar versão** ao lado dela.

## Próximos incrementos

1. Base vetorial OpenFreeMap, com dados OpenStreetMap e renderização MapLibre GL JS.
   Usar a camada nativa `heatmap` do MapLibre para futuros mapas de densidade,
   com filtros por período e respeito às permissões e à agregação de cada fonte.
   [Documentação OpenFreeMap](https://openfreemap.org/quick_start/) ·
   [Estilos MapLibre](https://maplibre.org/maplibre-style-spec/layers/#heatmap)
2. Base opcional Esri World Imagery e ortofotos, com revisão dos direitos de
   uso, atribuição e exportação.
3. Nominatim como geocodificação complementar para vias e lugares públicos.
   Priorizar instância própria ou provedor contratado no uso recorrente.
   A instância pública exige atribuição, identificação da aplicação, limite
   agregado de uma consulta por segundo, provedor substituível e ausência de
   autocomplete ou dados confidenciais. O resultado externo deve indicar a
   fonte e a precisão. O vínculo oficial com o quarteirão vem do RG.
   [Política do Nominatim público](https://operations.osmfoundation.org/policies/nominatim/)
4. Cadastro manual de prédios públicos e pontos de interesse pelo superadmin.
5. Ações e Atendimentos de Endemias que tenham coordenadas e camadas de
   vigilância, começando pela Esporotricose com controle de acesso e precisão.
6. População por seleção, composição e impressão de mapas personalizados.

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
