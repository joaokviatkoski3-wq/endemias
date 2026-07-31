# Auditoria final de SQL exclusivo do SQLite

Auditoria executada no fechamento da camada funcional dual. O verificador e:

```powershell
python scripts\auditar_sql_sqlite.py
```

Ele procura `PRAGMA`, `sqlite_master`, `executescript`, `lastrowid`,
`INSERT OR IGNORE/REPLACE`, `GROUP_CONCAT`, `COLLATE NOCASE`, `julianday`,
`strftime` SQL e modificadores SQLite de `date()`. Uma ocorrencia nova fora da
classificacao revisada faz o comando falhar.

## Classificacao

### Infraestrutura exclusivamente SQLite

- `criar_banco.py`, `app_core/sqlite_inventory.py` e
  `app_core/sqlite_maintenance.py`: criacao, inventario e manutencao do banco
  legado.
- `app_core/backup.py`: copia consistente e restauracao do arquivo SQLite.
- `app_core/dbml.py`: exportador DBML SQLite, ainda indisponivel no backend
  PostgreSQL.
- `app_core/postgresql_data_migration.py`: le o SQLite de origem durante a
  carga PostgreSQL; os `PRAGMA` verificam justamente essa origem.
- `app_core/db.py`: ramos do adaptador SQLite e excecao deliberada de
  `executescript` no wrapper PostgreSQL.

### Manutencao de esquema restrita ao SQLite

As ocorrencias em `agentes`, `amostras_animais`, `bri`, `boletim_mensal`,
`esporotricose`, `meteorologia`, `ovitrampas`, `ovitrampas_laboratorio`,
`pontos_estrategicos`, `recolhimentos`, `registro_geografico`, Acoes do Setor e
Agenda pertencem a `ensure_schema` ou migracoes locais. A fabrica Flask chama
essas rotinas somente quando `db_core.is_sqlite(database_target)`; no
PostgreSQL o esquema vem de `migrations/postgresql`.

### Expressoes duais intencionais

Dashboard, Laboratorio, Notificacoes, Relatorio por Servidor, Exportacoes,
Consolidados, Agenda, Acoes do Setor, Ovitrampas, Registro Geografico,
Esporotricose e o ETL conservam expressoes SQLite em helpers que escolhem
explicitamente a alternativa PostgreSQL (`string_agg`, intervalos, `RETURNING`
ou metadados de `information_schema`).

### Ferramentas historicas

Os usos restantes de `lastrowid`/`INSERT OR IGNORE` na importacao inicial CSV
do Registro Geografico e na importacao de planilhas historicas de doentes de
Esporotricose sao cargas unicas do arquivo SQLite, fora das rotas operacionais.
Eles permanecem documentados para reproducao do legado.

## Pendencia funcional encontrada e corrigida

A importacao Kobo ativa de Esporotricose ainda usava `INSERT OR IGNORE` e
`lastrowid`. Ela agora monta `ON CONFLICT DO NOTHING` no PostgreSQL, conserva
`INSERT OR IGNORE` no SQLite e recupera a identidade de novas localidades pelo
helper dual. O ensaio de visitas de Esporotricose executa insercao e repeticao
idempotente em tabelas temporarias PostgreSQL.

## Resultado

Nao restou SQL SQLite sem classificacao no caminho funcional dual. Manter o
verificador na regressao evita que novas dependencias exclusivas entrem sem
decisao explicita.
