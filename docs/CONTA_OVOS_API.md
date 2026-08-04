# Integracao privada com a API Conta Ovos

Estado em 03/08/2026: fundacao, sincronizacao GET e fila local das leituras do
laboratorio integradas a `master`; credencial protegida, escopo privado,
idempotencia real e semana epidemiologica validados. Nenhum endpoint de escrita
remota faz parte destes lotes.

## Regras de seguranca

- A chave nunca entra no Git, no PostgreSQL, em argumento de processo ou em
  log.
- O arquivo padrao e `C:\ProgramData\Endemias\contaovos.key`, com ACL apenas
  para `SYSTEM` e Administradores.
- A chave e solicitada com `Read-Host -AsSecureString` e gravada por troca
  atomica.
- A API exige `key` na query string. O cliente nunca publica a URL final em
  mensagens de erro.
- A suite define `ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK=1`; sem transporte
  falso injetado, o cliente recusa qualquer chamada real.
- Nao existe sandbox documentado. Testes automatizados nunca usam a chave.

## Configuracao e validacao supervisionada

Execute como administrador:

```text
configurar_contaovos.bat
```

O configurador:

1. solicita a chave em entrada mascarada;
2. protege o arquivo para `SYSTEM` e Administradores;
3. cria uma tarefa agendada temporaria com nome aleatorio;
4. executa como `SYSTEM` uma unica consulta `GET /lastcounting?page=1`;
5. confirma que todos os registros retornados pertencem ao codigo municipal
   `4100400` e ao estado `PR`;
6. grava apenas o resultado sanitizado em
   `C:\ProgramData\Endemias\contaovos_status.json`;
7. remove a tarefa temporaria e seu arquivo de retorno.

O endpoint de validacao nao envia, altera ou exclui dados. A chave recebida
possui formato diferente dos 45 caracteres alfabeticos descritos na
documentacao; por isso o formato nao e rejeitado localmente. A aceitacao pela
API e o escopo retornado sao a verificacao autoritativa.

## Componentes do lote

- `app_core/contaovos_credencial.py`: localiza e le a chave protegida.
- `app_core/contaovos_client.py`: cliente GET, timeout, respostas defensivas,
  tentativas limitadas para rede/HTTP 500 e mascaramento.
- `app_core/contaovos_health.py`: le e grava somente o status sanitizado.
- `app_core/contaovos_integracao.py`: schema dual de cursor e execucoes.
- `scripts/verificar_contaovos.py`: prova supervisionada de autenticacao e
  escopo.
- `scripts/configurar_credencial_contaovos_system.ps1`: instalacao da chave.
- `scripts/testar_credencial_contaovos_system.ps1`: prova real como `SYSTEM`.
- Central do Sistema: mostra configuracao, ultima verificacao e escopo, sem
  consultar a API durante o carregamento da pagina.

## Schema inicial

`migrations/postgresql/0002_integracao_contaovos.sql` cria:

- `contaovos_sync_cursor`: um cursor por fluxo, com IDs remotos como `text`;
- `contaovos_execucoes`: historico sanitizado de execucoes.

As filas de contagens e visitas nao pertencem a este lote. Elas serao tabelas
especificas por dominio, com FKs e estados de recuperacao, antes das primeiras
escritas remotas.

`migrations/postgresql/0003_contaovos_sync_lock.sql` acrescenta ao cursor o
token e o instante da execucao corrente. A aquisicao e atomica nos dois bancos;
uma trava abandonada pode ser retomada depois de 30 minutos, e a execucao
interrompida fica registrada como erro sanitizado.

## Sincronizacao GET das contagens

`app_core/contaovos_sync.py` pagina `/lastcounting`, valida o municipio em cada
item, normaliza o identificador da ovitrampa com a mesma regra do modulo
Ovitrampas e grava por `counting_id` na tabela historica ja alimentada pelo CSV.
A leitura de todas as paginas termina antes da primeira escrita local. Se o
limite de 100 paginas for atingido, nenhuma contagem e gravada e o operador deve
informar um intervalo de datas menor.

O endpoint privado documentado nao aceita filtro por `counting_id`. Portanto o
ID remoto funciona como cursor, chave idempotente e detector de novos itens,
mas nao e enviado como parametro inventado. A paginacao pode ser completa ou
limitada por `date_start`/`date_end`. O importador CSV permanece disponivel.

O comando supervisionado e `sincronizar_contaovos.bat`. No modo rotineiro ele
consulta os ultimos 45 dias, com sobreposicao; a reconciliacao anual permanece
como escolha deliberada para conferir o ano corrente inteiro e agora divide o
periodo em meses, pois o ensaio real encontrou mais de 100 paginas no ano.
Primeiro o script consulta todos os periodos sem alterar o banco; somente depois
de confirmacao humana repete as consultas e atualiza o historico local. A
operacao e exclusivamente GET na API.

Zeros a esquerda continuam preservados no identificador persistido. Para
comparar a API com o cadastro local, uma chave separada ignora apenas essa
variacao. Quando ha exatamente um cadastro correspondente, o historico usa o ID
local existente; duas variantes locais equivalentes interrompem o lote como
ambiguidade, sem gravacao parcial.

Em 03/08/2026, `0002` e `0003` foram aplicadas nos bancos `endemias` e
`endemias_teste`. O ensaio PostgreSQL temporario passou e a reconciliacao real
de 2026 processou 5.383 contagens: 1.452 inseridas e 3.931 atualizadas. A
repeticao dos ultimos 45 dias terminou com 1.108 itens sem alteracao e cursor
`3569727`, comprovando a idempotencia no ambiente oficial.

## Fila local das leituras do laboratorio

`migrations/postgresql/0004_contaovos_fila_contagens.sql` e
`app_core/contaovos_fila.py` preparam uma linha de fila para cada item concluido
do laboratorio. A fila guarda estado, tentativas, ID remoto, erro sanitizado e
SHA-256 do payload esperado. O payload nao e enviado neste lote.

A preparacao bloqueia o lote inteiro antes da primeira escrita quando falta
coordenada, quando a ocorrencia nao possui mapeamento seguro ou quando um item
ja confirmado foi alterado. O codigo remoto e derivado por inversao de
`ovitrampas.CONTA_OVOS_OCORRENCIAS`; o laboratorio continua limitado aos oito
codigos que possuem correspondencia conhecida. Leituras iguais no historico
GET ficam `confirmado`, ausentes ficam `pendente` e divergencias ficam `erro`.
Uma tentativa futura interrompida nunca volta automaticamente a pendente sem
reconciliacao.

O botao **Preparar e conferir** na administracao de Ovitrampas apenas grava e
reconcilia a fila local. O fluxo manual **Marcar envio manual** permanece como
contingencia. `scripts/verificar_semanas_contaovos.py` compara por GET os campos
brutos `date/year/week` da API com o algoritmo local; essa prova supervisionada
e condicao para qualquer lote posterior que habilite `/postcounting`.

O lote foi aprovado sem achados e integrado no merge `c81b6aa`. A migracao
`0004` foi aplicada nos bancos `endemias_teste` e `endemias`. O ensaio isolado
da fila passou sem alterar a tabela publica. A prova real percorreu 5.405
contagens brutas de 2026 por GET e encontrou zero divergencias entre
`date/year/week` remotos e o algoritmo epidemiologico local.

## Proximos lotes

1. Implementar o envio serial `/postcounting`, sempre reconciliando antes e
   depois da chamada, sem exclusao automatica e com piloto supervisionado.
2. Envio TBO por quarteirao somente depois de validar IDs remotos, tipos de
   imovel, unidade de larvicida e semana epidemiologica do servidor.

Endpoints `postdelete*` permanecem fora do planejamento inicial.
