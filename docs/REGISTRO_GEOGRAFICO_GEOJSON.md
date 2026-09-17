# Camada GeoJSON dos quarteirões

## Finalidade

O Registro Geográfico mantém uma camada territorial local dos quarteirões,
proveniente do QGIS. Ela alimenta o Mapa Territorial, o mapa interno do RG e
os mini-mapas dos RGs impressos. Esta camada não altera imóveis do RG, visitas,
ovitrampas ou qualquer dado no Conta Ovos.

## Importação administrativa

Somente administradores podem abrir a aba **Geometrias** em Registro
Geográfico e importar um arquivo `.geojson`/`.json`.

O arquivo deve ser uma `FeatureCollection` com as propriedades:

| Propriedade | Uso |
| --- | --- |
| `Localidade` | Código da localidade (`cod_localidade`), nome da localidade ou ID local reconhecido pelo cadastro. |
| `id_quart` | Número municipal único do quarteirão. Valores numéricos são preservados com quatro dígitos internamente. |

São aceitas geometrias `Polygon` e `MultiPolygon` em WGS 84 (GeoJSON padrão:
longitude, latitude). Todos os anéis precisam estar fechados e as coordenadas
precisam estar dentro dos limites geográficos. O limite do arquivo é 20 MB.

Antes de gravar, a prévia informa quantas geometrias são novas, alteradas,
iguais ou ausentes. A confirmação só é aceita para o mesmo arquivo da prévia,
validado por SHA-256. Quarteirões ausentes da nova versão nunca são excluídos
automaticamente: a nova versão apenas se torna a camada ativa.

Cada importação armazena arquivo de origem, hash, horário, usuário, versão e
todas as geometrias. A camada ativa é servida por
`/api/registro-geografico/geojson`; enquanto não existir uma versão importada,
o endpoint retorna o arquivo legado `static/quarteiroes.geojson`. Isso mantém
os mapas disponíveis durante a implantação.

## Tabelas

- `registro_geografico_geojson_importacoes`: metadados e estado ativo de cada
  versão.
- `registro_geografico_quarteiroes_geometrias`: geometria e propriedades de
  cada quarteirão em cada versão.

A migração PostgreSQL é `0013_registro_geografico_geojson.sql`. Em SQLite de
testes, as tabelas são criadas de forma compatível por
`registro_geografico.ensure_schema`.

## Relação futura com Conta Ovos

O importador não faz chamadas à API Conta Ovos. Ele prepara a fonte local para
uma futura prévia e sincronização supervisionada de quarteirões. A geometria
original é preservada; caso o `block_coordinates` remoto exceda 2.000
caracteres, uma eventual cópia simplificada deverá ser gerada apenas para o
Conta Ovos, com revisão humana e sem substituir a geometria do QGIS.
