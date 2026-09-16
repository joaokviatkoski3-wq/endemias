# Acompanhamento de ACS em visitas PVE

Atualizado em 15/09/2026.

## Campos do formulario Kobo

- `acs_presente`: escolha unica;
  - `sim_acs_presente` significa que um ACS esteve presente;
  - `nao_acs_presente` significa que nao houve acompanhamento de ACS.
- `acs_nome`: `select_multiple`, exibido somente para a resposta positiva.

Cada alternativa de ACS deve possuir um codigo tecnico estavel, unico e sem
espacos, como `maria_da_silva`; o formulario mostra o nome completo no rotulo.
O Kobo envia os codigos selecionados separados por espaco. Nao reutilize um
codigo para outra pessoa. Quando houver troca de nome, mantenha o mesmo codigo e
altere apenas o rotulo; quando for outra pessoa, crie outro codigo. A relacao
codigo-rotulo do XLSForm deve ser preservada para uma futura exibicao legivel.

## Persistencia

A tabela `visitas` possui:

- `acs_presente`: `1`, `0` ou `NULL` para visitas anteriores/sem resposta;
- `acs_nome`: sequencia normalizada de codigos selecionados, separada por
  espaco, para compatibilidade e rastreabilidade.

A tabela relacional `visita_acs` e a fonte para consultas futuras:

- `id_visita`;
- `acs_codigo`;
- chave primaria composta, que impede a repeticao do mesmo ACS na visita.

O importador aceita campos diretos e campos dentro de grupos, como
`grupo/acs_presente`. Uma PVE com tres ACS gera tres linhas em `visita_acs`; uma
nova importacao da mesma visita substitui integralmente essa lista. Se a
resposta for `nao_acs_presente`, o importador grava `acs_presente=0`, limpa
`acs_nome` e remove quaisquer vinculos anteriores.

Os campos sao aplicaveis somente a PVE. Para PE, TB e TBO, ambos permanecem
`NULL`.

Os ACS nao sao cadastrados em `agentes` nem entram em `visita_agentes`: essa
tabela continua reservada aos ACEs e demais agentes de endemias indicados no
formulario.

## Escopo atual

Na versao `1.40.0`, os ACS passaram a aparecer na listagem, no detalhe e na
exportacao de **Visitas arboviroses**. O filtro multiplo **ACS acompanhante**
seleciona visitas que tenham ao menos um dos ACS marcados. Enquanto nao existe
um catalogo local de rotulos, a tela converte o codigo tecnico em texto legivel
(por exemplo, `maria_da_silva` para `Maria da Silva`), preservando o codigo
canonico na API.

Uma etapa futura pode acrescentar esse catalogo local e relatorios de ACS sem
alterar os vinculos ja registrados.

## Banco de dados

- PostgreSQL: campos escalares em `0009_visitas_acs.sql` e selecao multipla em
  `0010_visita_acs.sql`, aplicada no banco oficial `endemias` em 15/09/2026;
- SQLite: criacao atualizada em `criar_banco.py` e compatibilidade idempotente
  em `app_core/sqlite_maintenance.py`.
