# Integracao privada com a API Conta Ovos

Estado em 03/08/2026: fundacao somente leitura implementada na branch
`codex/integrar-api-conta-ovos-base`. Nenhum endpoint de escrita faz parte
deste lote.

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

## Proximos lotes

1. Sincronizacao incremental de contagens por `counting_id`, com normalizacao
   de `ovitrampa_id`, single-flight e CSV preservado como fallback.
2. Fila de leituras do laboratorio, por item, com reconciliacao antes de
   confirmar. O mapa de ocorrencias sera derivado da fonte existente em
   `app_core/ovitrampas.py`.
3. Envio TBO por quarteirao somente depois de validar IDs remotos, tipos de
   imovel, unidade de larvicida e semana epidemiologica do servidor.

Endpoints `postdelete*` permanecem fora do planejamento inicial.
