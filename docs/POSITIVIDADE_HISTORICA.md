# Positividade histórica de coletas

Atualizado em 17/09/2026.

## Finalidade

A página **Positividade** (`/positividade`) consulta todos os focos positivos
para *Aedes aegypti* no período escolhido, inclusive quando não geram uma
notificação operacional. É a consulta adequada para comparar localidades entre
o histórico pré-sistema e as leituras atuais.

Ela não substitui **Resultados Lab.**: aquela página continua sendo a consulta
detalhada dos tubos que existem em `resultados_laboratorio`.

## Fontes e limites

| Origem exibida | Fonte | Informações disponíveis |
| --- | --- | --- |
| Histórico pré-sistema | `focos_positivos` com `origem='historico'` | Data, localidade, endereço, quarteirão, morador, tipo, depósitos e agentes gravados no foco. Tubo e quantidades podem não existir. |
| Leitura laboratorial | `resultados_laboratorio` + `coletas` + `visitas` | Resultado por tubo, formas de *Ae. aegypti*, endereço, localidade, imóvel e agentes. |

Os itens históricos não recebem números, espécie ou tubos inventados. A tela e
o XLSX indicam explicitamente quando o detalhe laboratorial não está disponível.

Os nomes de localidade são normalizados somente na consulta. Assim, grafias
legadas como `S. VENÂNCIO`, `SAO VENANCIO` e `São Venâncio` aparecem, filtram e
são somadas como **São Venâncio**, sem alterar o texto preservado no banco.

## Regras da consulta

- A fonte atual lê diretamente `resultados_laboratorio`, portanto inclui
  positivos em PE e em terreno baldio, mesmo que `gera_notificacao=0`.
- A fonte histórica lê os focos preservados, independentemente do status de
  notificação.
- Registros atuais não são buscados novamente em `focos_positivos`; isso evita
  duplicar um foco que tenha sido criado para a mesma visita.
- Filtros de agente no legado usam o texto que foi preservado no foco. Nos
  resultados atuais, usam a relação normalizada `visita_agentes`.

## Exportação

`/api/positividade/exportar` gera XLSX com o mesmo recorte da página. As
colunas de formas de *Ae. aegypti* ficam vazias para o histórico quando o dado
não existia antes do sistema.
