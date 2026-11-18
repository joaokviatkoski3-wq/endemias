# Conferência de medicação — 18/11/2026

Estado posterior: versão 2.9.1 ativada, segundo lote confirmado pelo operador
aplicado; 2.650 entregues (2.590 com baixa e 60 municipais dispensadas), zero
baixas pendentes. Acordo municipal e números atuais em docs/ESTOQUE_291.md.
As consultas e a candidata descritas abaixo são registros das etapas anteriores.

## Planilha recebida e conciliação por entrega

O arquivo zoomed.xlsx fornecido em 18/11 contém 85 entregas, 33 tutores e
confirma 2.590 cápsulas: 870 Município e 1.720 SESA. SHA-256 da origem:
251232802c0ced42d4980c65671d0a4c2f110cd708be1efe31f98a3b30a79bf4.
O nome do animal está vazio em todas as linhas. Repetições de tutor/data não
foram descartadas; há tutores com vários animais e entregas legítimas iguais.

Primeiro lote aplicado no PostgreSQL oficial em 18/11 às 10h56:
11 atualizações e uma inclusão. Entregas 20/21 passam
de 30 a 35 cápsulas; fontes corrigidas em 47/49/61/62/63/80; datas corrigidas
em 49/61/65/90; baixa 93 confirmada; inclui entrega municipal de 24/09 na
receita 76. Quantidades prescritas, situações clínicas, anexos, observações e
movimentos manuais de estoque ficam preservados. Resultado confirmado do lote:
2.680 entregues, Município 900 e SESA 1.780. Não é o fechamento da conciliação.

Permanecem sem decisão: duas correspondências de tutores com nomes diferentes;
ano de uma entrega de Celoni (2025 na origem versus 2026 no VSATT, sem animal);
entregas 45/88/91/96 ausentes no ZooMed, 120 cápsulas. As três últimas têm
baixa pendente. A observação do animal da entrega 96 informa medicamento da
Vigilância Ambiental sem lançamento no ZooMed. Não há evidência para apagar
essas entregas apenas para igualar totais. Perguntas encaminhadas ao operador.

Utilitário scripts/reconciliar_entregas_zoomed.py recebe plano privado e hash
da planilha. Validação read-only confere a assinatura das cinco tabelas.
Aplicação exige --aplicar, backup PostgreSQL com catálogo validado, bloqueio
curto das tabelas e revalidação. Transação única com auditoria por entrega,
antes/depois, IDs e linhas de origem; não permite excluir. Verifica todos os
registros de entregas e preserva as outras tabelas antes de confirmar. Planos,
dados pessoais, fonte e resultados não entram no Git. Cinco testes do
utilitário e 66 testes de Esporotricose passaram. Aplicação concluída, com 12
auditorias geradas pelo lote zoomed-20261118-lote1. Backup prévio de 7.752.966
bytes, catálogo validado, em ProgramData/EndemiasWeb/conciliacao-zoomed-20261118-105637;
SHA-256 bda449c2a8a16fdda88f29c24b989785e643fd229a0923ea0ee146a53fa6a3a2.
O utilitário conferiu o conteúdo de cada entrega e a preservação de receitas,
anexos, estoque manual e dados clínicos antes de confirmar a transação.
Uma nova conexão read-only confirmou as assinaturas e as 12 auditorias.
Saldo calculado 610, necessidade quantificada 880 em 11 animais ativos e
déficit 270. Ver docs/CONCILIACAO_ZOOMED_20261118.md para o registro completo.

## Consulta inicial (antes da planilha e das correções)

Consulta somente leitura no PostgreSQL oficial; nenhuma entrega, fonte,
baixa ou movimento de estoque foi alterado. Referência ZooMed informada pelo
usuário para todo o histórico: total 2.590, Município 870, restante 1.720.
Não houve consulta direta nem importação de relatório do ZooMed.

| Indicador | VSATT | Referência ZooMed |
|---|---:|---:|
| Total entregue | 2.640 | 2.590 |
| Município | 750 | 870 |
| SESA | 1.890 | 1.720 |
| Entregas marcadas como baixadas no VSATT | 2.520 | 2.590 |

Quatro entregas municipais de 30 cápsulas cada estão com baixa pendente:
IDs 88, 91, 93 e 96. As pendências de baixa não devolvem cápsulas ao estoque:
as entregas já realizadas continuam descontadas. Não foram encontrados
registros repetidos com mesma receita, data, fonte e quantidade; essa checagem
limitada não prova ausência de outros erros. Não há uma entrega isolada de 50
cápsulas que explique a diferença total. Necessário confrontar a relação de
entregas do ZooMed, linha a linha, antes de corrigir dados oficiais.

## Sobras e saldo

Cinco movimentos classificados como Sobra (IDs 1 a 5, em 03/07/2026) somam
270 cápsulas. Entradas: SESA 1.800 e Município 990; ajustes positivos 230;
entregas 2.640. Saldo: 1.800 + 990 + 230 + 270 - 2.640 = 650.
Excluir as sobras reduziria o saldo a 380. Ocultar somente o card não muda
esse cálculo. A raridade das devoluções não demonstra que os lançamentos
históricos estão incorretos; confirmar sua origem e o saldo físico antes de
excluir ou reclassificar. Os ajustes positivos de 230 também devem ser
considerados na conferência do inventário, sem confundi-los com entregas.

## Candidata 2.9.1

Worktree C:\endemias-estoque-zoomed, branch codex/estoque-conferencia-zoomed.
Novo card de entregas do VSATT com total, fontes Município/SESA e baixa marcada
ou pendente. Não fixa os números informados pelo usuário nem representa uma
sincronização com o ZooMed. Nenhuma remoção de sobras foi implementada.
66 testes de Esporotricose passaram. Tela conferida em Chromium a 1440/390 px,
com dados fictícios. Sem migração; candidata ainda não ativada.
