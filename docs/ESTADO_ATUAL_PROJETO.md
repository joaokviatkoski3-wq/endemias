# Estado atual e passagem de contexto do projeto

Atualizado em 27/08/2026. Este e o resumo operacional que uma nova conversa do
Codex deve ler depois de `CONTEXTO_PARA_IA.md`. Datas, commits,
branches e servicos podem mudar; confirme sempre o estado vivo antes de agir.

## Papeis vigentes

- **Codex e o operador unico e principal.** Investiga, implementa, testa,
  atualiza a documentacao, cria commits, faz push e pode integrar mudancas
  solicitadas na `master` depois das validacoes aplicaveis, sem revisao externa
  obrigatoria.
- **Claude Code participa apenas esporadicamente**, quando o usuario pedir uma
  revisao, investigacao ou implementacao delimitada. Sua ausencia nao bloqueia
  entrega. Se houver escrita por outro agente, use branch propria e nao edite
  simultaneamente os mesmos arquivos.
- Se o usuario identificar um erro depois da integracao, Codex investiga e
  corrige ou prepara rollback seguro. Isso nao autoriza rollback mecanico de
  dados reais.
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
- A ultima regressao ampla registrada terminou com `652` testes em `OK` e `5`
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
- `C:\endemias-revisao`: `revisao`, ambiente auxiliar historico; nunca
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

### Ambiente de teste padrao integrado

A branch `codex/ambiente-de-teste-padrao`, criada a partir de `f64c866`, foi
integrada na `master` pelo merge `b42f688`. Ela porta para a aplicacao a
configuracao segura de porta que antes existia somente na branch `revisao` e
acrescenta `testar.bat` na raiz.

O comportamento proposto e:

- `app.py` usa `ENDEMIAS_PORT` quando ela representa uma porta de 1 a 65535;
  valor ausente, invalido ou fora da faixa conserva o padrao `5000`;
- `testar.bat` usa sempre `5002`, recusa antes de qualquer outra acao quando
  esta em `C:\endemias` e avisa claramente quando outro ambiente ja ocupa a
  porta. Uma segunda barreira independente compara a identidade do banco de
  teste com `C:\endemias\endemias.db`, cobrindo tambem caminho curto, UNC,
  juncao, link simbolico e hard link; se a comparacao falhar, o batch recusa a
  inicializacao em vez de prosseguir;
- banco, anexos, uploads, log, chave, configuracao Kobo e backups apontam para
  o proprio worktree. Na primeira execucao, o usuario escolhe explicitamente
  entre um banco vazio e uma copia local do SQLite congelado;
- um arquivo SQLite existente so e aceito quando contem o esquema minimo do
  sistema. Banco vazio, corrompido ou incompleto e arquivado no proprio
  worktree antes de voltar a escolha de uma massa valida;
- a copia opcional e identificada como dado real de saude, permanece restrita
  ao worktree e deve ser apagada junto com ele. A origem
  `C:\endemias\endemias.db` e somente lida pelo comando de copia;
- `ENDEMIAS_AMBIENTE=teste` exibe em todas as telas, inclusive login, uma faixa
  fixa informando que os dados nao sao oficiais. Como defesa adicional, uma
  porta diferente de `5000` tambem ativa a faixa, mesmo sem a variavel ou com
  `producao` declarada. A faixa e escondida por CSS de impressao;
- `iniciar.bat` nao foi alterado: na pasta oficial, o marcador PostgreSQL
  continua bloqueando qualquer inicializacao SQLite.
- `parar_test.bat` encerra com dois cliques somente o servidor Python `app.py`
  na porta de teste `5002`; recusa outros programas e bloqueia explicitamente
  qualquer tentativa de atuar na porta oficial `5000`.

O smoke isolado respondeu HTTP 200 em `localhost:5002`, mostrou a faixa e fez
uma segunda execucao do batch recusar a porta ocupada com mensagem clara. Os 11
testes de scripts de inicializacao, os 268 testes de seguranca e os 4 testes da
identidade/esquema do banco passaram; a regressao completa terminou com 652
testes aprovados e 5 ignorados. O hash do
SQLite oficial permaneceu
`0600F6A70072320BC7FDE270848535EF428341AA1F093997EE4940F85376F63F`.

O sistema permanece em `1.20.0`, pois o lote nao muda a execucao oficial: a porta
padrao continua `5000`, `iniciar.bat` permanece intacto e a faixa nao aparece
na configuracao de producao normal.

Em 28/08/2026, o usuario cancelou integralmente o lote experimental do mapa de
bloqueio da Esporotricose. A branch, o worktree e a migracao proposta `0006`
foram descartados sem entrar na `master` e sem aplicacao em nenhum banco. O
sistema conserva o comportamento anterior a esse plano; o tema deixa de ser
prioridade e nao deve ser retomado sem um novo pedido expresso.

### Correcao importacao via API de Amostra de Animais

Na branch `trabalho-deepseek` foi corrigido o bug de importacao via API do
formulario `AMOSTRA_ANIMAIS`: a contagem de "novos" em "Ver pendencias" nunca
zerava apos a importacao. Causa: `kobo_api._extra_row` gerava o workbook sem a
coluna `Motivo da visita`, fazendo `amostras_animais.is_new_format` classificar o
arquivo como formato `legada`, o que descartava o `kobo_uuid` (registros eram
gravados como `legado` e sem vinculo Kobo, por isso a deduplicacao nunca os
encontrava). Correcao: novo `kobo_api._amostra_animal_row` traduz os campos do
formulario (incluindo `Motivo da visita`) para os rotulos que o ETL espera,
preservando o `kobo_uuid`. Ajuste de correcao (patch): versao `1.20.1`. A
regressao ampla terminou com 653 testes em `OK` e 5 ignorados.

### Cards de status dos doentes de Esporotricose

Na branch `trabalho-deepseek`, a aba "Lista" de doentes da pagina
`/esporotricose` passou a exibir um card por status alem dos cards fixos
(Doentes, Em tratamento, Medicação disponível e Receitas). Os cards usam a
lista canonica de status (`esporotricose_doentes_status`, ex.: Faleceu, Acabou
tratamento, Aguardando documentos, etc.) com **contagem exata** por valor de
status, exibindo zero quando nao ha doentes naquele status. A soma dos cards de
status e igual ao total de doentes cadastrados (registros sem status entram em
"Sem status"). "Em tratamento" e "Medicação disponível" contam somente os
doentes com exatamente esse status (o card "Em tratamento" deixou de usar
correspondencia por substring). Para os cards aparecerem, o filtro padrao de
status na carga inicial foi removido (antes a pagina abria so com "Em
tratamento"). Nova funcionalidade compativel: versao `1.21.0`. Teste
`test_pagina_esporotricose_exibe_abas_principais` cobre o novo container.

### Correcao sim/nao em Amostra de Animais

A importacao via API de Amostra de Animais gravava o codigo interno do Kobo
(`n_o` para "Não", `sim` para "Sim") nos campos `houve_acidente`/`houve_captura`
(tela mostrava "n_o"/"sim"), diferente do modulo esporotricose que ja normaliza.
`amostras_animais` agora tem `_normalizar_sim_nao`, aplicado no `parse_workbook`
(ex.: `n_o` -> "Não", `sim` -> "Sim"). Ajuste de correcao (patch): versao
`1.21.1`. Scripts novos: `scripts/diagnosticar_amostras_sim_nao.py` (somente
leitura) e `scripts/corrigir_amostras_sim_nao.py` (preview + `--aplicar`) para
normalizar dados ja gravados fora de `endemias_teste` com `--confirmar-banco`.

### Arrastar anexos de doentes para salvar no computador

Na pagina de detalhe do doente de Esporotricose, cada anexo (PDF) pode agora ser
arrastado para fora do navegador e salvo numa pasta do computador, usando o
recurso `DownloadURL` do HTML5 (suportado em Chrome/Edge/Brave). Cada card tambem
ganhou um botao "Baixar" (usa o endpoint `/download`), que funciona em qualquer
navegador como alternativa confiavel. Mudanca apenas de interface no template
`esporotricose_doente_detalhe.html` (sem tocar no banco). Nova funcionalidade
compativel: versao `1.22.0`.

1. **Envio supervisionado Conta Ovos:** a branch
   `codex/enviar-leituras-conta-ovos` prepara POST unitario, mas escrita remota
   continua fora da `master` ate piloto humano supervisionado. Nunca enviar
   dados reais por iniciativa do agente.
2. **Pendencia operacional de PE:** as edicoes dos PEs 1 e 24 que falharam em
   13 e 17/08 tiveram rollback integral e ainda precisam ser refeitas
   manualmente no sistema corrigido.
3. **Kobo PE-0045:** o codigo e os aliases ja estao na `master`; publicacao ou
   troca do XLSForm no Kobo continua uma operacao externa manual. O valor
   qualificado esperado e
   `RUA CAMPOS DE MINAS - BORRACHARIA GARAGEM OCULTA`.
4. **Fora deste eixo:** formulario/OCR de Registro Geografico, diarios offline
   e substituicoes graduais do Kobo sao projetos separados. GeoJSON + Registro
   Geografico permanecem a fonte territorial; Conta Ovos nao os sobrescreve.

Antes de iniciar qualquer uma delas, confira o pedido mais recente do usuario.
Ele pode mudar a prioridade, autorizar operacao real ou pedir apenas analise.

## Fechamento de cada lote

Um lote esta pronto somente com escopo claro, dados reais preservados, testes
focados e regressao proporcional, documentacao atualizada, commit e push. Para
lotes de risco (dados, PostgreSQL, autenticacao, backups e Conta Ovos), Codex
deve preferir branch isolada e ensaio seguro, mas pode integrar sem revisao
externa obrigatoria quando o pedido e as validacoes permitirem. Claude participa
somente se o usuario solicitar.
