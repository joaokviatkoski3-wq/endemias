# Acompanhamento de ACS em visitas PVE

Atualizado em 14/09/2026.

## Campos do formulario Kobo

- `acs_presente`: escolha unica;
  - `sim_acs_presente` significa que um ACS esteve presente;
  - `nao_acs_presente` significa que nao houve acompanhamento de ACS.
- `acs_nome`: atualmente texto com o nome do ACS, exibido no formulario quando
  a resposta anterior e positiva. O importador tambem aceita que o campo seja
  convertido futuramente em `select_one`; nesse caso, o codigo tecnico da
  escolha sera armazenado como valor canonico.

Os nomes tecnicos nao contem a palavra `agente`, evitando que o reconhecedor de
agentes de endemias interprete o ACS como integrante da equipe da visita.

## Persistencia

A tabela `visitas` possui:

- `acs_presente`: `1`, `0` ou `NULL` para visitas anteriores/sem resposta;
- `acs_nome`: texto ou `NULL`.

O importador aceita campos diretos e campos dentro de grupos, como
`grupo/acs_presente`. O nome so e persistido quando `acs_presente` equivale a
`sim_acs_presente`; qualquer nome residual recebido com resposta negativa e
descartado.

Os campos sao aplicaveis somente a PVE. Para PE, TB e TBO, ambos permanecem
`NULL`.

Se `acs_nome` passar a ser uma lista, use codigos estaveis e unicos, como
`maria_da_silva`, e mantenha o nome completo no rotulo da alternativa. Nao
reutilize um codigo para outra pessoa. A lista de codigos e rotulos devera ser
preservada para que uma futura interface apresente o nome legivel sem perder a
identidade canonica recebida do Kobo.

## Escopo atual

Os dados sao importados e armazenados, mas ainda nao sao mostrados nas telas ou
incluidos nas exportacoes. Uma etapa futura pode acrescentar filtros,
detalhamento, relatorios e um cadastro padronizado de ACS.

## Banco de dados

- PostgreSQL: migracao `migrations/postgresql/0009_visitas_acs.sql`, aplicada
  no banco oficial `endemias` em 14/09/2026 e validada antes em
  `endemias_teste`;
- SQLite: criacao atualizada em `criar_banco.py` e compatibilidade idempotente
  em `app_core/sqlite_maintenance.py`.
