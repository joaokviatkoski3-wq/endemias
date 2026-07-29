# Camada dual SQLite e PostgreSQL

## Estado em 29/07/2026

A aplicacao possui agora uma primeira camada de conexao capaz de consultar
SQLite ou PostgreSQL sem alterar a assinatura usada pelo codigo existente.

O SQLite continua sendo o banco padrao e o `iniciar.bat` nao foi alterado.
O modo PostgreSQL ainda e experimental e nao deve ser usado como servidor
operacional.

## O que foi implementado

- destino de banco explicito e imutavel, contendo tipo e local;
- selecao por `DB_BACKEND`, mantendo `sqlite` como padrao;
- conexao PostgreSQL por meio da configuracao libpq e do `pgpass.conf`;
- adaptadores para `conn.execute`, `cursor.execute`, `fetchone`, `fetchall`,
  `fetchmany`, `executemany`, transacoes e context managers;
- linhas PostgreSQL acessiveis tanto por indice quanto pelo nome da coluna;
- conversao segura dos placeholders `?` atuais para `%s`;
- preservacao de `?` existentes dentro de textos, identificadores e
  comentarios SQL;
- helpers comuns, autenticacao de leitura e dados globais da interface usando
  o destino configurado;
- persistencia das tentativas de login e eventos de auditoria;
- filtros portaveis por data no historico de auditoria;
- manutencao dessas tabelas em tempo de execucao restrita ao SQLite, pois no
  PostgreSQL elas sao controladas pelas migracoes;
- inicializacoes exclusivas do SQLite executadas apenas quando o destino e
  SQLite.

Operacoes antigas que recebem apenas um caminho de arquivo continuam abrindo
SQLite. Isso preserva o comportamento atual e os testes existentes.

## Validacao real

O comando abaixo executa somente leituras em `endemias_teste`:

```powershell
python scripts\testar_app_postgresql.py --database endemias_teste
```

Resultado validado:

| Verificacao | Resultado |
| --- | ---: |
| Tabelas publicas encontradas | `60` |
| Consulta com parametros | `OK` |
| Linhas retornadas por nome | `OK` |
| Tela de login Flask | `HTTP 200` |

O teste usa a propria factory Flask, os helpers compartilhados e o adaptador
PostgreSQL. Nenhuma linha e inserida, atualizada ou removida.

As escritas de autenticacao e auditoria sao validadas com:

```powershell
python scripts\testar_auth_postgresql.py --database endemias_teste
```

Esse teste cria tabelas temporarias com os mesmos contratos das tabelas
publicas, valida:

- gravacao, leitura, contagem e limpeza das tentativas de login;
- gravacao do evento de auditoria;
- serializacao e leitura dos detalhes JSON;
- filtros de acao e intervalo de datas;
- preservacao das contagens das tabelas publicas.

As tabelas temporarias existem apenas na conexao do teste e sao descartadas
automaticamente ao final.

## Controle de Pessoal

O primeiro modulo funcional completo migrado foi o **Controle de Pessoal**.
Estao compativeis com os dois bancos:

- listagem e filtros por situacao;
- busca por nome, nome completo, matricula e CPF;
- busca sem diferenca entre letras maiusculas e minusculas;
- cadastro com recuperacao segura do novo ID;
- consulta individual e edicao dos campos permitidos;
- normalizacao e criacao de servidores vindos das importacoes;
- CPF, data de nascimento e nome completo;
- historico consolidado das frentes de trabalho;
- renderizacao da pagina administrativa.

No PostgreSQL, a tabela `agentes` e administrada exclusivamente pelas
migracoes. O SQLite preserva a manutencao de compatibilidade usada pelos bancos
antigos.

O teste controlado e executado com:

```powershell
python scripts\testar_servidores_postgresql.py --database endemias_teste
```

Resultado da homologacao:

| Verificacao | Resultado |
| --- | ---: |
| CRUD em tabela temporaria | `OK` |
| Busca sem diferenca de caixa | `OK` |
| Eventos lidos no historico real | `2.868` |
| Origens presentes no historico | `8` |
| Pagina Controle de Pessoal | `HTTP 200` |
| Tabela publica `agentes` | Preservada |

O teste de pagina usa um administrador existente somente para estabelecer a
sessao. Nenhuma senha e lida e nenhum dado publico e alterado.

Por seguranca, outro banco exige:

```powershell
python scripts\testar_app_postgresql.py `
  --database outro_banco `
  --confirmar-banco outro_banco
```

## Limites atuais

A camada nao tenta reescrever automaticamente todo o dialeto SQLite. Os
seguintes recursos ainda precisam ser tratados nos respectivos modulos:

- `PRAGMA` e consultas a `sqlite_master`;
- `executescript`;
- `INSERT OR IGNORE` e `INSERT OR REPLACE`;
- `GROUP_CONCAT`;
- `COLLATE NOCASE`;
- funcoes e modificadores SQLite de `date()` e `datetime()`;
- recuperacao de IDs por `lastrowid`;
- criacao ou alteracao de esquema durante o inicio da aplicacao.

Ao encontrar `executescript` no PostgreSQL, o adaptador interrompe a operacao
com uma mensagem explicita. Isso evita uma execucao parcial de uma rotina
incompativel.

## Proxima etapa

Autenticacao, auditoria e Controle de Pessoal ja possuem leitura e escrita
basicas validadas. A proxima etapa e escolher outro modulo com dependencias
controladas e repetir a conversao completa.

Cada lote deve:

1. substituir manutencao de esquema em tempo de execucao por migracoes;
2. separar SQL comum das poucas consultas especificas de cada banco;
3. validar leituras e gravacoes em ambos os bancos;
4. testar a pagina correspondente contra `endemias_teste`;
5. manter o SQLite oficial como padrao ate a homologacao completa.
