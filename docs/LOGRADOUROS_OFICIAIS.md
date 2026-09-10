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

- A comparacao reconhece acentos, pontuacao, abreviacoes usuais, artigos e
  variacoes simples de singular/plural. Por exemplo, `Rua Salgueiro` sugere
  `Rua dos Salgueiros`.
- Correspondencias aproximadas exibem ate cinco alternativas, pontuacao e o
  motivo da sugestao. Nenhuma delas cria vinculo sem escolha e confirmacao do
  administrador.
- A confirmacao cria um endereco canonico e liga o grupo de visitas a ele. Os
  campos brutos `visitas.logradouro` e `visitas.numero` nunca sao alterados.
- Visitas do tipo `PE` sao excluidas da previa, mesmo quando positivas, porque
  Pontos Estrategicos possuem cadastro e georreferenciamento proprios.
- O vinculo usa o nome canonico da via, nao um `id_logr` de trecho: uma mesma
  rua pode ter muitos trechos e a definicao espacial do trecho fica para uma
  etapa posterior com geometria, quarteirao ou coordenada.

Grupos sem numero ou sem sugestao minima no catalogo ficam apenas indicados
para revisao futura. Confirmacoes anteriores funcionam como correspondencias
aprendidas quando uma nova visita repete a mesma grafia de origem; o endereco
bruto continua preservado.

### Revisao em lote e consulta dos vinculos

Desde a versao `1.32.0`, a previa cobre todas as positivas elegiveis e exibe a
equacao de cobertura: total de positivas = vinculadas + pendentes. Casos sem
logradouro ou numero tambem aparecem; PE continua fora dessa conta.

- A lista e paginada e permite selecionar todos os resultados filtrados da
  pagina, conservar selecoes entre paginas e confirmar ate 300 grupos de uma
  vez.
- Rua oficial e numero podem ser ajustados na propria linha. A rua digitada
  precisa existir na base oficial.
- O lote e atomico: todos os grupos sao revalidados antes da escrita e, se um
  deles estiver invalido ou desatualizado, nenhum vinculo e confirmado.
- A secao **Enderecos vinculados** mostra o endereco canonico, as grafias
  originais, localidades, periodo e quantidade de visitas.
- O detalhe do endereco lista as visitas reunidas e permite desfazer um
  vinculo. Essa acao nao apaga nem edita a visita; ela apenas a devolve para a
  fila de revisao e remove a entidade canonica se ela ficar sem visitas.

## PostgreSQL

As tabelas de producao sao criadas pelas migracoes
`0006_logradouros_oficiais.sql` e
`0007_enderecos_normalizados_visitas.sql`. Aplique as migracoes no banco
`endemias` antes de abrir a tela em producao. Em testes SQLite, as tabelas sao
criadas pelo proprio modulo.

As melhorias da versao `1.32.0` reutilizam essas tabelas e nao exigem uma nova
migracao depois da `0007`.

### Confirmacao e retorno visual

Desde a versao `1.32.1`, a confirmacao em lote mostra explicitamente quantos
grupos e visitas foram vinculados. Falhas de rede, sessao expirada e respostas
inesperadas do servidor deixam a selecao intacta, exibem uma mensagem e
reativam o botao para nova tentativa. Se a gravacao terminar, mas alguma lista
da pagina nao puder ser atualizada, a interface informa que o vinculo foi
salvo e orienta recarregar a pagina.

O vinculo e commitado antes do registro de auditoria. Por isso, uma falha
isolada de auditoria e registrada no log e retornada como aviso de operacao ja
concluida, em vez de ser apresentada incorretamente como falha total.

A versao `1.32.2` corrige o nome da variavel usada para montar e enviar o lote.
Na `1.32.1`, a divergencia entre `items` e `itens` interrompia o JavaScript
antes da requisicao; portanto, nenhuma selecao afetada por esse erro chegou ao
servidor.
