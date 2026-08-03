# Integracao privada com a API Conta Ovos

Estado em 03/08/2026: fundacao somente leitura integrada a `master`, credencial
protegida e escopo privado validados. A sincronizacao GET das contagens esta em
`codex/sincronizar-contagens-conta-ovos`. Nenhum endpoint de escrita remota faz
parte destes lotes.

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
como escolha deliberada para conferir o ano corrente inteiro. Primeiro o script
consulta sem alterar o banco; somente depois de confirmacao humana repete a
consulta e atualiza o historico local. A operacao e exclusivamente GET na API.

Zeros a esquerda continuam preservados no identificador persistido. Para
comparar a API com o cadastro local, uma chave separada ignora apenas essa
variacao. Quando ha exatamente um cadastro correspondente, o historico usa o ID
local existente; duas variantes locais equivalentes interrompem o lote como
ambiguidade, sem gravacao parcial.

## Proximos lotes

1. Revisar e homologar a sincronizacao incremental GET, inclusive o ensaio em
   tabelas temporarias de `endemias_teste`.
2. Fila de leituras do laboratorio, por item, com reconciliacao antes de
   confirmar. O mapa de ocorrencias sera derivado da fonte existente em
   `app_core/ovitrampas.py`.
3. Envio TBO por quarteirao somente depois de validar IDs remotos, tipos de
   imovel, unidade de larvicida e semana epidemiologica do servidor.

Endpoints `postdelete*` permanecem fora do planejamento inicial.
