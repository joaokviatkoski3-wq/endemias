# LIRAa — escolha de logradouros do RG

Integrado em 03/11/2026 na `master` (`1256d97`), código `1.74.0`. Solicitação do usuário: escolher a rua
do quarteirão no formulário, mantendo digitação para ruas novas. Essa mudança
autoriza a revisão do campo de logradouro do formulário manual aprovado; não
autoriza alterar o plano nem considera os ACS definitivamente escolhidos.

## Uso no campo

1. Escolher localidade e quarteirão.
2. Em **Logradouro**, escolher uma das ruas daquele quarteirão cadastradas no RG.
3. Se necessário, escolher **Outro — digitar** e preencher **Nome do outro
   logradouro** (obrigatório, até 300 caracteres).

As opções estão dentro do XLSForm, sem arquivo CSV ou consulta à internet
durante a visita. Para quarteirão sem ruas cadastradas, fica disponível Outro.
A lista cobre os quarteirões incluídos no formulário; um quarteirão digitado
em Outros que não consta desse plano também permite informar a rua por Outro.
Isso não autoriza esse quarteirão adicional no planejamento/importação.

## Preparar e publicar

- Em **Formulário do ciclo**, salvar os ACS e gerar o XLSForm. A lista de ACS
  continua editável depois, inclusive após importações.
- Cada geração consulta os nomes atuais do RG e cria uma lista por
  localidade/quarteirão. Não altera o RG. Variações apenas de caixa/acentos
  são agrupadas, com a grafia mais frequente e desempate estável.
- No ciclo 4, preserva as demais intervenções manuais: 267 quarteirões
  (261 sorteados e 6 adicionais), datas 09–13/11/2026, campos, tratamento,
  coleta, ciclo, assinatura e escolhas. Acrescenta a lista de ruas e o
  complemento de Outro e atualiza `settings.version`.
- Substituir o XLSForm no **mesmo projeto/formulário Kobo** e implantar
  novamente; manter o UID configurado no Endemias. A geração não publica.
- Atualizar o formulário nos aparelhos e conferir a versão antes do uso.
  Rascunhos e formulários já baixados não recebem a lista automaticamente.

A cópia entregue neste chat parte do XLSX manual e preserva exatamente os ACS
ali presentes, ainda provisórios. O download pelo sistema usa os ACS salvos na
configuração do ciclo. Não tratar nenhuma dessas listas como definição final.

## Importação e preservação

Cada escolha possui identificador único contendo um contexto de
localidade/quarteirão e o nome da rua no momento da geração. A importação
verifica o contexto e grava o nome legível no campo `logradouro`; não grava
o código como endereço. A escolha de Outro usa o texto complementar e o exige
preenchido. Mudanças posteriores no RG não renomeiam visitas antigas.

Respostas do formulário anterior, com logradouro em texto livre, continuam
aceitas. Não há normalização retroativa, alteração de respostas no Kobo,
criação de ruas no RG ou migração de banco. O XLSX-fonte aprovado permanece
byte a byte preservado (SHA-256
`01934925d87a5f9413628f9f0ccae8d4022f964ad1f12ccc8a441b10f49a88dd`).

## Conferências e situação operacional

- Consulta somente leitura ao PostgreSQL real: **267 quarteirões, 976 opções
  RG e nenhum quarteirão sem opções**. São opções por quarteirão, não 976 ruas
  distintas no município. Nenhum nome de morador ou número de imóvel é lido.
- XLSForm compilado com pyxform 4.5.0, sem avisos; filtro com localidade,
  quarteirão numérico e exceção para Outro. Sem validação externa Java/ODK.
- Filtro do XML compilado conferido em 535 combinações: os 267 quarteirões
  tanto escolhidos quanto digitados em Outros, mais um fora da lista. Todos
  retornaram as ruas corretas e Outro. Os 976 códigos retornam o nome RG.
- Testes sintéticos cobrem Unicode, contexto errado, Outro obrigatório,
  formulário antigo, grafia RG, filtros, repetição da geração, ACS mutáveis
  e preservação do restante do formulário/plano. Ensaio PostgreSQL usa
  somente tabelas temporárias em `endemias_teste`.
- Validação geral: **859 testes sem falhas, 5 ignorados**; 2 testes JavaScript
  LIRAa, 74 testes LIRAa focados finais e ensaio PostgreSQL 18 descartável também passaram. O SQLite congelado
  manteve SHA-256 `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
- **Ativação concluída às 09h04 de 03/11/2026**, após autorização expressa do
  usuário para esse reinício. `/login` respondeu HTTP 200 com `1.74.0`;
  comparação antes/depois preservou contagens e assinaturas das 11 tabelas
  LIRAa, SQLite congelado e XLSX-fonte. Verificador do plano retornou código 0.
  Nenhuma migração, importação, limpeza de visitas ou escrita no plano.
- Publicação no Kobo e teste no aparelho permanecem pendentes. Não antecipar
  as datas do ciclo real para realizar testes. Atualizar os aparelhos depois
  da implantação do XLSForm, antes de coletar com as novas escolhas.

Referência da sintaxe: [filtros de escolhas no Kobo](https://support.kobotoolbox.org/choice_filters_xls.html).
