# Estado atual e passagem de contexto do projeto

Atualizado em 24/08/2026. Este e o resumo operacional que uma nova conversa de
Codex ou Claude deve ler depois de `CONTEXTO_PARA_IA.md`. Datas, commits,
branches e servicos podem mudar; confirme sempre o estado vivo antes de agir.

## Papeis vigentes

- **Codex e o operador e implementador principal.** Investiga, implementa,
  testa, atualiza a documentacao, cria commit, faz push e, quando o usuario
  aprovar, integra em `master`.
- **Claude Code e o revisor independente somente-leitura.** Compara a branch
  do lote com `master`, procura erros e riscos, executa verificacoes seguras e
  devolve achados. Por padrao nao edita arquivos, nao altera dados, nao cria
  commits, nao faz push e nao integra na `master`.
- **Excecao controlada:** se o usuario pedir diretamente que Claude implemente
  uma correcao, ele pode faze-lo em uma branch `claude/nome-da-tarefa`, com
  testes, commit e push. Nessa situacao ele deixa de ser revisor daquele diff;
  Codex nao deve editar a mesma branch/arquivos simultaneamente e so revisa ou
  integra se o usuario solicitar. A excecao termina ao concluir a tarefa.
- O usuario decide regras de negocio, testes funcionais, alteracoes em dados
  reais, pilotos da API e reinicios do sistema oficial.

Consulte `docs/GUIA_TRABALHO_MULTIAGENTE.md` para o passo a passo e os prompts
de inicio. Uma mudanca solicitada sempre termina em commit e push.

## Produção e protecoes indispensaveis

- O sistema oficial esta em `C:\endemias`, branch `master`, porta 5000.
- PostgreSQL `endemias` e a base oficial desde 03/08/2026, executada pela
  tarefa Windows sob `SYSTEM`. O marcador
  `C:\ProgramData\Endemias\postgresql.enabled` bloqueia o fallback acidental
  para SQLite.
- `C:\endemias\endemias.db` e apenas o snapshot de rollback. Esta congelado e
  nao pode receber escritas nem ser aberto em paralelo com PostgreSQL. O hash
  preservado depois da restauracao e
  `0600F6A70072320BC7FDE270848535EF428341AA1F093997EE4940F85376F63F`.
- Credenciais PostgreSQL e Conta Ovos ficam fora do Git, protegidas por ACL
  para `SYSTEM`/Administradores. Nunca imprimir, copiar ou versionar senhas,
  chaves, bancos, anexos, logs ou backups.
- Testes e ensaios nunca podem alterar tabelas publicas de `endemias`. Para
  PostgreSQL use `endemias_teste`, tabelas temporarias e as confirmacoes dos
  scripts. Para a suite Python use obrigatoriamente:

```powershell
& $py -m unittest discover -s tests -t .
```

  O `-t .` importa `tests` como pacote e isola automaticamente uma copia
  temporaria do SQLite. Nunca rode um arquivo de teste diretamente nem omita
  essa opcao.
- A ultima regressao ampla registrada terminou com `632` testes em `OK` e `5`
  ignorados, preservando o hash do SQLite congelado. Reexecute a regressao
  aplicavel depois de qualquer lote; a contagem pode crescer.
- Backups automaticos PostgreSQL estao instalados sob `SYSTEM`: dump diario
  (02:00, retencao 30) e backup completo semanal (domingo, 03:00, retencao 8).
  Em 24/08 o verificador encontrou dump diario e backup completo validos. Em
  conta sem privilegio, acesso negado a `D:\BackupsEndemias` ou tarefa invisivel
  de `SYSTEM` significa **desconhecido**, nao falha confirmada; confira em
  console elevado antes de diagnosticar incidente.

## Estado confirmado antes desta atualizacao

O ponto de partida desta documentacao foi `master`/`origin/master` limpas em
`b51931e` (`fix: exibir cargo cadastrado no relatorio`), versao `1.20.0`.
Verifique o valor atual com:

```powershell
git status --short --branch
git log -12 --oneline
git worktree list
```

Worktrees conhecidos nesse ponto:

- `C:\endemias`: `master`, producao.
- `C:\endemias-revisao`: `revisao`, ambiente do Claude, porta 5002; nunca
  mesclar essa branch inteira na `master`.
- `C:\endemias-codex`: `codex/enviar-leituras-conta-ovos`, trabalho futuro
  ainda fora da `master`.
- `C:\endemias-palhetas` e `C:\endemias-claude`: worktrees antigos; confira se
  estao limpos e sem trabalho exclusivo antes de remove-los. Nao apague nada
  por suposicao.

## O que ja esta concluido

### PostgreSQL

A migracao funcional e operacional esta concluida: esquema, dados finais,
ensaios, backup/restauracao, tarefa de servico e todos os modulos da aplicacao
foram homologados no adaptador dual. SQLite foi mantido somente para testes e
rollback controlado. Os detalhes historicos estao em
`docs/MIGRACAO_POSTGRESQL.md`, `docs/POSTGRESQL_CAMADA_DUAL.md` e nos guias de
carga/esquema.

Depois da virada, a aplicacao voltou corretamente apos a atualizacao/reinicio
do Windows de 21/08; a verificacao de 24/08 encontrou PostgreSQL, servidor
Endemias e backups operacionais. Nao ha uma tarefa aberta de migracao do banco.

### Conta Ovos

- A central `Conta Ovos` e **somente leitura local**: as telas nunca chamam a
  API em tempo real. O espelho local e a base da interface; a API e a fonte de
  verdade para os campos que ela administra.
- As contagens GET de 2026 foram reconciliadas em producao: 5.383 registros
  (1.452 inseridos, 3.931 atualizados). Uma repeticao de 45 dias retornou 1.108
  itens sem mudanca, confirmando idempotencia. CSV/importacoes manuais seguem
  como contingencia, sem segundo historico paralelo.
- A central organiza `Visao geral`, `Ovitrampas` (Contagens, Monitoramento,
  Cadastro remoto, Mapa e Sincronizacao/divergencias), com EDLs e Quarteiroes/
  acoes reservados. A pagina operacional `/ovitrampas` continua necessaria e
  nao deve ser removida.
- O espelho do cadastro remoto existe (migracao `0005` aplicada e ensaio
  aprovado), mas a **primeira sincronizacao real desse cadastro ainda nao foi
  executada**. Ate ela, Cadastro remoto, Mapa e parte das divergencias podem
  ficar vazios; isso nao e defeito da interface.
- Nenhum POST da API Conta Ovos esta em `master`. A branch
  `codex/enviar-leituras-conta-ovos` prepara envio unitario supervisionado de
  `/postcounting`, mas ainda precisa ser atualizada sobre a `master`, ensaiada
  em `endemias_teste`, revisada e submetida a um piloto humano antes de ser
  considerada para integracao. Nao ha envio em lote e um resultado incerto
  jamais e reenviado automaticamente.

As regras de fonte de verdade e a arquitetura da tela estao em
`docs/CONTA_OVOS_INTERFACE.md`; detalhes da API e dos lotes em
`docs/CONTA_OVOS_API.md`.

## Pendencia concreta e proxima ordem recomendada

1. **Em revisao: mapeamento do PE-0045 para visitas Kobo:** a branch
   `codex/adicionar-pe-0045-kobo` registra aliases qualificados para
   **Borracharia Garagem Oculta** (Graziela, Rua Campos de Minas, 753,
   quarteirao 1336) e desativa aliases automaticos ambiguos. Quando dois PEs
   ativos compartilham a mesma rua/localidade, uma visita com a rua isolada
   fica sem vinculo para triagem; ela nunca e atribuida por ordem de cadastro.
   A deteccao tambem agrupa as variantes cadastrais conhecidas `Rua Campo de
   Minas` e `Rua Campos de Minas`, sem alterar nenhum dos dois cadastros.
   O identificador Kobo esperado e
   `RUA CAMPOS DE MINAS - BORRACHARIA GARAGEM OCULTA`.
   Esta branch **nao altera nem publica** o XLSForm no Kobo: essa atualizacao
   externa continua manual, depois da revisao e da autorizacao de integracao.
   Antes de integrar, o operador deve confirmar no PostgreSQL de producao que
   o cadastro `PE-0045` existe e esta ativo; sem esse cadastro, a semeadura do
   alias e ignorada para preservar a chave estrangeira. A regressao desta
   revisao terminou com 640 testes `OK` e 5 ignorados; o ensaio PostgreSQL em
   `endemias_teste` usou tabelas temporarias e preservou as tabelas publicas.
2. **Concluida: correcao de Pontos Estrategicos:** a branch
   `codex/corrigir-datas-pe`, aprovada pelo Claude e autorizada pelo usuario,
   normaliza `None`, campos vazios, espacos, `NaT` textual e `pandas.NaT` para
   `NULL` antes de persistir. Data preenchida mas invalida retorna HTTP 400 e
   a tela mostra a mensagem clara, sem mascarar excecoes de banco, auditoria,
   permissao ou concorrencia. Criacao e edicao foram cobertas em SQLite e no
   ensaio seguro PostgreSQL com tabelas temporarias em `endemias_teste`; a
   regressao posterior a correcao da revisao terminou com 639 testes `OK` e 5
   ignorados.
   As edicoes dos PEs 1 e 24 que falharam em 13 e 17/08 nao foram gravadas pela
   transacao original e continuam precisando ser refeitas manualmente depois da
   integracao.
3. **Consolidar a leitura Conta Ovos:** quando o usuario autorizar, executar
   primeiro o sincronizador supervisionado do cadastro remoto e conferir as
   divergencias na central. Novos dominios de consulta (EDLs e Quarteiroes/
   acoes) devem vir antes de qualquer nova escrita remota, cada um com GET,
   schema/espelho, ensaio e tela local.
4. **Escrita remota somente mais adiante:** decidir um piloto unitario de
   leitura depois de revalidar a branch preparada. Para TBO `/postaction`,
   inventariar antes todos os efeitos colaterais documentados (quarteirao,
   coordenadas, tipo de imovel, larvicida e semana); nao transformar o envio
   unitario em lote por um simples laco.
5. **Fora deste eixo:** formulario/OCR de Registro Geografico, diarios offline
   e substituicoes graduais do Kobo sao projetos separados. GeoJSON + Registro
   Geografico permanecem a fonte territorial; Conta Ovos nao os sobrescreve.

Antes de iniciar qualquer uma delas, confira o pedido mais recente do usuario.
Ele pode mudar a prioridade, autorizar operacao real ou pedir apenas analise.

## Fechamento de cada lote

Um lote esta pronto somente com escopo claro, dados reais preservados, testes
focados e regressao proporcional, documentacao atualizada, commit e push. Para
lotes de risco (dados, PostgreSQL, autenticacao, backups e Conta Ovos), Codex
publica primeiro uma branch `codex/nome-do-lote`; Claude revisa somente em
leitura; Codex corrige achados validos; o usuario testa e autoriza a integracao
final.
