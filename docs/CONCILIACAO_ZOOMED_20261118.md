# Conciliação de entregas com ZooMed — 18/11/2026

Atualização após confirmações do usuário: segundo lote aplicado às 11h40,
com oito auditorias; Caramelo/Peralta não receberam, Suelen/Pitoquinha receberam
e estão dispensados de baixa, identidades dos dois tutores confirmadas.
2.650 cápsulas físicas: 2.590 com baixa (870 Município, 1.720 SESA) + 60
municipais dispensadas, nenhuma baixa pendente. Só a data/animal de Celoni
continua pendente. Registro atual completo em docs/ESTOQUE_291.md. As seções
abaixo preservam o estado e as decisões do primeiro lote.

## Fonte e resultado confirmado

Planilha zoomed.xlsx fornecida pelo usuário, histórico completo: 85 entregas,
33 tutores, 2.590 cápsulas (870 Município, 1.720 SESA). SHA-256:
251232802c0ced42d4980c65671d0a4c2f110cd708be1efe31f98a3b30a79bf4.
Todos os nomes de animais estão vazios na planilha. Não deduplicar tutor/data:
há tutores com vários animais. Não corrigir apenas para igualar totais.

Primeiro lote aplicado no PostgreSQL oficial às 10h56, após pedido explícito
do usuário para corrigir conforme a planilha. Não depende de nova versão do
servidor nem exige reinício. A aplicação segue em 2.9.0.

| Indicador | Antes do lote | Após o lote | ZooMed |
|---|---:|---:|---:|
| Registros | 87 | 88 | 85 |
| Cápsulas | 2.640 | 2.680 | 2.590 |
| Município | 750 | 900 | 870 |
| SESA | 1.890 | 1.780 | 1.720 |
| Com baixa marcada no VSATT | 2.520 | 2.590 | 2.590 |
| Baixa pendente | 120 | 90 | — |

O total com baixa marcada coincide por compensação de diferenças ainda
pendentes; não significa equivalência por entrega, animal ou fonte.

## Alterações efetivas

- Quantidades: entregas 20/21 de 30 para 35 cápsulas.
- Fontes: 47/49/61/63/80 de SESA para Município; 62 de Município para SESA.
- Datas: 49 para 26/06, 61 para 31/07, 65 para 07/07, 90 para 13/10/2026.
- Baixa: 93 confirmada como Sim pela presença na planilha.
- Inclusão: entrega de 30 Município em 24/09/2026, receita 76, animal 51.

Receitas, anexos, observações preexistentes, estoque manual e situação clínica
preservados. Nenhuma entrega foi excluída. Sobras retornadas (270 cápsulas),
entradas e ajustes também não foram alterados. Foi constatada prescrição de
30 versus entrega de 35 em uma receita; não ajustar prescrição sem documento.

## Pendências enviadas ao usuário

1. Confirmar Elisama Nadelina Mesquita = Elisama Diniz. Se confirmado: entrega
   31 de 01/04 para 04/04/2026 e fontes 43/44 para Município (60 cápsulas).
2. Confirmar Luiz Henrique Scherelber = Luis Henrique Schreiber. Se confirmado:
   incluir 30 SESA de 27/10/2026 na receita 75.
3. Celoni: origem traz 13/03/2025; VSATT traz duas entregas de 13/03/2026 para
   animais diferentes. Não escolher o animal nem trocar o ano sem confirmação.
4. Entregas 45/88/91/96 não aparecem no ZooMed: 120 cápsulas, sendo 30 SESA
   com baixa Sim e 90 Município com baixa Não. Confirmar se ocorreram fisicamente
   ou são erros. O cadastro da entrega 96 informa medicamento da Vigilância
   Ambiental sem lançamento ZooMed. Ausência na planilha não prova erro local.

Se ambas as identidades forem confirmadas e as quatro entregas extras forem
comprovadas como incorretas, os valores resultariam em 2.590 (870 + 1.720).
Essa igualdade não comprova que se deva excluir os quatro registros.

## Estoque observado após o lote

Consulta atual encontrou 60 animais, 11 em tratamento, necessidade quantificada
880, saldo calculado 610 (SESA 520, Município 90) e déficit 270 cápsulas.
Nenhum ativo sem quantidade e sete situações para revisão. São dados do momento,
que incluem lançamentos operacionais anteriores ao lote; não são uma contagem
física nem garantia de cobertura de toda a duração futura do tratamento.

## Proteções e evidências

Utilitário scripts/reconciliar_entregas_zoomed.py: plano privado com assinatura
de cinco tabelas e hash da origem, validação read-only, backup PostgreSQL com
catálogo validado, bloqueio de tabelas com espera máxima de cinco segundos,
revalidação e transação única. Auditoria por entrega contém antes/depois,
IDs, linhas da planilha, lote e hashes. Não permite excluir. Antes do commit,
confere cada entrega e a preservação dos demais registros envolvidos.

Lote zoomed-20261118-lote1: 12 auditorias. Nova conexão de leitura confirmou
as assinaturas após o commit. SQLite congelado preservado, SHA-256
964152e21de44b4fff985f72a0d7945e8e7dcf260bbb019708b868c3b3a7a025.
Cinco testes de transação/rollback/proteção e 66 de Esporotricose passaram.

Backup privado:
C:\ProgramData\EndemiasWeb\conciliacao-zoomed-20261118-105637\antes_conta_limitada.dump
(7.752.966 bytes, catálogo validado), SHA-256
bda449c2a8a16fdda88f29c24b989785e643fd229a0923ea0ee146a53fa6a3a2.
Fonte e plano também copiados para essa pasta. Relatório nominal entregue no
Desktop do operador: Conferencia_ZooMed_VSATT_18-11-2026.md. Nenhum dado nominal,
planilha, plano privado ou dump foi incluído no Git.
