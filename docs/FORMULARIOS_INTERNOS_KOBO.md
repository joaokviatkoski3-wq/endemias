# Formulários internos compatíveis com Kobo — piloto ativo

Pedido em 06/11/2026. Branch `codex/formularios-internos-kobo`, worktree
`C:\endemias-interface`. Produção 2.3.0 ativa desde 06/11/2026 às 13h36, release `bf36464`.

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
