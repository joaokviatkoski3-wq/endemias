# Estado atual e passagem de contexto do projeto

Atualizado em 12/11/2026. Este e o resumo operacional que uma nova conversa do
Codex deve ler depois de `CONTEXTO_PARA_IA.md`. Datas, commits,
branches e servicos podem mudar; confirme sempre o estado vivo antes de agir.

## Versão ativa 2.7.5 — reenvios idênticos do LIRAa

Worktree C:\endemias-interface, branch codex/consolida-reenvios-liraa.
A consulta de 12/11 confirmou nos dois envios com UUID compartilhado o
mesmo formulário, horários de preenchimento, local e sequências 1 e 2.
O segundo foi recebido 3min44s depois. Nenhuma das duas versões estava
no banco à hora da consulta.

A versão consolida reenvios com IDs distintos, mesma instância,
horários e conteúdo idênticos, salvo metadados de recebimento. Conserva
o menor ID e preserva a expansão das sequências. Divergências continuam
em revisão. Sem migração. A ativação inclui prévia do par real em leitura.
Passaram 165 testes focados e ensaio PostgreSQL isolado pelo painel,
importação e rotina automática.
Ativada em 12/11/2026, release 88ac73c. O relatório
ativacao-liraa-reenvio275-resultado.json confirmou 96 tabelas comparadas,
dados preservados, entradas disponíveis e automação Kobo restabelecida.
Portal e logins externos e locais responderam em 2.7.5. Às 16h49, a
prévia real confirmou diferenças apenas em ID e horário de recebimento,
com um reenvio agrupado e duas visitas novas, sequências 1 e 2. Consulta
somente leitura, registrada em .venv/reenvio-liraa-275-real.json.

## Histórico 2.7.4 — identificação dos envios LIRAa

Worktree C:\endemias-interface, branch codex/corrige-identidade-consulta-liraa.
A paginação usa o ID permanente para verificar se o mesmo envio reapareceu
durante a consulta. A resposta completa inclui envios com UUID ausente ou
compartilhado. Esses envios são identificados na prévia e ficam pendentes,
com os IDs Kobo disponíveis. A importação manual e a automática continuam
com os envios válidos. Mantém a proteção contra reimportação de versões.
Sem migração. Passaram 164 testes focados e o ensaio PostgreSQL isolado
com prévia web, importação e rotina automática. Ativada em 12/11/2026,
release 38344f8. Relatório ativacao-liraa-identidade274-resultado.json
aplicado/concluído, 96 tabelas comparadas, dados preservados e automação
Kobo restabelecida. Portal e logins públicos e locais responderam em 2.7.4.
Consulta real somente leitura concluída em 12/11/2026 às 15h41. Tanto sem
filtro quanto no recorte dos últimos sete dias, vieram 1.611 envios.
Dois IDs distintos compartilham UUID e ficaram pendentes de identificação.
Os outros 1.609 passaram nessa verificação. Relatório local
C:\endemias-interface\.venv\consulta-liraa-274-real.json.

## Histórico 2.7.3 — proteção das importações LIRAa

Worktree C:\endemias-interface, branch codex/protege-reimportacao-liraa.
O ID permanente e os UUIDs anteriores informados pelo Kobo identificam
edições de envios conhecidos. A classificação sinaliza versões em revisão
na prévia e impede nova gravação. A transação repete a checagem sob trava
compartilhada pelos importadores. Sem migração de banco.
Passaram 162 testes focados e o ensaio PostgreSQL isolado de prévia,
importação e rotina automática. Ativada em 11/11/2026, release 668b215.
Relatório ativacao-liraa-edicoes273-resultado.json aplicado/concluído,
96 tabelas comparadas, dados preservados e automação Kobo restabelecida.
Portal, logins públicos e entradas locais responderam em 2.7.3.

A auditoria de 11/11 identificou 15 envios com versões já importadas, 48
registros de visita, 6 tubitos e 4 leituras. Prévia local em
.venv/liraa-previa-reconciliacao-20261111.md. O tratamento dessas versões
e a aplicação de alterações do Kobo ficam para a reconciliação revisada.

## Histórico 2.7.2 — zero inicial nas ovitrampas

Worktree C:\endemias-interface, branch codex/restaura-zero-ovitrampas.
Campos novos mostram zero. O rascunho salva as edições e ocorrências, e
os zeros padrão são confirmados na conclusão. Uma ocorrência sem contagem
mantém o campo vazio se o zero ainda era o valor padrão. Sem migração.
Ativada em 11/11/2026, release e94f554. O relatório
ativacao-ovi-zero272-resultado.json confirmou 96 tabelas comparadas,
dados preservados e automação Kobo restabelecida. Portal, logins públicos e
entradas locais responderam em 2.7.2. Teste de tablet e 11 testes do
laboratório repetidos com sucesso após a ativação, em base isolada.

## Histórico 2.7.1 — ovitrampas e importação do LIRAa

Worktree C:\endemias-interface, branch codex/corrige-ovitrampas-kobo-liraa.
Rascunhos de laboratório preservam ocorrências sem quantidade. Ocorrências
2 a 6 podem encerrar a linha sem contagem. A interface distingue esse caso
de zero informado, e identifica a armadilha pendente na conclusão.
Sem mudança de esquema. No envio ao Conta Ovos, a API recebe zero e o
código de ocorrência quando não houve contagem.

Consulta LIRAa paginada no painel, na aba do ciclo e na rotina automática.
Valida offsets, UUIDs e total, quando informado pelo Kobo, e usa os mesmos
filtros em todas as páginas. Mantém o limite configurado por formulário.
170 testes focados passaram. O ensaio isolado de PostgreSQL e o fluxo
de rascunho e conclusão em Chromium com tela de tablet também passaram.
Ativada em 11/11/2026, release 0d248e3. Relatório
ativacao-ovi-liraa271-resultado.json aplicado/concluído, 96 tabelas
comparadas, dados preservados, sem migrações e automação Kobo restabelecida.
Portal, logins externos e entradas locais responderam com 2.7.1.
Falta confirmar a consulta do lote real na tela autenticada de importação.

## Histórico 2.7.0 — acompanhamento do LIRAa

Aba Acompanhamento com filtros de ciclo, data e turno. Dia 1 é a data de
início configurada. Turnos pela hora de início: manhã antes de 12h, tarde
até 17h59, noite a partir de 18h e registros sem horário em grupo separado.
Comparação do recorte com o ciclo, com visitas por tipo, visitas com coleta,
tubitos coletados, leituras e pendências. O recorte mostra a situação atual
das leituras dos tubos coletados naquele período. Tipos agrupados no Kobo
continuam agrupados no painel.

A meta é o n do sorteio original, com saldo calculado por estrato. Adicionais
ficam separados da meta original. Visitas fora do plano aparecem no total
operacional e em contador próprio. Cobertura lista quarteirões do plano sem
visita e estratos sem sorteio. Consulta autenticada e em leitura, com snapshot
consistente no PostgreSQL. A aba aberta atualiza a cada minuto com registros
já importados e leituras lançadas.

Worktree C:\endemias-interface, branch codex/liraa-acompanhamento.
101 testes LIRAa, 24 do instalador, ensaio PostgreSQL isolado e Chromium
desktop/celular passaram. No navegador, uma leitura fictícia reduziu o
contador na atualização automática. Ativação confirmada em 09/11/2026 às
13h14, release ed53387. Relatório ativacao-liraa270-resultado.json aplicado e
concluído, com backup completo e PostgreSQL, 96 tabelas preservadas, prova
limitada OK e automação Kobo restabelecida. Oito verificações de publicação
passaram: cinco entradas 2.7.0, dois JS iguais aos instalados e consulta da
aba protegida por login. Evidência local .venv/publicacao-270.json. A aba foi
testada autenticada com massa fictícia, e a conferência em produção foi feita
sem sessão de usuário.

## Histórico 2.6.1 — equipe dos tubitos LIRAa no laboratório

Conferência de 09/11/2026 em leitura: os 198 envios consultados no Kobo
correspondem a 221 visitas no banco. Doze envios múltiplos geraram 35 visitas,
sem divergência de sequência, tubitos ou tratamentos copiados em filhas.
No ciclo 4, 214 visitas no sorteio atual e sete fora. Seis tubitos válidos,
sem numeração repetida no ciclo e ainda sem leitura à hora da conferência.
Quatro em visitas com ACE e ACS, um só com ACS e um sem participante registrado.

O laboratório consultava somente ACE. Candidata mostra a equipe LIRAa na fila,
no formulário de leitura e no histórico, incluindo ACS pelo catálogo e nomes
informados em Outros. Quando o catálogo não resolve um código, exibe o código.
Rótulo Equipe da visita descreve a atribuição gravada no formulário. Correção
em consulta, sem reimportação ou migração. Worktree C:\endemias-interface,
branch codex/liraa-acs-coleta. 2.6.1 ativa desde 09/11 às 12h42, release
2e73614. Relatório ativacao-liraa261-resultado.json aplicado/concluído.
Portal, login externo e entrada local confirmados em 2.6.1.
100 testes LIRAa, 24 do instalador e ensaio PostgreSQL isolado passaram.

## Histórico 2.6.0 — sequências múltiplas no LIRAa

Usuário pediu expansão de sequências numéricas e alfanuméricas no LIRAa.
Branch `codex/liraa-sequencias`, worktree `C:\endemias-interface`.
Guia: `docs/LIRAA_SEQUENCIAS.md`. Separadores flexíveis, repetidas deduplicadas,
UUIDs estáveis e metadados de origem no JSON existente. Tubitos/leituras e
tratamentos permanecem na primeira unidade. Novos envios podem gerar várias
visitas; lançamentos históricos já importados não são reinterpretados.
Sem DDL ou importação real; produção agora em 2.6.0. Validados 98 testes LIRAa,
16 focados finais, 7 de aplicação via ETL/formulários, 33 de setores, 24 do
instalador e PostgreSQL isolado. Ativação confirmada em 06/11/2026 às 16h11,
release `d219216`. Relatório `ativacao-liraa260-resultado.json`: aplicado/concluído,
backup completo e PostgreSQL realizados, 96 tabelas preservadas, prova limitada
OK incluindo o parser LIRAa, contas/ambiente/Kobo preservados e automação
restabelecida. `.venv/publicacao-260.json`: nove verificações passaram, cinco
entradas na versão 2.6.0, API anônima negada e fontes/templates iguais aos
testados. Nenhuma resposta importada nem dado histórico reprocessado nesta
conferência. Conferir pequeno lote na prévia antes da aplicação operacional.

## Histórico 2.5.0 — continuidade do trabalho de campo

Usuário autorizou as propostas 1, 2, 7 e 8: salvamento automático online,
próxima visita com reaproveitamento escolhido, vínculo com agenda/retornos
confirmados pela gestão e orientações de correção por campo. QR Code somente
explicado; não implementado. Branch `codex/formularios-fluxo-campo`, worktree
`C:\endemias-interface`; produção atual em 2.5.0.
Metadados no envelope JSON existente, sem DDL. Agenda não conclui atividade
apenas por receber formulário; aprovação/aplicação permanecem explícitas.
Kobo e RG offline preservados. Regressão geral: 1.199 testes, seis ignorados e
nenhuma falha. API focada 22 testes, instalador 22, Node/SW, Chromium móvel/
desktop e PostgreSQL isolado passaram. Testados edição durante perda de recibo,
retomada online, próxima visita, correção e confirmação idempotente de retorno.
Ativação confirmada em 06/11/2026 às 15h45, release `5668a5b`.
Relatório `ativacao-formularios250-resultado.json`: aplicado/concluído, backup
completo e PostgreSQL realizados, prova limitada OK, 96 tabelas preservadas,
contas/ambiente/Kobo preservados e automação restabelecida.
`.venv/publicacao-250.json`: 25 verificações públicas/locais passaram; cinco
entradas na versão 2.5.0, JS/CSS dos formulários e agenda iguais aos instalados,
APIs anônimas negadas e catálogo privado não exposto. Não houve criação de
formulário ou evento real nesta conferência; piloto operacional segue necessário.
Guia operacional:
`docs/FORMULARIOS_INTERNOS_KOBO.md`.

## Histórico 2.4.0 — praticidade dos formulários em campo

Pedido em 06/11/2026, após a ativação 2.3.0. Branch
`codex/formularios-campo-praticidade`, em `C:\endemias-interface`.
Dez formulários online com uma coluna, equipe em grade sem rolagem interna,
identificação imutável da conta autora e agente vinculado obrigatório no envio.
Perfil básico pode escolher colegas exclusivamente no formulário, a pedido do
usuário; as regras de anonimização de consultas/relatórios permanecem vigentes.
Sugestões territoriais consultam RG e geometria ativa, sem dados de moradores;
campos livres continuam aceitando digitação. PE e LIRAa mantêm códigos/vínculos
válidos; PE oferece quarteirão antes da rua, com a correspondência preservada.
Sem DDL, mudança de contas ou ampliação do offline. Produção agora em 2.4.0.
Guia: `docs/FORMULARIOS_INTERNOS_KOBO.md`. Regressão: 1.189 testes, seis
ignorados, nenhuma falha; API focada 17 testes, instalador 20, navegador nos dez
tipos e PostgreSQL isolado passaram. Ativação confirmada em 06/11/2026 às
14h17, release `97f0fcb`. Relatório `ativacao-formularios240-resultado.json`:
aplicado/concluído, backup completo/PostgreSQL realizados, prova limitada OK,
96 tabelas preservadas, contas/ambiente/Kobo preservados e automação restabelecida.
`.venv/publicacao-240.json`: 21 verificações públicas/locais passaram; cinco
entradas na versão 2.4.0, JS/CSS publicados, APIs inclusive referências exigem
login e catálogo privado não exposto. Nenhum envio real nesta conferência;
piloto operacional pelo usuário permanece necessário.

## Histórico 2.3.0 — formulários internos equivalentes ao Kobo

Usuário pediu os dez tipos existentes e confirmou revisão por admin antes da
aplicação. Worktree `C:\endemias-interface`, branch `codex/formularios-internos-kobo`.
Definições implantadas consultadas pelo usuário com atalho elevado: 10 tipos,
zero pendências, sem respostas. Arquivo privado não versionável em
`.venv/formularios-internos/definicoes.json`. Guia: `docs/FORMULARIOS_INTERNOS_KOBO.md`.
Captura nova online; RG offline e Kobo mantidos. Endemias recebe 8 tipos e Ambiental 2,
com laboratório condicionado à permissão; perfil básico escolhe o próprio agente.
Aplicação e auditoria confirmam juntas via ETL, sem DDL. Protótipos/ensaios fictícios
passaram nos dez tipos, no navegador e no PostgreSQL descartável. Regressão geral: 1.181 testes, seis ignorados e nenhuma falha. Verificações
focadas finais e navegador também passaram. Ativação confirmada em 06/11/2026 às 13h36, release `bf36464`.
Relatório `ativacao-formularios230-resultado.json`: aplicado/concluído, prova
limitada OK, backup completo e PostgreSQL conferidos, 96 tabelas preservadas,
sem DDL, contas/ambiente/configurações Kobo preservados e automação restabelecida.
`.venv/publicacao-230.json`: 19 verificações públicas/locais passaram, cinco entradas
na versão 2.3.0, JS/CSS publicados, APIs anônimas negadas e catálogo privado
não exposto. Não houve envio de formulário real nesta conferência. Homologação
operacional dos campos e Android físico continua com o usuário no piloto.

## Histórico 2.2.1 — importação Kobo por admin

Primeira tentativa retornou automaticamente à2.2.0, commit `dffb0d7`.
Relatório `ativacao-adminkobo221-resultado.json`: falha na prova de assets,
backup confirmado,96 tabelas preservadas e login do rollback OK.
A prova verificava todas as chaves, embora save_config acrescente chaves
vazias de outros tipos. Agora confere somente UIDs preenchidos; tipos ativos
do setor errado continuam bloqueados (dois testes específicos passaram).
Correção da tela admin reaplicada e teste Node passou. Usuário executou novamente:
relatório aplicado/concluído em06/11/2026 às11h51, release `7b5e289`.
Prova limitada OK;96 tabelas e arquivos operacionais preservados, sem DDL,
configurações Kobo/contas/ambiente preservados e automação restabelecida.
`.venv/publicacao-221.json`: cinco entradas na versão2.2.1 e JS conferido nos
dois domínios. Nenhuma importação real disparada pela verificação; ainda cabe
confirmar o uso com uma conta admin no navegador. Token/servidor/UIDs seguem
reservados ao superadmin. A primeira tentativa e seu rollback ficam no histórico.

## Histórico 2.2.0 — piloto PWA do RG

Preparada em `C:\endemias-interface`, branch `codex/pwa-rg-piloto`, a pedido do
usuário; ativada em06/11/2026 às10h12 após execução elevada pelo usuário.
Decisão expressa: apenas bloqueio de tela Android, sem outra senha/criptografia
local do aplicativo. Guia e limites em `docs/PILOTO_PWA_RG.md`. RG móvel com
autosave, rascunhos por conta, captura versionada, recibos idempotentes e
conflitos preservados; aprovação/oficialização continuam com o gestor.
Cache somente RG/estáticos, renovação online em24h, sem APIs/anexos/relatórios.
Não amplia usuários nem altera Kobo/DNS/serviços de terceiros; sem DDL.
Android físico e iOS não homologados; piloto não significa liberação geral.
Validação: suíte geral1152 testes/6 ignorados; após ajustes finais,10 de
protocolo e16 do ativador; ensaio PostgreSQL descartável(porta55444), Node/SW
e Chromium móvel/desktop. Cobertos fechamento offline, recibos/CAS, devolução,
502, sessão vencida, armazenamento cheio, troca de conta e atualização aguardada.

Ativação confirmada: release `428b4d6`, relatório
`C:\ProgramData\EndemiasWeb\ativacao-pwarg220-resultado.json`,
status aplicado/concluído,96 tabelas preservadas, prova limitada OK, sem DDL,
contas/ambiente/Kobo preservados e automação restabelecida.
Verificação pública/local em `.venv/publicacao-220.json`:24 checagens.
O SW publicado corresponde ao instalado; origem devolve no-cache, mas a
Cloudflare devolve max-age=14400 (4h). Pendente configurar bypass de cache
para `/sw.js` e `/manifest.webmanifest`, evitando atraso em futuras atualizações.
Homologação física no Android segue pendente; não houve ampliação da equipe.

## Histórico: 2.1.1 — logos transparentes e portal claro

Em06/11 usuário entregou três logos novos com contorno branco. Cópias exatas
em `static/img`, sem edição de PNG. CSS remove bases brancas e inversões de
cor; contorno pequeno reforçado sem fundo. Rodapés discretos esclarecem marca
Ambiental não oficial/provisória e, no portal, as duas marcas e a sigla VSATT.
Portal não segue mais o modo escuro do aparelho; setores mantêm seus temas.

Integração em `C:\endemias-interface`, branch `codex/logos-transparentes-211`.
30 testes de setores +14 do ativador passaram; Chromium26 combinações de
tamanho/tema/telas, alpha/cores/avisos, sem erro JS ou overflow. Só interface,
ativos e versão; sem DDL ou dados. Usuário executou o novo atalho: relatório
`C:\ProgramData\EndemiasWeb\ativacao-logos211-resultado.json` aplicado/concluído,
release`3acb327`, janela08h43.96 tabelas/dados/arquivos, contas, dois Kobo,
tarefa/identidade/ambiente preservados; prova limitada OK e agendamento devolvido.
Dezesseis checagens em `.venv/publicacao-211.json`: portal/logins HTTPS e
locais5000/5004 retornam200/2.1.1; APIs anônimas401; avisos e sete ativos públicos
conferem. CSS app publicado igual ao instalado; só CRLF difere da candidata.
Logos byte a byte iguais aos fornecidos, portal sem regra de modo escuro.
SQLite congelado mantém hash. Ver `docs/LOGOS_TRANSPARENTES_211.md`.
Não repetir o atalho2.1.1 nem ativadores anteriores.

## Histórico: 2.1.0 — identidade, logs e ajuda

Usuário solicitou subagentes por frente. Estilo em `C:\endemias-visual`, logs em
`C:\endemias-logs`, ajuda em `C:\endemias-ajuda`; integração isolada em
`C:\endemias-interface`, branch `codex/identidade-logs-ajuda`. Endemias mantém
azul, Ambiental verde com sua marca e portal VSATT usa a marca própria/duas
cores. Ajuda deve respeitar setor e permissões; trilha técnica não deve guardar
segredos ou corpos de formulário. Produção atualizada para2.1.0 pelo usuário.
Sem DDL ou alteração de usuários/dados/Kobo. Ver
`docs/IDENTIDADE_LOGS_AJUDA_210.md` para implantação e verificações deste lote.

Integração terminada. Suíte1.141/sem falhas/seis ignorados, 14 focados finais,
Chromium/CSRF/CSP e PG descartável55444 OK; três processos/600 logs sem perdas.
Logos por hash iguais aos originais e azul do Endemias preservado. Nova ajuda
com matriz cinco níveis×dois setores e laboratório exclusivo; consultas de
gestão separadas da fonte técnica Super, export sem corte silencioso10.000/16MiB.
Prova da conta limitada inclui marcas e rotação privada. Atalho elevado
`Atualizar VSATT - Identidade Logs e Ajuda 2.1.0.bat` já executado; não repetir.
Relatório `C:\ProgramData\EndemiasWeb\ativacao-identidade210-resultado.json`
aplicado/concluído, release`db3f1cb`, janela16h28:96 tabelas/dados/arquivos,
contas, configurações Kobo, tarefa/identidade/ambiente preservados. Prova
limitada OK, sem DDL, agendamento devolvido. Quinze checagens posteriores:
portal/logins HTTPS e locais5000/5004 com200/2.1.0, APIs anônimas401,
seis assets públicos iguais à fonte e IDs de requisição válidos. Prova de
logs privados/rotação OK; conteúdo protegido contra leitura direta pela
conta interativa, não lido nesta conferência. SQLite congelado com hash
preservado. Evidência privada `.venv/publicacao-210.json` na integração.

## Histórico 2.0.2 — BRI/API em 05/11/2026

- Usuário confirmou API como entrada principal, XLSX emergencial. Histórico BRI
  do novo relato já foi conferido por UUID e recomposto pela interface2.0.1, com
  auditoria e preservação dos demais campos. Não repetir. Evidência privada:
  `C:\endemias-interface\.venv\bri-historico\recomposicao-20261105.json`.
- Código2.0.2 em `C:\endemias-interface`, branch `codex/bri-formatos-historicos`:
  contratos API/XLSX unificados, parcelas de carga nulas consideradas e exibição
  de local/endereço.129 testes focados, PG descartável e Chromium OK.
- Usuário executou o atalho. Relatório `C:\ProgramData\EndemiasWeb\ativacao-bri202-resultado.json`
  aplicado/concluído, release`da8a2e5`, janela15h35.96 tabelas/dados/arquivos
  preservados, incluindo recomposição; mesma tarefa/identidade/ambiente e dois
  Kobo, prova limitada OK e agendamento devolvido. Sem DDL; SQLite mantém hash.
- Portal/dois logins HTTPS e locais5000/5004:200/2.0.2; APIs anônimas401; script
  público confere. Tela real autenticada validada, com cargas preservadas e
  estabelecimento/rua ausente explícitos. Evidência `.venv/publicacao-202.json`.
- Ler `docs/BRI_IMPORTACAO_202.md` para backups/limites. Não repetir ativadores
  ou recomposição. A API permanece entrada principal; Geo segue futuro.

## Histórico 2.0.1 — correções em 05/11/2026

- Usuário executou o atalho e confirmou sucesso. Relatório
  `C:\ProgramData\EndemiasWeb\ativacao-correcoes201-resultado.json` aplicado/concluido,
  release `93c5866`, janela15h03.96 tabelas/dados/arquivos/configurações preservados;
  sem DDL; mesma tarefa/identidade/ambiente, prova limitada OK, agendamento devolvido.
  Ler `docs/CORRECOES_201.md` para comportamentos, backups e limites.
- Suíte final 1.102 testes/sem falhas/seis ignorados; 15 focados após ajuste do
  mapa, PostgreSQL descartável e Chromium OK. Três HTTPS e logins locais5000/5004:
  200/2.0.1; APIs anônimas401 e script público confere byte a byte. Evidências
  `.venv/publicacao-201.json` e `.venv/csp-201-publico.json` na worktree de integração.
- Não reimportar históricos automaticamente: BRI foi recomposto por conferência
  explícita no relato posterior acima; não repetir. Contas/setores preservados.
- Regra humana definida pelo usuário: data mais recente determina situação;
  retroativo acrescenta histórico; empate pelo último incluído na mesma data.
- Ativador `scripts/ativar_correcoes_201_windows.py` já aplicado; não repetir
  nenhum atalho anterior. SQLite congelado conserva hash anterior; Geo futuro.

## Histórico 2.0.0 — fechamento e revisão em 05/11/2026

- Usuário aprovou o visual, autorizou 2.0.0 e executou o atalho. Relatório
  `C:\ProgramData\EndemiasWeb\ativacao200estavel-resultado.json` aplicado/concluido,
  release `fa0aba8`, janela 13h29.96 tabelas/dados/arquivos e os dois Kobo preservados;
  mesma tarefa/identidade/ambiente, prova limitada OK, agendamento devolvido.
  Sem DDL/alterações funcionais. Backups/hashes em `docs/VERSAO_200_ESTAVEL.md`.
- Três HTTPS e logins locais 5000/5004: 200/2.0.0, private/no-store; portal sem
  cookie; APIs anônimas: 401. Evidência:
  `C:\endemias-interface\.venv\publicacao-200-estavel.json`.
- Revisão funcional ampla concluída:301 rotas inventariadas,44 combinações de
  páginas/setores,148 GETAPIs,73 navegações por perfil; Chromium27 páginas/33 subabas
  Endemias/comuns e18 páginas/oito subabas Ambiental; suíte de 1.030 testes OK/seis ignorados.
  Dez estruturas implantadas Kobo lidas, nenhuma resposta consultada.
- Relatório detalhado LOCAL na Área de Trabalho `VSATT - Auditoria funcional
  2.0.0.md`, com evidências em `.venv/auditoria-*`. O repositório é público;
  não versionar o diagnóstico técnico pendente. Registro seguro em
  `docs/REVISAO_FUNCIONAL_200_20261105.md`. Ler relatório antes de corrigir;
  as correções dos achados não foram aplicadas nesta etapa.
- Não repetir os ativadores. SQLite congelado mantém hash anterior. Geo futuro.

## Histórico 2.0.0-rc.3 — portal no topo e etiquetas leves

- Usuário aprovou o visual da rc.2 e relatou travamento ao ativar etiquetas no
  mapa Ambiental. Pediu botão para `vsatt.com.br` ao lado da troca de setor.
- Em `C:\endemias-interface`, branch `codex/mapa-leve-atalho-portal`: Portal
  VSATT para contas autenticadas; permissões da troca de setor preservadas.
  Etiquetas em canvas único/área visível, até 300 sem sobreposição, sem refazer
  os polígonos ao marcar/desmarcar. Dados e filtros preservados.
- 69 testes focados OK; Chromium/CSRF/CSP/desktop/celular conferidos. Ensaio
  com 1.500 polígonos/CPU4x: rc.2 10.019,7 ms e candidata 87,5 ms; 6.000 na
  candidata: 316,7 ms. Sem recriar polígonos/1 canvas. Sem DDL ou consulta nova.
- Usuário executou o atalho administrativo e informou conclusão. Relatório
  `C:\ProgramData\EndemiasWeb\ativacao-mapa-portal200rc3-resultado.json`:
  aplicado/concluido, release `2bf6171`, janela iniciada às 12h55 de 05/11.
- 96 tabelas/dados e arquivos operacionais preservados. Nenhuma migração,
  alteração de contas/senhas/Kobo, firewall ou Cloudflare; mesma tarefa,
  identidade e ambiente. Prova da conta limitada OK e agendamento Kobo devolvido.
- Backup PostgreSQL: 7.548.728 bytes/catalogado, SHA-256
  `43e018da3d6dea20bde7d04b3b3c6230f921a0895725f7f032200f95e9aea5a0`.
  Completo: `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261105_125554.zip`,
  310.617.849 bytes, SHA-256
  `f147c9473c765faa6a516483999ab6ae68f0fd8d6f566204f9074e4861467860`.
  SQLite congelado mantém o hash previamente registrado.
- Três HTTPS e logins locais 5000/5004: 200/rc.3; private/no-store, CF DYNAMIC;
  portal sem sessão. APIs anônimas: 401. Scripts e CSS publicados conferidos
  byte a byte contra arquivos oficiais. Evidência:
  `C:\endemias-interface\.venv\publicacao-mapa-portal200rc3.json`.
- Detalhes em `docs/MAPA_PORTAL_200RC3.md`. Usuário ainda não informou teste
  das etiquetas após a correção. Não repetir os atalhos já executados.

## Histórico 2.0.0-rc.2 — interface ativada em 05/11/2026

- Pedido de nove melhorias do usuário: portal com versão e visual institucional;
  troca autorizada no topo; relatórios/filtros e dashboard/gráficos ambientais;
  gota do Vigiágua; mapa com ruas/satélite/etiquetas/filtros; início simplificado;
  setas e previsão visível na agenda dos dois setores.
- Usuário executou o atalho e informou conclusão. Relatório
  `C:\ProgramData\EndemiasWeb\ativacao-interface200rc2-resultado.json` confirma
  `aplicado/concluido`, release `2772226`, janela iniciada às 11h20.
  Master integrada; sem migração, alterações de contas/senhas ou divisão de Kobo.
- 96 tabelas/dados e arquivos operacionais preservados; configurações dos dois
  Kobo, tarefa/identidade/ambiente preservados. Prova na conta limitada passou
  em todos os checks. Agendamento Kobo devolvido ao estado original. Sem
  mudança de firewall, Cloudflare ou restauração de banco.
- Backup PostgreSQL: 7.545.887 bytes, catálogo validado, SHA-256
  `732661726d274d6b087736065367e4992807eff3cc445d562d0c94dee931ae0b`.
  Completo: `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261105_112051.zip`,
  310.615.133 bytes, SHA-256
  `25cfbdc93727878849360f2d118194802230933cde2bb6742e1d23c7f4ec8493`.
  SQLite congelado mantém hash `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
- Portal e dois logins HTTPS: 200/rc.2, `private, no-store`, CF DYNAMIC.
  Portal sem sessão e com os dois links. APIs anônimas: 401. Logins locais
  5000/5004: 200/rc.2. Cloudflared automático/rodando. Evidência:
  `C:\endemias-interface\.venv\publicacao-interface200rc2.json`.
- Suíte de preparação: 1.024 OK, seis ignorados; 41 focados OK; Chromium e
  PostgreSQL descartável confirmados. Capturas de desktop/celular conferidas.
  Limites e procedimento em `docs/INTERFACE_SETORES_200RC2.md`.
  Usuário aprovou o visual da rc.2 e relatou peso das etiquetas, tratado na rc.3; não declarar
  2.0 estável. Não repetir os atalhos já aplicados. Geo continua futuro.

## Histórico 2.0.0-rc.1 — divisão ativada em 05/11/2026

- Usuário executou o atalho administrativo e informou conclusão. Relatório
  `C:\ProgramData\EndemiasWeb\ativacao-setores200rc1-resultado.json`:
  `status=aplicado`, `stage=concluido`, release `29b478a`, janela 09h04.
  Somente 0035 aplicada; 96 tabelas/colunas anteriores comparadas e preservadas,
  assim como arquivos operacionais, chave, config e SQLite congelado. Contas,
  níveis e senhas preservados; contas comuns continuam Endemias.
- Backup PostgreSQL de 7.541.541 bytes/catalogado, SHA-256
  `57c00bdfb971c3f5b89153950061949ca8b4678bc4cc034ebe48fdeeb21b763c`.
  Completo anterior à 0035: `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261105_090441.zip`,
  310.611.983 bytes, SHA-256
  `b8974c9f1ef756dbbba2bff95bb58cd41eb1764c87b91704162295c2e1b511b3`.
  Restaurar este completo para código 2.0 exige aplicar 0035 antes de abrir uso.
- Mesma tarefa/identidade/credencial do servidor. Prova real na conta limitada
  passou em todos os checks, incluindo escrita controlada nos dois Kobo,
  chaves por setor, três hosts, negação anônima, backup SQL e código sem escrita.
  Tarefa Kobo das 12h30 encontrada e devolvida ao estado original; mesmo horário
  e identidade. Executor agora seleciona os dois setores separadamente.
  Primeira execução automática após a divisão ainda não conferida.
- LAN Endemias 5000 e Ambiental 5004 respondem 200 no servidor; origem Tunnel
  127.0.0.1:5001 responde aos três Hosts corretamente. Regra Ambiental criada
  só para interface/sub-rede local e perfis privado/domínio. Teste de outro
  aparelho confirmado pelo usuário em 05/11. **Reinício real confirmado:**
  usuário informou sucesso; LastBootUpTime passou de 04/11 09h49 para
  05/11/2026 09h21. Cloudflared automático/rodando, portas locais e origem
  corretas e três HTTPS 200 após o boot; logins dos setores seguem 2.0.0-rc.1
  com no-store/private. Perda real da internet ainda não simulada.
- **Publicação dos três hosts confirmada em 05/11:** usuário salvou as rotas
  no mesmo Tunnel. Portal `https://vsatt.com.br` 200, links corretos e sem cookie
  do sistema; `https://endemias.vsatt.com.br/login` e
  `https://ambiental.vsatt.com.br/login` 200/2.0.0-rc.1, cada título correto,
  `no-store, private` e CF DYNAMIC. APIs anônimas dos dois setores retornam 401.
  HTTP 301 para HTTPS nos três, TLS 1.0/1.1 recusados com alerta de versão,
  certificados conferidos e TLS 1.2/1.3 aceitos. Evidência local:
  `C:\endemias-setores\.venv\publicacao-setores-tls.json`.
- Usuário confirmou acesso com sua conta real aos dois setores pelo portal e
  abertura do login Ambiental em outro aparelho da rede local. Não foram
  alteradas contas comuns, senhas ou níveis. Estética continua adiada.
- Prévia fictícia aprovada pelo usuário em 05/11. Estética do Ambiental/portal
  ficou para depois. Não marcar 2.0 estável antes das conferências operacionais.
  Geo permanece futuro. Não repetir o atalho de atualização já aplicado.

## Histórico da preparação 2.0.0-rc.1 — antes da ativação

- Worktree `C:\endemias-setores`, branch `codex/divisao-setores-2`; produção
  continua 1.80.0. Portal raiz e aplicações Endemias/Ambiental por Host exato,
  setores das contas independentes do nível, sessões/agendas/Kobo e consultas
  separados. Meteorologia comum; Esporotricose integral/Amostras só Ambiental.
- Usuário esclareceu: agentes Endemias registram Esporotricose apenas no Kobo;
  gestão web só Ambiental. Sem exceção de acesso; vínculos históricos mantidos.
- 0035 aditiva preparada, não aplicada à produção; contas/eventos antigos
  permanecem Endemias até revisão, históricos mistos preservados como legado
  na Central. Nenhuma conta/senha/dado/serviço/DNS alterado nesta preparação.
- `ENDEMIAS_SETORES_ENABLED` exige ativação explícita e esquema pronto. Não
  integrar templates na master com processo antigo ativo nem usar ativador
  antigo. Implantação Windows/ACL/configuração Kobo/rotas Cloudflare/LAN 5004,
  homologação real e reinício ainda pendentes. Geo permanece após 2.0.
- Validação concluída: suíte geral de 1.001 testes OK (seis ignorados),
  incluindo 21 novos testes da divisão; 29 focados de setores/Kobo automático OK.
  Chromium/CSRF/desktop/celular e três entradas Waitress conferidos; PostgreSQL
  novo em 55444/SCRAM confirmou 0035 aditiva, consultas, relatórios e agendas.
  Cluster/credenciais temporários removidos, sem listeners de teste restantes.
  Login público 200/1.80.0 e no-store/private reconfirmados; hash do SQLite
  congelado permanece `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
- Ver `docs/DIVISAO_SETORES_200.md` para regras, limites e procedimento.

### Histórico do pacote de implantação em 05/11 — executado depois

- Usuário conferiu a prévia fictícia e aprovou seguir com a divisão. Ajustes
  estéticos do Ambiental e do portal ficaram para depois. Confirmou manter
  todas as contas comuns em Endemias; gestores continuam nos dois setores.
- Pacote `scripts/ativar_setores_windows.py`: backup PostgreSQL e completo,
  assinatura por colunas anteriores à 0035, preservação de anexos/chave/config/
  SQLite congelado, divisão privada do Kobo, prova na mesma identidade limitada
  e retorno de código/configuração sem restaurar dump ou reduzir esquema.
- Inclui prova dos três hosts na conta limitada e entrada Ambiental LAN 5004,
  com regra somente para a interface local/sub-rede, perfis privado/domínio.
  Não altera a tarefa/credencial do servidor nem o Tunnel.
- Importação diária das 12h30 existia no histórico. O pacote a consulta de forma
  elevada, pausa o agendamento na janela e devolve seu estado original. O mesmo
  executor passa a chamar Endemias/Ambiental separadamente, preservando horário,
  identidade e credencial; não cria tarefa nova nem faz importação real no ensaio.
- 46 verificações focadas OK; última rodada de instalador/executor: 10 OK.
  Simulações de sucesso/retorno e PowerShell com programas fictícios conferidas.
  PostgreSQL temporário confirmou que o novo comparador aceita ADD COLUMN e
  detecta alteração de valores antigos. Cluster e senhas temporários removidos.
- A execução elevada, confirmação na identidade real, novos DNS/rotas, teste
  LAN em outro aparelho e reinício continuam pendentes. Produção ainda 1.80.0.
  Não confundir pacote aprovado com ativação concluída. Conferir o relatório
  `C:\ProgramData\EndemiasWeb\ativacao-setores200rc1-resultado.json` após execução.

## Histórico 1.80.0 — correções de segurança preservadas

- Usuário executou o ativador manualmente e informou conclusão. Relatório
  `C:\ProgramData\EndemiasWeb\ativacao180-resultado.json` aplicado/concluído;
  snapshot `ativacao180-20261104-143513`, release `31fb0e2`, 04/11 às 14h35.
  Backup PostgreSQL de 7.538.186 bytes/catalogado, somente 0034 aplicada.
  93 tabelas anteriores e chave/Kobo/config/SQLite congelado preservados.
  Nenhum perfil/senha real alterado. Mesma tarefa/identidade/ambiente e portas.
- Nove pacotes instalados de wheels locais com hashes/pins e pip check OK.
  Relatório `seguranca180-preparacao.json` confirma ACL da raiz/das duas cópias
  antigas sem grupos amplos e hashes preservados; ACL de arquivo reconferida.
  Ensaio EndemiasWeb com todos os checks verdadeiros, incluindo backup real.
- Backup completo atual criado com aplicação parada, antes da migração:
  `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261104_143519.zip`,
  310.610.296 bytes, SHA-256
  `9d6964ee4dc400c943a70c05aa2413e6283b36f175f3754e27644e6095172c0d`.
- **Restauração real isolada concluída:** script
  `scripts/validar_backup_completo_isolado.py`, worktree de manutenção,
  pasta privada antes da extração, PostgreSQL temporário 127.0.0.1:55443 com
  senha aleatória/SCRAM. 96 tabelas restauradas, 663 arquivos/configurações
  conferidos byte a byte por hash, zero índices inválidos e superadmin único.
  Não iniciou aplicação com as credenciais restauradas. Instância encerrada,
  cópias expandidas e credenciais temporárias removidas; origem/produto intactos.
  Resultado local `.venv/restauracao180-resultado.json`. Snapshot é anterior à
  0034; recuperação para código 1.80 exige essa migração antes de liberar uso.
- Às 14h45, sonda PowerShell confirmou HTTPS/login 200/1.80, nonces diferentes
  por resposta, private/no-store/DYNAMIC, API BRI anônima 401 e Central 302 para
  login. Sonda urllib recebeu 403 e não foi usada como confirmação de versão.
  Origem e LAN 200 no ativador. PostgreSQL permanece só loopback; 55443 encerrado.
- 980 testes gerais OK (seis ignorados), 16 focados adicionais e nove dos
  ativadores; Chromium com CSRF real e política CSP final conferido. Usuários
  precisam entrar novamente. Reinício completo após 1.80 ainda não ensaiado;
  tarefa/credencial/inicialização automática existentes preservadas.
- **Cloudflare concluída:** após orientação por atalho para Edge Certificates,
  usuário informou "Pronto". Às 14h56, conexões TLS 1.0/1.1 foram recusadas com
  alerta de versão, 1.2/1.3 aceitas e HTTP retornou 301 para HTTPS oficial.
  Nenhum ajuste de conta/Tunnel/firewall foi feito pelo agente para isso.
- Pendências: HTTPS local, segundo fator do Endemias e primeira cópia externa
  criptografada conferida. Windows mantido por decisão do usuário.
- **Google Drive definido:** usuário já envia pastas inteiras do sistema/backups
  à conta pessoal. Informa acesso somente seu e verificação em duas etapas na
  conta Google; não auditados pelo agente. Aprovou envio manual dos novos backups
  completos `.zip.7z`, frase separada e preservação das cópias antigas até conferir
  a nova. Não confundir relato de cópias antigas com validação de restauração ou
  confirmação do primeiro upload cifrado. Agente não acessou/alterou Drive, não
  enviou/excluiu arquivos nem configurou automação. Ver `ROTINA_BACKUP_GOOGLE_DRIVE.md`.

### Preparação anterior à ativação 1.80 — histórico

- Worktree `C:\endemias-seguranca`, branch `codex/correcao-seguranca`. BRI,
  Amostras, cartões do mapa e tipos do Conta Ovos escapam texto. Scripts dos
  templates recebem nonce; strict-dynamic e bloqueio de eventos inline nas
  telas já migradas. Outros módulos ainda têm eventos inline por compatibilidade.
- Sessões persistidas/revogadas (0034), limite absoluto de oito horas e recusa
  de cookie anterior à atualização; todos precisarão entrar novamente.
  Fórmulas CSV neutralizadas, coordenadas preservadas, lista de senhas comuns.
- Downloads de backups somente superadmin, via frase exclusiva/7z AES-256;
  rede local HTTP remota recusada para não expor a frase. ZIPs/dumps originais
  permanecem privados no servidor. Nova dependência py7zr e nove wheels locais
  com hashes versionados; OSV sem alertas nos nove pacotes consultados.
- Ativador prepara pacotes e ACL das duas cópias antigas em D:\BackupsEndemias,
  preserva hashes e registra ACL anteriores. Só depois faz a janela comum de
  backup/0034/ensaio/retorno, sem redefinir senhas ou perfis. Não executado nesta
  preparação; produção permanece 1.79. Ver `CORRECOES_SEGURANCA_180.md`.
- Chromium/CSRF real, ataque com CSP desativada e ativa, cookie copiado, mapa e
  download/restauração fictícia conferidos. PostgreSQL descartável em 55442
  confirmou migração, revogação, expiração e isolamento entre sessões; encerrado.
- Regressão final: 980 testes OK, seis ignorados; 16 focados adicionais e
  navegador após a política CSP final também OK. SQLite congelado mantém o
  SHA-256 `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
  Ativador deste lote cria também backup completo com a aplicação parada,
  para disponibilizar uma cópia atual ao ensaio de restauração real posterior.
- Pendências explícitas: TLS mínimo/HTTPS redirect na Cloudflare (controle
  interrompido por não conseguir confirmar URL; ensaio ainda aceita TLS 1.0/1.1
  e HTTP 403 sem redirect), HTTPS local, segundo fator, cópia externa e ensaio
  completo de restauração real em ambiente privado. Usuário perguntou sobre
  nuvem; explicado fluxo de upload do arquivo já cifrado, sem enviar dados.
  Dispõe só de conta pessoal: explicado funcionamento técnico, preferência
  por controle institucional e necessidade de observar as regras do setor.
  Windows segue como está por decisão do usuário. Nenhum desses riscos foi
  declarado resolvido pelo pacote. Não tentar contornar o bloqueio do navegador.

## Histórico 1.79.0 — superadmin e gestão delegada

- Ativação posterior confirmada pelo relatório privado
  `C:\ProgramData\EndemiasWeb\ativacao179-resultado.json`: aplicado/concluído,
  snapshot `ativacao179-20261104-115828`, release `02701c2`. Backup de 7.536.799
  bytes com catálogo validado; somente 0033 aplicada. Assinaturas de 93 tabelas
  anteriores e arquivos protegidos preservados antes da promoção autorizada.
  `joao`/id 2 é superadmin; todas as outras contas preservadas, zero resets reais.
- Ensaio EndemiasWeb com todos os checks verdadeiros; mesma tarefa/identidade/
  ambiente/portas, logins LAN e origem externa 200. HTTPS oficial 200/1.79.0
  reconfirmado em 04/11. O primeiro pedido automático de elevação foi cancelado;
  não confundir com esta ativação posterior concluída. Não repetir o ativador.
- Reinício completo após 1.79 não ensaiado; automação existente preservada.
  Revisão de segurança trazida pelo usuário em 04/11 motivou preparação isolada
  posterior em `C:\endemias-seguranca`, `codex/correcao-seguranca`; não é versão
  ativa ainda. Windows sem ESU permanece por decisão do usuário; HTTPS local e
  segundo fator exigem avaliação operacional, sem imposição automática.

### Preparação anterior à ativação 1.79

- Usuário confirmou a conta pessoal `joao`, id 2, como único superadmin.
  Implementação na worktree `C:\endemias-superadmin`, branch
  `codex/superadmin-permissoes`. Admin mantém operação e gestão de contas
  inferiores; Central/backups/credenciais Kobo e gestão de admins são técnicas.
  Conta superadmin protegida na web, índice único e recuperação local Windows.
- 964 testes gerais OK (sete ignorados), ensaio PostgreSQL descartável e
  Chromium com CSRF real/celular. Ver `SUPERADMIN_PERMISSOES.md`.
- Naquele momento ainda não ativada; a produção era 1.78.0 descrita abaixo.
  Ativador exige essa origem, backup validado, somente migração 0033 e promoção
  de `joao`/id 2, comparando todas as outras contas. Não altera suas senhas.

## Histórico 1.78.0 — presença de usuários ativa

- Ativada em 04/11/2026 às 10h55, release `7e1a3fe`, após autorização do
  usuário. Gestão de Usuários mostra presença, última vez online e total,
  somente admin. Sinais visíveis a cada 30s, janela 120s, múltiplas abas/aparelhos,
  logout isolado e invalidação após troca de senha/desativação. Polling não
  renova cookies continuamente. Coleta inicia agora; páginas anteriores devem
  ser recarregadas. Não reconstruir presença a partir dos logins históricos.
- Backup de 7.530.824 bytes com catálogo validado; apenas 0032 aplicada.
  Assinaturas/contagens de 91 tabelas anteriores e chave/Kobo/config/SQLite
  congelado preservados. Mesma tarefa/credencial/ambiente EndemiasWeb e portas;
  conector, PostgreSQL e firewall preservados. Nenhuma senha real redefinida.
- Relatório privado `C:\ProgramData\EndemiasWeb\ativacao178-resultado.json`:
  aplicado/todos os checks verdadeiros. Snapshot `ativacao178-20261104-105523`.
  Ensaio limitado confirmou identidade, permissões, SQL, backup, XLSX/PDF,
  rotação e login. Às 10h56, HTTPS e LAN/loopback 200/1.78.0, API de sinal sem
  sessão 401 e consulta administrativa anônima redirecionada ao login,
  private/no-store/DYNAMIC; recurso JS público entregue 200, com cache estático.
- 949 testes gerais passaram (sete ignorados), focados adicionais do pacote/
  conta exclusiva/termo, PostgreSQL descartável e Chromium/CSRF/celular. Zero
  erros JS, expiração/retomada, várias abas/aparelhos, data Brasília e ausência
  de renovação do cookie por polling conferidos. Menu do usuário também abre
  no primeiro clique. Ver `PRESENCA_USUARIOS.md`. Worktree `C:\endemias-presenca`,
  branch `codex/presenca-usuarios`.
- Reinício do Windows após 1.78 ainda não ensaiado; a inicialização automática
  foi preservada. Backups/restauração isolada e uso funcional pela equipe
  continuam em acompanhamento; limitações do Windows já registradas permanecem.

## Histórico 1.77.0 — recuperação assistida ativa

- Ativada em 04/11/2026 às 10h23, release `3f35afe`, após solicitação do
  usuário. Gestão de Usuários oferece link de recuperação (15 minutos/uso único);
  titular escolhe a senha. Login oferece orientação "Esqueci minha senha".
  Sem envio automático por e-mail/mensagens; identidade confirmada pelo responsável.
- Backup prévio de 7.526.925 bytes com catálogo validado; somente 0031 aplicada.
  Assinaturas/contagens de 90 tabelas anteriores preservadas; chave/Kobo/config/
  SQLite congelado iguais. Nenhuma conta real teve senha alterada ou link gerado
  pelo ensaio. Mesma tarefa/identidade/credencial e ambiente, sem alterar
  Cloudflared, PostgreSQL, firewall, portas ou inicialização automática.
- Ensaio sob EndemiasWeb confirmou permissões, SQL sem privilégios administrativos,
  XLSX/PDF, rotação, backup e login. Relatório privado aplicado/todos os checks
  verdadeiros: `C:\ProgramData\EndemiasWeb\ativacao177-resultado.json`, snapshot
  `ativacao177-20261104-102300`. Primeira chamada foi recusada antes de mudar
  qualquer recurso por divergência no commit de origem; chamada final usou SHA
  consultado diretamente e concluiu. Relatório de falha anterior é histórico.
- Às 10h24, HTTPS oficial/login/esqueci-senha/recuperar-senha 200/1.77.0;
  private/no-store/DYNAMIC, cookie Secure/HttpOnly e recuperação no-referrer.
  LAN e loopback:5000 confirmados 200. Reinício do Windows após esta versão
  ainda não ensaiado; inicialização 1.76 já foi validada conforme abaixo.
- Validação: 928 testes gerais passaram (sete ignorados), focados adicionais,
  PostgreSQL descartável com concorrência e Chromium/CSRF real/celular. Ver
  `RECUPERACAO_SENHA.md`. Desenvolvimento isolado em `codex/recuperacao-senha`,
  worktree `C:\endemias-recuperacao-senha`.

## Produção 1.76.0 publicada e reinício confirmado — 04/11/2026

- Ativação concluída às 09h08, release `f425cc8` integrada na master com a
  aplicação parada. Backup PostgreSQL de 7.523.821 bytes com catálogo validado;
  apenas 0030 aplicada. Contagens/assinaturas das 90 tabelas anteriores iguais,
  chave/Kobo/config/SQLite congelado preservados. Zero aceites reais no ensaio.
- Mesma tarefa/credencial EndemiasWeb, agora Waitress: LAN/loopback:5000 e
  origem Tunnel só 127.0.0.1:5001. PostgreSQL confirmado 127.0.0.1/::1:5432,
  sem escuta LAN. Login 200/1.76.0 e cookies separados conferidos às 09h16.
- Relatório privado `C:\ProgramData\EndemiasWeb\ativacao176-resultado.json`:
  aplicado, todos os checks verdadeiros; snapshot/backup em
  `ativacao176-20261104-090744`. Não usar o retorno de conta/ACL de 03/11:
  helper antigo agora recusa versão/servidor posteriores. Retorno da ativação
  é automático durante sua execução; eventual retorno tardio exige plano
  específico, preservando banco/0030/aceites, sem restaurar dump sobre dados novos.
- **Publicação oficial concluída:** usuário acessou `endemias.vsatt.com.br`;
  em 04/11 às 09h35 conferidos login HTTPS 200/1.76.0, API sem sessão 401,
  home redirecionada ao login, cookie Secure/HttpOnly, CSP/HSTS e respostas
  private/no-store/CF-Cache-Status DYNAMIC. Não foi feito login automatizado
  com conta real; funcionamento autenticado informado pelo usuário.
- **Reinício confirmado:** Windows iniciou às 09h49; usuário confirmou que
  voltou a funcionar. Às 09h58 reconfirmados HTTPS e suas proteções, login
  LAN/loopback 200/1.76.0, mesmo processo nas entradas 5000/5001, PostgreSQL
  somente 127.0.0.1/::1:5432 e serviços Cloudflared/PostgreSQL Running/Auto.
  Nenhum processo/serviço foi iniciado manualmente pelo agente após o boot.
  Não confundir com o piloto fictício, que continua manual.
- Pendências operacionais: conferir funções usadas pela equipe no endereço
  oficial e rotina de backups/restauração em ambiente separado. Não restaurar
  dump sobre a produção para ensaiar. Limitação de atualizações do Windows
  permanece conforme decisão do usuário; VPS é intenção futura.
- Regressão: 910 testes passaram (sete ignorados); cinco focados de ativação,
  piloto HTTP e navegador passaram. Evidências em `CLOUDFLARE_VALIDACAO_EXTERNA.md`.

### Validações anteriores à ativação

- Usuário escolheu `endemias.vsatt.com.br` para o sistema oficial e confirmou
  que a equipe ainda não usa o formulário RG offline.
- Piloto HTTPS validado com três perfis, permissões/propriedade de rascunho,
  três XLSX reabertos, PDF reaberto, upload/SSE, CSRF e navegador desktop/celular
  com RG offline e limpeza de cache no logout, sem erros JavaScript.
- Conector Cloudflared aplicado como `NT SERVICE\Cloudflared`, sem administrador
  e com privilégios reduzidos; SID real/retorno HTTPS conferidos. Token continua
  em arquivo protegido, sem leitura de seu conteúdo ou alteração de argumentos.
- Prévia SQL somente leitura: sete contas ativas, quatro administradores,
  sem alterar permissões/senhas. Migrações anteriores íntegras, somente 0030
  pendente. IP LAN é manual/fixo. Plano em `CLOUDFLARE_VALIDACAO_EXTERNA.md`.
- Esse pré-voo foi seguido da ativação local acima; 0030 não está mais pendente.

## Piloto externo com dados fictícios — publicado em 03/11

- **04/11, após reinício do Windows:** Cloudflared iniciou Running/Auto e
  produção respondeu 200/1.75.0 na porta 5000. Piloto não tinha listeners
  5002/5003; o hostname público retornou 502. Iniciado novamente somente
  `scripts/piloto_web.py` na worktree; HTTPS voltou a 200/1.76.0 e API sem
  login a 401, ambas com `private, no-store`. Sem alteração de tarefa, serviço,
  DNS, firewall ou banco real. Piloto continua manual; após reinício, usar
  `C:\endemias-cloudflare\piloto_web.bat`. O conector automático não inicia a
  aplicação de teste. Não confundir esse comportamento com falha de produção.

- Usuário criou/conectou `vsatt-piloto` na Cloudflare e publicou somente
  `https://piloto.vsatt.com.br` para 127.0.0.1:5003. O processo isolado em
  `C:\endemias-cloudflare` usa SQLite fictício, sem credenciais/dados reais.
- HTTPS real confirmou login 200/1.76.0, API sem login 401, home redirecionada
  ao login, cookie Secure/HttpOnly, CSP/HSTS e respostas privadas sem cache.
  Usuário confirmou login, termo e novo acesso sem repetir o mesmo termo em
  03/11. Testes funcionais mais amplos concluídos em 04/11, conforme acima.
- Cloudflared era LocalSystem em 03/11; desde 04/11 usa conta virtual limitada
  `NT SERVICE\Cloudflared`. Token não foi consultado/exportado pelo agente.
- O piloto usa apenas dados fictícios. Produção local atualizada separadamente
  em 04/11, conforme abertura deste documento; hostname oficial já publicado.
- Detalhes na branch `codex/preparar-cloudflare`, documento
  `docs/CLOUDFLARE_INFRAESTRUTURA.md`. Piloto sem autostart, mesmo com conector
  automático; iniciar `piloto_web.bat` na worktree se necessário após reinício.

## Conta limitada do servidor — aplicada em 03/11/2026

- Usuário autorizou aplicar as proteções locais enquanto mantém o Windows atual;
  VPS é intenção futura. A tarefa `Endemias - Servidor` passou de SYSTEM para
  a conta dedicada `EndemiasWeb`, sem privilégios administrativos ou login
  interativo/RDP/rede do Windows. Confirmação HTTP 200/1.75.0 às 16h05.
- Python e componentes próprios em `C:\ProgramData\EndemiasWeb`; código,
  templates e dependências sem escrita pela conta web. Chaves/credenciais
  protegidas; mesma chave e configuração Kobo, sem trocar tokens/senhas reais.
- Ensaio antes da troca confirmou identidade, permissões efetivas, SQL sem
  privilégios administrativos, escrita operacional, XLSX/PDF, rotação, login
  e backup com catálogo validado. Backup prévio e retorno privados guardados.
  Hashes de app/chave/Kobo/config/SQLite congelado preservados.
- Na etapa de 03/11 o código permaneceu **1.75.0**, sem integração da 1.76.0,
  migração, alteração do PostgreSQL/firewall/DNS ou publicação do Tunnel. O
  usuário confirmou login por outro aparelho da rede local.
- Logs/status/temporários da aplicação agora em ProgramData; backups manuais
  da interface em `D:\BackupsEndemias\backups_web`. Backups automáticos e
  importação agendada continuam nos caminhos/identidades anteriores.
- Detalhes, limitação da listagem de backups, retorno e próximos passos em
  `docs/CONTA_LIMITADA_WINDOWS.md`. Não reinstalar a tarefa pelo configurador
  histórico SYSTEM; o atalho de reinício usa a tarefa já registrada.

## Integração operacional LIRAa — código 1.75.0 ativo

- Usuário autorizou a integração gradual, abrangendo todas as consultas/relatórios pertinentes, e depois autorizou expressamente a atualização do banco e o reinício. Branch `codex/liraa-integracao-gradual`, worktree `C:\endemias-liraa-correcoes`; código integrado na `master` em `a0d3c3c`.
- Visitas, tubos e leituras permanecem nas tabelas LIRAa. Conexões de consulta explicitamente integradas unem os registros aos da rotina; as gravações são encaminhadas aos serviços próprios, sem duas cópias editáveis. Importação geral/automática e XLSX completo, fila/histórico comuns, notificações, arboviroses, relatórios individuais/do setor, produção do laboratório, painel, mapa, positividade, boletim mensal e consolidados abrangidos.
- Mantém plano real, assinatura, cinco sorteios, 261 sorteados + seis adicionais, datas, regras específicas do boletim e ACS ainda provisórios. Positivo de aegypti gera um foco por visita, exceto a notificação em terreno baldio; correção negativa desativa a fila sem apagar histórico. Albopictus permanece no laboratório/boletim.
- Migração aditiva 0029 vincula focos LIRAa e registra origem/UUID das leituras. Não altera tipos antigos nem transfere visitas entre tabelas. Aplicada como única migração pendente, depois do backup PostgreSQL com catálogo validado: `D:\BackupsEndemias\backups_banco\pre_liraa175\endemias_pre_liraa175_20261103_113206.dump` (7.520.438 bytes). Não houve reconciliação porque não existiam visitas LIRAa.
- **Ativo em 03/11/2026 às 11h32 (America/Sao_Paulo)**: `/login` respondeu HTTP 200 com `1.75.0`. Contagens/assinaturas dos dados anteriores em 15 tabelas (11 LIRAa, visitas, coletas, resultados e focos), SQLite congelado e XLSX aprovado iguais antes/depois. Verificador somente leitura retornou código 0: ciclo 4, cinco sorteios, assinatura correta, 267 quarteirões correspondentes ao formulário, nenhum sem RG/geometria e zero visitas. Nenhuma importação, leitura, novo sorteio ou publicação no Kobo foi executada.
- Validação: 876 testes gerais sem falhas (cinco ignorados), três JS LIRAa e PostgreSQL 18 temporário incluindo relatórios, consolidado e leitura Kobo. Ver `docs/LIRAA_INTEGRACAO_OPERACIONAL.md`.

## Logradouros do RG no formulário — código 1.74.0

- Solicitação de 03/11: ao escolher localidade/quarteirão, oferecer as ruas RG correspondentes, com **Outro — digitar** e complemento obrigatório. Lista embutida para uso offline. O importador verifica o contexto da escolha e guarda o nome; aceita texto livre dos formulários anteriores.
- Essa solicitação autoriza revisar o campo Logradouro do modelo manual aprovado, acrescentar `Logradouro_outro`, lista e versão. Os demais campos/regras, 267 quarteirões com os 6 adicionais, datas, ciclo e assinatura permanecem preservados. A fonte XLSX não muda. Os **ACS ainda são provisórios e podem mudar depois**.
- Conferência somente leitura do PostgreSQL: 267 quarteirões com 976 opções RG, nenhum sem ruas. Arquivo compilado com pyxform 4.5.0 sem avisos; filtro conferido em 535 combinações. 859 testes gerais sem falhas (5 ignorados), 74 focados finais, 2 JS e ensaio PostgreSQL 18 descartável passaram. Preparado na worktree `C:\endemias-liraa-correcoes`, branch `codex/liraa-logradouros-rg`, integrado e enviado à `master` em `1256d97`.
- **Ativo em 03/11/2026 às 09h04 (America/Sao_Paulo)**, após nova autorização de reinício do usuário: `/login` respondeu HTTP 200 com `1.74.0`. Contagens/assinaturas das 11 tabelas LIRAa iguais antes/depois, XLSX-fonte e SQLite congelado preservados. Verificador somente leitura retornou código 0; nenhum dado do plano ou visita foi modificado. Sem migração ou publicação no Kobo.
- Substituir/implantar o XLSForm no mesmo projeto Kobo e atualizar os aparelhos continua sendo operação manual. Conferir versão ativa do importador antes de importar respostas novas. Ver `docs/LIRAA_LOGRADOUROS_RG.md`.

## Ampliação de campo confirmada em 03/11/2026 — código 1.73.1

- Usuário esclareceu que os quarteirões extras do formulário são intencionais e devem permanecer no sistema. São Rosana **1030 e 1032**, São João Batista **613 e 619**, Tranqueira **518 e 548**.
- Os 6 adicionais estão registrados em `app_core/data/liraa_adicionais.json`, vinculados ao ciclo 4 e à assinatura do sorteio aprovado. Pertencem aos estratos já cadastrados. O plano de campo tem **261 sorteados + 6 adicionais = 267**; o sorteio congelado, N/n, sua assinatura/histórico e o formulário aprovado não são reescritos. Sem migração ou escrita nas tabelas do planejamento.
- Mapa, KML e PDFs identificam os adicionais. A importação usa vínculo `adicional`, respeitando ciclo/período/assinatura/estrato, e o laboratório os identifica. Os boletins incluem os resultados adicionais nos totais, detalhando quantos imóveis/tubitos/positivos vieram da ampliação. A amostra programada original é mantida.
- Prévia somente leitura executada no PostgreSQL real com o código novo: assinatura confere, 5 sorteios, 267 quarteirões de campo correspondentes ao formulário, sem estratos sem sorteio, quarteirões sem RG ou geometrias ausentes; nenhuma visita no ciclo. Os ACS ainda não são considerados uma definição definitiva e continuam editáveis.
- Em 03/11, `/login` confirmou HTTP 200 com `1.73.0`. A ativação anterior terminou em **30/10/2026 às 17h46**, após confirmação UAC, e preservou contagens/assinaturas das **11 tabelas LIRAa** e o SQLite congelado. O processo havia ficado aguardando a confirmação do Windows no encerramento do chat e terminou depois.
- Validação de `1.73.1`: **853 testes gerais sem falhas (5 ignorados)**, 68 focados finais, 2 testes JS, ensaio PostgreSQL 18 descartável e PDFs renderizados/conferidos. Código integrado e enviado à `master` em `47afeef`.
- **Ativação concluída em 03/11/2026 às 08h30 (America/Sao_Paulo)**, com autorização vigente: `/login` confirmou HTTP 200 com `1.73.1`. A comparação antes/depois preservou contagens e assinaturas das **11 tabelas LIRAa** e o hash do SQLite congelado. Verificador somente leitura retornou código 0: ciclo 4, assinatura correta, 5 sorteios, 261 sorteados + 6 adicionais = 267, formulário correspondente, nenhum sem RG/geometria e zero visitas. Nenhuma migração, novo sorteio, importação, leitura ou alteração no Kobo foi executada. Fonte aprovada XLSX manteve SHA-256 `01934925d87a5f9413628f9f0ccae8d4022f964ad1f12ccc8a441b10f49a88dd`. Ver `docs/LIRAA_CORRECOES_2026_10.md`.

## Lote LIRAa de 30/10/2026 — código 1.73.0

- Usuário autorizou as correções da auditoria e confirmou: **ciclos, estratos, N e sorteios salvos são reais**, destinados ao próximo LIRAa. As visitas existentes são testes. A limpeza dessas visitas não integra este lote e não autoriza remover o plano.
- Formulário aprovado: cópia integral versionada em `app_core/data/liraa_ciclo_aprovado.xlsx`, SHA-256 `01934925d87a5f9413628f9f0ccae8d4022f964ad1f12ccc8a441b10f49a88dd`. Ciclo 4, período 09–13/11/2026. O original do usuário foi preservado. Nenhuma publicação no Kobo.
- **ACS ainda podem mudar:** participantes permanecem configuráveis, inclusive após visitas. Para o ciclo aprovado, o download altera somente as linhas da lista ACS, mantendo “Nenhum ACS” e “Outros”. Divergência entre assinatura salva e formulário bloqueia o download, sem modificar sorteios para forçar compatibilidade.
- Importação reconhece quarteirão “Outros”, tipos residência/comércio/outros e campos complementares. Preserva o contrato legado. Mostra alertas de coleta inconsistente, possíveis visitas duplicadas e números de tubito repetidos; não une nem exclui registros automaticamente.
- O plano completo fica protegido após importações. O ciclo do formulário aprovado permanece protegido mesmo depois de excluir as visitas de teste. Edição, importação e sorteio usam bloqueios na mesma ordem; datas devem pertencer ao ano do ciclo.
- Admin pode corrigir os dados locais da visita, com motivo, auditoria e versão; UUID/plano/tubitos/leituras são preservados. Há liberação explícita de reimportação de um envio excluído, sem recuperar leituras apagadas. Admin também pode corrigir número de tubito ao lançar/corrigir a leitura.
- Boletim/PDF sinalizam revisão de campo e laboratório, inclusive quarteirões sem visitas. Os índices finais, CV e `.lira` continuam no escopo registrado anteriormente, com fechamento no programa oficial.
- Na preparação inicial, não houve migração ou alteração de produção e o serviço estava em `1.72.4`. O reinício autorizado posterior ativou `1.73.0` em 30/10 às 17h46. A conferência administrativa foi executada em 03/11 e identificou os adicionais intencionais, tratados na seção acima. `scripts/verificar_liraa_prontidao.py` permanece exclusivamente de leitura.
- Validação: 845 testes gerais sem falha (5 ignorados), 62 testes LIRAa focados finais, 2 testes JS, ensaio PostgreSQL 18 descartável e inspeção visual do PDF com os alertas. A cópia aprovada do formulário manteve o SHA-256 original. A ativação em produção não foi realizada durante a implementação.
- Ver `docs/LIRAA_CORRECOES_2026_10.md` para operação, verificações e pendências. Os registros abaixo documentam implantações históricas e não autorizam reaplicar migrações ou reiniciar o serviço.

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

Versão `1.68.0` integrada na `master` (`c726f56`) e ativa em 08/10/2026
às 10h18 (America/Sao_Paulo), após autorização e reinício: em Territorialização > RG,
**Impressão e planilhas** permite baixar um XLSX de um ou vários quarteirões
selecionados da mesma localidade. Uma aba, uma linha por registro, sem mapas,
resumos, IDs técnicos ou decoração; preserva ordem, datas, agentes, referências
e campos do cadastro. Impressão/PDF inalterados. Não exige migração nem altera
dados. A integração ocorreu com o serviço parado, pois os templates são
recarregados automaticamente e não devem expor o botão antes da nova rota.
`/login` confirmou HTTP 200 com `Endemias v1.68.0`. Sem sessão, Territorialização,
exportação XLSX e impressão responderam HTTP 302 para login, sem HTTP 404/500.
Conferência somente leitura do PostgreSQL preservou contagens das 91 tabelas
e 19 assinaturas territoriais/LIRAa antes/depois da integração. A exportação
real por consulta somente leitura gerou 2 RGs, 232 linhas e 11 colunas,
com seleção, tipos e ausência de fórmulas conferidos. Nenhum arquivo com
dados reais foi salvo nem houve edição de imóveis, sorteios ou geometrias.
Validação: suíte completa com 794 testes (5 ignorados), 19 testes focados finais,
7 arquivos de testes JS, renderização/reabertura de XLSX sintético e HTTP no
Flask isolado, incluindo login e versão `1.68.0`. Foi acrescentado teste de
650 imóveis para garantir exportação sem o limite da consulta paginada.
SQLite congelado e alteração preexistente em `tests/test_security.py` preservados.
Ver `docs/RG_EXPORTACAO_PLANILHAS.md`.

Correção `1.67.1` integrada na `master` (`fe0c4d5`) e ativa em 07/10/2026:
no LIRAa cada registro COND conta como **1 imóvel**, mesmo que tenha 20 ou
mais unidades. Inventário, referências dos mapas/seleções e plano/exportações
usam essa contagem; RG e microáreas mantêm suas contagens anteriores. A lista
do sorteio mostra RG atual separado do snapshot histórico, sem reescrever
N confirmado, parâmetros, quarteirões selecionados ou hash do plano.
Não exige migração. Reinício autorizado concluído às 13h15
(America/Sao_Paulo); `/login` confirmou HTTP 200 com `Endemias v1.67.1`.
Conferência somente leitura do PostgreSQL antes/depois da integração:
contagens das 91 tabelas e 19 assinaturas dos registros territoriais/LIRAa
preservadas; plano existente consultado sem erro (252 quarteirões).
Se o N manual já incluir unidades de condomínio, cabe conferir esse valor
antes do uso oficial, sem alteração automática de dados reais.
Validação: 789 testes SQLite isolados (5 ignorados), 37 testes específicos
LIRAa, testes JS dos mapas e contagem em PostgreSQL descartável com tabelas
TEMP concluídos sem falha; banco operacional não usado nos ensaios.

Na implantação inicial em 07/10/2026, código `1.67.0` integrado à `master` (`e9feb85`):
mapa e KML dos sorteados, PDF de plano de campo, totais por localidade,
ressorteio com início casual opcional e histórico, seleção ACS/UID por ciclo,
XLSForm com quarteirões em cascata, aba Tubos · LIRAA em Lançamentos Laboratório e boletins PDF
por estrato ou localidade. Não altera a fórmula amostral homologada nem os
sorteios existentes. A migração **0026 foi aplicada** após autorização do usuário
e backup validado. O serviço oficial foi reiniciado em 07/10/2026 às 11h35
(America/Sao_Paulo): `/login` respondeu HTTP 200 com `Endemias v1.67.0`.
`/liraa`, `/laboratorio/lancamentos?modulo=liraa` e `/liraa/laboratorio`
redirecionaram ao login (HTTP 302) sem sessão, sem HTTP 500.
O backup é `D:\BackupsEndemias\backups_banco\endemias_pre_liraa_0026_20261007_113443.dump`,
com 6.544.369 bytes e catálogo validado por `pg_restore`. Após a migração,
as contagens das 87 tabelas anteriores e as assinaturas dos ciclos, estratos,
sorteios e vínculos territoriais LIRAa permaneceram iguais. Plano e boletim
do ciclo existente foram consultados sem erro (252 quarteirões, 5 grupos);
o laboratório encontrou 1 tubo LIRAA pendente. Não foram importadas visitas,
salvas leituras ou alterados sorteios nessa implantação. O SQLite congelado
conserva SHA-256 `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
A alteração local de `tests/test_security.py` foi preservada e não entrou no commit.
A regressão SQLite isolada
passou com **786 testes (5 ignorados)**, além da conversão XLSForm
sem avisos e inspeção dos PDFs. A UI isolada confirmou leitura→boletim e
filtros, incluindo a aba Tubos · LIRAA no laboratório e o contador 3→2 após salvar.
O ensaio PostgreSQL 18 passou em instância descartável localhost:55432,
com tabelas temporárias, migração 0026, ressorteio/histórico, formulário,
importação, leitura, contador, boletim e exclusão em cascata. A instância foi
encerrada; não houve acesso ao banco oficial. Uma tentativa anterior de conexão PostgreSQL em contexto
não elevado não obteve credencial; não houve alteração de ACL ou cópia de
senha. A implantação oficial utilizou a credencial protegida em console elevado,
sem copiar senha nem mudar ACL. A tarefa Windows identifica SYSTEM como
`SISTEMA`; seu SID foi conferido como `S-1-5-18` antes da operação.
Falta validação real de upload e uso do
formulário no Kobo, além da conferência operacional do primeiro ciclo.
Ver `docs/LIRAA_OPERACAO_CICLO.md`.

Em 06/10/2026, a branch `codex/liraa-kobo-visitas` foi integrada na `master`.
O código `1.66.0` oferece importação separada do diário Kobo LIRAa,
visitas/tubitos, conferência de quarteirão municipal (`408.1` e `408,1`),
filtros e exclusão local auditada com bloqueio de reimportação. O backup
PostgreSQL `D:\BackupsEndemias\backups_banco\endemias_pre_liraa_0025_20261006_160900.dump`
teve o catálogo validado antes da migração `0025_liraa_visitas_kobo.sql`,
que consta como aplicada. O serviço oficial foi reiniciado: `/login` respondeu
HTTP 200 com `Endemias v1.66.0`, e `/liraa` redirecionou ao login sem sessão.
Nenhuma visita Kobo foi importada nessa implantação. A regressão isolada
passou com 773 testes (5 ignorados) e os 32 testes focados LIRAa passaram
depois dos ajustes finais. A validação autenticada e um primeiro lote pequeno
continuam pendentes. Ver `docs/LIRAA_VISITAS_KOBO.md`.

No codigo `1.65.2`, a exportacao KML de Territorializacao > Microareas inclui
um estilo por microarea (poligono semitransparente e contorno), inclusive nos
lados parciais. As cores sao unicas no conjunto atual e distribuidas com
prioridade de contraste para areas proximas; o filtro nao muda a cor de uma
microarea. O embaralhamento do mapa continua exclusivo do navegador, e o
GeoJSON permanece sem estilos. Nao ha migracao nem alteracao dos cadastros.
Validacao: 12 testes focados de Microareas e regressao completa de 764 testes
(5 ignorados) aprovados. O servico oficial foi reiniciado em 05/10/2026 por
autorizacao do usuario; `/login` respondeu HTTP 200 com `Endemias v1.65.2`.
O download colorido esta disponivel; a aparencia no Google Earth ainda depende
de conferencia visual pelo usuario apos importar o novo KML.

Em 02/10/2026, o código `1.65.1` apresenta na página **Relatório por Agente**
um download separado do histórico de visitas de vetores e esporotricose por
agente e intervalo de datas. Cada visita ocupa até cinco linhas em A4 paisagem,
com resumo dos depósitos e sem identificadores/metadados técnicos. O conjunto
de visitas continua completo; textos longos são abreviados. É leitura
autenticada, sem migração nem escrita em banco. Requer `reportlab` no ambiente;
foi instalado no Python local de serviço. O serviço oficial respondeu
`Endemias v1.65.0` em 02/10/2026 antes da integração/reinício do formato
compacto. Ver
`docs/RELATORIO_VISITAS_COMPLETO.md` para fontes, campos e validação.

Em 01/10/2026, foi integrada na `master` a versão de código `1.64.0`, com exclusão administrativa de ciclos LIRAa
preenchidos e de estratos com sorteios. A operação remove os sorteios antes
dos registros pais na mesma transação e registra contagens na auditoria.
Nenhum ciclo, estrato ou sorteio real foi apagado nos testes. Em 02/10/2026,
`/login` respondeu `Endemias v1.64.0`; a versão está carregada no serviço.
A regressão isolada
passou com 757 testes (5 ignorados), e os 22 testes focados LIRAa passaram após
a última revisão da rota de exclusão.

Em 01/10/2026, a branch `codex/liraa-sorteio-homologacao` foi integrada na
`master`, **sem reiniciar o serviço oficial**. Os parâmetros amostrais foram
confrontados com cinco estratos do programa LIRAa/LIA; depois, as 12 listas
por bairro/localidade enviadas pelo usuário permitiram reproduzir as 241
posições sorteadas. No estrato 3, o IC impresso como `2` não informa a parte
decimal: `2,9` foi inferido como valor compatível, não confirmado. O programa
renumera cada localidade a partir de 1; no Endemias, a posição é traduzida
para o ID municipal real pela ordem numérica dos quarteirões daquela
localidade ou parte incluída no estrato. O resultado mostrará ambos os
números. Nenhum sorteio real, migração, alteração de banco ou reinício foi
feito nesta validação. O sorteio continua de ensaio até conferir essa tradução
num estrato real e a ordem de localidades. Ver `docs/LIRAA_PLANEJAMENTO.md`.
Os testes focados LIRAa (19), o teste JavaScript do mapa geral e a regressao
SQLite isolada (752 testes, 5 ignorados) passaram durante a preparacao; as
ultimas edicoes de interface foram revalidadas pelos testes focados.

Em 01/10/2026, a branch `codex/liraa-mapa-geral` foi integrada na `master`
(`f82fd6c`) e o servico oficial reiniciado em `1.63.0`. A subaba
**Mapa geral · consulta** do LIRAa mostra todos os estratos de um ciclo
sobre a mesma camada territorial, com cores, quarteiroes sem estrato em cinza,
resumo e detalhes ao clicar. E somente leitura e nao exigiu migracao;
nenhum ciclo ou sorteio real foi alterado. A suite isolada passou com 748
testes Python (5 ignorados), alem dos testes JavaScript do LIRAa e do mapa
de Microareas. `/login` respondeu HTTP 200 com `Endemias v1.63.0`, o novo
JavaScript respondeu HTTP 200 e `/liraa` redirecionou visitantes sem sessao
para login. A validacao visual autenticada continua pendente com o usuario.

Em 01/10/2026, a branch `codex/microareas-consulta-geral` foi integrada na
`master` (`6b5945c`) e o serviço oficial reiniciado na versão `1.62.0`.
A nova subaba **Mapa geral · consulta** em Territorialização → Microáreas
não exigiu migração. `/login` respondeu HTTP 200, a rota
`/territorializacao` redirecionou visitantes sem sessão para login e o
JavaScript atualizado respondeu HTTP 200. A leitura direta do relatório de
Microáreas no PostgreSQL retornou 101 microáreas e 10 lados parciais.
Os testes do código foram executados em SQLite isolado antes da integração:
748 testes Python (5 ignorados) e testes JavaScript de mapa geral, desenho e
cores passaram. A validação visual autenticada continua com o usuário.

A subaba carrega todos os quarteirões da camada ativa, destaca simultaneamente
todas as microáreas (inclusive os lados parciais) e permite conferir ACS,
quarteirões, RG, população estimada e observações ao clicar, sem controles
de edição. Usa as mesmas cores e APIs de leitura já existentes.

Em 30/09/2026, a branch `codex/liraa-estratos-mapa` foi integrada na
`master` (`061853e`). A migração `0024_liraa_estrato_quarteiroes.sql` foi
aplicada após backup específico validado
`D:\BackupsEndemias\backups_banco\endemias_pre_liraa_0024_20260930_151050.dump`.
O serviço oficial foi reiniciado e `/login` respondeu HTTP 200 com
`Endemias v1.61.0`; `/liraa` redirecionou ao login sem sessão. Leitura
direta do painel no PostgreSQL retornou 15 localidades, 1.415 quarteirões
e um ciclo já cadastrado, sem estratos (1.415 quarteirões não atribuídos).
Nenhum ciclo, estrato ou sorteio foi criado por esta implantação. A nova
subaba permite dividir localidades entre estratos por quarteirão inteiro,
com contagem RG apenas provisória e `N` confirmado manualmente. O sorteio
permanece experimental; a interface autenticada ainda requer validação
visual pelo operador.

Em 30/09/2026, a branch `codex/liraa-planejamento` foi integrada na `master`
(`27fcace`) e a pagina separada `/liraa` entrou em operacao na versao
`1.60.0`, com inventario RG/GeoJSON, ciclos, estratos por
localidade e sorteio sistematico congelado em snapshot auditavel. O total `N`
de imoveis deve ser confirmado manualmente; PE e REF ficam fora da previa RG.
A migracao PostgreSQL `0023_liraa_planejamento.sql` foi aplicada no banco
oficial apos backup especifico validado
`D:\BackupsEndemias\backups_banco\endemias_pre_liraa_0023_20260930_132619.dump`.
O servico foi reiniciado pelo script administrativo, `/login` respondeu HTTP
200 com `Endemias v1.60.0`, e `/liraa` redirecionou visitantes nao autenticados
ao login. A leitura direta do painel no PostgreSQL retornou 15 localidades,
1.415 quarteiroes e zero ciclos; **nenhum sorteio real foi executado**.
A pagina nao exporta `.lira` nem calcula indices sem visitas LIRAa. O sorteio
e de ensaio ate a homologacao com o programa oficial. Consultar
`docs/LIRAA_PLANEJAMENTO.md` antes do uso em campo.

Em 30/09/2026, foi preparada a versao `1.59.0`: as telas de doentes de
Esporotricose oferecem **Apagar entrega** em cada entrega da receita. A API
ja tinha DELETE, mas a interface nao o expunha; agora a exclusao verifica se
o registro existe, preserva a receita e informa quantidade/fonte retiradas.
O estoque e calculado a partir das entregas, portanto os saldos geral e por
fonte voltam automaticamente sem lancamento manual compensatorio. Nao ha
migracao nem alteracao automatica de dados reais. Corrigir separadamente
eventual baixa na plataforma ZooMed. O servico oficial respondeu `1.58.4`
antes desta alteracao; integrar e reiniciar somente apos validacoes. A suite
Python passou com 735 testes (5 ignorados) e o JavaScript das duas telas
passou na verificacao de sintaxe.

Em 29/09/2026, o usuario capturou a causa de uma rejeicao ao salvar lado
parcial: "O desenho deve ficar inteiramente dentro do quarteirao oficial".
A regra foi removida no codigo `1.58.4` a pedido do usuario: o poligono pode
ficar dentro, fora ou atravessar o contorno. Mantem-se o vinculo ao RG, a
validacao geometrica e a proibicao de sobreposicao entre lados do mesmo
quarteirao. Nenhuma migracao ou mudanca em dados reais e necessaria. Confirmar
integracao, reinicio do servico e teste funcional do usuario antes de declarar
a correcao ativa. A suite Python passou com 733 testes (5 ignorados); os
testes JavaScript de desenho e cores passaram.

Em 29/09/2026, o usuario relatou que desenhou lados dos Q. 796 e 758 de Sede
na microarea 10, mas apos F5 ambos voltaram como inteiros. A pagina ativa
respondia `1.58.2`; a leitura da tela confirmou 21 quarteiroes inteiros e zero
lados parciais nessa area. A Auditoria nao registrava atualizacao bem-sucedida
da microarea 10 depois da criacao. Nao foi possivel recuperar a resposta de
erro das tentativas anteriores, portanto a causa de eventual rejeicao pelo
servidor permanece desconhecida. O bug confirmado na interface era mostrar o
desenho na lista antes de receber confirmacao de gravacao. A correcao `1.58.3`
mantem os lados nessa lista apenas apos resposta positiva e releitura do banco;
erros aparecem em destaque e alerta, o desenho rejeitado permanece para
correcao, e F5 durante desenho/envio dispara aviso. A criacao de microarea
nova por lado tambem e gravada ao concluir, desde que o numero esteja
preenchido. Sem migracao; confirmar implantacao e teste visual. Nenhuma
geometria real foi alterada durante este diagnostico.
Os 732 testes Python terminaram em OK (5 ignorados), assim como os testes
JavaScript de desenho, rejeicao/reenvio, criacao por lado e cores.

Correcao `1.58.2` para lados parciais: no cadastro real, Q. 796 da Sede
continuava inteiro na microarea 10, sem nenhum lado parcial salvo. A interface
antiga mostrava todos os lados como ja atribuidos fora da edicao e exigia um
segundo clique em **Salvar alteracoes** depois de concluir o desenho, sem deixar
clara essa etapa. A nova interface oferece **Editar microarea 10** junto ao
aviso do quarteirao ocupado; para microarea existente, **Concluir e salvar lado**
envia a alteracao e rele os dados para confirmar que o lado foi salvo. Para
microarea nova, **Criar microarea** continua obrigatorio. O diagnostico via
navegador foi somente leitura; nao se alterou o Q. 796. Os 732 testes Python
passaram (5 ignorados), assim como os testes JavaScript focados. Esta correcao
nao requer migracao; conferir integracao, reinicio e teste visual antes de
considera-la disponivel em producao.

O usuario encontrou um defeito no desenho dos lados parciais: cliques dentro
dos poligonos do quarteirao nao marcavam vertices. A correcao `1.58.1`
desativa a captura de cliques pelas camadas vetoriais somente durante o
desenho; ao terminar, a interacao normal retorna. Nao altera banco e nao
exige migracao. Foi integrada a `master` e o servico reiniciado em 29/09/2026:
`/login` respondeu HTTP 200 com `Endemias v1.58.1`, e o JS corrigido respondeu
HTTP 200. Restam a validacao visual do usuario e nenhum cadastro de teste foi
criado em producao pelo agente. Foram aprovados 18 testes focados de Python e
os testes JavaScript do desenho e das cores.

O codigo `1.58.0` foi integrado a `master` para divisao excepcional de
quarteiroes por lados do RG e desenho manual no mapa. O usuario executou o
migrador administrativo e mostrou `0022_territorializacao_microareas_partes.sql`
como **applied** em 29/09/2026. Shapely 2.1.2 foi instalado no Python local.
O reinicio elevado terminou com codigo 0; `/login` e o JavaScript de
Microareas responderam HTTP 200, com `Endemias v1.58.0` no login. A conta
desta sessao nao possui leitura da credencial PostgreSQL. A migracao foi
confirmada pela saida enviada pelo usuario, nao por uma consulta independente
nesta sessao. Falta teste funcional com um quarteirao real escolhido pelo
usuario, sem criar cadastro experimental por iniciativa do agente. Consulte
`docs/MICROAREAS_PARTES.md` para funcionamento, testes e limites.

O codigo `1.57.1` amplia de 12 para 37 cores a paleta do mapa de Microáreas
e faz **Embaralhar cores** produzir mais combinações: entre opções com bom
contraste local, prefere cores menos usadas. A escolha continua apenas no
navegador, sem alterar banco ou exportações. Não exige migração. A última
versão confirmada no serviço oficial é `1.57.0`; reinício de `1.57.1` depende
de autorização do usuário.

Em 29/09/2026, a verificacao administrativa no banco oficial `endemias`
mostrou `0021_territorializacao_microareas.sql` como **applied**, sem
migracoes pendentes; ela nao precisou ser reaplicada. Os backups existentes
foram verificados antes do reinicio. A tarefa oficial foi reiniciada e
`/login` respondeu HTTP 200 com `Endemias v1.57.0`. O arquivo
`tests/test_security.py` ja tinha modificacao local alheia a esta operacao e
nao foi alterado.

O codigo `1.57.0` melhora as cores do mapa em Territorialização > Microáreas:
os polígonos são aproximados por caixas geográficas e áreas a até 200 m
entram no mesmo grupo de vizinhança para receber cores contrastantes. Uma
legenda por localidade e o botão **Embaralhar cores** permitem conferir e variar
a paleta; a variação fica no armazenamento deste navegador. É uma escolha
visual, sem gravar no banco nem alterar KML/GeoJSON. Não exige nova migração;
a 0021 foi confirmada como aplicada em 29/09/2026.

O codigo `1.56.0` acrescenta ao Painel de Microáreas um controle para incluir
(padrão) ou excluir a população estimada dos condomínios residenciais. O RG
identifica essas unidades pelo imóvel residencial com `condominio > 0`; ao
excluir, todas essas unidades ficam fora da estimativa, sem alterar cadastros.
Cards, média por ACS, lista, relatório imprimível e XLSX usam o mesmo modo. O
relatório imprimível agora usa A4 retrato. A indicação do modo fica visível no
relatório e na planilha. Não há nova migração nesta versão; a 0021 foi
confirmada como aplicada em 29/09/2026.

O codigo `1.55.0` separa **Painel** de **Cadastro e exportações** em
Territorialização > Microáreas. Os filtros são compartilhados. O painel mostra
microáreas por localidade, carga populacional estimada por ACS e áreas sem
responsável; há relatório imprimível e XLSX com indicadores, resumos por ACS e
localidade e detalhes das microáreas/quarteirões. A população vem das
residências reais do RG multiplicadas por 2,93 (IBGE Censo 2022); quarteirão
sem RG não é tratado como população zero. A média divide a população estimada
atribuída pelos ACS do recorte com ao menos um quarteirão com RG. "ACS do
catálogo sem microárea" é contagem global cadastral, não disponibilidade real
de pessoal. A diferença 1:1 é uma hipótese cadastral, não déficit de equipe.
Esta melhoria não exige nova migração nem altera o cadastro de microáreas.

O codigo `1.54.0` renomeia a pagina de navegação para **Territorialização**
e conserva o RG em aba própria e na rota legada. A nova aba **Microáreas**
vincula quarteirões inteiros, com número único por localidade e ACS opcional.
Um ACS pode ser responsável por várias microáreas, inclusive de localidades
diferentes. Microáreas salvas podem ser reabertas na consulta para trocar o ACS
sem alterar os quarteirões; essa relação não exige nova migração.
No editor, a seleção pode ser feita pelo mapa com etiquetas numéricas ou por
lista pesquisável, com sincronização entre ambos. O fundo do mapa pode alternar
entre ruas, satélite e satélite com ruas, como no mapa do RG. Exporta XLSX,
GeoJSON e KML.
Na prévia compartilhada anteriormente pelo usuário, a migração PostgreSQL
`0021_territorializacao_microareas.sql` constava **pendente**; a verificação
administrativa de 29/09/2026 mostrou-a **applied** antes do reinício.

O codigo `1.53.0` adicionou **Doentes > Entregas por fonte** em Esporotricose,
consultando as entregas ja registradas nas receitas, com totais por fonte,
filtros e paginação. Não altera lançamentos nem exige migração. O serviço
oficial foi atualizado para `1.57.0` em 29/09/2026.
Na lista de Doentes, o filtro **Situação da receita** distingue pendência,
receita sem pendência e ausência de receita; não exige migração.

O codigo `1.52.0` prepara importacao automatica Kobo dos ultimos 7 dias de
envio, com validacao de resposta completa, filtro UUID, simulacao antes da
gravacao, transacao e historico em Processar. A tarefa diaria 12h30 foi
instalada pelo usuario em 28/09/2026, que mostrou estado `Ready`.
Em 28/09/2026, o usuario mostrou a migracao 0020 como `applied`, a simulacao
e duas execucoes assistidas com zero registros novos e sem erro. A instalacao
foi concluida ao chamar o instalador com `powershell.exe -NoProfile
-ExecutionPolicy Bypass -File` no console administrativo, sem alterar a
politica permanente. Depois do reinicio feito pelo usuario, `/login`
respondeu HTTP 200 com `Endemias v1.52.0`. A conta desta sessao nao consegue
consultar diretamente a tarefa SYSTEM: o estado `Ready` veio da saida do
usuario. O primeiro ciclo agendado com dados novos ainda nao foi verificado.

O codigo `1.51.0` acrescenta ACS acompanhante as visitas de Esporotricose,
com multiplos codigos, nomes via catalogo Kobo, exibicao no historico do
imovel/detalhe animal e filtro nas visitas. A migracao PostgreSQL
`0020_esporotricose_visitas_acs.sql` foi informado pelo usuario como `applied`
em 28/09/2026. Registros antigos
nao recebem ACS retroativamente por uma sincronizacao Kobo normal.

A versao `1.50.0` introduz `fonte_medicacao` (`Zoomed` ou `Município`) nas
entregas dos animais com esporotricose e nos movimentos de estoque. A migração
PostgreSQL `0018_esporotricose_fontes_medicacao.sql` foi aplicada no banco
oficial em 24/09/2026, após validar os backups. A verificação leu 71 entregas
e 17 movimentos de estoque, todos `Zoomed`. O usuário deverá corrigir
manualmente as entregas recentes de origem municipal e lançar as entradas da
compra municipal. O estoque exibe saldos separados por fonte e as entregas
municipais não compõem a baixa Zoomed. Para os anexos dos animais, a ação
principal no detalhe solicita cada arquivo separadamente, sem ZIP; o navegador
pode pedir permissão para múltiplos downloads. O ZIP continua como alternativa.
Na lista de animais, "Anexos (N)" abre diretamente essa seção do detalhe.
Após a migração e o commit `2c16b4e`, a tarefa oficial foi reiniciada com
sucesso; `/login` respondeu HTTP 200 com `Endemias v1.50.0`.

No codigo `1.50.1`, a fonte antes denominada `Zoomed` foi renomeada para
`SESA`; a outra fonte e `Município`. Zoomed e a plataforma de pedidos e baixas
de **ambas** as fontes, entao "Pedido Zoomed" foi mantido e as baixas municipais
podem ser marcadas e filtradas normalmente. A migracao PostgreSQL
`0019_esporotricose_sesa_baixa_zoomed.sql` foi aplicada no banco oficial em
24/09/2026, apos validar os backups. A conferencia mostrou 71 entregas SESA,
1 Município e 17 movimentos de estoque SESA, sem fonte legada `Zoomed`; os
valores de baixa foram preservados (68 `Sim`, 4 `Não`). A tarefa oficial foi
reiniciada, e `/login` respondeu HTTP 200 com `Endemias v1.50.1`. Nao presumir
que entregas municipais antigas foram baixadas: conferir caso a caso antes
de alterar o status.

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
`0016_esporotricose_pacientes_humanos.sql` foi aplicada no banco oficial.
Consulte `docs/ESPOROTRICOSE_CASOS_HUMANOS.md`.

A versao `1.48.1` corrige a consulta da lista no PostgreSQL. A ordenacao
original tentava combinar `data_notificacao` (`date`) com `criado_em` (`text`)
em um `COALESCE`, causando HTTP 500 somente na listagem; o cadastro do paciente
ja havia sido gravado e nao foi perdido.

A versao `1.49.0` adiciona **CSV QGIS** na lista de casos humanos. A exportacao
respeita os filtros atuais, inclui coordenadas em colunas numericas separadas e
usa UTF-8 com BOM e `;`. O arquivo contem dados pessoais e de saude; por isso,
o endpoint e exclusivo de administradores, mostra alerta de confidencialidade
e registra cada download na auditoria.

A versao `1.49.1` adiciona ao cadastro humano a situacao do bloqueio
(`Realizado` ou `Nao realizado`), exibida no detalhe, listagem, filtro e CSV
QGIS. Sem preenchimento, permanece desconhecida. A migracao aditiva
`0017_esporotricose_humanos_bloqueio.sql` deve ser aplicada antes do reinicio.

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

## Nivel de acesso 'usuario' (1.69.0)

Em 08/10/2026 foi adicionado um quarto nivel de acesso: `usuario` (rotulo
"Usuario"). Ele e somente leitura, com o mesmo alcance de paginas do
`visualizador`, porem com a **identidade dos demais agentes ocultada**: em
qualquer campo que atribui producao a servidores (colunas "Agentes",
laboratorista, rankings, agenda, relatorio por agente e exportacoes XLSX),
apenas o proprio agente vinculado a conta permanece identificado; os demais
viram "—" e as quebras nominais (`por_agente`/`por_laboratorista`) sao
removidas por inteiro. Enderecos, moradores e demais conteudos operacionais
seguem visiveis (decisao do usuario: nao redigir PII de morador/endereco).

- Vinculo: `usuarios.id_agente` (ja existente, migracao 0011) e obrigatorio;
  sem vinculo, nenhum nome de agente e exibido (fail-closed).
- Mecanismo: `app_core/escopo_agente.py` (resolvedor estrito + redacao
  recursiva) + `after_request` em `app_core/app_setup.py` que redige as
  respostas JSON das APIs; telas server-rendered (notificacoes, foco,
  agenda de impressao, territorializacao de impressao, doente esporotricose)
  e exportacoes XLSX sao redigidas pontualmente.
- `relatorio_agente` e forcado ao proprio agente; o PDF do setor e bloqueado.
- Migracao PostgreSQL `0027_usuarios_nivel_usuario.sql` altera o CHECK de
  `nivel`; aplicar antes de usar o nivel em producao.

Pendencia futura (registrada, nao implementada): permitir que o admin escolha,
por usuario, quais paginas cada conta pode abrir, no molde do
`somente_laboratorio` (allowlist de modulos por conta). O mecanismo
`modules.required_permission` ja suporta flags booleanas de `usuarios`, o que
viabiliza essa evolucao sem novo schema.

## Base XLSForm do LIRAa atualizada (1.69.1)

Em 15/10/2026, o modelo-base do formulario LIRAa (`app_core/data/liraa_kobo_base.xlsx`)
foi substituido pelo arquivo enviado pelo usuario (`C:\LIRAa.xlsx`). As unicas
diferencas em relacao ao modelo anterior: o grupo de tratamento foi renomeado de
`group_rb5ho54` para `tratamento_001`, o campo "foi tratado" de
`O_im_vel_foi_Tratado_com_Larvi` para `foi_tratado`, e a opcao "nao" da lista
`xv2ud66` passou de `n_o` para `nao`. O grupo de tratamento ja vem fora do
repetidor de tubitos (nivel do imovel). `liraa_xlsform.gerar` e
`liraa_kobo._tratamento` foram ajustados para os novos nomes, mantendo leitura
dos nomes legados para formularios antigos. Nao ha migracao de banco. Antes do
uso, gerar novamente o XLSForm do ciclo e substituir o formulario publicado no
Kobo. Ver `docs/LIRAA_OPERACAO_CICLO.md`.

## Alias do Ponto Estrategico PE-0046 (1.69.2)

Em 15/10/2026, foi adicionado o alias determinístico do novo PE `PE-0046` em
`pontos_estrategicos.PE_ALIAS_SEED`, mapeando o nome interno do Kobo
`RUA DOMINGOS SCUCATO - AUTO PEÇAS JOÃO 3:16` ao código `PE-0046`. Garante que
visitas de Ponto Estratégico lançadas nesse PE sejam identificadas mesmo se o
alias automático do cadastro não casar com o nome do formulário. Para aplicar
na produção, salvar (editar e gravar) o PE-0046 uma vez após a implantação, o
que reexecuta `_seed_aliases` e grava o alias; visitas PE antigas sem vínculo
podem ser religadas por `pontos_estrategicos.vincular_visitas_existentes_por_alias`.

Pendência futura (registrada pelo usuário, não implementada): permitir
configurar os **aliases na interface**, como uma aba dentro da página de Pontos
Estratégicos, para editar o mapeamento nome-do-Kobo -> PE sem alterar o código
(`PE_ALIAS_SEED`). Hoje os aliases vivem em `PE_ALIAS_SEED` + geração automática
(`_aliases_automaticos`), persistidos em `pontos_estrategicos_alias`.

## Aba "Aliases" em Pontos Estratégicos (1.70.0)

Implementada em 15/10/2026 a configuração de aliases pela interface: uma nova
aba **Aliases** em `/pontos-estrategicos`. O administrador/operador pode criar,
editar, ativar/desativar e excluir **aliases manuais** (novo `OBS_ALIAS_MANUAL`),
visualizar os aliases `Seed`/`Automático`/`Ambíguo` (somente leitura) e ver o
`alias_normalizado` para prever o casamento na importação. Sem migração de
banco (reaproveita `pontos_estrategicos_alias`).

- Core: `listar_aliases`, `salvar_alias_manual`, `alternar_alias_manual`,
  `excluir_alias_manual` em `app_core/pontos_estrategicos.py`.
- Rotas: `/api/pontos-estrategicos/aliases*` (escrita `operador`), com auditoria
  `alias_criado`/`alias_editado`/`alias_excluido`.
- Regras: alias manual nunca colide com outro PE; `_seed_aliases` preserva os
  manuais (não sobrescreve nem desativa). Testes em
  `tests/test_pontos_estrategicos_aliases.py`.

## Hub "Formulários" com atualização de RG offline (1.71.1)

Em 15/10/2026 foi criada a página **Formulários** (`/formularios`), um hub
genérico de formulários internos com o primeiro formulário: **Atualização de
Registro Geográfico (RG)**. O agente (nível `usuario`) captura em campo no
celular/tablet Android, com funcionamento **offline**, e envia para revisão; o
admin revisa/corrige e **oficializa** (substitui o quarteirão via
`salvar_quarteirao`).

- **Arquitetura genérica**: registro `FORMULARIOS` em `app_core/formularios.py` +
  tabela comum `formularios` (tipo + payload JSON + status + autor + revisão),
  reutilizável por formulários futuros. Migração PostgreSQL **0028**.
- **RG**: `app_core/rg_formulario.py` (`snapshot` de quarteirões/logradouros +
  `oficializar`). Páginas `/formularios/rg-campo` e `/formularios/rg-revisao`.
- **Offline**: Service Worker (`static/sw.js`), IndexedDB
  (`static/js/rg_campo_offline.js`) e `static/manifest.webmanifest`. O campo baixa
  quarteirões, preenche rascunhos sem rede e sincroniza ao voltar a ficar online.
- **Estados**: `rascunho → enviado → aprovado/devolvido → oficializado`.
- Testes: `tests/test_formularios.py`, `tests/test_rg_formulario.py`.

Ajustes de campo (1.71.1): o salvamento passou a ser "local primeiro" (grava no
IndexedDB e só então tenta enviar), eliminando o "Failed to fetch" ao salvar
offline; correção do botão "Novo lado" (colisão de nome de função); campo de
quantidade ao marcar "Condomínio: Sim" (o `condominio` do RG é o nº de unidades);
confirmação antes de remover logradouro; e reabertura do quarteirão recupera o
rascunho salvo em vez de zerar.

Pendência operacional: aplicar a migração 0028 em produção (console elevado) e
fazer um teste real offline no Android/Chrome antes do uso em campo.

Antes de iniciar qualquer uma delas, confira o pedido mais recente do usuario.
Ele pode mudar a prioridade, autorizar operacao real ou pedir apenas analise.

## Fechamento de cada lote

Um lote esta pronto somente com escopo claro, dados reais preservados, testes
focados e regressao proporcional, documentacao atualizada, commit e push. Para
lotes de risco (dados, PostgreSQL, autenticacao, backups e Conta Ovos), Codex
deve preferir branch isolada e ensaio seguro, mas pode integrar sem revisao
externa obrigatoria quando o pedido e as validacoes permitirem. Claude participa
somente se o usuario solicitar.
