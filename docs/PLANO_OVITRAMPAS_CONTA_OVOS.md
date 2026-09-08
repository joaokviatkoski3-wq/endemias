# Ovitrampas + Conta Ovos — plano e estado (08/09/2026)

Este arquivo consolida, para a proxima IA, o que estava planejado na area de
Ovitrampas/Conta Ovos e o que ficou feito ate o fechamento da sessao de
08/09/2026. Serve de guia curto; o detalhe operacional completo esta em
`docs/ESTADO_ATUAL_PROJETO.md` (seccao "Fechamento da sessao").

## Estado atual (vivo)

- `master` em `8ab2ff1` como base deste lote, versao alvo `1.28.0`.
- Worktree de trabalho `trabalho-deepseek` limpo e igual a `master`.
- Producao: PostgreSQL `endemias`, executada sob `SYSTEM`.
- A refatoracao maior de Ovitrampas foi retomada em lotes incrementais; o
  primeiro lote adicionou indicadores de origem e sincronizacao GET dos
  espelhos pela interface. O segundo lote, `1.28.0`, conclui a troca da aba
  Leituras para o espelho API e retira importacoes redundantes da interface.
- O **problema real das 12 ovitrampas no Conta Ovos foi diagnosticado** e o
  usuario fez a correcao manual no site.

## 1.1) Primeiro lote da retomada — integrado na master

- A página exibe a fonte de cada bloco: API Conta Ovos, lançamentos
  laboratoriais ou cadastro local.
- Administradores possuem o botão **Atualizar espelhos GET**, que sincroniza o
  cadastro público e as contagens recentes, grava somente os espelhos locais e
  registra auditoria.
- A ação não chama `/postcounting`, `/postaction` nem qualquer exclusão remota.
- O lote preservou a operação segura do Laboratório e do Calendário.

## 1.2) Segundo lote da retomada — implementado

- A aba **Leituras** consulta exclusivamente o espelho GET de contagens da API,
  mostrando detalhes da contagem, resultado, coleta e envio.
- Laboratorista, data da leitura e ocorrência são exibidos a partir dos lotes e
  itens preenchidos na aba **Laboratório**, cruzados por ovitrampa e data de
  coleta. Os antigos controles manuais de edição foram retirados da interface.
- **Monitoramento** continua usando a API para indicadores, positivas, ranking e
  localidades; o Histórico de ocorrências usa os lançamentos do Laboratório.
- A importação CSV ficou somente na aba **Armadilhas**, onde o cadastro local
  ainda possui dados que a API não fornece.
- A importação XLSX dos **Diários** foi retirada da interface. Diários,
  responsáveis e telefones continuam locais, editáveis e usados na impressão.
- As rotas/importadores legados permanecem no backend por compatibilidade e
  preservação de dados históricos, mas não são mais oferecidos pela página.

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

## 2) Refatoracao planejada (historico do pedido; itens principais implementados)

Pedidos acumulados do usuario para a pagina Ovitrampas (interrompidos):

1. **Remover importacao redundante de ocorrencias via CSV** — concluido; as
   ocorrencias do Monitoramento vem dos lancamentos de laboratorio.
2. **Indicadores discretos de origem** — concluido.
3. **Revisar redundancias/estrutura** — concluido para Leituras, Monitoramento
   e Diarios.
4. **Botao/config na interface para atualizar os dados da API** — concluido;
   a acao administrativa sincroniza os espelhos por GET.
5. **Migrar a aba Leituras para o espelho API**, remover import CSV de leituras,
   remover import XLSX de diarios e retirar edicao manual de laboratorista/data
   — concluido no lote `1.28.0`.

**Observacao para quem retomar:** o espelho de contagens
(`ovitrampas_ocorrencias_conta_ovos`) NAO carrega a ocorrencia; endereco/REALOCAR
sao locais. A central `Conta Ovos` e somente leitura. Qualquer mudanca de
sincronizacao/escrita remota exige confirmacao do usuario e piloto supervisionado.

## Arquivos de diagnostico (somente leitura, rastreados na master)

- `scripts/diagnosticar_ovitrampas_cadastro_vazio_contaovos.py`
- `scripts/diagnosticar_duplicata_cadastro_contaovos.py`

Um script de correcao via API foi criado e depois removido (nao funciona).
