# Cards de entregas no estoque — versão ativa 2.9.2

Ativada em 18/11/2026, release 165aad1. Backups PostgreSQL e completo,
preservação das 98 tabelas e arquivos operacionais, prova da conta limitada,
automação Kobo restabelecida e todas as entradas confirmadas. Portal e logins
públicos/locais dos dois setores responderam HTTP 200 em 2.9.2. Sem migração
ou mudança de dados; agregados de estoque antes/depois permaneceram iguais.

Consulta real da ativação: Município registrado ZooMed 870, somente VSATT
119, total municipal 989; SESA 1.720; total ZooMed 2.590; geral 2.709.
Baixas pendentes zero. Saldo calculado 581 (SESA 580, Município 1), necessidade
quantificada 821 em 11 ativos, déficit 240. Não é contagem física.

A diferença para as 60 municipais da conciliação anterior são dois novos
lançamentos em 18/11 às 13h22, IDs 99/100, de 29 e 30 cápsulas. Entregas
88/96 continuam com 30 cada. Consulta somente leitura confirmou os quatro
registros; não houve correção dessas quantidades. Foi perguntado ao operador
se a quantidade 29 deve permanecer ou ser corrigida para 30. Não alterar sem
resposta. Os dados nominais ficaram somente no relatório privado local.

Solicitação: distinguir as 870 cápsulas municipais com registro no ZooMed
das 60 municipais entregues somente pelo VSATT, compondo 930 municipais.

Estoque disponível, necessidade ativa, saldo após atendimento e sobras ficam
no primeiro grupo. As entregas aparecem em um grupo próprio, com unidades
explícitas em cápsulas e abrangência de todo o histórico:

- Município registrado no ZooMed: 870 na conferência anterior.
- Município somente no VSATT, dispensado de ZooMed: 60.
- Total entregue pelo Município: 930, com composição 870 + 60 = 930.
- Total entregue pela SESA: 1.720, indicando registradas e pendentes.
- Total registrado no ZooMed: 2.590, com composição por fonte.
- Total geral entregue no VSATT: 2.650, incluindo as municipais dispensadas.

São valores da conferência anterior, não constantes fixas da tela. A API
agrega baixa dispensada e pendente por fonte, além dos totais já existentes.
Os cards usam os agregados e incluem eventual baixa municipal antiga pendente
na composição do total municipal, sem ocultá-la ou tratá-la como dispensada.
Texto explica que todas essas entregas já descontaram estoque, e que os
valores ZooMed correspondem às baixas informadas no VSATT.

Sem migração nem alteração de entregas, receitas, estoque ou arquivos de anexo.
14 testes de estoque, regra municipal e smoke de páginas passaram. Ensaio com
dados fictícios no Chromium a 1440/390 px conferiu os seis valores, composição,
cenário com pendências posteriores, ausência de erros JS e de alargamento da
página. Não foi repetida a suíte completa por se tratar de alteração localizada.

Ativador scripts/ativar_estoque_292_windows.py mantém o fluxo controlado de
backup PostgreSQL e completo, pausa da automação Kobo, janela curta, integração
ff-only, assinaturas de tabelas/arquivos, prova da conta limitada e entradas.
Resultado em C:\ProgramData\EndemiasWeb\ativacao-estoque292-resultado.json:
aplicado/concluído, 98 tabelas, sem migração. Backup PostgreSQL:
C:\ProgramData\EndemiasWeb\ativacao-estoque292-20261118-132951\antes_conta_limitada.dump
(7.757.359 bytes, catálogo validado), SHA-256
3898678be8e8ba90a02f7ac52480e47a76d8b16a9920d9b0027e680d9424b5a7.
Backup completo: D:\BackupsEndemias\backups_web\completos\endemias_completo_20261118_132957.zip
(311.598.101 bytes), SHA-256
88366cd0ead465d1a20d3041e235d42da8fd16ac3e219c16f38c76bbf3e86d85.
