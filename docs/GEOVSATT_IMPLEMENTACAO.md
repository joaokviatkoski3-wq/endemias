# GeoVSATT - implementação e continuidade

Atualizado em 26/11/2026.

## Estado deste incremento

O GeoVSATT deixa de ser apenas planejamento e passa a ter uma fundação executável
no mesmo repositório do VSATT. A versão candidata é `2.16.0`; isso não significa
que `geo.vsatt.com.br` já esteja publicado. A produção confirmada continua sendo a
versão indicada em `ESTADO_ATUAL_PROJETO.md` até implantação e homologação.

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
- o endereço público, o Tunnel, DNS, firewall e serviços Windows não foram alterados.

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

## Próximos incrementos sugeridos

1. Prédios públicos, começando pelas fontes com coordenadas e responsáveis definidos.
2. Pontos estratégicos, ovitrampas, esporotricose e bloqueios, com validação de precisão
   e proteção dos dados pessoais.
3. Ferramentas de distância, área, população por seleção e impressão cartográfica.
4. Provedores de satélite e ortofoto com licença, atribuição, cache e versionamento
   formalmente definidos.

## Implantação futura

Antes de publicar:

- executar a suíte completa em banco isolado;
- homologar o mapa e os detalhes do RG com superadmin e contas comuns;
- validar desempenho em computador e celular com as três camadas iniciais;
- configurar a porta local GeoVSATT (`ENDEMIAS_GEO_LOCAL_PORT`, padrão `5005`);
- criar o hostname e a rota do Tunnel somente depois de autorização do usuário;
- confirmar backup, reinício e retorno das três áreas existentes.
