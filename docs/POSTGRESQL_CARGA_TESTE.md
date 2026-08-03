# Primeira carga de dados no PostgreSQL

## Estado atualizado em 31/07/2026

Uma copia consistente do banco SQLite oficial foi carregada em
`endemias_teste`.

O sistema em producao continua usando `endemias.db`. O banco
Uma copia consistente mais recente foi carregada em `endemias_migracao` para o
ensaio integrado. O SQLite oficial permaneceu aberto somente para leitura.

## Resultado

| Verificacao | Resultado |
| --- | ---: |
| Tabelas carregadas | `59` |
| Registros no snapshot integrado | `154.217` |
| Identidades reajustadas | `34` |
| Conversoes temporais para `NULL` | `51` |
| Divergencias de contagem | `0` |
| Divergencias de checksum | `0` |
| Restricoes PostgreSQL nao validadas | `0` |
| Constraints nao validadas | `0` |
| Identidades desalinhadas | `0` de `34` |
| Smokes de modulos aprovados | `20` de `20` |
| Sessoes concorrentes | `5` |

Os `51` valores convertidos foram:

| Tabela e coluna | Quantidade |
| --- | ---: |
| `esporotricose_animais.data_atendimento` | `2` |
| `esporotricose_doentes_animais.data_bloqueio` | `5` |
| `pontos_estrategicos.data_inclusao` | `22` |
| `pontos_estrategicos.data_desativacao` | `22` |

Eram strings vazias ou o marcador `NaT`. No PostgreSQL, esses valores agora
sao `NULL`. Nenhuma linha foi descartada.

## Processo de seguranca

1. O utilitario cria um snapshot SQLite temporario por meio da API de backup.
   Isso inclui os dados confirmados presentes no WAL e fornece uma visao
   consistente mesmo com o sistema em uso.
2. O snapshot passa por `quick_check` e `foreign_key_check`.
3. O esquema PostgreSQL e comparado com o inventario do snapshot.
4. As tabelas sao ordenadas automaticamente pelas dependencias das chaves
   estrangeiras.
5. Os registros sao inseridos em lotes, preservando os IDs.
6. Cada linha recebe uma representacao canonica usada apenas para checksum.
7. Contagem e checksum de cada tabela sao comparados entre a origem convertida
   e o PostgreSQL.
8. As `34` identidades sao posicionadas no maior ID existente.
9. O `COMMIT` ocorre somente depois de todas as validacoes.

Qualquer erro antes do passo final desfaz toda a operacao no PostgreSQL. O
arquivo SQLite de origem nunca e modificado.

## Uso

Primeira carga em um destino vazio:

```powershell
python scripts\copiar_dados_postgresql.py --database endemias_teste
```

Atualizar a copia de teste:

```powershell
python scripts\copiar_dados_postgresql.py `
  --database endemias_teste `
  --substituir
```

Sem `--substituir`, a ferramenta recusa um destino que ja contenha dados. A
limpeza e a recarga com `--substituir` fazem parte da mesma transacao.

O relatorio local fica em:

```text
saida/migracao/carga_postgresql_teste.json
```

Ele contem somente contagens, checksums e estatisticas de conversao. O arquivo
esta fora do versionamento e nao contem valores das linhas.

## O que ainda nao mudou

- A aplicacao nao abre conexoes PostgreSQL durante o uso normal.
- `iniciar.bat` continua iniciando a versao SQLite.
- Backups operacionais continuam protegendo o SQLite oficial.
- Nenhuma credencial ou dado do banco foi enviado ao GitHub.

## Validacao integrada

Depois da carga, `scripts/validar_migracao_integrada_postgresql.py` recalculou
as contagens e checksums das 59 tabelas, conferiu constraints e o estado das 34
identidades. `scripts/testar_smoke_integrado_postgresql.py` executou os 20
ensaios funcionais homologados. Uma nova validacao depois do smoke confirmou
que os 154.217 registros permaneciam identicos.

`scripts/testar_concorrencia_postgresql.py` abriu cinco sessoes e confirmou 25
escritas numa tabela efemera, exercitando retries de lock e removendo a tabela
ao final. Nenhuma tabela publica do sistema foi alterada pelos testes.

## Proxima etapa

O `pg_restore` real ja foi homologado em `endemias_teste`, preservando as 59
tabelas e 153.419 registros existentes nesse banco. Restam definir o banco
final, aplicar a credencial/tarefa da conta Windows `SYSTEM` e planejar a janela
curta de congelamento, carga final e virada.
