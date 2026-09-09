# Logradouros oficiais

Atualizado em 09/09/2026.

O cadastro em `/logradouros` recebe o CSV municipal de logradouros. Ele e a
fonte canonica de grafia para uma etapa futura de normalizacao e vinculo das
visitas; a importacao atual **nao altera** visitas, imoveis, focos ou dados do
Registro Geografico.

## CSV aceito

O arquivo deve ter cabecalho e as tres colunas abaixo:

```csv
nome,localidade,id_logr
Rua Sao Joao,Sede,uuid-estavel-do-trecho
```

- `id_logr` e a identidade estavel do trecho fornecida pela fonte municipal;
  nao deve ser renumerado pelo sistema.
- `nome` e a grafia oficial exibida.
- `localidade` e metadado do trecho, nao parte da identidade da rua. Uma rua
  pode atravessar varias localidades.

Nomes repetidos sao validos e esperados: por exemplo, varios trechos de
"Rodovia dos Minerios" mantem IDs distintos. O sistema nunca funde trechos
somente porque o nome e igual.

## Atualizacoes seguras

A importacao usa `id_logr` para inserir ou atualizar um trecho. Se o mesmo ID
vier com nome ou localidade corrigidos, o registro e atualizado. Linhas que nao
existem na nova versao do CSV sao preservadas: a tela nao exclui nem desativa
automaticamente nenhum logradouro.

O nome normalizado (sem diferenca de acentos e pontuacao simples) serve apenas
para busca e para a futura conciliacao de enderecos. A grafia original da
visita importada continuara preservada como evidencia da fonte.

## PostgreSQL

A tabela de producao e criada pela migracao
`migrations/postgresql/0006_logradouros_oficiais.sql`. Aplique as migracoes no
banco `endemias` antes de abrir a tela em producao. Em testes SQLite, a tabela
e criada pelo proprio modulo.
