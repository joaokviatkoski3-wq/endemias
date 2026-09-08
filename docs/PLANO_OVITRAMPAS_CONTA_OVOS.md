# Ovitrampas + Conta Ovos — plano e estado (08/09/2026)

Este arquivo consolida, para a proxima IA, o que estava planejado na area de
Ovitrampas/Conta Ovos e o que ficou feito ate o fechamento da sessao de
08/09/2026. Serve de guia curto; o detalhe operacional completo esta em
`docs/ESTADO_ATUAL_PROJETO.md` (seccao "Fechamento da sessao").

## Estado atual (vivo)

- `master` em `7f17b33`, versao `1.26.1`.
- Worktree de trabalho `trabalho-deepseek` limpo e igual a `master`.
- Producao: PostgreSQL `endemias`, executada sob `SYSTEM`.
- A **refatoracao de Ovitrampas nao foi implementada** (interrompida).
- O **problema real das 12 ovitrampas no Conta Ovos foi diagnosticado** e o
  usuario fez a correcao manual no site.

## 1) Problema real investigado (cadastro em branco)

**Sintoma:** 12 ovitrampas (131, 137, 138, 140, 142, 145, 148-A, 149, 151,
154, 156, 157) ficaram com o cadastro do Conta Ovos em branco apos envios de
contagem da semana 34 (coleta 02/09/2026). Todas da localidade local "Sede".

**Conclusoes confirmadas:**
- O `POST /postcounting` **nao atualiza** cadastro/endereco de ovitrampa ja
  existente — so grava a contagem. O endereco vem da tela de cadastro propria
  da ovitrampa no site do Conta Ovos.
- Tentar corrigir por API (delete+repost via /postcounting) **nao funciona**
  (testado na 131).
- As 12 estao registradas no cadastro publico do Conta Ovos (municipio tem um
  unico grupo remoto 1867, 343 ovitrampas = total do cadastro local). O espelho
  local `contaovos_registro_ovitrampas` esta **vazio (0)** porque nunca foi
  sincronizado.
- "Sede" e correlacao, nao causa (ha 35 de Sede, so 12 afetadas). Causa
  provavel: no envio da semana 34 essas 12 ainda nao tinham cadastro preenchido
  no Conta Ovos e ele as criou/vinculou sem endereco.

**Correcao:** preenchimento manual do cadastro no site do Conta Ovos (feita
pelo usuario). Enderecos corretos (localidade Sede) estao disponiveis no
cadastro local `ovitrampas_armadilhas`.

**Prevencao recomendada (nao feita):** sincronizar o espelho do cadastro remoto
e, no fluxo de envio, avisar/bloquear ovitrampas sem cadastro remoto.

## 2) Refatoracao planejada (nao implementada)

Pedidos acumulados do usuario para a pagina Ovitrampas (interrompidos):

1. **Remover importacao redundante de ocorrencias via CSV** (as ocorrencias do
   Monitoramento ja vem dos lancamentos de laboratorio).
2. **Indicadores discretos de origem** dos dados na tela (CSV vs API).
3. **Revisar redundancias/estrutura** das abas de Ovitrampas.
4. **Botao/config na interface para atualizar os dados da API** (sincronizacao
   hoje so via CLI em `scripts/sincronizar_contagens_contaovos.py` e
   `sincronizar_registro_ovitrampas_contaovos.py`).
5. Ajustes que o usuario indicou: migrar a aba Leituras para o espelho API;
   remover import CSV de leituras; remover import XLSX de diarios (diarios sao
   mantidos no sistema); laboratorista/edicao em lote fora da aba Leituras.

**Observacao para quem retomar:** o espelho de contagens
(`ovitrampas_ocorrencias_conta_ovos`) NAO carrega a ocorrencia; endereco/REALOCAR
sao locais. A central `Conta Ovos` e somente leitura. Qualquer mudanca de
sincronizacao/escrita remota exige confirmacao do usuario e piloto supervisionado.

## Arquivos de diagnostico (somente leitura, nao commitados)

- `scripts/diagnosticar_ovitrampas_cadastro_vazio_contaovos.py`
- `scripts/diagnosticar_duplicata_cadastro_contaovos.py`

Um script de correcao via API foi criado e depois removido (nao funciona).
