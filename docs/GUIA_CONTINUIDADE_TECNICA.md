# Guia tecnico para continuidade por outra IA

Complementa `CONTEXTO_PARA_IA.md`. Use este documento para evitar redescobrir
decisoes tecnicas e operacionais ja consolidadas.

## Perfil do usuario e colaboracao

- Responda em portugues.
- O usuario conhece SQL/SQLite e o fluxo do setor, mas nao se considera
  programador; explique decisoes tecnicas em linguagem concreta.
- Implemente quando o pedido for de alteracao. Nao pare apenas numa proposta.
- Quando o usuario pedir somente analise, nao modifique nada.
- O usuario prefere poucos testes visuais no navegador e costuma validar a UI
  pessoalmente. Testes automatizados e verificacoes focadas continuam
  necessarios conforme o risco.
- Toda modificacao solicitada deve terminar em commit e push.
- Nao sobrescreva mudancas inesperadas; podem ter sido feitas pelo usuario.
- Evite interromper o sistema oficial na porta 5000.
- Dados de saude, CPF, telefones, anexos e bancos sao sensiveis.

## Estrutura principal

- `app.py`: fabrica Flask, configuracao, caminhos e inicializacao do servidor.
- `app_core/db.py`: adaptador dual e conexoes SQLite/PostgreSQL.
- `app_core/postgresql.py`: configuracao e conexao PostgreSQL.
- `app_core/backup_health.py`: regra unica de saude dos backups, compartilhada
  pelo verificador de linha de comando, pela Central e pelo diagnostico.
- `app_core/backup_tasks.py`: leitura somente consulta das tarefas de backup no
  Agendador do Windows; nunca cria, altera, inicia nem remove tarefa.
- `app_core/`: regras de negocio e persistencia por dominio.
- `blueprints/`: rotas, APIs e coordenacao HTTP.
- `templates/`: paginas Jinja e parte relevante do JavaScript de cada modulo.
- `static/`: CSS, JavaScript compartilhado, imagens, icones e GeoJSON.
- `migrations/`: esquema e migracoes PostgreSQL.
- `scripts/`: diagnosticos, copia, comparacao e homologacao PostgreSQL.
- `tests/`: regressao automatizada.
- `docs/POSTGRESQL_CAMADA_DUAL.md`: diario tecnico detalhado da conversao.

## Padrao da camada dual

Ao migrar um modulo:

1. Obtenha a conexao por `app_core.db`, sem usar `sqlite3.connect` diretamente
   no caminho funcional dual.
2. Use parametros `?`; o adaptador converte para PostgreSQL.
3. Evite interpolar valores no SQL. Interpole somente identificadores internos
   controlados quando inevitavel.
4. Para IDs gerados, use o helper portavel existente em vez de depender de
   `cursor.lastrowid` no PostgreSQL.
5. Separe pequenas consultas especificas por backend quando isso for mais
   claro que uma traducao automatica complexa.
6. Normalize `date`, `datetime`, `Decimal` e linhas retornadas antes de JSON.
7. Use transacoes explicitas em operacoes compostas.
8. Nao execute manutencao SQLite (`PRAGMA`, `executescript`, migracoes em tempo
   de execucao) numa conexao PostgreSQL.
9. Preserve compatibilidade SQLite para testes e rollback controlado, mas nao
   permita escritas paralelas depois da virada oficial.
10. Nao transforme toda a aplicacao ou crie uma segunda implementacao paralela
    quando uma adaptacao localizada for suficiente.

Recursos que normalmente exigem tratamento:

- `INSERT OR IGNORE` -> `ON CONFLICT DO NOTHING`;
- `INSERT OR REPLACE` -> `ON CONFLICT ... DO UPDATE`, com semantica conferida;
- `GROUP_CONCAT` -> `string_agg`;
- `COLLATE NOCASE` -> comparacao normalizada ou `ILIKE`;
- `date()`/`datetime()` SQLite -> SQL portavel ou calculo em Python;
- `sqlite_master` -> metadados do backend/helper existente;
- `PRAGMA table_info` -> helper de inspecao de colunas;
- `lastrowid` -> `RETURNING`/helper portavel;
- valores booleanos e datas, que chegam com tipos nativos no PostgreSQL.

## Modelo dos ensaios PostgreSQL

Os scripts existentes sao a referencia, especialmente:

- `scripts/testar_importacao_kobo_postgresql.py`;
- `scripts/testar_ovitrampas_postgresql.py`;
- `scripts/testar_registro_geografico_postgresql.py`;
- `scripts/testar_agenda_home_postgresql.py`;
- `scripts/testar_acoes_setor_postgresql.py`;
- `scripts/testar_boletim_mensal_postgresql.py`.
- `scripts/testar_mapa_notificacoes_relatorio_postgresql.py`;
- `scripts/testar_exportacoes_admin_postgresql.py`.

Um novo ensaio deve:

1. confirmar explicitamente o banco permitido;
2. registrar contagens das tabelas publicas antes do teste;
3. criar tabelas temporarias ou usar transacao descartavel;
4. exercitar leitura, criacao, edicao e exclusao aplicaveis;
5. abrir pagina e APIs reais quando seguro;
6. descartar tudo ao final, inclusive depois de falha;
7. comparar novamente as tabelas publicas;
8. falhar se detectar alteracao na carga de homologacao.

Comandos usuais no computador do setor:

```powershell
$py = 'C:\Users\Geoprocessamento\AppData\Local\Python\pythoncore-3.14-64\python.exe'
& $py -m unittest discover -s tests
& $py scripts\verificar_postgresql.py --database endemias_teste
```

A descoberta de testes cria automaticamente uma copia temporaria do SQLite de
referencia antes de importar a aplicacao. Isso impede que rotinas de
compatibilidade e testes legados de escrita alterem o `endemias.db` congelado.

Nao presuma que a regressao continua no ultimo total registrado: o numero
cresce. Registre no documento da migracao o resultado atual de cada lote.

## Lote concluido: Boletim Mensal

O Boletim Mensal usa agora o destino dual em pagina, APIs, PDF e XLSX. A
manutencao do esquema ficou restrita ao SQLite, os indicadores leem as fontes
operacionais nos dois bancos e o fechamento grava ajustes e linhas manuais
com auditoria na mesma transacao. O ensaio isolado cobre permissao de leitura,
bloqueio de edicao para visualizador, persistencia por operador e preservacao
das tabelas publicas.

## Lote concluido: Mapa, Notificacoes e Relatorio por Servidor

O lote usa agora o destino dual nas paginas e APIs dos tres modulos. O Mapa
normaliza datas de visitas e Ovitrampas, calcula PE atrasado sem `julianday` e
usa filtros, `HAVING` e ordenacao alfanumerica portaveis. Notificacoes usa
buscas case-insensitive nos dois bancos, `string_agg` no historico PostgreSQL
e grava mudancas e auditoria na mesma transacao, com resposta retentavel para
conflitos. O Relatorio por Servidor possui expressoes especificas por backend
para duracao e semana, agregacoes portaveis e serializacao de datas e valores
decimais.

O ensaio integrado e:

```powershell
python scripts\testar_mapa_notificacoes_relatorio_postgresql.py `
  --database endemias_teste
```

Ele cria tabelas temporarias para todo o esquema, abre as rotas reais dos tres
modulos, exercita escrita e auditoria de Notificacoes e confirma que as `60`
tabelas publicas ficaram inalteradas. A regressao ampla teve `419` testes
aprovados e `5` ignorados.

## Ensaio integrado concluido

A copia consistente mais recente do SQLite foi carregada em
`endemias_migracao`: 59 tabelas, 154.217 registros, 34 identidades alinhadas e
zero divergencias de contagem/checksum ou constraints nao validadas. Os
comandos reproduziveis sao:

```powershell
python scripts\validar_migracao_integrada_postgresql.py `
  --database endemias_migracao `
  --confirmar-banco endemias_migracao
python scripts\testar_smoke_integrado_postgresql.py `
  --database endemias_migracao `
  --confirmar-banco endemias_migracao
python scripts\testar_concorrencia_postgresql.py `
  --database endemias_migracao `
  --confirmar-banco endemias_migracao
```

O smoke executa os 20 ensaios homologados. A concorrencia usa cinco sessoes,
uma tabela efemera e limpeza garantida; nao grava nas tabelas do sistema.
No banco final ja criado, o smoke exige uma terceira confirmacao:

```powershell
python scripts\testar_smoke_integrado_postgresql.py `
  --database endemias `
  --confirmar-banco endemias `
  --autorizar-banco-final "TESTAR BANCO FINAL SEM ALTERAR DADOS"
```

Em 03/08/2026, a carga preliminar de 154.240 registros foi substituida durante
a janela sem escritas pela carga final de 154.250 registros. As 59 tabelas
mantiveram contagens/checksums identicos, as 34 identidades ficaram alinhadas e
nao restou constraint sem validacao. Os 20 ensaios passaram e uma segunda
validacao depois do smoke confirmou novamente todo o conteudo.

## Restore e preparacao da conta SYSTEM

O restore real foi homologado somente em `endemias_teste`:

```powershell
python scripts\testar_restore_real_postgresql.py `
  --database endemias_teste `
  --confirmar-banco endemias_teste `
  --autorizar-restore "RESTAURAR BANCO DESCARTAVEL"
```

O comando preservou as 59 tabelas e 153.419 registros por checksum, incluindo
dump validado, SHA-256, backup `pre_restore` e `pg_restore` transacional.

Para configurar a conta `SYSTEM`, execute como administrador:

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\configurar_credencial_postgresql_system.ps1 `
  -Database endemias

powershell -ExecutionPolicy Bypass -File `
  scripts\configurar_inicializacao_automatica.ps1 `
  -Backend postgresql `
  -Database endemias `
  -ValidarSomente
```

A credencial vai para `C:\ProgramData\Endemias\pgpass.conf`, com ACL somente
para `SYSTEM` e Administradores. A senha e solicitada como `SecureString` e nao
entra nos argumentos, na tarefa ou no repositorio. O launcher define backend,
banco e `PGPASSFILE` apenas no processo filho.

Valide a autenticacao realmente sob a conta de servico, sem iniciar a
aplicacao, usando uma tarefa temporaria removida ao final:

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\testar_credencial_postgresql_system.ps1 `
  -Database endemias
```

A tarefa oficial foi registrada inicialmente sem iniciar com:

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\configurar_inicializacao_automatica.ps1 `
  -Backend postgresql `
  -Database endemias `
  -NaoIniciar
```

No estado conferido em 03/08/2026, a tarefa oficial estava ativa sob `SYSTEM`,
com backend `postgresql`, banco `endemias` e credencial protegida. A aplicacao
respondia HTTP 200. Depois de uma regressao legada tocar metadados do SQLite, o
arquivo de rollback foi restaurado atomicamente do backup consistente e
validado com `PRAGMA integrity_check`. Seu SHA-256 atual e
`0600F6A70072320BC7FDE270848535EF428341AA1F093997EE4940F85376F63F`.

## Protocolo de estabilizacao pos-virada

1. Monitorar logs, diagnostico e backups PostgreSQL nos primeiros dias.
2. Usar **Reiniciar Endemias** quando a tarefa precisar ser recuperada.
3. Nunca executar `iniciar.bat` para contornar uma falha: o marcador
   `C:\ProgramData\Endemias\postgresql.enabled` bloqueia o SQLite.
4. Preservar o SQLite e o backup `endemias_pre_virada_postgresql` sem altera-los.
5. Num rollback autorizado, interromper primeiro todas as escritas PostgreSQL e
   somente depois remover a tarefa/marcador.

As rotinas PostgreSQL de backup usam formato custom, `--no-password`, SHA-256
e validacao por `pg_restore --list`. A restauracao aceita somente dumps com os
metadados gerenciados completos, exige o nome exato do banco,
gera dump de seguranca e usa `--clean --if-exists --single-transaction
--exit-on-error`. Os caminhos podem ser configurados por `ENDEMIAS_PG_BIN`,
`ENDEMIAS_PG_DUMP` e `ENDEMIAS_PG_RESTORE`; credenciais continuam a cargo do
`pgpass`/libpq e nunca entram na linha de comando.

O lote `codex/automatizar-backups-postgresql` prepara duas tarefas sob
`SYSTEM`: dump diario as 02:00 com retencao de 30 arquivos e backup completo
semanal aos domingos as 03:00 com retencao de 8 ZIPs. O instalador e
`configurar_backup_postgresql.bat`; ele tambem pode criar e validar os primeiros
artefatos imediatamente. Antes do merge/revisao, as tarefas nao devem ser
instaladas no computador oficial.

O configurador protege as pastas de destino com ACL exclusiva para `SYSTEM` e
Administradores, inclusive por heranca nos novos artefatos. A verificacao
manual precisa ser executada numa sessao elevada.

O verificador abaixo nao conecta ao banco. Ele recalcula SHA-256, executa
`pg_restore --list` no dump, testa o ZIP e confere o hash do dump interno:

```powershell
Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command "cd C:\endemias; python scripts\verificar_backups_postgresql.py"'
```

## Operacao depois da migracao

- PostgreSQL `endemias` e o banco oficial.
- O `endemias.db` final e o backup da virada sao somente rollback; nao escrever.
- Nao copiar alteracoes do PostgreSQL de volta ao SQLite fora de um plano de
  rollback especifico e validado.
- O atalho comum abre a tarefa; se a conta local nao puder dispara-la, ele
  solicita **Reiniciar Endemias** com elevacao, sem fallback SQLite.
- Backups operacionais novos devem ser dumps PostgreSQL com metadados e SHA-256.

## Arquivos locais e Git

Normalmente ficam fora do Git:

- `endemias.db`, WAL e SHM;
- `.env`, `pgpass.conf` e chaves;
- `kobo_config.json`;
- anexos e uploads temporarios;
- backups;
- logs;
- planilhas e consolidados gerados.

Ao ver um arquivo sensivel como nao rastreado, nao o adicione. Confira
`.gitignore` e corrija a protecao se necessario.

## Ambientes e branches

- `master` e o sistema oficial.
- `origin/master` deve refletir os commits oficiais publicados.
- `revisao` e um worktree auxiliar, nao a versao de producao.
- A branch `revisao` possui alteracoes proprias para porta 5002; nao faca merge
  cego dela na `master`.
- No futuro, implementacoes grandes devem ir para `codex/nome-da-tarefa`, ser
  revisadas e so depois integradas.
- Enquanto o usuario nao declarar a mudanca definitiva do fluxo, confirme a
  branch atual e siga a instrucao mais recente dele.

## Fluxos de negocio que nao devem ser confundidos

- Ovitrampas/Leituras importadas: historico vindo do Conta Ovos por CSV.
- Ovitrampas/Laboratorio: espelho local preenchido pelo laboratorista antes do
  lancamento externo.
- Conta Ovos/SisPNCD: apoio operacional; ainda nao existe integracao privada
  ativa com a API Conta Ovos.
- Esporotricose/Visitas: dados importados do Kobo.
- Esporotricose/Doentes: cadastro clinico manual, receitas e estoque.
- Registro Geografico: banco interno atualizado a partir do trabalho de campo;
  a ideia de formulario Kobo para RG foi descartada.
- LARVAS Kobo e Lancamentos Laboratorio coexistem por contingencia.

## Funcionalidades futuras fora do escopo imediato

Nao misture estas ideias com o fechamento da migracao PostgreSQL:

- API privada do Conta Ovos;
- envio automatico de leituras ao Conta Ovos;
- diarios digitais offline para agentes em tablets;
- formularios proprios para substituir gradualmente o Kobo;
- PostgreSQL remoto/VPS;
- banco demonstrativo ficticio versionado.

Essas ideias foram discutidas, mas nao autorizam remover os fluxos atuais.

## Checklist da primeira resposta do novo agente

1. Ler `AGENTS.md` e `CONTEXTO_PARA_IA.md`.
2. Conferir `git status`, branch e ultimos commits.
3. Confirmar que PostgreSQL segue como producao e que o marcador esta ativo.
4. Confirmar que o SQLite congelado nao recebeu escritas.
5. Ler o final de `docs/POSTGRESQL_CAMADA_DUAL.md`.
6. Verificar o PostgreSQL sem escrever em tabelas publicas.
7. Retomar a estabilizacao, os backups automaticos e os diagnosticos, salvo
   nova orientacao.
8. Manter o usuario informado durante exploracao, edicao, testes e push.
