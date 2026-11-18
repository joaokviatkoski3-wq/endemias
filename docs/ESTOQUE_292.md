# Cards de entregas no estoque — candidata 2.9.2

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
A situação efetiva será registrada após a ativação. Versão ativa anterior 2.9.1.
