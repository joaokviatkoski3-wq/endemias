# LIRAa — planejamento e sorteio (primeiro incremento)

Atualizado em 30/09/2026. Código da branch `codex/liraa-planejamento`
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

## Escopo disponível

- Página separada `/liraa`, com leitura para usuários autenticados e alterações
  restritas a administradores, por formulário protegido por CSRF.
- Inventário de quarteirões da camada GeoJSON ativa do Registro Geográfico,
  agrupado por localidade. Cada par localidade/quarteirão é uma unidade
  amostral; a ordem usada no sorteio é nome da localidade e número do
  quarteirão. Todas as áreas são **tratadas provisoriamente como urbanas**.
- Contagens de referência do RG: registros e unidades residenciais de
  condomínio, excluindo tipos `PE` e `REF`. Quarteirões sem RG continuam no
  universo, com estimativa indisponível. A contagem RG **não substitui** o
  número `N` de imóveis, que deve ser confirmado e informado pelo operador.
- O cadastro de estratos aceita a seleção de quarteirões individuais de uma
  ou mais localidades na subaba Mapa dos estratos. Um estrato pode ser editado
  ou excluído antes do sorteio. Um ciclo pode ser corrigido antes do primeiro
  sorteio e excluído se estiver vazio.
- Sorteio sistemático registrado uma única vez por estrato, com semente,
  parâmetros, universo completo, hash SHA-256 e quarteirões selecionados.
  Depois do sorteio o estrato fica congelado; atualização do GeoJSON ou RG
  não altera o resultado salvo.

## Fórmulas

Para `N` imóveis confirmados e `A` quarteirões do estrato:

`n = teto(450 N / (N + 450))`; `B = N / A`;
`Q = mínimo(A, teto(n / (p B)))`; `IA = A / Q`.

`p = 0,20` no estrato normal (8.100–12.000 imóveis) e `p = 0,50`
no reduzido (2.000–8.100). O código exige essas faixas para sortear,
aceitando 8.100 em ambos os tipos, conforme sobreposição nos limites
informados. O início casual `IC` é sorteado em `(0, IA)`, e os índices
selecionados são `teto(IC + i IA)`, para `i = 0..Q-1`, na ordem do universo.
Foi usada a fórmula não arredondada de `B` para evitar aproximação precoce;
o exemplo numérico do manual de 2013 apresenta valores intermediários
inconsistentes entre si. Com `N=9.000`, `A=350`, o cálculo exato produz
`n=429` e `Q=84`.

Referência metodológica: [Manual LIRAa 2013, Ministério da Saúde](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/svsa/dengue/manual_liraa_2013.pdf).

## O que ainda não está implementado

- Classificação efetiva urbano/rural. Se algum quarteirão rural estiver na camada, **não sortear** esse
  ciclo até o cadastro territorial estar corrigido ou essa classificação
  existir no LIRAa.
- Diário Kobo LIRAa, sorteio/registro de imóveis visitados, resultados de
  laboratório e cálculo dos índices. Visitas TB/TBO/PVE existentes não são
  interpretadas como inspeções LIRAa.
- Exportação `.lira`. Quatro arquivos históricos de 2025 mostram 28 campos
  consolidados precedidos de `1` e `30`, mas o significado formal desses dois
  valores e a aceitação de arquivo próprio ainda exigem validação. Não gerar
  arquivo com dados inventados ou incompletos. Ver
  `docs/LIRAA_FORMATO_LIRA.md` para o mapeamento observado.
- Comparação com o programa LIRAa/LIA e homologação do sorteio oficial. A
  lista local deve ser conferida antes de uso em campo; não presumir que seja
  intercambiável com o sorteio do programa legado.

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
