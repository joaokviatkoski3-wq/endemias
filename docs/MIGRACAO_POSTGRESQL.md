# Migracao gradual para PostgreSQL

## Estado atual

O PostgreSQL e uma infraestrutura paralela de migracao. O sistema em producao
continua usando exclusivamente o arquivo `endemias.db`.

Nenhuma variavel PostgreSQL ativa a troca do banco da aplicacao nesta etapa.
Isso evita uma mudanca acidental antes da conversao e validacao de todas as
consultas do sistema.

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

## Configuracao opcional

Os valores abaixo so afetam as ferramentas de migracao:

| Variavel | Padrao |
| --- | --- |
| `ENDEMIAS_PG_HOST` | `127.0.0.1` |
| `ENDEMIAS_PG_PORT` | `5432` |
| `ENDEMIAS_PG_DATABASE` | `endemias_teste` |
| `ENDEMIAS_PG_USER` | `endemias_app` |
| `ENDEMIAS_PG_CONNECT_TIMEOUT` | `5` |
| `ENDEMIAS_PG_SSLMODE` | `prefer` |

As variaveis padrao do libpq (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` e
`PGSSLMODE`) tambem sao aceitas. A senha continua sob responsabilidade do
`pgpass`.

## Sequencia prevista

1. Inventariar o esquema e os dados reais do SQLite.
2. Criar migracoes SQL versionadas para o PostgreSQL.
3. Copiar os dados para `endemias_teste`, preservando IDs e relacionamentos.
4. Comparar contagens, chaves estrangeiras e totais de negocio.
5. Adaptar e testar a aplicacao completa em ambiente PostgreSQL separado.
6. Ensaiar a migracao com uma copia recente do banco oficial.
7. Fazer backup, carga final, validacao e troca controlada.

O SQLite final sera preservado como ponto de recuperacao e nao sera apagado.
