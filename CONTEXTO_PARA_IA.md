# Contexto para continuidade do projeto

Atualizado em 24/09/2026. Este arquivo e o ponto de entrada para qualquer IA
que assumir o projeto em outra conta ou conversa. Leia depois
`docs/ESTADO_ATUAL_PROJETO.md` (estado vivo) e, em especial, a seccao
"Fechamento da sessao (08/09/2026)" para nao repetir a investigacao do cadastro
em branco do Conta Ovos nem retomar a refatoracao de Ovitrampas sem contexto.

## Projeto e forma de trabalho

- Sistema local Flask para o Setor de Endemias de Almirante Tamandare-PR.
- Repositorio oficial: `joaokviatkoski3-wq/endemias`.
- Branch oficial: `master`.
- Diretorio oficial no computador do setor: `C:\endemias`.
- Versao atual no codigo e no servico oficial: `1.50.1`, definida em `app_core/version.py`.
- O usuario exige commit e push ao final de toda modificacao solicitada.
- Nao reverta alteracoes do usuario nem dados reais.
- Use `apply_patch` para edicoes manuais.
- PostgreSQL e a base oficial de producao desde 03/08/2026.
- `endemias.db` esta congelado como rollback e nao pode receber novas escritas.
- `iniciar.bat` recusa o modo SQLite quando o marcador operacional PostgreSQL
  esta instalado.
- Credenciais, bancos, anexos, backups e tokens nao podem ser versionados.

Na versao `1.50.0`, a origem do itraconazol nas entregas e no estoque de
esporotricose e registrada em `fonte_medicacao` (`Zoomed`/`Município`). A
migração PostgreSQL `0018_esporotricose_fontes_medicacao.sql` foi aplicada no
banco oficial em 24/09/2026. Os 71 lancamentos de entrega e 17 movimentos de
estoque anteriores ficaram como `Zoomed`; entregas municipais recentes devem
ser reclassificadas manualmente e suas entradas de estoque registradas. O ZIP
de todos os anexos de um animal pode ser baixado no detalhe como alternativa.
A tarefa oficial foi reiniciada apos a migracao; `/login` respondeu HTTP 200
exibindo `Endemias v1.50.0`. Posteriormente, o usuario preferiu downloads
individuais sem ZIP: no detalhe do animal, "Baixar todos separadamente" solicita
um download por anexo; o navegador pode pedir permissao para multiplos arquivos.
Na lista, "Anexos (N)" abre essa secao do detalhe. O ZIP continua opcional.

Na correcao `1.50.1`, a origem `Zoomed` passa a se chamar `SESA`; a outra
origem permanece `Município`. Zoomed continua sendo a plataforma onde se
registram pedidos e baixas de **ambas** as origens, portanto o campo "Pedido
Zoomed" conserva seu nome e a baixa Zoomed pode ser marcada nas entregas
municipais. A migracao PostgreSQL `0019_esporotricose_sesa_baixa_zoomed.sql`
foi aplicada no banco oficial em 24/09/2026, depois de validar os backups; o
servico foi reiniciado e `/login` respondeu HTTP 200 com `Endemias v1.50.1`.
A conferencia encontrou 71 entregas SESA, 1 Município e 17 movimentos de
estoque SESA, sem origem legada `Zoomed` nessas tabelas. Os estados de
`baixa_zoomed` foram preservados (68 `Sim`, 4 `Não`). Nao marcar
automaticamente como concluidas as baixas municipais antigas: conferir na
plataforma e corrigir manualmente quando couber.

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

## Retirada do experimento de normalizacao de enderecos

Em 10/09/2026, por decisao do usuario, foi retirada integralmente a pagina
`/logradouros` e todo o fluxo experimental de catalogo oficial, normalizacao de
enderecos positivos e geocodificacao. O fluxo nao foi aprovado para uso e deve
ser redesenhado do zero caso volte a ser discutido. Nao reaproveite como regra
vigente o codigo dos commits historicos `f745f3d` a `9bcb0af`.

Antes da retirada dos dados foi criado e validado um backup completo do
PostgreSQL de producao com o prefixo `endemias_pre_remocao_logradouros`. As
tabelas exclusivas `logradouros_oficiais`, `enderecos_normalizados` e
`visitas_enderecos_normalizados` e os registros das migracoes `0006` a `0008`
foram removidos para deixar livre uma futura implementacao. Os enderecos brutos
das visitas e as ferramentas preexistentes do Registro Geografico nao foram
alterados.
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
  impressoes HTML/DOCX e auditoria atomica. Focos vindos de resultados
  laboratoriais usam uma regra comum ao ETL e aos Lançamentos Laboratorio: PE
  nunca gera notificacao; TB, TBO e PVE somente geram fora de terreno baldio.
  Consulte `docs/NOTIFICACOES_LABORATORIO.md` antes de alterar esse fluxo.
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
status da integracao Conta Ovos e a proxima ordem recomendada estao concentrados
em `docs/ESTADO_ATUAL_PROJETO.md`. A `master` ja possui envio supervisionado de
leituras por lote via `/postcounting` e, no lote atual da pagina Ovitrampas,
sincronizacao GET dos espelhos restrita a administradores. A correcao segura de
datas `NaT` em Pontos Estrategicos ja foi integrada; confirme os testes antes
de tratar essa pendencia como aberta.

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
- A sincronizacao GET de contagens esta homologada. A pagina operacional
  Ovitrampas le o espelho local; Leituras e Monitoramento
  usam as contagens sincronizadas da API, e os dados de laboratorista/data da
  leitura e ocorrencia sao derivados dos lancamentos laboratoriais. A pagina
  Ovitrampas oferece, para administradores, uma acao explicita que sincroniza
  por GET o cadastro publico e as contagens recentes, gravando apenas os
  espelhos locais. CSV de leituras/ocorrencias e XLSX de diarios nao fazem mais
  parte da interface; o CSV permanece apenas na aba Armadilhas.
- Desde a versao `1.35.0`, o Monitoramento apresenta IPO, IDO e IMO (equivalente
  ao IDV) no resumo, nos graficos, por semana, por localidade e por ovitrampa.
  Para periodos com varias semanas, cada contagem sincronizada equivale a uma
  leitura; a quantidade de IDs unicos lidos e mostrada separadamente. O
  ranking pode ser filtrado por ID, minimo de leituras, IPO, IDO e IMO minimos,
  e ordenado por positivas, IPO, IDO, ovos, leituras ou recencia. Consulte
  `docs/CONTA_OVOS_INTERFACE.md` para as formulas.
- A versao `1.35.1` corrigiu os filtros de semanas com o ano automatico,
  acrescentou o recorte por datas e passou a aplicar filtros automaticamente.
  A interface adotou "leitura" em vez de "exame" e o grafico de leituras,
  positivas e ovos usa um unico eixo quantitativo, sem ampliar visualmente
  series pequenas por meio de escalas diferentes.
- A versao `1.35.2` removeu todas as requisicoes diretas ao servidor publico de
  blocos do OpenStreetMap depois de um bloqueio HTTP 403. O mapa territorial,
  o mapa do Registro Geografico e os mapas dos RGs impressos usam bases Esri;
  a impressao limita a duas as renderizacoes simultaneas. Nao reintroduza
  `tile.openstreetmap.org` como dependencia de producao. Consulte
  `docs/MAPAS_BASE_CARTOGRAFICA.md`.
- A versao `1.39.0` passou a tratar `acs_nome` como `select_multiple` nas
  visitas PVE. Cada codigo selecionado e persistido em `visita_acs`, sem criar
  ACS em `agentes` ou em `visita_agentes`; `acs_nome` conserva a sequencia de
  codigos para rastreabilidade. Os campos ainda nao aparecem na interface.
  Consulte `docs/PVE_ACS.md`. A migracao PostgreSQL `0010_visita_acs.sql` foi
  aplicada no banco oficial `endemias` em 15/09/2026 e a versao foi reiniciada.
- A versao `1.40.0` tornou os ACS visiveis e filtraveis em **Visitas
  arboviroses**, inclusive na exportacao XLSX. A exibicao humaniza os codigos
  Kobo; o vinculo e a filtragem continuam usando `visita_acs.acs_codigo`.
- A versao `1.40.1` corrige a assinatura dos resultados em **Lançamentos
  Laboratório**. A conta pode ser vinculada explicitamente a um agente em
  Gestão de Usuários (`usuarios.id_agente`); esse vínculo tem prioridade sobre
  comparações de nome. Sem vínculo, o fluxo legado também reconhece o nome
  completo do agente, desconsiderando acentos e pontuação. A migração
  `0011_usuarios_agentes.sql` é aditiva e deve ser aplicada no PostgreSQL
  oficial antes de reiniciar a versão; em seguida, vincule cada laboratorista
  ao agente correspondente. ACS não é e nunca passa a ser agente de Endemias.
- A versao `1.40.2` permite que apenas administradores corrijam o
  laboratorista responsavel por uma leitura ja registrada. Em tubos, o seletor
  usa os agentes ativos; em leituras de ovitrampas, usa contas ativas com
  acesso ao laboratorio. Uma correcao comum de quantidades preserva a autoria
  existente. As APIs tambem bloqueiam tentativas de operadores de alterar essa
  atribuicao, inclusive nas leituras legadas de ovitrampas.
- A versao `1.40.3` reconhece o codigo Kobo `jo_o` como **João** ao importar
  agentes de visitas. Assim, a grafia de opcao do formulario nao cria um novo
  agente; o vinculo usa o cadastro existente de João.
- A versao `1.40.4` reconhece o nome tecnico publicado `Qual_quais_ACS` como a
  selecao multipla de ACS da PVE, sem perder a compatibilidade com `acs_nome`.
  O preenchimento retroativo controlado usa
  `scripts/reconciliar_acs_pve_kobo.py` e altera somente os campos e vinculos
  de ACS das visitas PVE ja existentes. A reconciliacao historica foi concluida
  e nao e mais exposta na interface de producao.
- As versoes `1.47.0` e `1.47.1` acrescentam `acs_catalogo`: a relacao
  codigo/rotulo do XLSForm PVE ja foi atualizada localmente, e lista, detalhe e
  filtro mostram o nome oficial para codigos como `ACS-026`; filtros e vinculos
  continuam usando o codigo em `visita_acs`. Os controles manuais de atualizacao
  e reconciliacao foram removidos da interface. A cada preparacao de importacao
  PVE, o catalogo e atualizado sem bloquear a importacao se a consulta ao Kobo
  falhar. A migracao PostgreSQL `0015_acs_catalogo.sql` deve ser aplicada antes
  do reinicio em producao.
- A versao `1.48.0` acrescenta o cadastro separado de casos humanos de
  Esporotricose, integralmente restrito a administradores. O modulo guarda
  dados cadastrais e epidemiologicos, acompanhamentos, anexos e vinculos
  confirmados com imoveis acompanhados e animais doentes. Sugestoes por
  endereco nunca vinculam automaticamente. Medicacoes e condutas clinicas
  humanas permanecem fora do sistema, sob responsabilidade da UBS. A migracao
  `0016_esporotricose_pacientes_humanos.sql` deve ser aplicada antes do
  reinicio. Consulte `docs/ESPOROTRICOSE_CASOS_HUMANOS.md`.
  A versao `1.48.1` corrige a ordenacao da lista no PostgreSQL, evitando
  combinar diretamente os tipos `date` e `text`; cadastros salvos antes do
  ajuste permanecem preservados e passam a aparecer normalmente.
  A versao `1.49.0` acrescenta a exportacao administrativa **CSV QGIS** dos
  casos humanos. O arquivo respeita pesquisa, status e localidade selecionados,
  usa UTF-8 com BOM, separador `;` e latitude/longitude numericas separadas.
  Por conter dados pessoais e de saude, o download e auditado e permanece
  exclusivo de administradores.
  A versao `1.49.1` acrescenta `bloqueio` ao caso humano com as opcoes
  `Realizado` e `Nao realizado`; ausencia de resposta continua vazia. A migracao
  `0017_esporotricose_humanos_bloqueio.sql` e necessaria antes do reinicio.
  O campo aparece na edicao, listagem, detalhe, filtro e CSV QGIS.
- A versao `1.41.0` criou a pagina **Positividade**, que combina os focos
  legados de `focos_positivos` (`origem='historico'`) com positivos atuais de
  `resultados_laboratorio`, preservando a ausencia de detalhes laboratoriais no
  legado. Ela inclui todos os positivos, inclusive PE e terreno baldio. Consulte
  `docs/POSITIVIDADE_HISTORICA.md` antes de alterar suas fontes ou filtros.
- A versao `1.41.1` corrige a uniao PostgreSQL entre a data `date` das leituras
  atuais e a data textual do legado. Ela tambem apresenta e filtra variantes
  historicas de localidade pela forma canonica, sem reescrever dados antigos.
- A versao `1.42.0` permite ao administrador excluir uma visita e todas as
  dependencias operacionais diretamente vinculadas. O nucleo em
  `app_core/visitas.py` preserva auditoria e lotes de importacao, exige uma
  confirmacao na interface e a rota bloqueia operadores e visualizadores.
- A versao `1.44.0` adiciona importacao administrativa e versionada do GeoJSON
  de quarteiroes do QGIS. A camada local valida `FeatureCollection`,
  `Localidade`, `id_quart`, Polygon/MultiPolygon e coordenadas; a previa exige
  confirmacao do mesmo SHA-256 e a importacao nunca exclui quarteiroes ausentes.
  Mapa Territorial, RG e RGs impressos consultam a rota local com fallback no
  arquivo estatico ate a primeira importacao. A migracao PostgreSQL `0013` e
  obrigatoria antes do primeiro uso em producao. Esta etapa nao envia nem cria
  quarteiroes no Conta Ovos. Consulte `docs/REGISTRO_GEOGRAFICO_GEOJSON.md`.
- A versao `1.44.1` aceita a estrutura do QGIS sem renomear campos: `Localidade`
  pode ser o nome normalizado e acentuado da localidade (por exemplo, `São
  Venâncio`) e o identificador do quarteirão pode ser `id_Q`. O alias legado
  `id_quart` continua compatível; a camada servida aos mapas usa a chave
  canônica `id_quart` internamente.
- A versao `1.45.0` introduz o historico de imoveis de Esporotricose. A nova
  entidade preserva cada visita Kobo e apenas cria vinculos auditaveis por
  localidade, quarteirao, logradouro e numero; coincidencias exatas podem ser
  aplicadas pelo administrador depois de previa, enquanto semelhancas exigem
  confirmacao manual. Consulte `docs/ESPOROTRICOSE_IMOVEIS_HISTORICO.md`.
- A versao `1.46.0` torna a consulta do historico por imovel operacional em
  listas grandes: o painel acompanha a rolagem, cada visita mostra situacao,
  equipe, tipo de imovel, morador, telefone, animais e observacoes. A lista e
  paginada e pode ser filtrada por periodo, localidade, quarteirao, situacao,
  agente, tipo de imovel e texto; os paineis administrativos de vinculo ficam
  antes da lista.
- A versao `1.37.0` acrescentou ao Monitoramento de Ovitrampas a exportacao
  filtrada em XLSX. O arquivo reune resumo, todas as leituras do recorte,
  cadastro consolidado local/remoto, indicadores por semana e localidade e
  ocorrencias do laboratorio. O download usa apenas os espelhos locais e nao
  faz chamadas nem escritas na API. Consulte `docs/OVITRAMPAS_EXPORTACAO_XLSX.md`.
- A versao `1.38.0` ampliou esse recorte com selecao multipla de localidades e
  de ovitrampas. O segundo filtro e em cascata: lista IDs, endereco e localidade
  apenas do cadastro correspondente as localidades marcadas, com pesquisa e
  acao para selecionar as opcoes visiveis. Cards, graficos, tabelas,
  ocorrencias, pendencias e XLSX recebem exatamente a mesma selecao. Nenhuma
  migracao de banco foi necessaria.
- O envio remoto de leituras por lote via `/postcounting` ja existe na `master`,
  sob demanda, com confirmacao no navegador, sem retentativa automatica e sem
  envio silencioso. Ele nao deve ser confundido com a sincronizacao GET.
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
