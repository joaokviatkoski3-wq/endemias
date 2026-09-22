# Estado atual e passagem de contexto do projeto

Atualizado em 16/09/2026. Este e o resumo operacional que uma nova conversa do
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

- Os espelhos locais da integracao Conta Ovos sao a base da interface; as telas
  nao chamam a API em tempo real. A API e a fonte de verdade para os campos que
  ela administra.
- As contagens GET de 2026 foram reconciliadas em producao: 5.383 registros
  (1.452 inseridos, 3.931 atualizados). Uma repeticao de 45 dias retornou 1.108
  itens sem mudanca, confirmando idempotencia. CSV/importacoes manuais seguem
  como contingencia, sem segundo historico paralelo.
- A pagina operacional `/ovitrampas` concentra Leituras, Monitoramento,
  Armadilhas, Diarios, Laboratorio e Calendario. A antiga central de consulta
  `/conta-ovos` foi retirada por duplicidade; a pagina
  `/conta-ovos-sispncd` continua independente.
- O espelho do cadastro remoto existe (migracao `0005` aplicada e ensaio
  aprovado), mas a **primeira sincronizacao real desse cadastro ainda nao foi
  executada**. Ate ela, Cadastro remoto, Mapa e parte das divergencias podem
  ficar vazios; isso nao e defeito da interface.
- O envio remoto de leituras por lote via `/postcounting` ja esta na `master`,
  sob demanda e com confirmacao no navegador. O fluxo nao faz retentativa
  automatica, nao reenvia item ja reconciliado e nao envia lote silencioso.
  A branch `codex/enviar-leituras-conta-ovos` continua existindo com trabalho
  derivado, mas nao deve ser tratada como se a funcionalidade basica ainda
  estivesse fora da `master`.
- Na versao `1.43.0`, a API atualizada passou a permitir `POST
  /posteditovitrap`. O detalhe do lote concluido permite ao administrador
  preparar alteracoes cadastrais vindas do diario fisico. Elas atualizam o
  cadastro local e entram em fila propria antes da leitura: cadastro remoto
  confirmado primeiro, `/postcounting` depois. Resultado de rede incerto nao
  recebe reenvio automatico. Pela regra do setor, `Localidade` e enviada tanto
  como district quanto sector; telefone permanece somente local. A importacao
  CSV final de 17/09/2026 e a linha de corte, e CSV passa a contingencia.

As regras de fonte de verdade e a arquitetura da tela estao em
`docs/CONTA_OVOS_INTERFACE.md`; detalhes da API e dos lotes em
`docs/CONTA_OVOS_API.md`.

Na versao `1.35.0`, a aba Monitoramento passou a calcular os indicadores
entomologicos diretamente sobre o espelho de contagens da API: IPO (leituras
positivas / leituras x 100), IDO (ovos / leituras positivas) e IMO (ovos /
leituras, equivalente ao IDV). Os valores aparecem no resumo, em graficos de
evolucao e volume, na tabela semanal, no ranking e no detalhamento por
localidade. A tela diferencia leituras no periodo de IDs unicos e acrescenta
busca por ovitrampa, minimo de leituras, limites minimos de IPO/IDO/IMO,
ordenacao do ranking e limpeza dos filtros. Nenhuma migracao foi necessaria.

Na versao `1.35.1`, o intervalo semanal informado passou a ser respeitado mesmo
quando o ano permanece automatico (nesse caso, usa-se o ano mais recente). O
Monitoramento tambem aceita data inicial/final e aplica automaticamente os
filtros gerais em cards, graficos e tabelas. A interface usa "leitura" no lugar
de "exame", ganhou legenda simples para IPO/IDO/IMO e o grafico de leituras,
positivas e ovos passou a compartilhar um unico eixo Y. Os limites minimos e a
ordenacao continuam exclusivos do ranking, conforme indicado na tela.

Na versao `1.37.0`, o mesmo conjunto de filtros do Monitoramento passou a gerar
uma exportacao XLSX analitica. O arquivo contem abas de resumo, leituras,
armadilhas, semanas, localidades e ocorrencias. As leituras nao possuem o limite
visual da pagina; cadastro local, espelho do cadastro publico do Conta Ovos e
lotes do laboratorio sao unidos sem chamar a API durante o download. Armadilhas
sem leitura no periodo continuam na aba cadastral com indicadores zerados, o que
permite auditar cobertura. Nenhuma migracao de banco foi necessaria. Consulte
`docs/OVITRAMPAS_EXPORTACAO_XLSX.md`.

Na versao `1.38.0`, localidade e ovitrampa deixaram de ser filtros unitarios no
Monitoramento. Agora e possivel combinar varias localidades e, em seguida,
escolher varias armadilhas exatas dentre as cadastradas nesse conjunto. Os dois
seletores possuem pesquisa, limpeza e selecao das opcoes visiveis. A selecao e
aplicada em conjunto aos cards, graficos, tabelas, ocorrencias laboratoriais,
pendencias de realocacao e exportacao XLSX. O cadastro local alimenta as opcoes
em cascata; a leitura e os indicadores continuam vindo do espelho GET do Conta
Ovos. Nenhuma migracao foi necessaria.

### Mapas-base

Na versao `1.35.2`, o sistema deixou de consultar diretamente os blocos
publicos de `tile.openstreetmap.org`, que responderam HTTP 403 por politica de
uso. O mapa territorial, o mapa do Registro Geografico e os mapas incluidos na
impressao dos RGs usam as bases Esri World Street Map e World Imagery; as
legendas do modo hibrido usam a camada Esri World Boundaries and Places. A
impressao processa no maximo dois mini-mapas simultaneamente para evitar
rajadas de requisicoes. Nao houve migracao nem alteracao de dados. Consulte
`docs/MAPAS_BASE_CARTOGRAFICA.md`.

Na versão `1.44.0`, o Registro Geográfico recebeu uma camada GeoJSON local
versionada. Administradores podem validar e importar uma `FeatureCollection`
do QGIS com `Localidade` e `id_quart`; cada versão preserva hash, autor,
horário e geometrias, e a prévia compara novos, alterados, iguais e ausentes
sem excluir nada automaticamente. Mapa Territorial, mapa do RG e RGs impressos
passam a consumir `/api/registro-geografico/geojson`, que mantém o arquivo
estático como contingência até a primeira importação. A migração PostgreSQL
`0013_registro_geografico_geojson.sql` precisa ser aplicada antes do primeiro
uso da importação em produção. Não há comunicação com Conta Ovos nesta etapa.
Consulte `docs/REGISTRO_GEOGRAFICO_GEOJSON.md`.

Na versão `1.44.1`, o importador passou a aceitar diretamente os nomes de
campos do QGIS: `Localidade` pode conter o nome normalizado e acentuado da
localidade, e `id_Q` identifica o quarteirão. O nome é validado contra o
cadastro local; `id_quart` continua aceito para os arquivos legados.

Na versão `1.45.0`, Esporotricose passou a manter o histórico por imóvel sem
fundir as visitas importadas. O vínculo usa localidade, quarteirão, logradouro
e número; importações futuras recebem apenas vínculos exatos, enquanto o
histórico e os casos parecidos dependem de prévia e confirmação administrativa.
A migração PostgreSQL `0014_esporotricose_imoveis_historico.sql` cria as duas
tabelas novas, mas não vincula dados: a primeira ação histórica é explícita na
aba **Histórico por imóvel**. Consulte
`docs/ESPOROTRICOSE_IMOVEIS_HISTORICO.md`.

Na versão `1.46.0`, a aba **Histórico por imóvel** recebeu filtros por período,
localidade, quarteirão, situação, agente, tipo de imóvel e texto, além de
paginação de 25, 50 ou 100 itens. O painel de detalhe acompanha a rolagem em
telas largas e cada visita apresenta situação, equipe, tipo de imóvel,
morador/telefone, animais e observações. Os controles administrativos de
vínculo foram reposicionados antes da lista para uso prático em bases grandes.

### Acompanhamento de ACS em visitas PVE

Na versao `1.36.0`, visitas PVE passaram a armazenar os campos do formulario
Kobo `acs_presente` e `acs_nome`; a migracao escalar `0009_visitas_acs.sql` foi
aplicada no banco oficial `endemias` em 14/09/2026. Na versao `1.39.0`,
`acs_nome` passou a ser tratado como `select_multiple`: cada codigo selecionado
e persistido em `visita_acs`, enquanto `acs_nome` conserva a sequencia para
rastreabilidade. A API reconhece os campos mesmo dentro de grupos. A resposta
`sim_acs_presente` e normalizada para `1`, `nao_acs_presente` para `0`, e a
resposta negativa remove os vinculos de ACS. ACS nunca e cadastrado como agente
de endemias. A migracao PostgreSQL `0010_visita_acs.sql` foi aplicada no banco
oficial `endemias` em 15/09/2026; SQLite possui atualizacao compativel e
idempotente. Na versao `1.40.0`, os ACS passaram a aparecer como **ACS
acompanhantes** na listagem e no detalhe de **Visitas arboviroses**. O filtro
multiplo seleciona visitas que tenham ao menos um dos ACS escolhidos e tambem
se aplica a exportacao XLSX. A apresentacao humaniza codigos Kobo, mas a
filtragem usa o codigo canonico de `visita_acs`. Consulte `docs/PVE_ACS.md`.

Na versao `1.47.0`, a tabela `acs_catalogo` passa a separar os codigos Kobo dos
nomes exibidos. Filtros, listagem e detalhes mostram o nome oficial para
codigos como `ACS-026`, mas continuam filtrando e vinculando pelo codigo
canonico. A migracao PostgreSQL `0015_acs_catalogo.sql` deve ser aplicada antes
de reiniciar a producao. Na versao `1.47.1`, os controles manuais de atualizacao
e reconciliacao de ACS foram retirados das telas; ao preparar uma importacao
PVE, o catalogo e atualizado automaticamente a partir do XLSForm, sem alterar
visitas ja existentes e sem bloquear a importacao se essa consulta falhar.

### Casos humanos de Esporotricose

A versao `1.48.0` implementa uma area separada em **Esporotricose > Casos
humanos**, acessivel somente a administradores. O cadastro preserva nome,
nascimento, cartao SUS, nome da mae, telefone, endereco, coordenadas,
observacoes e os status `Em tratamento`, `Acabou tratamento` e `Outros`.

O detalhe possui linha do tempo de acompanhamentos, anexos e sugestoes de
relacao com imoveis acompanhados e animais doentes. As sugestoes usam endereco,
quarteirao e localidade, mas exigem confirmacao humana e sao auditadas. Nao ha
controle de medicacao humana. A migracao aditiva
`0016_esporotricose_pacientes_humanos.sql` ainda precisa ser aplicada no banco
oficial antes do reinicio. Consulte `docs/ESPOROTRICOSE_CASOS_HUMANOS.md`.

A versao `1.48.1` corrige a consulta da lista no PostgreSQL. A ordenacao
original tentava combinar `data_notificacao` (`date`) com `criado_em` (`text`)
em um `COALESCE`, causando HTTP 500 somente na listagem; o cadastro do paciente
ja havia sido gravado e nao foi perdido.

### Vínculo de conta para lançamentos laboratoriais

Na versão `1.40.1`, a assinatura de resultados em **Lançamentos Laboratório**
deixou de depender exclusivamente da igualdade entre o nome da conta e o nome
curto do agente. A migração aditiva `0011_usuarios_agentes.sql` cria
`usuarios.id_agente`; em **Gestão de Usuários**, o administrador pode vincular
cada conta ao agente ativo correspondente. Esse vínculo é prioritário. Sem
vínculo, a compatibilidade legada também considera `nome_completo` e ignora
acentos e pontuação. Antes de reiniciar a versão no servidor oficial, aplique a
migração no PostgreSQL e vincule os laboratoristas. ACS permanece apenas em
`visita_acs`, sem qualquer relação com `agentes`.

Na versão `1.40.2`, somente contas de nível **admin** podem corrigir o
responsável por uma leitura já existente. A edição de um tubo preserva o
laboratorista original quando o administrador não seleciona outro agente. Na
leitura de ovitrampas, a reatribuição seleciona uma conta ativa que tenha acesso
ao laboratório. A proteção é aplicada também nas APIs; operadores não podem
forçar a mudança por requisição direta.

Na versão `1.40.3`, o importador Kobo passou a normalizar `jo_o` para **João**
na extração de agentes. Esse é o código da opção no formulário PVE e não deve
ser tratado como novo agente. A regressão cobre diretamente a leitura dessa
coluna antes de gravar `visita_agentes`.

Na versão `1.40.4`, a escolha múltipla de ACS publicada no Kobo passou a ser
lida também pelo nome técnico `Qual_quais_ACS`, inclusive quando estiver dentro
de grupo. O nome inicialmente previsto, `acs_nome`, permanece compatível. O
script controlado `scripts/reconciliar_acs_pve_kobo.py` faz a prévia e, sob
dupla confirmação, atualiza exclusivamente os campos ACS das PVE já existentes;
nenhum outro dado da visita é reimportado. Como essa reconciliação já foi
concluída, ela não é mais exposta na interface de produção.

### Notificacoes laboratoriais

- A fonte da pagina `/notificacoes` e `focos_positivos`, nao a tabela bruta de
  resultados do laboratorio.
- A regra comum cobre importacao Kobo e Lançamentos Laboratorio: um positivo de
  Aedes aegypti cria ou atualiza um foco por visita; PE nunca gera notificacao;
  TB, TBO e PVE so entram na fila quando o imovel nao e terreno baldio.
- O script `scripts/diagnosticar_notificacoes_laboratorio.py` faz a previa de
  positivos historicos divergentes e so reconcilia sob confirmacao dupla em
  uma unica transacao, com auditoria. Confira
  `docs/NOTIFICACOES_LABORATORIO.md` antes de qualquer escrita em dados reais.

### Positividade historica de coletas

- Desde a versao `1.41.0`, a pagina **Positividade** reune os focos legados
  (`focos_positivos` com `origem='historico'`) e os positivos atuais de
  `resultados_laboratorio`, sem duplicar focos atuais nem inventar detalhes que
  nao existem no legado. A consulta inclui PE e terreno baldio, pois nao usa a
  restricao operacional de notificacoes.
- Consulte `docs/POSITIVIDADE_HISTORICA.md` para fontes, limites dos dados e
  semantica dos filtros/exportacao.
- A correcao `1.41.1` uniformiza o tipo de data entre as fontes no PostgreSQL
  e normaliza localidades somente na consulta. Variantes historicas de Sao
  Venancio passam a ser apresentadas e filtradas como **Sao Venancio**.

### Exclusao administrativa de visitas

- Desde a versao `1.42.0`, somente administradores podem excluir uma visita em
  **Visitas arboviroses**. A acao exige confirmacao na tela e remove, em uma
  transacao, os depositos, tratamentos, coletas, pendencias/resultados de
  laboratorio, focos e vinculos de agentes/ACS. A auditoria e o lote de
  importacao permanecem preservados para rastreabilidade.

### Experimento de normalizacao de enderecos retirado

- A pagina `/logradouros`, o catalogo municipal importado, os vinculos de
  visitas positivas e a geocodificacao foram retirados por decisao do usuario
  em 10/09/2026. O fluxo nao agradou e nao deve ser retomado incrementalmente.
- Uma eventual nova solucao deve ser projetada do zero, voltando a validar com
  o usuario o modelo de endereco, o fluxo de revisao e a geocodificacao.
- Um backup PostgreSQL completo e validado, prefixado como
  `endemias_pre_remocao_logradouros`, foi criado antes da exclusao.
- As tabelas exclusivas da experiencia e os registros das migracoes PostgreSQL
  `0006`, `0007` e `0008` foram removidos. Visitas e seus enderecos originais
  permaneceram intactos, assim como as ferramentas do Registro Geografico.

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

### Baixar anexos de doentes (por anexo e todos em ZIP)

Na pagina de detalhe do doente de Esporotricose, cada anexo tem um botao
"Baixar" (usa o endpoint `/download`) e foi adicionado o botao "Baixar todos",
que gera um unico ZIP de todos os anexos do doente (novo endpoint
`/esporotricose/doentes/<id>/anexos/baixar-todos`). A tentativa inicial de
"arrastar o arquivo para fora do navegador" (`DownloadURL`) foi **removida** por
ser um recurso experimental que nao funciona de forma confiavel; o download e a
via garantida. Mudanca de interface e um endpoint novo, sem alterar o banco.
Nova funcionalidade compativel: versao `1.23.0`.

### Correcao da semantica de data no payload do postcounting (fila)

No Conta Ovos, `date` e a data de instalacao (ancora da semana) e
`counting_date_collect` e a data de coleta. Em um lote/diario de laboratorio, o
`data_movimento` e a coleta (troca/retirada). A fila (`contaovos_fila`) usava
`data_movimento` como `date` (sem `counting_date_collect`), o que colocaria a
contagem na data/semana errada. Correcao: `_derivar_instalacao` obtem do
calendario a data de instalacao (ultimo evento instalacao/troca do grupo antes
da coleta) e o payload passa a enviar `date`=instalacao e
`counting_date_collect`=coleta. Retrocompativel quando nao ha evento/calendario.
E um ajuste de correcao (patch): versao `1.23.1`. Testes novos em
`test_contaovos_fila`.

### Botao "Enviar ao Conta Ovos" por lote/diario

Na pagina Ovitrampas > Laboratorio, cada lote/diario concluido ganhou um botao
"Enviar ao Conta Ovos", que envia as leituras via `POST /postcounting` (com
`date`=instalacao derivada do calendario e `counting_date_collect`=coleta), marca
a fila e o lote como `enviado_conta_ovos`. E uma escrita externa real, feita sob
demanda (botao por lote, com confirmacao no navegador), nunca lote automatico
silencioso. Nova funcionalidade: versao `1.24.0`. Testes novos em
`test_contaovos_fila` (`send_lot`). Apos o piloto real, o retorno de feedback na
interface foi aprimorado: mensagem clara de sucesso (contagem de enviadas) e, em
caso de falha, aviso persistente listando os itens que falharam com a mensagem
da API e orientacao do que fazer (o lote nao e marcado como enviado ate todas
passarem). Ajuste: versao `1.24.1`.

### Frente 1 (incremento 1) - contagens via API no Ovitrampas

Direcao aprovada pelo usuario: alimentar as abas de contagens de Ovitrampas pela
API (Conta Ovos como fonte da verdade), remover a importacao manual de CSV de
contagens e consolidar a pagina Conta Ovos na Ovitrampas. Incremento 1 (na
branch, para teste no ambiente de teste): nova
funcao `ovitrampas.contagens_api_para_aba` e endpoint
`/api/ovitrampas/ocorrencias-api` leem o espelho API
(`ovitrampas_ocorrencias_conta_ovos`, alimentado por GET /lastcounting) e a aba
Monitoramento mostra quantas contagens sao via API. Nao altera
`ovitrampas_leituras` nem o fluxo de laboratorio. Nova funcionalidade (incremento):
versao `1.25.0`.

### Frente 1 (incremento 2) - Monitoramento de Ovitrampas le o espelho API

Ao verificar uma divergencia (tela mostrava ~4212 leituras de 2026 enquanto o
Conta Ovos tinha 6603), confirmou-se que o Monitoramento lia `ovitrampas_leituras`
(CSV/manual), e nao o espelho API. Incremento 2: nova `ovitrampas.monitoramento_contagens`
faz o Monitoramento ler `ovitrampas_ocorrencias_conta_ovos` (espelho API) com
filtro de periodo (ano/semana) e join no cadastro local para localidade/endereco,
corrigindo a contagem para refletir o Conta Ovos. Ranking/ocorrencias/realocar
ainda estao sendo migrados (vazios nesta etapa). Versao continua `1.25.0`
(Frente 1 ainda nao integrada a master).

### Frente 1 (incremento 3) - Monitoramento completo a partir do espelho API

Incremento 3 completa as secoes que o incremento 2 deixou vazias, lendo o
espelho API (`ovitrampas_ocorrencias_conta_ovos`) e o cadastro local:

- **Ranking de positividade** (`ranking_positivas`): agrega por `ovitrampa_id`
  no espelho (leituras, positivas, % de positividade, ovos, ultima semana
  positiva), via novo campo `media_ovos_positiva` em localidades e
  `vezes_positiva` em positivas recentes (campos que o frontend ja lia).
- **Historico de ocorrencias** (`ocorrencias` + `totais["ocorrencias"]`):
  vem dos **lancamentos de laboratorio** (`ovitrampas_laboratorio_itens.ocorrencia`,
  codigos 1..8), cruzados com o espelho pela ovitrampa e pela data de coleta
  (lote concluido/enviado) para respeitar o periodo do Monitoramento. O GET
  `/lastcounting` do Conta Ovos **nao devolve a situacao/observacao** (confirmado
  ao vivo), entao o espelho nao carrega ocorrencia. Helper
  `ovitrampas._monitoramento_ocorrencias_laboratorio` (+ `_..._detalhes_laboratorio`).
- **Pendentes para realocacao** (`realocar` + `totais["realocar"]`): continua
  **local**, lendo `ovitrampas_armadilhas` por `_armadilhas_realocar`. Os
  endpoints GET da API Conta Ovos (`getmunicipalityovitraps[public]`) **nao
  devolvem endereco nem REALOCAR**; os campos `ovitrap_address_*` so existem no
  corpo do POST /postcounting ao instalar. Por isso endereco/REALOCAR seguem
  locais (via CSV/Diarios), conforme decisao do usuario.

Laboratorista "via lote" ficou **fora** do Monitoramento (a pagina nao exibe
laboratorista); decisao registrada para entrega futura na aba de lotes.
Versao `1.26.1`. (Ajuste posterior no proprio incremento 3: ocorrencias passaram
a vir do laboratorio, pois o espelho GET nao as traz.)

### Fechamento da sessao (08/09/2026) - registro historico da refatoracao adiada

Naquele momento, esta sessao terminou com duas frentes distintas. **Nenhuma
mudanca de codigo de refatoracao havia sido integrada**; a arvore de trabalho
`trabalho-deepseek` estava limpa em `7f17b33`. O texto abaixo e um registro
historico do que foi planejado e descoberto, nao o estado posterior do lote
`1.27.0`.

**A) Refatoracao de Ovitrampas/Conta Ovos - planejada, NAO implementada.**

O usuario pediu (em andamento) que, na pagina Ovitrampas:
- removesse a importacao redundante de ocorrencias via CSV;
- mostrasse, de forma discreta, a origem dos dados (CSV vs API);
- revisasse redundancias/estrutura das abas;
- adicionasse botao/configuracao para atualizar os dados da API na interface.

Durante o levantamento daquela sessao (sem alterar codigo) confirmou-se: a sincronizacao GET
Conta Ovos roda **somente via CLI** (`sincronizar_contagens_contaovos.py` e
`sincronizar_registro_ovitrampas_contaovos.py`), nao ha botao web; a central
`Conta Ovos` e somente leitura; o espelho de contagens
(`ovitrampas_ocorrencias_conta_ovos`) NAO carrega a ocorrencia (o GET
/lastcounting nao a devolve); endereco/REALOCAR sao locais. A refatoracao foi
**interrompida** porque surgiu um problema real no Conta Ovos (item B) que passou
a prioridade. Ao retomar, revisar: remover import CSV de ocorrencias e de
leituras, remover import XLSX de diarios (diarios hoje sao mantidos no sistema),
migrar aba Leituras para o espelho API, indicadores discretos de origem, e botao
de sincronizacao na central Conta Ovos.

**Atualizacao posterior:** a retomada do projeto iniciou o lote `1.27.0` na
pagina `/ovitrampas`. A tela agora identifica as fontes dos dados e oferece a
administradores uma sincronizacao GET dos espelhos locais, sem envio remoto.
Os fluxos CSV/XLSX permanecem nesta primeira etapa como contingencia.

**Atualizacao posterior 1.28.0:** a aba **Leituras** passou a consultar o
espelho GET `ovitrampas_ocorrencias_conta_ovos`, com detalhes da API e
enriquecimento de laboratorista, data da leitura e ocorrencia pelos lotes da
aba **Laboratorio**. O Monitoramento permanece API para indicadores e usa o
Laboratorio no historico de ocorrencias. A importacao CSV foi retirada de
Leituras e do historico de ocorrencias; a importacao XLSX foi retirada de
Diarios. O CSV continua somente em Armadilhas, enquanto responsaveis e
telefones dos Diarios seguem locais, editaveis e usados na impressao.

**B) Diagnostico do cadastro em branco de 12 ovitrampas no Conta Ovos.**

Sintoma reportado pelo usuario: apos envios de contagens da semana 34 (coleta
02/09/2026) via /postcounting, as ovitrampas **131, 137, 138, 140, 142, 145,
148-A, 149, 151, 154, 156, 157** ficaram com o cadastro do Conta Ovos em branco
(Distrito/Rua/Numero/Complemento/Localizacao/Setor/Responsavel), mantendo
somente coordenadas e contagens. Todas sao da localidade **"Sede"** no cadastro
local.

Conclusoes tecnicas confirmadas (somente leitura + pilotos reais):
- O `POST /postcounting` **NAO atualiza o cadastro/endereco de uma ovitrampa
  ativa**: ele so grava a contagem. O endereco exibido no Conta Ovos vem da
  tela de cadastro propria da ovitrampa (nao do corpo da contagem). O piloto na
  131 e o teste controlado de `TESTE` confirmaram essa limitacao.
- No teste controlado de `TESTE` em 08/09/2026, o `POST
  /pt-br/api/postdeleteovitrap` retornou HTTP 200. As leituras `3947141` e
  `3947235` permaneceram no historico, mas com `ovitrap_id` alterado para
  `TESTE [DELETED]209336`. Em seguida, o mesmo ID de grupo foi recriado pelo
  `/postcounting` com corpo `x-www-form-urlencoded`, gerando novo cadastro
  remoto `ovitrap_website_id=209347` e leitura `3947301` com os dados de
  endereco alterados para "B". O fluxo exclusao + recriacao funciona, mas
  substitui a identidade remota, marca o historico anterior como deletado e
  nao e uma edicao simples de cadastro.
- As 12 estao sim registradas no cadastro publico do Conta Ovos
  (`getmunicipalityovitrapspublic` retorna todas; o municipio tem um unico
  grupo remoto `1867` com 343 ovitrampas = mesmo total do cadastro local). O
  espelho local `contaovos_registro_ovitrampas` esta **vazio (0 registros)**
  porque a sincronizacao desse cadastro nunca foi executada.
- O padrao "Sede" e correlacao, nao causa: ha 35 ovitrampas de Sede no total e
  so 12 ficaram em branco. A causa provavel: essas 12, no momento do envio da
  semana 34, nao possuiam ainda cadastro preenchido no Conta Ovos; ao receber a
  contagem, o Conta Ovos as criou/vinculou sem endereco. As demais (que ja
  estavam cadastradas) mantiveram o endereco. Confirmar a causa exata exigiria
  dados internos do Conta Ovos (data de criacao/cadastro), nao expostos pela API
  publica.

Correcao adotada pelo usuario (acao real, manual no site do Conta Ovos): o
usuario preencheu manualmente o cadastro das ovitrampas afetadas no site. Ele
informou que **atualizou** as ovitrampas e encerrou a sessao. Os enderecos
corretos (do cadastro local) de todas as 12 estao registrados no diagnostico
desta sessao (todos da localidade Sede). Ajustar a 131, se ainda estiver com um
endereco de "teste" que o usuario usou durante o experimento.

**Prevencao recomendada (NAO implementada):** como o espelho do cadastro remoto
esta vazio, a protecao mais solida seria sincronizar `contaovos_registro_ovitrampas`
e, no fluxo de envio de contagens, avisar/bloquear ovitrampas que nao constem no
cadastro remoto - evitando que o Conta Ovos crie ovitrampas sem endereco. O
usuario optou por nao mexer no fluxo nesta sessao.

**Arquivos criados nesta sessao (somente leitura, nao commitados):**
- `scripts/diagnosticar_ovitrampas_cadastro_vazio_contaovos.py` (le espelho API
  /lastcounting + cadastro local das ovitrampas de um alvo);
- `scripts/diagnosticar_duplicata_cadastro_contaovos.py` (cruza cadastro local x
  espelho remoto por chave de comparacao).
Um terceiro script de correcao (`corrigir_endereco_contagens_contaovos.py`) foi
criado e depois **removido**, pois ele tentava alterar cadastro ativo pelo
`/postcounting`, que nao atualiza esses campos. O fluxo destrutivo de
exclusao/recriacao foi apenas testado sob autorizacao e nao foi incorporado.

1. **Sincronizacao dos espelhos Conta Ovos:** a pagina Ovitrampas agora possui
   acao administrativa explicita para executar GET do cadastro publico e das
   contagens recentes. O primeiro uso real ainda deve ser acompanhado pelo
   administrador e conferido na propria pagina Ovitrampas.
2. **Pendencia operacional de PE:** as edicoes dos PEs 1 e 24 que falharam em
   13 e 17/08 tiveram rollback integral. A normalizacao de datas vazias/`NaT`
   ja foi integrada e possui testes; as edicoes reais continuam dependendo de
   operacao manual autorizada.
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
