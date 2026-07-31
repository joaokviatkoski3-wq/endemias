# Migracao gradual para PostgreSQL

## Estado atual

O PostgreSQL e uma infraestrutura paralela de migracao. O sistema em producao
continua usando exclusivamente o arquivo `endemias.db`.

O SQLite continua sendo o padrao da aplicacao e do `iniciar.bat`. Existe um
modo PostgreSQL experimental para testes controlados da camada ja convertida,
mas ele ainda nao deve ser usado como servidor operacional.

A primeira migracao de esquema ja foi aplicada e validada em
`endemias_teste`. Ela criou as `59` tabelas do sistema, sem copiar dados. O
banco recebeu depois uma copia validada de `153.419` registros do SQLite. Em
31/07/2026, `endemias_migracao` recebeu o snapshot recente com `154.217`
registros e passou pelo smoke integrado. Os detalhes estao em
`docs/POSTGRESQL_SCHEMA_INICIAL.md` e
`docs/POSTGRESQL_CARGA_TESTE.md`.

A primeira camada dual da aplicacao tambem foi criada. Os helpers comuns e a
tela de login ja foram testados em modo somente leitura contra
`endemias_teste`. Tentativas de login e auditoria tambem tiveram suas escritas
validadas em tabelas PostgreSQL temporarias. O primeiro modulo funcional
concluido foi o Controle de Pessoal, incluindo CRUD, filtros, historico e
renderizacao da pagina. Gestao de Usuarios foi homologada em seguida, e o
Historico de Importacoes teve seu nucleo convertido para SQL portavel.
Recolhimentos de Materiais e Amostras de Animais tambem tiveram leitura,
escrita, filtros, resumos, paginas e APIs homologados. Os limites atuais estao
documentados em `docs/POSTGRESQL_CAMADA_DUAL.md`. BRI e Pontos Estrategicos
foram homologados em seguida, incluindo aliases e vinculos com visitas, focos
e tratamentos. A pagina Visitas de Arboviroses tambem possui agora filtros,
listagem, detalhes e edicao homologados nos dois bancos. Dashboard Integrado,
Producao Operacional e a consulta geral de Resultados Laboratoriais completam
o lote seguinte. As visitas de Esporotricose importadas do Kobo, incluindo
animais encontrados, localidades e buscas de feridos, tambem estao
homologadas. O cadastro manual de doentes, receitas, entregas, estoque e
metadados dos anexos completa a cobertura funcional da pagina.
Ovitrampas, Conta Ovos/SisPNCD e o Registro Geografico tambem estao
homologados. No Registro Geografico, a cobertura inclui cadastro, edicao,
acompanhamento, mapa, impressao, sugestoes de logradouros e edicao em lote.
A Importacao Kobo tambem foi homologada de ponta a ponta: simulacao,
processamento transacional, normalizacao, reimportacao idempotente, resultados
de larvas, focos positivos, pendencias e renderizacao da pagina.
Agenda, Pagina Inicial e Meteorologia completam o lote seguinte, incluindo
eventos manuais e automaticos, recorrencias, alertas para trabalho de campo,
sincronizacao meteorologica e os resumos operacionais da tela inicial.
Acoes e Atendimentos do Setor tambem esta homologado: CRUD, filtros,
servidores, anexos, galeria, downloads, relatorio tecnico, permissoes e
auditoria foram exercitados com escritas somente em tabelas temporarias.
O Boletim Mensal completa o lote seguinte, incluindo todos os indicadores
automaticos, ajustes e itens manuais, fechamento mensal, PDF, XLSX, permissoes
e auditoria transacional.
Mapa geral, Notificacoes e Relatorio por Servidor completam o lote seguinte.
Foram homologados filtros e camadas territoriais, historico e escritas
auditadas de Notificacoes, relatorios individual e do setor, duracoes,
evolucao semanal e os blocos de laboratorio, Esporotricose, Ovitrampas e
Registro Geografico.

## Bancos locais

- `endemias_teste`: criacao de esquema, cargas descartaveis e testes.
- `endemias_migracao`: ensaios completos e validados antes da troca definitiva.
- `endemias.db`: fonte oficial enquanto a migracao estiver em andamento.

## Credenciais

As ferramentas usam o mecanismo `pgpass` do PostgreSQL. No Windows, o arquivo
do usuario interativo fica normalmente em:

```text
%APPDATA%\postgresql\pgpass.conf
```

Senhas nao devem ser colocadas em scripts, arquivos `.sql`, configuracoes
versionadas ou URLs de conexao. O repositorio ignora `pgpass.conf`, arquivos
`*.pgpass` e arquivos `.env` como protecao adicional.

O servidor automatico atual roda pela conta `SYSTEM`. Antes da troca definitiva,
sera configurada uma credencial propria e protegida para essa conta. O
`pgpass.conf` do usuario `Geoprocessamento` atende apenas as ferramentas
interativas desta fase.

## Diagnostico

Na raiz do projeto:

```powershell
python scripts\verificar_postgresql.py
```

O comando verifica os dois bancos, a versao, a codificacao, o fuso horario e a
permissao de escrita por meio de uma tabela temporaria desfeita ao final.

Para conferir apenas a leitura:

```powershell
python scripts\verificar_postgresql.py --somente-leitura
```

Para conferir um banco especifico:

```powershell
python scripts\verificar_postgresql.py --database endemias_teste
```

## Inventario do SQLite

O inventario pode ser refeito enquanto o SQLite continuar como fonte oficial:

```powershell
python scripts\inventariar_sqlite.py
```

O resultado detalhado fica em
`saida/migracao/inventario_sqlite.json`. Ele contem esquema, contagens e
classes de armazenamento, mas nao exporta os valores das linhas. O diagnostico
atual e as decisoes de conversao estao em
`docs/POSTGRESQL_INVENTARIO_SQLITE.md`.

## Configuracao opcional

Os valores abaixo atendem as ferramentas de migracao e os testes controlados
da camada dual:

| Variavel | Padrao |
| --- | --- |
| `ENDEMIAS_PG_HOST` | `127.0.0.1` |
| `ENDEMIAS_PG_PORT` | `5432` |
| `ENDEMIAS_PG_DATABASE` | `endemias_teste` |
| `ENDEMIAS_PG_USER` | `endemias_app` |
| `ENDEMIAS_PG_CONNECT_TIMEOUT` | `5` |
| `ENDEMIAS_PG_SSLMODE` | `prefer` |

`ENDEMIAS_DB_BACKEND=postgresql` seleciona o adaptador experimental. Essa
variavel nao foi adicionada ao `iniciar.bat` e nao deve ser configurada no
servidor oficial enquanto os modulos funcionais ainda estiverem em conversao.

As variaveis padrao do libpq (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` e
`PGSSLMODE`) tambem sao aceitas. A senha continua sob responsabilidade do
`pgpass`.

## Sequencia prevista

1. Concluido: inventariar o esquema e os dados reais do SQLite.
2. Concluido: criar e validar a migracao inicial em `endemias_teste`.
3. Concluido: copiar os dados para `endemias_teste`, preservando IDs e
   relacionamentos.
4. Concluido: comparar contagens, checksums e chaves estrangeiras.
5. Concluido: adaptar e testar a aplicacao em ambiente PostgreSQL
   separado. A camada comum, o primeiro teste Flask, autenticacao e auditoria
   estao concluidos; Controle de Pessoal e o primeiro modulo funcional
   homologado, seguido por Gestao de Usuarios e pelo nucleo do Historico de
   Importacoes. Recolhimentos de Materiais e Amostras de Animais tambem estao
   homologados. BRI e Pontos Estrategicos completam o lote seguinte, com seus
   vinculos operacionais validados. Visitas de Arboviroses completa o lote
   posterior. Dashboard Integrado, Producao Operacional e a consulta
   laboratorial geral tambem estao homologados. O bloco de visitas de
   Esporotricose, seus animais e buscas de feridos completa o lote seguinte.
   O cadastro manual de doentes, receitas, entregas, estoque e metadados dos
   anexos foi homologado na sequencia. A pagina Ovitrampas tambem esta
   concluida: cadastro, historico, leituras, ocorrencias, monitoramento,
   diarios, ordenacao, calendario, lotes do laboratorio e conferencia para o
   Conta Ovos usam a camada dual. O espelho Conta Ovos/SisPNCD, incluindo
   pendencias, consolidacoes e baixas, foi homologado em seguida. O Registro
   Geografico tambem esta concluido, incluindo consultas, acompanhamento,
   mapa, impressao e todas as operacoes de edicao. A Importacao Kobo tambem
   esta concluida, incluindo o ETL principal, simulacao, confirmacao,
   reimportacao, larvas, pendencias e historico. Agenda, Pagina Inicial e
   Meteorologia foram homologadas na sequencia, com leituras e escritas
   isoladas em tabelas temporarias. Acoes e Atendimentos do Setor completa o
   lote seguinte, incluindo CRUD, filtros, servidores, anexos, relatorio,
   permissoes e auditoria. O Boletim Mensal foi homologado na sequencia, com
   indicadores automaticos, fechamento, linhas manuais, PDF, XLSX, permissoes
   e auditoria. Mapa geral, Notificacoes e Relatorio por Servidor foram
   homologados na sequencia, incluindo consultas territoriais, escrita e
   auditoria de Notificacoes, relatorios individual e consolidado e os blocos
   complementares. A regressao ampla deste lote teve 419 testes aprovados e 5
   ignorados; as 60 tabelas publicas permaneceram inalteradas no ensaio
   PostgreSQL.
6. Concluido: ensaiar a migracao recente em `endemias_migracao`, validar
   checksums, constraints, 34 identidades, 20 smokes e cinco sessoes
   concorrentes sem alterar tabelas publicas.
7. Pendente: validar restore em segundo banco descartavel e preparar a conta
   `SYSTEM` antes do backup, carga final, validacao e troca controlada.

O SQLite final sera preservado como ponto de recuperacao e nao sera apagado.
