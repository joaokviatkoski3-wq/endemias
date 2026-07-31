# Contexto para continuidade do projeto

Atualizado em 31/07/2026. Este arquivo e o ponto de entrada para qualquer IA
que assumir o projeto em outra conta ou conversa.

## Projeto e forma de trabalho

- Sistema local Flask para o Setor de Endemias de Almirante Tamandare-PR.
- Repositorio oficial: `joaokviatkoski3-wq/endemias`.
- Branch oficial: `master`.
- Diretorio oficial no computador do setor: `C:\endemias`.
- Versao atual: `1.12.1`, definida em `app_core/version.py`.
- O usuario exige commit e push ao final de toda modificacao solicitada.
- Nao reverta alteracoes do usuario nem dados reais.
- Use `apply_patch` para edicoes manuais.
- SQLite ainda e a base oficial de producao ate a virada final.
- `iniciar.bat` oficial deve continuar usando SQLite ate a migracao completa.
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

## Estado da migracao PostgreSQL

A migracao e gradual e dual: cada modulo convertido deve continuar funcionando
em SQLite e PostgreSQL. A cobertura funcional esta em aproximadamente 90%.

Bancos conhecidos:

- `endemias.db`: fonte oficial enquanto a migracao estiver em andamento;
- `endemias_teste`: esquema, carga de homologacao e ensaios descartaveis;
- `endemias_migracao`: reservado para o ensaio completo antes da virada.

Infraestrutura ja validada no PostgreSQL:

- 59/59 tabelas;
- 691/691 colunas;
- 59/59 chaves primarias;
- 29/29 restricoes unicas;
- 55/55 chaves estrangeiras;
- 32/32 checks;
- 34/34 identidades;
- 105/105 indices.

A ultima regressao ampla registrada teve 395 testes aprovados e 5 ignorados.
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

Commits mais recentes da migracao:

```text
4de3738 feat: migrar agenda e meteorologia para postgres
bfa38c8 feat: migrar importacao kobo para postgres
409be89 feat: migrar registro geografico para postgres
6a3b6e2 feat: migrar conta ovos e sispncd para postgres
b5ff38b feat: concluir migracao de ovitrampas para postgres
```

## Proxima tarefa recomendada

Migrar **Boletim Mensal** para a camada dual, incluindo:

- indicadores automaticos e itens manuais;
- consulta, edicao e persistencia do fechamento mensal;
- geracao do PDF e exportacao XLSX;
- leitura das fontes operacionais nos dois bancos;
- auditoria e permissoes;
- teste PostgreSQL isolado em tabelas temporarias;
- garantia de que tabelas publicas de `endemias_teste` nao sejam alteradas.

Depois, prosseguir com:

1. mapa geral fora do Registro Geografico;
2. Notificacoes;
3. Relatorio por Servidor;
4. exportacoes e consolidados;
5. Central do Sistema, diagnosticos e rotinas administrativas;
6. auditoria final de SQL exclusivo do SQLite.

## O que falta para abandonar o SQLite

Mesmo apos os modulos restantes, ainda sera necessario:

1. Implementar backup PostgreSQL com `pg_dump`.
2. Implementar restauracao com `pg_restore`.
3. Adaptar o botao de backup da Central do Sistema.
4. Configurar credenciais PostgreSQL protegidas para a conta Windows `SYSTEM`.
5. Configurar o servico automatico para iniciar com PostgreSQL.
6. Testar concorrencia realista com 4 ou 5 usuarios.
7. Buscar `PRAGMA`, `sqlite_master`, `executescript`, `lastrowid`,
   `INSERT OR IGNORE/REPLACE`, `GROUP_CONCAT`, `COLLATE NOCASE` e funcoes de
   data exclusivas do SQLite.
8. Ensaiar com copia recente do SQLite em `endemias_migracao`.
9. Comparar contagens, checksums, FKs e sequencias de identidade.
10. Executar smoke CRUD de toda a aplicacao em PostgreSQL.
11. Fazer congelamento curto de escrita, carga final e validacao.
12. Somente entao definir `ENDEMIAS_DB_BACKEND=postgresql` no servidor oficial.
13. Preservar o `endemias.db` final congelado como rollback; nao apagar.

## Regras para testes PostgreSQL

- Nunca use dados reais em operacoes destrutivas.
- Prefira tabelas temporarias e transacoes revertidas.
- Os scripts `scripts/testar_*_postgresql.py` sao o padrao existente.
- O Python usado neste computador e:
  `C:\Users\Geoprocessamento\AppData\Local\Python\pythoncore-3.14-64\python.exe`.
- PostgreSQL local usa normalmente `127.0.0.1:5432`, usuario `endemias_app` e
  autenticacao pelo `pgpass`; nunca registre a senha no repositorio.
- Para banco diferente do padrao, use a confirmacao explicita exigida pelos
  scripts.
- Depois do teste focado, execute a regressao ampla e a comparacao do esquema.

## Ambiente de revisao

Existe um worktree separado em `C:\endemias-revisao`, branch `revisao`,
publicada em `origin/revisao`. Ele foi preparado para o Claude atuar como
revisor e possui `CLAUDE.md` proprio.

- `C:\endemias` / `master`: sistema oficial, porta 5000;
- `C:\endemias-revisao` / `revisao`: revisao, porta 5002 e SQLite local vazio.

Os commits `eae9b37` e `75c8f04` pertencem apenas a `revisao`; nao estao na
`master`. A configuracao PostgreSQL isolada da revisao ainda devera ser feita
apos a migracao funcional terminar.

Fluxo futuro pretendido:

1. Codex implementa em `codex/nome-da-tarefa` e faz push.
2. Claude revisa o diff contra `master`, sem alterar por padrao.
3. Codex corrige os achados na branch da tarefa.
4. Usuario testa em ambiente isolado.
5. So depois ocorre merge e push para `master`.

Enquanto esse fluxo ainda nao estiver oficialmente adotado, siga a orientacao
expressa do usuario sobre trabalhar diretamente na `master` e sempre fazer
push.

## Decisoes futuras ja discutidas

- Foi discutida a solicitacao da API privada do Conta Ovos como possibilidade
  futura; nao ha confirmacao registrada de que a chave ja tenha sido recebida.
- A API pode substituir importacoes CSV e marcacoes manuais, mas a integracao
  ainda nao foi implementada nem foi recebida chave.
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
