# Acompanhamento de ACS em visitas PVE

Atualizado em 15/09/2026.

## Campos do formulario Kobo

- `acs_presente`: escolha unica;
  - `sim_acs_presente` significa que um ACS esteve presente;
  - `nao_acs_presente` significa que nao houve acompanhamento de ACS.
- `acs_nome`: nome originalmente previsto para a escolha multipla, exibida
  somente para a resposta positiva.
- `Qual_quais_ACS`: nome tecnico efetivamente publicado na versao atual do
  formulario; tambem e uma `select_multiple` e e a fonte usada pelo importador.

Cada alternativa de ACS deve possuir um codigo tecnico estavel, unico e sem
espacos, como `ACS-026` ou `maria_da_silva`; o formulario mostra o nome
completo no rotulo.
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

A tabela `acs_catalogo` guarda somente a correspondencia entre `acs_codigo` e
o nome exibido no formulario, com a data da ultima atualizacao. Ela nao altera
nem substitui codigos ja gravados em `visita_acs`.

O importador aceita campos diretos e campos dentro de grupos, como
`grupo/acs_presente` e `grupo/Qual_quais_ACS`, preservando compatibilidade com
o antigo `acs_nome`. Uma PVE com tres ACS gera tres linhas em `visita_acs`; uma
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
seleciona visitas que tenham ao menos um dos ACS marcados.

Na versao `1.47.0`, o catalogo local de codigos e rotulos foi preenchido a
partir da definicao publicada do formulario PVE no Kobo. Filtros, lista e
detalhe exibem o nome oficial, inclusive quando o codigo tecnico e algo como
`ACS-026`; os valores internos de filtro e os vinculos existentes continuam
usando o codigo. Se algum codigo historico nao existir no formulario atual, a
tela conserva a formatacao legada dele em vez de ocultar a informacao.

Na versao `1.47.1`, os controles manuais foram retirados de **Visitas
arboviroses** e de **Importacao Kobo**, pois a reconciliacao historica ja foi
concluida. A cada preparacao de importacao PVE, o sistema atualiza em segundo
plano o catalogo de nomes a partir do XLSForm. Assim, novos codigos publicados
no Kobo recebem seu nome na proxima importacao PVE, sem modificar visitas ja
existentes nem bloquear a importacao se o Kobo estiver indisponivel.

## Reconciliacao de registros ja importados

Na versao `1.40.4`, o script
`scripts/reconciliar_acs_pve_kobo.py` permite preencher retroativamente somente
os dados ACS das PVE que ja estavam no sistema quando o campo publicado ainda
nao era reconhecido. Ele consulta o Kobo, cruza exclusivamente pelo UUID Kobo e
altera apenas `acs_presente`, `acs_nome` e `visita_acs`. A execucao padrao e uma
previa; para qualquer banco fora de `endemias_teste`, exige confirmacao explicita
do banco e da aplicacao. Registros sem resposta ACS sao preservados.

Como a reconciliacao historica foi concluida, ela nao aparece mais na interface
do sistema oficial. O script permanece apenas como referencia tecnica para uma
eventual manutencao excepcional, nunca como parte da rotina de importacao.

## Banco de dados

- PostgreSQL: campos escalares em `0009_visitas_acs.sql` e selecao multipla em
  `0010_visita_acs.sql`, aplicada no banco oficial `endemias` em 15/09/2026;
  catalogo de rotulos em `0015_acs_catalogo.sql`;
- SQLite: criacao atualizada em `criar_banco.py` e compatibilidade idempotente
  em `app_core/sqlite_maintenance.py`.
