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
9. Preserve compatibilidade SQLite ate a virada oficial.
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

Nao presuma que a regressao continua no ultimo total registrado: o numero
cresce. Registre no documento da migracao o resultado atual de cada lote.

## Lote concluido: Boletim Mensal

O Boletim Mensal usa agora o destino dual em pagina, APIs, PDF e XLSX. A
manutencao do esquema ficou restrita ao SQLite, os indicadores leem as fontes
operacionais nos dois bancos e o fechamento grava ajustes e linhas manuais
com auditoria na mesma transacao. O ensaio isolado cobre permissao de leitura,
bloqueio de edicao para visualizador, persistencia por operador e preservacao
das tabelas publicas.

## Protocolo recomendado para o proximo lote

Para o **Mapa geral**:

1. Inspecionar `blueprints/mapa.py`, `templates/mapa.html`, testes e todas as
   fontes das duas APIs do modulo.
2. Inventariar SQL exclusivo do SQLite, agregacoes, datas, filtros e tabelas
   opcionais usadas nas camadas territoriais.
3. Passar pagina e APIs a usar o destino configurado pela camada dual.
4. Preservar as regras de quarteirao, localidade, visitas, focos, cobertura e
   Ovitrampas.
5. Normalizar datas e valores nativos antes da serializacao JSON.
6. Criar um ensaio PostgreSQL isolado com tabelas temporarias e abrir a pagina
   e as duas APIs reais.
7. Executar testes focados, regressao ampla e comparacao de esquema.
8. Atualizar os documentos PostgreSQL, fazer commit e push da branch.

## Operacao durante a migracao

- O setor pode continuar usando o sistema SQLite normalmente entre os lotes.
- Nao aplicar `ENDEMIAS_DB_BACKEND=postgresql` ao `iniciar.bat` oficial.
- Nao copiar automaticamente alteracoes feitas em `endemias_teste` de volta ao
  SQLite.
- Antes do ensaio final, gere uma copia nova do SQLite oficial; a carga antiga
  de homologacao deixa de representar dados adicionados durante a migracao.
- A virada exigira uma janela curta sem escritas para evitar divergencia.
- O SQLite congelado sera a opcao de rollback durante a estabilizacao.

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
3. Confirmar que SQLite segue como producao.
4. Ler o final de `docs/POSTGRESQL_CAMADA_DUAL.md`.
5. Verificar o PostgreSQL sem escrever em tabelas publicas.
6. Retomar o Mapa geral como proximo lote, salvo nova orientacao.
7. Manter o usuario informado durante exploracao, edicao, testes e push.
