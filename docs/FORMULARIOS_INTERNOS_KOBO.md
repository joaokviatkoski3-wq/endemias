# Formulários internos compatíveis com Kobo — piloto ativo

Pedido em 06/11/2026. Branch `codex/formularios-internos-kobo`, worktree
`C:\endemias-interface`. Produção 2.5.0 ativa desde 06/11/2026 às 15h45, release `5668a5b`.
As melhorias de campo 2.4.0 foram ativadas anteriormente no release `97f0fcb`.
A entrada inicial dos dez formulários ocorreu na 2.3.0, release `bf36464`.

Usuário confirmou revisão por admin antes de gravar nos registros oficiais.
Kobo permanece em paralelo, sem migração nem importação de respostas reais.
O usuário executou a consulta administrativa de definições: 10 formulários,
zero pendências. Saída privada, não versionável:
`.venv/formularios-internos/definicoes.json`. Contém listas nominais de opções,
mas não respostas, tokens ou identificadores privados dos projetos.

## Escopo

Endemias: PE, TB, TBO, PVE, LIRAa, Larvas, BRI, Recolhimento.
Ambiental: Esporotricose e Amostras de Animais. RG atual preservado.
Captura dos novos formulários começa online. Offline de formulários com dados
pessoais exige desenho próprio; não ampliar o cache e armazenamento do piloto RG.

Reproduzir campos, tipos, opções, condições, obrigatoriedade e repetições das
definições implantadas. Usar as importações existentes para aplicar dados,
sem duplicar regras de negócio e sem escrever respostas de volta ao Kobo.
Revisão, aprovação e oficialização devem ser ações distintas e auditadas;
oficialização e marcação do formulário devem confirmar na mesma transação.
Reenvios devem ser idempotentes e não sobrescrever dados aprovados/oficializados.

## Cuidados específicos

- Filtrar hub/listagem/APIs por setor, inclusive URLs diretas e acesso de admin.
- Somente laboratório habilitado/gestão deve registrar resultados laboratoriais.
- Respeitar vínculo e exposição de nomes de agentes conforme perfil existente.
- LIRAa exige ciclo/plano do sistema; não repetir automaticamente um período
  fixo da definição Kobo em ciclos futuros. Respeitar sorteio e vínculo de tubos.
- Reutilizar conversão `kobo_api.write_etl_workbooks` e ETL transacional;
  validar campos consumidos, coletas, animais e totais com massa fictícia.
- Definições completas ficam em arquivo privado do servidor, fora de static/Git;
  a API autenticada só disponibiliza as opções permitidas ao perfil.
- Não incluir banco, respostas, catálogos nominais ou credenciais nos commits.

## Implementado na versão 2.3.0

- Motor de condições sem eval;417 regras das definições implantadas compiladas.
- Campos e escolhas dos dez tipos, grupos condicionais e até100 repetições.
- Página de captura móvel online, rascunho no servidor e acompanhamento por conta.
- Revisão/devolução/aprovação por admin e superadmin no domínio do setor.
- ACS selecionados sincronizados atomicamente com o catálogo; textos que começam
  com sinal de igual preservados como texto nos arquivos intermediários.
- Aplicação usando o ETL existente; confirmação e auditoria na mesma transação.
- Revisões/recibos por UUID, trava na aplicação e comparação de versão na revisão.
- Vínculos de visita/coleta/resultado, animais e ciclo/sorteio LIRAa preservados.
- Horários automáticos de preenchimento persistidos antes da revisão; o registro
  usa prefixo `vsatt-` para distinguir a origem interna e preservar idempotência.
- Catálogo privado em `C:\ProgramData\EndemiasWeb\formularios-kobo.json`, fora
  de static/Git. Instalador copia a definição consultada e aplica a proteção da
  configuração do serviço. O backup completo inclui o arquivo; ao restaurar,
  recolocá-lo nesse caminho ou configurar `ENDEMIAS_FORMULARIOS_KOBO_SCHEMA`.
- O instalador não executa DDL nem altera contas, senhas, Kobo, DNS ou firewall.

## Validação realizada e pendências de homologação

Massa de negócio fictícia, sem respostas Kobo: gravação dos dez tipos em SQLite,
com dois animais na mesma visita, resultados ligados à coleta e LIRAa com ciclo/
sorteio/tubito. PostgreSQL descartável confirmou captura, aprovação, aplicação,
repetição idempotente e rollback de dados/status quando a auditoria falha.
Navegador Chromium: dez telas em 390/1365px, CSP efetiva, sem erro JS/overflow;
fluxo completo de Recolhimento pela UI, com CSRF e participantes/localidade fictícios.
Teste também exercita a alternativa de UUID para entrada LAN sem randomUUID.

Regressão geral: 1.181 testes, seis ignorados e nenhuma falha. Após os ajustes
finais, passaram os testes focados de captura/permissões (12), RG (10) e nova
conferência no navegador. Ativação administrativa confirmada: relatório aplicado/concluído, backup completo
e PostgreSQL conferidos, 96 tabelas preservadas e prova limitada OK.
Publicação conferida em 19 verificações: cinco entradas na versão 2.3.0, assets
iguais aos instalados, APIs anônimas negadas e catálogo privado não exposto.
Nenhum formulário real enviado ou oficializado nesta conferência. Android real e comparação operacional de todos os campos continuam
para o piloto do usuário; testes automáticos não substituem essa homologação.

## Uso paralelo e limites explícitos

Kobo segue disponível. UUID evita repetir um mesmo envio interno, mas não
reconhece automaticamente a mesma atividade cadastrada separadamente no Kobo.
Durante comparação, mantenha o novo envio em rascunho/enviado e não aplique duas
vezes a mesma produção. A tela de revisão alerta o gestor antes da aplicação.
Nenhum formulário novo aplica dados oficiais apenas ao salvar ou enviar.

Não há coleta offline dos novos formulários, fotos/anexos ou criação de novas
contas neste pacote. Não se ampliou o cache do RG. O navegador mantém alterações
não salvas somente na tela; salve com conexão antes de fechar. Campo obrigatório,
opção inválida, sessão vencida ou falha de gravação não deve anunciar sucesso.
As definições são um retrato da versão implantada no Kobo. Alterações posteriores
no Kobo não modificam silenciosamente o catálogo interno: exigem atualização
conferida, preservação da definição anterior e tratamento de rascunhos existentes.

## Evolução 2.4.0 — piloto ativo

- Uma coluna de perguntas em celular e desktop; só a seleção da equipe usa grade.
  Todas as opções da equipe ficam visíveis na página, sem caixa com rolagem interna.
- Responsável pelo envio identificado pela conta autenticada (`usuario_id`), nome
  e vínculo de agente. O servidor monta o retrato `responsavel`; o navegador não
  escolhe o autor. Revisão preserva esse retrato e mantém o autor original.
- Agente vinculado pré-selecionado e bloqueado no navegador; servidor recusa envio
  ou aprovação se ele for retirado. Contas sem vínculo ativo e inequívoco podem
  salvar rascunhos, mas precisam de conferência do vínculo antes de enviar.
  Não há associação automática pelo nome de login nem alteração de contas.
- A pedido do usuário, o perfil básico pode selecionar os colegas participantes
  na captura. Esta é uma exceção localizada à seleção de equipe; não modifica a
  anonimização de consultas, rankings, relatórios ou outras áreas.
- Quarteirões sugeridos a partir do RG e das geometrias ativas da localidade;
  logradouros sugeridos a partir dos imóveis do RG daquele quarteirão. A API não
  entrega números de imóveis, nomes de moradores ou produção. Localidade sem
  correspondência única ou referência ausente retorna lista vazia.
- Campos livres apresentam lista de sugestões e conservam entrada manual. Trocar
  a localidade limpa quarteirão/rua dependentes; trocar a quadra limpa a rua.
  Não altera o RG: a sugestão apenas facilita o preenchimento.
- PE preserva o catálogo específico do ponto: escolher quadra determina a rua
  compatível, sem inventar uma combinação fora do ponto cadastrado. LIRAa mantém
  as escolhas condicionais e os campos existentes de outra quadra/outra rua.
- Dados antigos conservam a conta autora já registrada. Não se atribui
  retroativamente um vínculo de agente que não tenha sido registrado no envio.
  Um rascunho antigo passa pelas novas regras ao ser salvo/enviado novamente.
- Kobo em paralelo e RG offline preservados. Os dez novos formulários continuam
  online; os catálogos e rascunhos não foram adicionados ao cache do dispositivo.

Validações com massa fictícia: API de autor/equipe, revisão imutável, restrição
por setor, referências sem moradores, formulário móvel/desktop e preenchimento
manual. Regressão geral: 1.189 testes, seis ignorados, nenhuma falha. API
focada: 17 testes; instalador: 20 testes. Chromium confirmou dez formulários
em celular/desktop, uma coluna, equipe fixa, sugestões e texto livre, seleção
de PE em ordem quadra/rua e envio/revisão/aplicação. PostgreSQL descartável
confirmou referências sem moradores e aplicação/auditoria atômicas. Teste Node
confirmou o isolamento do cache offline. Ativação administrativa confirmada
em 06/11/2026 às 14h17: relatório aplicado/concluído, backup completo e
PostgreSQL realizados, 96 tabelas preservadas e prova limitada OK.
As 21 verificações públicas/locais passaram: cinco entradas na versão 2.4.0,
assets iguais aos instalados, APIs anônimas negadas e catálogo privado não exposto.
Kobo e sua automação preservados. Nenhum formulário real enviado nesta conferência;
conferência operacional no aparelho do piloto continua com o usuário.

## Evolução 2.5.0 — piloto ativo

Pedido expresso do usuário: propostas 1, 2, 7 e 8. QR Code/amostras apenas
explicados, sem implementação. Os dez formulários seguem online.

### Salvamento automático

Após uma pausa no preenchimento, salva rascunho no servidor, sem aplicação de
dados oficiais. Indicação separada distingue salvando, salvo e não confirmado.
Alterações durante uma requisição continuam na tela e são enviadas na revisão
seguinte. Repetição após perda de recibo reapresenta o mesmo conteúdo/UUID/revisão;
conflito entre abas pede conferência do envio, sem sobrescrita automática.
Requisição recusada por validação pode ser corrigida na própria tela.
Sem internet, manter a página aberta: não há armazenamento offline novo nem
garantia de recuperação de alterações ainda não recebidas se o aparelho fechar
a página. Reabre pelo endereço do envio ou por Meus envios. Salvar rascunho não
preenche a data de envio; o primeiro envio efetivo preenche esse registro.

### Próxima visita

Enviar e iniciar próxima visita primeiro confirma o recebimento do envio atual.
Só depois oferece escolher equipe, data da visita e localidade para reaproveitar.
Cria UUID novo e limpa os demais campos, repetições, endereço, proposta de retorno
e vínculo de agenda. O agente responsável continua obrigatório. Dados do imóvel,
morador, animal ou resultados não são copiados automaticamente.

### Agenda e retornos

No detalhe de uma atividade manual de campo da agenda, Registrar atividade
oferece formulários permitidos no setor/perfil. O novo envio fica associado ao
ID do evento e à data da ocorrência (inclusive recorrentes). Evento de outro
setor, inexistente ou data incompatível é recusado; é possível desvincular o
preenchimento pela tela. A agenda mostra links/situações dos envios próprios;
gestão pode conferir os demais permitidos. Não há conclusão automática da tarefa.

O agente pode propor data, hora opcional e observação de retorno. Após aprovar,
a gestão confirma em botão específico. Criação do evento, vínculo e auditoria
confirmam na mesma transação, com trava de linha e proteção contra duplicação.
Mesmo após aplicar os dados oficiais, pode confirmar uma proposta já existente.
Retorno confirmado deve ser alterado pela agenda; não se reescreve a proposta
para criar outro evento silenciosamente. Não apaga eventos ao editar formulários.
A observação confirmada fica visível na agenda do setor: usar apenas informações
necessárias ao agendamento.

### Correção dirigida

Na revisão, cada pergunta permite orientação de até 500 caracteres. Devolução
conserva motivo geral e lista de campos válidos; o agente vê resumo e mensagens
junto das perguntas. Salvar/reenviar não remove orientações por decisão do agente.
Nova aprovação encerra os apontamentos. Para repetições, a orientação é por campo;
o revisor deve indicar o número da coleta/animal na mensagem quando necessário.

Sem novas contas, alterações de credenciais ou envio de respostas ao Kobo.
Homologação operacional em aparelho real continua necessária antes de ampliação.

Validação 2.5.0: regressão geral com 1.199 testes, seis ignorados e nenhuma falha;
API focada 22 testes, instalador 22. Navegador Chromium móvel/desktop nos dez
formulários; fluxo de salvamento, recarga, offline/online, recibo perdido com
edição posterior, próxima visita, devolução por campo, reenvio, aprovação,
confirmação de retorno e aplicação com dados fictícios. PostgreSQL isolado
confirmou criação idempotente de retorno e aplicação/auditoria transacionais.
Node confirmou isolamento do offline. Ativação administrativa confirmada
em 06/11/2026 às 15h45: relatório aplicado/concluído, backup completo e
PostgreSQL realizados, 96 tabelas preservadas e prova limitada OK.
As 25 verificações públicas/locais passaram: cinco entradas na versão 2.5.0,
assets de formulários/agenda iguais aos instalados, APIs anônimas negadas e
catálogo privado não exposto. Kobo e sua automação preservados. Nenhum formulário
ou evento real criado nesta conferência; teste operacional em campo permanece
com o usuário.
