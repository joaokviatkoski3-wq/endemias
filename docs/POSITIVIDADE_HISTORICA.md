# Positividade histórica de coletas

Atualizado em 27/11/2026.

## Finalidade

A página **Positividade** (`/positividade`) consulta os positivos para
*Aedes aegypti* no período escolhido, inclusive quando não geram uma notificação
operacional. O seletor alterna a unidade de contagem da tabela, dos indicadores,
dos totais por localidade e da exportação.

- **Focos positivos por imóvel** (padrão). Uma visita com pelo menos uma
  amostra positiva é um foco. A linha mostra o total de amostras positivas
  e os respectivos tubos. Outra visita positiva ao mesmo imóvel é outra
  ocorrência. A identificação usa o ID da visita, sem agrupamento por
  texto de endereço ou nome do morador.
- **Amostras positivas**. Uma linha por coleta com leitura positiva.
  A visão usa somente a fonte laboratorial.

Por exemplo, três tubos positivos em uma visita equivalem a três amostras
positivas e a um foco. A busca por um desses tubos na visão de focos retorna
a visita com todos os seus tubos positivos.

Ela não substitui **Resultados Lab.**: aquela página continua sendo a consulta
detalhada dos tubos que existem em `resultados_laboratorio`.

## Fontes e limites

| Origem exibida | Fonte | Informações disponíveis |
| --- | --- | --- |
| Histórico pré-sistema | `focos_positivos` com `origem='historico'` | Data, localidade, endereço, quarteirão, morador, tipo, depósitos e agentes gravados no foco. Tubo e quantidades podem não existir. |
| Leitura laboratorial | `resultados_laboratorio` + `coletas` + `visitas` | Resultado por tubo, formas de *Ae. aegypti*, endereço, localidade, imóvel e agentes. |

O histórico pré-sistema é exibido na visão de focos, conforme o registro
preservado. A quantidade de amostras fica indisponível quando a relação com as
coletas não é conhecida. A tela e o XLSX indicam a ausência do detalhe
laboratorial.

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

`/api/positividade/exportar` gera XLSX com o mesmo modo e filtros da página.
A planilha de focos inclui a coluna **Amostras positivas**. A quantidade e
as colunas de formas de *Ae. aegypti* ficam vazias nos focos históricos
quando o detalhe laboratorial não está disponível.
