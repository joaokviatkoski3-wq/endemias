# Fechamento da versão 2.0.0

Em 05/11/2026 o usuário aprovou o visual e pediu explicitamente retirar o
sufixo de candidata. Esta promoção altera somente a identificação da versão;
não implica que toda função tenha passado por homologação operacional.

Código preparado em `C:\endemias-interface`, branch `codex/versao-200-e-auditoria`.
Produção segue 2.0.0-rc.3 até execução/conferência do pacote administrativo.
Mesmos dados, permissões, dependências, migrações e configurações.

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
