# Conferência de medicação — 18/11/2026

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
