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

## Piloto: visitas positivas

Desde a versao `1.31.0`, administradores podem abrir a previa em
`/logradouros` para revisar apenas visitas que possuem resultado positivo para
*Aedes aegypti* e ainda nao receberam um vinculo de endereco normalizado.

- A comparacao reconhece acentos, pontuacao e abreviacoes usuais, como `R.` e
  `Rua`.
- A sugestao so existe quando o nome da via corresponde exatamente a um nome
  do catalogo e a visita possui numero. Similaridade aproximada nao cria
  vinculo.
- A confirmacao cria um endereco canonico e liga o grupo de visitas a ele. Os
  campos brutos `visitas.logradouro` e `visitas.numero` nunca sao alterados.
- O vinculo usa o nome canonico da via, nao um `id_logr` de trecho: uma mesma
  rua pode ter muitos trechos e a definicao espacial do trecho fica para uma
  etapa posterior com geometria, quarteirao ou coordenada.

Grupos sem numero ou sem correspondencia no catalogo ficam apenas indicados
para revisao futura; o piloto nao cria aliases nem corrige dados de origem.

## PostgreSQL

As tabelas de producao sao criadas pelas migracoes
`0006_logradouros_oficiais.sql` e
`0007_enderecos_normalizados_visitas.sql`. Aplique as migracoes no banco
`endemias` antes de abrir a tela em producao. Em testes SQLite, as tabelas sao
criadas pelo proprio modulo.
