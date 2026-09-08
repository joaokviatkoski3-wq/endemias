# Conta Ovos e Ovitrampas: decisao de interface

## Decisao atual

Em 08/09/2026, a central de consulta `/conta-ovos` foi retirada da interface.
Ela duplicava dados que agora sao apresentados diretamente na pagina
`/ovitrampas`, que e a area operacional adotada pelo setor.

Isso nao remove a integracao Conta Ovos. Permanecem ativos a sincronizacao dos
espelhos, as tabelas locais, a fila de leituras do Laboratorio e o envio
supervisionado de leituras pela pagina `/ovitrampas`.

A pagina `/conta-ovos-sispncd` e independente e foi preservada. Ela continua
responsavel pelas consultas TBO/Conta Ovos, pendencias de envio e consolidado
SisPNCD.

## Dados visiveis em Ovitrampas

`/ovitrampas` concentra as informacoes de interesse operacional:

- **Leituras:** usa o espelho GET do Conta Ovos como fonte das contagens,
  enriquecendo laboratorista, data da leitura e ocorrencia pelos lancamentos
  locais do Laboratorio.
- **Monitoramento:** calcula positivas recentes, ranking, localidades e
  demais indicadores sobre as contagens de proveniencia API; o historico de
  ocorrencias vem do Laboratorio.
- **Armadilhas:** continua sendo o cadastro local e a unica aba com importacao
  CSV, pois a API nao fornece todos os campos cadastrais necessarios.
- **Diarios:** preserva responsaveis e telefones locais, editaveis e usados
  na impressao.
- **Laboratorio:** registra leituras, pendencias e envio supervisionado ao
  Conta Ovos.
- **Calendario:** permanece como base sensivel das datas operacionais.

## Fontes de verdade

- **Contagens de ovos:** API Conta Ovos, espelhada em
  `ovitrampas_ocorrencias_conta_ovos`. Registros historicos CSV podem existir,
  mas Leituras e Monitoramento filtram explicitamente a proveniencia API.
- **Cadastro operacional e complementos locais:** Endemias, em
  `ovitrampas_armadilhas`. Responsavel, telefone, localidade operacional e
  demais complementos locais nao devem ser apresentados como dados da API.
- **Cadastro remoto disponivel pela API:** espelho
  `contaovos_registro_ovitrampas`, atualizado por GET supervisionado. Ele
  guarda somente os campos devolvidos pela API e nao sobrescreve o cadastro
  local.
- **Territorio:** Registro Geografico e `quarteiroes.geojson` continuam sendo
  a fonte local de quarteiroes e localidades.
- **Historico de ocorrencias:** lancamentos preenchidos pelo laboratorista;
  o GET `/lastcounting` nao devolve essa situacao.

## Integracao preservada

Os seguintes componentes continuam necessarios e nao devem ser removidos ao
alterar a interface:

- `app_core/contaovos_client.py`, `contaovos_credencial.py` e
  `contaovos_health.py`;
- `app_core/contaovos_sync.py` e o comando supervisionado de sincronizacao;
- `app_core/contaovos_registro.py` e o espelho do cadastro remoto;
- `app_core/contaovos_fila.py` e o envio supervisionado de lotes;
- `migrations/postgresql/0002_integracao_contaovos.sql` ate `0005`;
- as rotas de sincronizacao e envio dentro de `blueprints/ovitrampas.py`;
- tabelas `contaovos_sync_cursor`, `contaovos_execucoes`,
  `contaovos_registro_ovitrampas`, `ovitrampas_ocorrencias_conta_ovos` e a
  fila das leituras.

## Regras para evolucao

1. A pagina `/ovitrampas` e a unica interface de operacao das ovitrampas.
2. Sincronizacao GET continua supervisionada e grava apenas espelhos locais.
3. Envio remoto exige confirmacao humana, reconciliacao GET posterior e nunca
   deve ser automatico ou silencioso.
4. EDLs e Quarteiroes/acoes continuam fora do escopo; a documentacao da API
   nao autoriza implementar esses dominios sem novo levantamento.
5. O fluxo de exclusao/recriacao de ovitrampas remotas, documentado em
   `docs/CONTA_OVOS_API.md`, permanece fora da interface.
