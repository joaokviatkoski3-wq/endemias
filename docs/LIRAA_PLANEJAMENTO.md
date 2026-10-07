# LIRAa — planejamento e sorteio (primeiro incremento)

Atualizado em 01/10/2026. Código inicial da branch `codex/liraa-planejamento`
integrado na `master` e disponível no serviço oficial `1.60.0`. A migração
PostgreSQL `0023_liraa_planejamento.sql` foi aplicada com autorização do
usuário. **Não usar o sorteio em campo sem homologação metodológica.**

Disponível no serviço oficial `1.61.0` desde 30/09/2026: subaba Mapa dos
estratos. A migração 0024
guarda quarteirões individuais por ciclo/estrato. É possível selecionar
localidade inteira ou somente alguns quarteirões, inclusive repartindo uma
localidade entre estratos; cada quarteirão tem um único estrato no ciclo.
O mapa e a lista representam a mesma seleção. A soma de unidades RG é
prévia e não substitui o `N` confirmado. O painel mostra quarteirões sem RG
e sem estrato. Planos antigos por localidade permanecem legíveis e são
convertidos para vínculos explícitos quando editados. Um estrato sorteado
continua congelado; quarteirões que desaparecem da camada bloqueiam novo
sorteio até revisão. A migração 0024 foi aplicada com autorização do usuário
após backup validado; o serviço foi reiniciado. A interface autenticada ainda
requer validação visual pelo operador.

Em 01/10/2026, a branch `codex/liraa-mapa-geral` foi integrada na `master`
e o servico oficial reiniciado em `1.63.0`, disponibilizando a terceira subaba
**Mapa geral · consulta**. A validacao visual autenticada continua pendente.
A consulta mostra juntos todos os estratos do ciclo escolhido, em diferentes
cores, incluindo todas as localidades; quarteiroes sem estrato ficam cinza.
Lista, filtro e clique no mapa mostram N confirmado, referencia RG, localidades,
observacoes e alerta de quarteiroes ausentes da camada. Nao ha edicao nem
sorteio nessa subaba. A geometria vem da mesma API de leitura ja existente;
nao ha migracao nem alteracao de dados reais.

## Escopo disponível

- Página separada `/liraa`, com leitura para usuários autenticados e alterações
  restritas a administradores, por formulário protegido por CSRF.
- Inventário de quarteirões da camada GeoJSON ativa do Registro Geográfico,
  agrupado por localidade. Cada par localidade/quarteirão é uma unidade
  amostral; a ordem usada no sorteio é nome da localidade e número do
  quarteirão. Todas as áreas são **tratadas provisoriamente como urbanas**.
- Contagens de referência do RG no LIRAa (correção `1.67.1`): cada registro
  de imóvel conta uma vez, inclusive COND = 20 conta como 1, excluindo tipos
  `PE` e `REF`. Não expande unidades de condomínio. Quarteirões sem RG continuam no
  universo, com estimativa indisponível. A contagem RG **não substitui** o
  número `N` de imóveis, que deve ser confirmado e informado pelo operador.
- O cadastro de estratos aceita a seleção de quarteirões individuais de uma
  ou mais localidades na subaba Mapa dos estratos. Um estrato pode ser editado
  antes do sorteio; um ciclo pode ser corrigido antes do primeiro sorteio.
  Administradores podem excluir um estrato mesmo após o sorteio, removendo
  juntos seu sorteio e os vínculos territoriais. Também podem excluir um ciclo
  com todos os estratos e sorteios vinculados. Os botões exigem confirmação,
  e a exclusão com auditoria ocorre em uma única transação. Outros ciclos,
  a camada de quarteirões e os registros do RG não são alterados.
- Sorteio sistemático registrado uma única vez por estrato, com semente,
  parâmetros, universo completo, hash SHA-256 e quarteirões selecionados.
  Depois do sorteio o estrato fica congelado; atualização do GeoJSON ou RG
  não altera o resultado salvo.

## Fórmulas e validação do sorteio

Para `N` imóveis confirmados e `A` quarteirões do estrato:

Nos estratos normais, `n = arredondar(450 N / (N + 450))`; nos reduzidos,
`n = arredondar(250 N / (N + 250))`. Em ambos,
`B = teto(N / A)`, `Q = mínimo(A, máximo(1, arredondar(n / (p B))))`
e `IA = A / Q`. O arredondamento de `n` e `Q` é ao inteiro mais próximo,
com empate para cima. A base 250 no reduzido e o teto de `B` foram inferidos
do relatório gerado pelo aplicativo legado, não da fórmula genérica impressa
no manual.

`p = 0,20` no estrato normal (8.100–12.000 imóveis) e `p = 0,50`
no reduzido (2.000–8.100). O código exige essas faixas para sortear,
aceitando 8.100 em ambos os tipos. O início casual `IC` é sorteado em
`(0, IA)`, como estabelece o manual. O relatório legado exibiu valores inteiros
de `IC`, mas não permite concluir se houve arredondamento apenas na exibição.
O sorteio é distribuído por **localidade** (bairro no aplicativo legado), na
ordem fixa do universo territorial. Cada localidade recebe um início local
obtido de `arredondar(IC + selecionados_anteriores × IA -
quarteirões_anteriores)`, limitado a 1. Em cada uma, somam-se múltiplos de
`IA` ao início local, selecionando a **parte inteira** das posições enquanto
o ponto amostral não ultrapassar o número de quarteirões daquela localidade.
A sequência usa frações para reduzir erros de precisão. `Q` é o total
planejado; a soma efetiva por localidade pode diferir ligeiramente, como o
manual admite. Os dois números são exibidos separadamente.

O aplicativo legado numera as posições sorteadas de `1` até o total de cada
bairro. Isso **não é o ID municipal do quarteirão**. No Endemias, a localidade
substitui o bairro e a posição é traduzida para o quarteirão municipal real
pela ordem numérica crescente dos IDs cadastrados na camada. Se apenas parte
de uma localidade fizer parte do estrato, a sequência `1..A` aplica-se somente
aos quarteirões dessa parte. A tabela do resultado mostra lado a lado a
posição sorteada e o ID municipal correspondente. O usuário deve conferir a
composição e a ordenação antes de usar a lista em campo.

O relatório de simulação `teste-lira.pdf` enviado pelo usuário trouxe cinco
casos: `(N,A,n,B,Q)` iguais a `(12104,325,434,38,57)`,
`(10214,266,431,39,55)`, `(9312,228,429,41,52)`,
`(12071,349,434,35,62)` e `(5090,166,238,31,15)`.
Os parâmetros acima reproduzem todos os cinco valores de `n`, `B`, `Q` e `IA`;
há testes automatizados para impedir regressão. Dois estratos simulados
ultrapassam os 12.000 imóveis recomendados pelo manual: foram usados apenas
como evidência do cálculo, sem liberar sorteios fora da faixa no Endemias.
O exemplo do manual com `N=9.000`, `A=350` produz `n=429`, `B=26`, `Q=83`.
O quadro de quarteirões do manual usa arredondamento ao inteiro mais próximo,
embora o texto adjacente e alguns valores intermediários sejam inconsistentes.
O relatório de parâmetros `liraa-Plano Amostral.pdf` e as 12 listas por
localidade enviadas em 01/10/2026 permitem confrontar **241 posições** nos
cinco estratos. A distribuição por localidade acima reproduz todas, inclusive
as contagens por bairro. No estrato 3, o relatório só imprime `IC = 2`;
`IC = 2,9` é um valor **inferido**, compatível com a lista, não um valor
comprovado no aplicativo. O Endemias guarda o IC completo para auditoria.

**Ainda não homologado para campo:** os 241 valores comprovam a sequência
**posicional**, mas o aplicativo legado não informa os IDs municipais
correspondentes. Falta conferir num caso real se a ordenação por ID municipal
faz sentido operacionalmente, além de validar a ordem das localidades e o
tratamento das localidades repartidas. Sorteios registrados anteriormente
permanecem congelados com seus parâmetros e seleção originais; esta correção
somente afeta novos sorteios de ensaio.

Referência metodológica: [Manual LIRAa 2013, Ministério da Saúde](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/svsa/dengue/manual_liraa_2013.pdf).

## O que ainda não está implementado

- Classificação efetiva urbano/rural. Se algum quarteirão rural estiver na camada, **não sortear** esse
  ciclo até o cadastro territorial estar corrigido ou essa classificação
  existir no LIRAa.
- O diário Kobo LIRAa e o registro de imóveis visitados estão disponíveis no
  código `1.66.0` (migração PostgreSQL 0025 aplicada em 06/10/2026), mas
  aguardam configuração do UID e validação com um primeiro lote pequeno.
  Resultados de laboratório e cálculo dos índices ainda não
  estão implementados. Ver `docs/LIRAA_VISITAS_KOBO.md`. Visitas TB/TBO/PVE
  existentes não são interpretadas como inspeções LIRAa.
- Exportação `.lira`. Quatro arquivos históricos de 2025 mostram 28 campos
  consolidados precedidos de `1` e `30`, mas o significado formal desses dois
  valores e a aceitação de arquivo próprio ainda exigem validação. Não gerar
  arquivo com dados inventados ou incompletos. Ver
  `docs/LIRAA_FORMATO_LIRA.md` para o mapeamento observado.
- Conferência em campo da tradução das posições `1..A` para os IDs municipais
  reais, da ordem das localidades e dos casos com localidade repartida entre
  estratos. O confronto das 241 posições não homologa sozinho essa tradução.

## Banco e implantação

SQLite cria as quatro tabelas LIRAa localmente em banco **de teste** ao abrir
o módulo. PostgreSQL usa a migração 0023. A migração não modifica tabelas
preexistentes do RG ou visitas. Foi aplicada ao banco oficial `endemias`
em 30/09/2026, após criar e validar o backup
`D:\BackupsEndemias\backups_banco\endemias_pre_liraa_0023_20260930_132619.dump`.
O serviço reiniciou com `1.60.0`; `/login` respondeu HTTP 200 e `/liraa`
redirecionou ao login sem sessão. A leitura direta do painel no PostgreSQL
retornou 15 localidades, 1.415 quarteirões e 0 ciclos. Não foi criado
nenhum dado de teste no banco oficial.

Testes focados: `python -m unittest discover -s tests -p test_liraa.py -v`
(com banco SQLite temporário). A regressão ampla usa a cópia isolada do
snapshot SQLite conforme `tests/_database_isolation.py`. Em 30/09/2026,
os 7 testes focados e os 742 testes da regressão ampla passaram
(5 ignorados); permaneceram avisos antigos de conexões SQLite em outros
módulos. A regressão usou cópia isolada do SQLite; a migração e o smoke
PostgreSQL foram realizados separadamente com autorização.

Para a subaba Mapa dos estratos, 13 testes focados e a regressão completa
de 747 testes passaram (5 ignorados), com SQLite copiado para isolamento.
A migração 0024 foi aplicada ao PostgreSQL oficial após o backup
`D:\BackupsEndemias\backups_banco\endemias_pre_liraa_0024_20260930_151050.dump`.
Após o reinício, o login respondeu HTTP 200 em `1.61.0` e a leitura direta
do painel retornou 15 localidades, 1.415 quarteirões e um ciclo existente
sem estratos. Nenhum sorteio foi executado. A interface autenticada ainda
não foi homologada visualmente pelo operador.
