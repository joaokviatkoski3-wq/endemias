# Inventario do SQLite para migracao PostgreSQL

Levantamento executado em 29/07/2026 contra o banco oficial, em modo somente
leitura e dentro de uma transacao consistente. O arquivo JSON detalhado e
gerado localmente em `saida/migracao/inventario_sqlite.json` e nao e
versionado.

## Resultado geral

| Item | Resultado |
| --- | ---: |
| Integridade SQLite | `ok` |
| Violacoes de chave estrangeira | `0` |
| Tabelas | `59` |
| Colunas | `691` |
| Registros no momento do inventario | `153.409` |
| Indices | `164` |
| Chaves estrangeiras | `55` |
| Views | `0` |
| Triggers | `0` |
| Tabelas sem chave primaria | `0` |
| Colunas com classes SQLite misturadas | `0` |
| Incompatibilidades entre tipo declarado e armazenado | `0` |

O total de registros pode aumentar enquanto o sistema estiver em uso,
principalmente por auditoria e novas importacoes. Isso nao afeta a estrutura
inventariada.

As maiores tabelas sao:

| Tabela | Registros |
| --- | ---: |
| `registro_geografico_imoveis` | `44.870` |
| `visita_agentes` | `36.808` |
| `visitas` | `16.814` |
| `registro_geografico_imovel_agentes` | `10.350` |
| `depositos_inspecionados` | `9.116` |
| `ovitrampas_leituras` | `8.452` |
| `ovitrampas_ocorrencias_conta_ovos` | `8.185` |

O volume e pequeno para PostgreSQL. O risco principal esta na conversao das
consultas e nao na quantidade de dados.

## Limpezas necessarias na carga

Quatro colunas temporais possuem marcadores aceitos pelo SQLite, mas recusados
pelo tipo `DATE` do PostgreSQL:

| Tabela e coluna | Situacao | Conversao |
| --- | --- | --- |
| `esporotricose_animais.data_atendimento` | `2` strings vazias | `NULL` |
| `esporotricose_doentes_animais.data_bloqueio` | `5` valores `NaT` | `NULL` |
| `pontos_estrategicos.data_inclusao` | `22` valores `NaT` | `NULL` |
| `pontos_estrategicos.data_desativacao` | `22` valores `NaT` | `NULL` |

Os demais valores declarados como `DATE` usam `AAAA-MM-DD`. Os campos `TIME`
validos usam `HH:MM` ou `HH:MM:SS`. A limpeza sera feita durante a copia, sem
alterar antecipadamente o banco oficial.

## Indice redundante

`resultados_laboratorio.id_coleta` possui duas garantias unicas equivalentes:

- restricao `UNIQUE`, representada pelo indice automatico do SQLite;
- indice explicito `idx_resultado_lab_coleta_unico`.

O PostgreSQL recebera somente uma restricao unica. O indice redundante nao sera
reproduzido.

## Conversao inicial de tipos

| SQLite | PostgreSQL inicial | Observacao |
| --- | --- | --- |
| `TEXT` | `text` | Mantem conteudo e comparacoes atuais |
| `INTEGER` | `integer` ou `bigint` | Flags `0/1` permanecem numericas inicialmente |
| `REAL` | `double precision` | Evita perda de precisao existente |
| `DATE` | `date` | Depois da limpeza dos marcadores invalidos |
| `TIME` | `time` | Formatos atuais sao compativeis |
| `VARCHAR(20)` | `varchar(20)` | Preserva o limite declarado |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | identidade PostgreSQL | IDs atuais serao preservados e sequencias reajustadas |

Converter imediatamente todos os campos `0/1` para `boolean` quebraria
consultas que hoje comparam esses campos numericamente. Essa melhoria deve ser
feita depois da compatibilidade funcional.

## Incompatibilidades no codigo

O levantamento encontrou:

| Recurso SQLite | Ocorrencias | Conversao prevista |
| --- | ---: | --- |
| `INSERT OR IGNORE` | `29` em `12` arquivos | `ON CONFLICT DO NOTHING` |
| `INSERT OR REPLACE` | `1` | `ON CONFLICT ... DO UPDATE` explicito |
| `GROUP_CONCAT` | `39` em `14` arquivos | `string_agg` |
| `COLLATE NOCASE` | `25` em `4` arquivos | ordenacao PostgreSQL coerente com UTF-8 |
| `lastrowid` | `31` em `16` arquivos | `INSERT ... RETURNING` |
| `PRAGMA` | `58` em `21` arquivos | remover ou consultar catalogos PostgreSQL |
| `sqlite_master` | `24` em `16` arquivos | `information_schema`/`pg_catalog` |
| `BEGIN IMMEDIATE` | `3` | transacao e bloqueio apropriados ao PostgreSQL |

Tambem existem pelo menos `25` aberturas diretas por `sqlite3.connect` fora da
interface principal. Elas precisam ser centralizadas antes de o aplicativo
rodar integralmente em PostgreSQL.

Os placeholders posicionais `?` usados amplamente pelo SQLite tambem devem ser
convertidos para o formato aceito pelo driver PostgreSQL. Essa conversao sera
tratada pela camada de banco, sem substituicoes cegas dentro de textos SQL.

## Decisoes de seguranca

- SQLite continua sendo a fonte oficial.
- Nenhum dado pessoal faz parte deste documento ou do inventario versionado.
- O JSON local contem somente esquema, contagens e classes de armazenamento,
  sem nomes, enderecos, CPF, telefones ou valores das linhas.
- A primeira carga sera feita somente em `endemias_teste`.
- IDs e relacionamentos serao preservados.
- O esquema PostgreSQL sera criado por migracoes versionadas, nao manualmente
  pelo pgAdmin.
- Rotinas SQLite de manutencao e criacao dinamica nao rodarao no PostgreSQL.

## Etapa de esquema concluida

A primeira migracao foi gerada, aplicada em `endemias_teste` e comparada
automaticamente. Tabelas, colunas, chaves, restricoes e indices coincidem com
o plano documentado. Consulte `docs/POSTGRESQL_SCHEMA_INICIAL.md`.

A proxima etapa e copiar os dados para `endemias_teste`, aplicar as limpezas
temporais descritas acima e validar as contagens e os relacionamentos.
