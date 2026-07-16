# Formulário Kobo para atualização completa do RG

Arquivo: `formularios_kobo/RG_Atualizacao_Completa_Kobo.xlsx`

## Objetivo

O formulário registra um quarteirão completo, preenchido do zero em campo. Cada
submissão representa um único quarteirão e não altera automaticamente o Registro
Geográfico oficial.

## Estrutura

- Identificação: localidade, quarteirão, data, agentes e observação geral.
- Trechos: um grupo repetido por combinação de logradouro e lado.
- Imóveis: grupo repetido dentro de cada trecho, com número, sequência, tipo,
  condomínio e observação.
- Conferência: totais automáticos e confirmação obrigatória de preenchimento
  integral.

O tipo `REF` não está disponível no Kobo. Ele permanece uma decisão interna do
revisor durante a preparação ou edição do RG no sistema.

## Listas incorporadas

O arquivo foi gerado com uma fotografia das listas existentes no banco em
16/07/2026:

- 15 localidades;
- 1.413 quarteirões;
- 2.109 combinações de localidade e logradouro;
- 21 agentes ativos;
- tipos `R`, `C`, `O`, `TB`, `PE` e `A`.

Localidades, quarteirões e logradouros usam identificadores técnicos sem acentos,
mas exibem os nomes oficiais aos agentes. Isso evita que variações de codificação
sejam gravadas como novas localidades.

## Uso no KoboToolbox

1. Crie um projeto no KoboToolbox por upload de XLSForm.
2. Selecione `RG_Atualizacao_Completa_Kobo.xlsx`.
3. Verifique a prévia antes de implantar o projeto.
4. Teste no KoboCollect com um quarteirão pequeno, um médio e um grande.
5. Somente depois do piloto, distribua o formulário aos demais agentes.

O formulário pode ser usado offline no KoboCollect depois de ser baixado no
dispositivo.

## Integração pendente

O XLSForm coleta e valida os dados, mas a subaba de revisão e a importação para o
Registro Geográfico ainda precisam ser implementadas. Essa integração deverá:

1. receber a submissão em uma área temporária;
2. comparar o RG enviado com a versão atual;
3. permitir ajustes, rejeição ou aprovação manual;
4. criar backup e histórico antes da confirmação;
5. substituir integralmente o quarteirão aprovado, sem somar linhas antigas;
6. impedir reimportação ou duplicidade pela identidade estável da submissão Kobo.

## Atualização das listas

Quando localidades, quarteirões, logradouros ou agentes mudarem no sistema, uma
nova versão do XLSForm deverá ser gerada e substituída no projeto Kobo. Registros
já coletados permanecem associados à versão usada no momento da coleta.
