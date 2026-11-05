# Fechamento da versão 2.0.0

Em 05/11/2026 o usuário aprovou o visual e pediu explicitamente retirar o
sufixo de candidata. Esta promoção altera somente a identificação da versão;
não implica que toda função tenha passado por homologação operacional.

Produção **2.0.0 ativa**, release `fa0aba8`, promovida a partir de rc.3 em
05/11/2026 às 13h29. Código preparado em `C:\endemias-interface`, branch
`codex/versao-200-e-auditoria`. Mesmos dados, permissões, dependências,
migrações e configurações.

`scripts/ativar_200_estavel_windows.py` seleciona rc.3 → 2.0.0 no instalador
conferido: backup PostgreSQL/completo, parada das três entradas, comparação
de dados/arquivos, prova na conta limitada, atualização da versão protegida e
retorno apenas de código/configuração em falha. Nenhum DDL ou nova divisão Kobo.

Atalho previsto: **Atualizar VSATT - Versao 2.0.0.bat** na Área de Trabalho.
Relatório: `C:\ProgramData\EndemiasWeb\ativacao200estavel-resultado.json`.
Não repetir os ativadores anteriores.

Suíte de preparação: **1.030 testes OK, seis ignorados**, 430,187 segundos,
em banco fictício (`.venv/regressao-200-estavel.log`). A versão é exibida por
`app_core/version.py`, login, rodapé, portal e importação feita por `iniciar.bat`.
Chromium/CSRF/CSP confirmou portal, logins e páginas dos dois setores, desktop
e celular, em `.venv/setores-browser-resultado.json` (capturas
`browser-setores-_x446zy3`).

Após a atualização, o mesmo atalho chama `scripts/auditar_esquemas_kobo.py`:
consulta GET somente da estrutura dos formulários configurados, preferindo
versão implantada quando disponível, sem consultar `/data/` ou respostas.
Grava `.venv/auditoria-geral/kobo-esquemas.json`, sem token, URL/UID privado
ou listas nominais. Redirecionamentos são recusados e endpoints permitidos
são restritos a metadados de asset/versão. A coleta não altera `last_sync`,
Kobo, banco ou configurações; falha parcial não desfaz a promoção. Prova
fictícia confirmou bloqueio de `/data/` e exclusão de token/listas pessoais.

Após esta promoção, o usuário pediu auditoria funcional ampla de cada página,
ligação entre módulos e correspondência com Kobo, começando por carga do BRI.
Auditoria deve separar confirmado, suspeita e melhoria; ensaios só fictícios,
sem modificar dados/configurações de produção ou fazer importações reais.
Correções descobertas serão tratadas separadamente do fechamento desta versão.

## Ativação e revisão conferidas

- Usuário executou o atalho; relatório `ativacao200estavel-resultado.json`:
  aplicado/concluido,96 tabelas/dados e arquivos preservados, mesmas configurações Kobo,
  tarefa/identidade/ambiente, agendamento restaurado; todos os checks da conta
  limitada passaram. Nenhum DDL.
- Backup PostgreSQL:7.548.674 bytes/catalogado, SHA-256
  `c53bd9db0c640b59e8106e59b320692cf89f59d9ba4c927861ce1e35ddaf944d`.
  Completo: `D:\BackupsEndemias\backups_web\completos\endemias_completo_20261105_132918.zip`,
  310.617.801 bytes, SHA-256
  `a166d9d41a933356bfe97aa3cd90f9aff576de71fd46a696df213a2574c81844`.
- Portal/logins HTTPS e logins locais 5000/5004: 200/2.0.0; APIs sem sessão: 401;
  portal sem cookie e respostas private/no-store. Evidência em
  `.venv/publicacao-200-estavel.json`.
- Coleta de dez estruturas implantadas concluiu sem erros e sem respostas
  consultadas. Revisão funcional finalizada; o registro público é
  `docs/REVISAO_FUNCIONAL_200_20261105.md`, com ponteiro para relatório local.
- Não repetir os atalhos já executados. Achados da auditoria não foram corrigidos
  por esta promoção de numeração.
