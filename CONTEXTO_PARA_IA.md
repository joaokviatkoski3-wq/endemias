# Contexto para continuidade do projeto

Atualizado em 24/08/2026. Este arquivo e o ponto de entrada para qualquer IA
que assumir o projeto em outra conta ou conversa.

## Projeto e forma de trabalho

- Sistema local Flask para o Setor de Endemias de Almirante Tamandare-PR.
- Repositorio oficial: `joaokviatkoski3-wq/endemias`.
- Branch oficial: `master`.
- Diretorio oficial no computador do setor: `C:\endemias`.
- Versao atual: `1.24.1` nesta branch, definida em `app_core/version.py`.
- O usuario exige commit e push ao final de toda modificacao solicitada.
- Nao reverta alteracoes do usuario nem dados reais.
- Use `apply_patch` para edicoes manuais.
- PostgreSQL e a base oficial de producao desde 03/08/2026.
- `endemias.db` esta congelado como rollback e nao pode receber novas escritas.
- `iniciar.bat` recusa o modo SQLite quando o marcador operacional PostgreSQL
  esta instalado.
- Credenciais, bancos, anexos, backups e tokens nao podem ser versionados.

Antes de trabalhar, execute:

```powershell
git status --short --branch
git log -8 --oneline
```

Leia tambem:

- `AGENTS.md`;
- `docs/GUIA_CONTINUIDADE_TECNICA.md`;
- `docs/GUIA_TRABALHO_MULTIAGENTE.md`;
- `docs/MIGRACAO_POSTGRESQL.md`;
- `docs/POSTGRESQL_CAMADA_DUAL.md`;
- `docs/POSTGRESQL_SCHEMA_INICIAL.md`;
- `docs/POSTGRESQL_CARGA_TESTE.md`.
- `docs/POSTGRESQL_AUDITORIA_SQL_FINAL.md`.
- `docs/ESTADO_ATUAL_PROJETO.md` (estado operacional atual, papeis e
  prioridades; leia antes de assumir qualquer lote).

O registro em `docs/ESTADO_ATUAL_PROJETO.md` prevalece sobre secoes antigas
deste arquivo que descrevem a estabilizacao de ferias ou uma proxima etapa ja
executada. Os documentos historicos nao devem ser apagados: eles explicam como
a migracao foi feita e como recuperar ou auditar sua evidencia.

## Estado da migracao PostgreSQL

A migracao funcional e operacional foi concluida. A camada continua dual para
preservar a possibilidade de rollback controlado e os testes SQLite, mas o
backend oficial e PostgreSQL.

Bancos conhecidos:

- `endemias.db`: snapshot final congelado para rollback, somente leitura;
- `endemias_teste`: esquema, carga de homologacao e ensaios descartaveis;
- `endemias_migracao`: carga recente e ensaio completo antes da virada;
- `endemias`: banco PostgreSQL oficial de producao.

Infraestrutura ja validada no PostgreSQL:

- 59/59 tabelas;
- 691/691 colunas;
- 59/59 chaves primarias;
- 29/29 restricoes unicas;
- 55/55 chaves estrangeiras;
- 32/32 checks;
- 34/34 identidades;
- 105/105 indices.

A regressao ampla executada na `master` depois da integracao do ambiente de
teste padrao terminou com `652` testes em `OK` e `5` ignorados, usando uma copia
temporaria isolada de `C:\endemias\endemias.db`; o hash do SQLite oficial
permaneceu inalterado
(`0600F6A70072320BC7FDE270848535EF428341AA1F093997EE4940F85376F63F`).
Ela cria uma copia SQLite temporaria antes de importar a aplicacao; nunca rode
testes contra o `endemias.db` congelado.
Confirme novamente depois de novos lotes. Existe um `ResourceWarning` antigo de
conexoes SQLite em testes de Ovitrampas; nao confundir automaticamente com uma
regressao nova.

### Modulos homologados nos dois bancos

- adaptador dual, esquema, copia e validacao de dados;
- autenticacao, auditoria e permissoes;
- Gestao de Usuarios e Controle de Pessoal;
- Historico de Importacoes e Importacao Kobo completa;
- Recolhimentos e Amostras de Animais;
- BRI e Pontos Estrategicos;
- Visitas de Arboviroses;
- Dashboard, Producao Operacional e Resultados Laboratoriais;
- Esporotricose: visitas, animais, buscas, doentes, receitas, entregas, estoque
  e metadados de anexos;
- Ovitrampas: cadastro, historico, leituras, ocorrencias, monitoramento,
  diarios, calendario e laboratorio;
- Conta Ovos/SisPNCD;
- Registro Geografico completo;
- Agenda, Pagina Inicial e Meteorologia;
- Acoes e Atendimentos do Setor: CRUD, filtros, servidores, anexos, galeria,
  relatorio tecnico, auditoria e permissoes.
- Boletim Mensal: indicadores automaticos, ajustes e itens manuais, fechamento,
  PDF, XLSX, auditoria e permissoes.
- Mapa geral: visitas, focos, Esporotricose, Pontos Estrategicos e camada de
  Ovitrampas, incluindo filtros, datas e ordenacao alfanumerica.
- Notificacoes: pagina, filtros, detalhe, historico, atualizacao de status,
  impressoes HTML/DOCX e auditoria atomica.
- Relatorio por Servidor: relatorio individual e consolidado do setor,
  duracoes, evolucao semanal, producao operacional, laboratorio,
  Esporotricose, Ovitrampas e Registro Geografico.
- Exportacoes e consolidados: XLSX de visitas, notificacoes e laboratorio,
  alem dos consolidados PE, TB, TBO e PVE sob demanda.
- Central do Sistema: status do backend, contagens e diagnostico rapido/completo.
  Backup, restauracao e backup completo usam `pg_dump`/`pg_restore` quando o
  PostgreSQL esta ativo; o DBML continua exclusivo do SQLite.
- Saude dos backups: `app_core/backup_health.py` avalia dump diario e backup
  completo em modo rapido ou completo, e `app_core/backup_tasks.py` le o estado
  das tarefas agendadas sem nunca altera-las. A Central e o diagnostico
  administrativo consomem essa camada.

Commits mais recentes da migracao:

```text
6bab11d feat: configurar banco final postgres
8fe6eed feat: preparar operacao postgres no windows
8ecbed8 test: validar ensaio integrado postgres
7b6095f fix: exigir metadados no restore postgres
87a0e2e feat: concluir auditoria e backups postgres
3b14422 fix: corrigir diagnosticos postgresql da central
2d175f9 docs: agrupar modulos nas revisoes multiagente
ac23b99 fix: tratar concorrencia no boletim mensal
44a87f2 feat: migrar boletim mensal para postgres
7972bde fix: corrigir achados da revisao de acoes
64930d1 feat: migrar acoes do setor para postgres
4de3738 feat: migrar agenda e meteorologia para postgres
bfa38c8 feat: migrar importacao kobo para postgres
409be89 feat: migrar registro geografico para postgres
6a3b6e2 feat: migrar conta ovos e sispncd para postgres
b5ff38b feat: concluir migracao de ovitrampas para postgres
```

## Backups automaticos em operacao

O lote `codex/automatizar-backups-postgresql` foi revisado, aprovado e
integrado a `master` no commit `c97a299`. Segundo o administrador do setor:

- as tarefas `Endemias - Backup PostgreSQL Diario` (02:00, retencao 30) e
  `Endemias - Backup Completo PostgreSQL` (domingo 03:00, retencao 8) foram
  instaladas sob a conta `SYSTEM`;
- o primeiro dump e o primeiro backup completo foram criados e aprovados pelo
  verificador `scripts/verificar_backups_postgresql.py`.

Cuidado ao conferir esse estado: uma sessao sem privilegio administrativo nao
enxerga tarefas registradas para `SYSTEM` e recebe "tarefa nao encontrada" tanto
para tarefa ausente quanto para tarefa apenas invisivel. As pastas em
`D:\BackupsEndemias` tambem tem ACL exclusiva de `SYSTEM` e Administradores e
respondem "acesso negado" para contas comuns. Confirme sempre pelo servico ou
por um console elevado antes de concluir que um backup falhou.

Desde `claude/backup-health-acl-ferias`, a pasta inacessivel deixou de virar
alarme falso: `app_core/backup_health.py` distingue "pasta protegida por ACL"
de "pasta sem backups" e devolve o nivel `desconhecido` com o motivo, em vez do
antigo `erro` "Nenhum dump PostgreSQL foi encontrado". A causa era o
`Path.glob`, que engole o erro de permissao e devolve lista vazia. Uma pasta
legivel e realmente vazia continua sendo `erro`.

## Estado pos-ferias e prioridades vigentes

O congelamento operacional de ferias terminou. A `master` continua em producao
com PostgreSQL e o SQLite congelado segue somente como rollback controlado. A
tag `operacao-ferias-2026-08-05` e um marco historico, nao uma instrucao para
manter o desenvolvimento bloqueado.

O estado efetivamente atual, as pendencias encontradas depois do retorno, o
status da central Conta Ovos e a proxima ordem recomendada estao concentrados
em `docs/ESTADO_ATUAL_PROJETO.md`. Em particular, nenhum POST Conta Ovos esta
habilitado na `master`; a prioridade imediata registrada e a correcao segura de
datas `NaT` em Pontos Estrategicos.

Qualquer rollback continua sendo decisao do administrador: primeiro interrompa
novas escritas PostgreSQL e so depois remova tarefa e marcador. Nunca abra o
SQLite congelado em paralelo.

## Virada concluida

Em 03/08/2026:

1. o servidor SQLite foi parado e a porta 5000 ficou fechada;
2. o `endemias.db` foi congelado com SHA-256
   `7AE434197BE4500B9BDCDB2A32B06C27FA3F825977B6AB9DD7663A0051061A90`;
3. foi criado backup consistente e validado em
   `D:\BackupsEndemias\backups_banco`, prefixo
   `endemias_pre_virada_postgresql`;
4. o banco `endemias` recebeu 59 tabelas e 154.250 registros;
5. contagens/checksums, zero constraints pendentes, 34 identidades e os 20
   smokes foram validados, inclusive nova validacao depois do smoke;
6. a tarefa `Endemias - Servidor` foi registrada para PostgreSQL sob `SYSTEM`;
7. a aplicacao foi iniciada pela tarefa, respondeu HTTP 200 e o hash do SQLite
   permaneceu inalterado durante a carga e os smokes PostgreSQL;
8. uma regressao legada executada depois da virada revelou escritas de
   manutencao no SQLite padrao. O PostgreSQL nao foi afetado. O `endemias.db`
   foi restaurado atomicamente do backup consistente, passou em
   `PRAGMA integrity_check` e agora tem SHA-256
   `0600F6A70072320BC7FDE270848535EF428341AA1F093997EE4940F85376F63F`.
   A suite passou a isolar automaticamente o banco em uma copia temporaria.

Concluidos em `endemias_migracao`: snapshot recente, 59 tabelas e 154.217
registros com contagens/checksums identicos, 34 identidades alinhadas, zero
constraints nao validadas, smoke dos 20 ensaios de modulos e concorrencia com
cinco sessoes. Os testes temporarios nao mudaram as tabelas publicas.
O restore real foi homologado em `endemias_teste`, preservando por checksum as
59 tabelas e 153.419 registros. A carga preliminar de 154.240 registros foi
substituida pela carga final de 154.250 registros descrita acima. A credencial
protegida permanece em `C:\ProgramData\Endemias\pgpass.conf`, com ACL exclusiva
para `SYSTEM` e Administradores. O marcador
`C:\ProgramData\Endemias\postgresql.enabled` impede fallback acidental para
SQLite.

## Regras para testes PostgreSQL

- Nunca use dados reais em operacoes destrutivas.
- Nunca execute ensaios destrutivos no banco final `endemias`.
- Prefira tabelas temporarias e transacoes revertidas.
- Os scripts `scripts/testar_*_postgresql.py` sao o padrao existente.
- O Python usado neste computador e:
  `C:\Users\Geoprocessamento\AppData\Local\Python\pythoncore-3.14-64\python.exe`.
- PostgreSQL local usa normalmente `127.0.0.1:5432`, usuario `endemias_app` e
  autenticacao pelo `pgpass`; nunca registre a senha no repositorio.
- Para banco diferente do padrao, use a confirmacao explicita exigida pelos
  scripts.
- Depois do teste focado, execute a regressao ampla e a comparacao do esquema.

## Modelo operacional vigente

Existe um worktree separado em `C:\endemias-revisao`, branch `revisao`,
publicada em `origin/revisao`. Ele e um ambiente auxiliar historico e nao faz
parte obrigatoria do fluxo de entrega.

- `C:\endemias` / `master`: sistema oficial, porta 5000;
- `C:\endemias-revisao` / `revisao`: revisao, porta 5002 e SQLite local vazio.

Nao faca merge cego da branch `revisao`: ela pode conter configuracao exclusiva
do ambiente auxiliar. O iniciador padrao de worktrees passou a ser
`testar.bat`, integrado na `master` em 27/08/2026.

Fluxo vigente:

1. Codex confirma o estado e implementa a solicitacao em escopo seguro.
2. Codex executa testes focados, regressao proporcional e ensaios isolados.
3. Codex atualiza a documentacao, cria commit e faz push.
4. Quando a mudanca estiver pronta e o pedido autorizar a entrega, Codex pode
   integrar e publicar a `master` sem revisao externa obrigatoria.
5. Se o usuario identificar erro, Codex investiga e corrige ou prepara rollback
   seguro; nunca reverta dados reais mecanicamente.

Claude participa somente em intervencoes esporadicas solicitadas pelo usuario.
Essa participacao nao muda Codex como operador principal nem cria uma aprovacao
obrigatoria para integracao.

## Decisoes futuras ja discutidas

- A credencial privada Conta Ovos foi recebida, protegida para `SYSTEM` e
  Administradores e validada em uma consulta supervisionada somente leitura.
- A sincronizacao GET de contagens esta homologada; importacoes CSV e marcacoes
  manuais continuam como fallback. A central Conta Ovos e somente leitura do
  espelho local. Cadastro remoto possui schema e ensaio aprovados, mas a
  primeira sincronizacao real ainda depende de autorizacao operacional.
  Nenhum POST remoto esta habilitado na `master`.
- O plano futuro inclui diarios digitais offline em tablets, com revisao de
  alteracoes cadastrais e sincronizacao posterior; isso nao faz parte da
  migracao PostgreSQL atual.
- O Kobo continua operacional. Nao retire importacoes ou formularios atuais
  antes de uma substituicao homologada.

## Criterio de conclusao de cada lote

Um lote so esta concluido quando:

- funciona em SQLite e PostgreSQL;
- preserva regras, permissoes e auditoria;
- possui testes focados de leitura e escrita;
- nao altera dados publicos durante a homologacao;
- passa pela regressao aplicavel;
- atualiza a documentacao da migracao;
- termina com commit e push bem-sucedidos.
