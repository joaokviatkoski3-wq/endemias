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
- uso dos arquivos SVG e PNG oficiais anexados para a nova marca.

Limites explícitos:

- a camada Localidades deste incremento é representativa; não declara limites oficiais;
- Bairros, hidrografia, satélite e ortofotos permanecem sem geometria até entrada de fonte
  oficial e metadados;
- as camadas operacionais sensíveis ainda não foram expostas;
- upload, versões, simbologia e permissões por camada ainda não gravam configuração;
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

## Próximos incrementos sugeridos

1. Catálogo persistente de camadas, metadados e versões, com upload e rollback pelo
   superadmin.
2. Regras de visibilidade por nível, setor e usuários escolhidos, aplicadas tanto aos
   dados quanto às buscas, detalhes, exportações e impressão.
3. Prédios públicos, começando pelas fontes com coordenadas e responsáveis definidos.
4. Pontos estratégicos, ovitrampas, esporotricose e bloqueios, com validação de precisão
   e proteção dos dados pessoais.
5. Ferramentas de distância, área, população por seleção e impressão cartográfica.
6. Provedores de satélite e ortofoto com licença, atribuição, cache e versionamento
   formalmente definidos.

## Implantação futura

Antes de publicar:

- executar a suíte completa em banco isolado;
- homologar o mapa e os detalhes do RG com superadmin e contas comuns;
- validar desempenho em computador e celular com as três camadas iniciais;
- configurar a porta local GeoVSATT (`ENDEMIAS_GEO_LOCAL_PORT`, padrão `5005`);
- criar o hostname e a rota do Tunnel somente depois de autorização do usuário;
- confirmar backup, reinício e retorno das três áreas existentes.
