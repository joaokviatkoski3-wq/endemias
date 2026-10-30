# LIRAa — correções e preparação para novembro de 2026

Código `1.73.0`, preparado em 30/10/2026 a partir de `ad5e05f`.
Não implica ativação no serviço nem homologação do levantamento real.

## Dados que devem ser preservados

O usuário confirmou que os ciclos, estratos, N confirmado e sorteios salvos
serão usados no próximo LIRAa. Esses registros não são testes. Somente as
visitas existentes foram identificadas como testes. Nenhum registro real foi
alterado nem houve limpeza de visitas neste lote.

O XLSX manual aprovado está preservado em
`app_core/data/liraa_ciclo_aprovado.xlsx`, cópia integral do arquivo enviado,
com SHA-256 `01934925d87a5f9413628f9f0ccae8d4022f964ad1f12ccc8a441b10f49a88dd`.
O formulário identifica o ciclo 4, período 09 a 13/11/2026 e contém a assinatura
do plano. A cópia original do usuário permanece inalterada.

## ACS continuam configuráveis

Em **Formulário do ciclo**, salvar a relação de participantes e baixar o XLSX.
Para o ciclo aprovado, o sistema atualiza somente as linhas da lista ACS.
Preserva os campos, grupos, tipos de imóvel, quarteirão “Outros”, coleta
manual de tubitos, regras, datas, assinatura, configurações e demais escolhas.
“Nenhum ACS” e “Outros” continuam disponíveis, incluindo `ACS_outros`.

A lista pode ser alterada novamente mais tarde, inclusive após importar
visitas, sem mudar a assinatura nem as respostas já gravadas. Os participantes
ainda não foram definidos definitivamente; a interface não presume essa
definição. A seleção vazia salva significa explicitamente nenhum ACS naquele
download. Fazer upload/publicação no Kobo continua uma operação manual.

Se a assinatura do banco divergir do arquivo aprovado, o download é recusado.
Conferir a divergência; nunca apagar/recriar sorteios reais para contornar o
aviso. Outros ciclos conservam o gerador genérico anterior.

## Compatibilidade da importação

- Reconhece `residencia`, `comercio`, `outros` e `terreno_baldio`, mantendo
  compatibilidade com `rco`. Os subtipos são preservados; o boletim reúne os
  três primeiros com `rco` em outros imóveis.
- Quando `Quarteir_o = outros`, usa `Quarteir_o_outros`, validando o número
  municipal e seu vínculo normal com o sorteio. Não inclui números fora do plano
  na amostra. Mantém leitura de decimais de formulários legados.
- Conserva `ACS_outros` e `Houve_coleta`. Para evitar migração e preservar o
  schema já implantado, os complementos ficam na chave reservada `_campo` do
  JSON existente `tratamento_json`. As chaves antigas de tratamento continuam
  intactas; a leitura dos complementos é centralizada em `dados_campo`.
- Coleta “Sim” sem tubito, “Não” com tubitos e amostras sem número positivo
  válido geram aviso de revisão. A importação não converte ausência de amostras
  em resultado negativo.
- UUID já importado continua idempotente; alterações no Kobo não sobrescrevem
  silenciosamente visitas ou leituras locais.

## Correções e reimportação administrativas

Em **Visitas LIRAa → Corrigir dados de campo**, admin pode ajustar tipo,
localidade/quarteirão, endereço, data, observações e complementos. Exige motivo
e a versão atual da visita. A correção deve corresponder ao plano/período e
não pode colocar a coleta depois de uma leitura existente. Preserva UUID,
metadados do formulário, IDs dos tubitos, resultados e tratamento; audita o
antes/depois na mesma transação. Não altera o Kobo.

Em **Envios excluídos — permitir nova importação**, a liberação exige motivo e
confirmação. Remove somente o bloqueio por UUID. A consulta/importação seguinte
traz novamente o envio do Kobo com novos tubitos sem leitura. Não recupera
resultados apagados e não importa nada automaticamente. São mostrados até
100 bloqueios recentes do filtro escolhido.

No laboratório, admin também pode corrigir o número do tubito ao lançar ou
corrigir a leitura; a versão e a auditoria das leituras continuam valendo.

## Integridade do plano e revisão dos resultados

Operações de edição/sorteio/importação bloqueiam primeiro o ciclo e depois
seus estratos, na mesma ordem. As condições de congelamento são conferidas
sob esses bloqueios. Ano e datas do ciclo precisam ser coerentes.

Qualquer visita importada protege a composição do ciclo inteiro, incluindo
outros estratos sem visitas. O ciclo do formulário aprovado permanece
protegido mesmo sem visitas, evitando perder o plano real depois da limpeza
dos testes. ACS e UID continuam editáveis; isso não modifica o sorteio.

Duplicidade é alerta, sem união/exclusão automática: considera possível visita
duplicada no mesmo dia/localidade/quarteirão/logradouro/número/sequência quando
há endereço suficiente e sinaliza números de tubito repetidos dentro do ciclo.
Os números podem exigir conferência com agente/dia; o alerta não impõe uma
unicidade municipal arbitrária.

Boletins e PDFs sinalizam coletas inconsistentes, suspeitas de duplicação,
tubitos pendentes, tipos/depósitos inválidos e quarteirões sem visitas.
Também avisam sobre estratos sem sorteio e visitas fora do plano/período.
Suspeitas permanecem nos totais até revisão administrativa. Não há encerramento
automático somente por atingir `n`; IIP/IB finais, CV e `.lira` continuam no
fluxo do programa oficial conforme o escopo já registrado.

## Validação e ativação

- Suíte geral: 845 testes, sem falhas, 5 ignorados. Após acrescentar os casos
  de concorrência e das novas rotas administrativas, os 62 testes LIRAa focados
  passaram. Os dois testes JavaScript dos mapas também passaram. Os avisos
  antigos de conexões SQLite não encerradas em outros módulos permaneceram.
- Ensaios SQLite usam cópias/bancos descartáveis, nunca o SQLite congelado.
- Testes de regressão específicos reproduzem os erros da auditoria, correção
  com leituras preservadas, conflitos de versão, rollback de auditoria,
  reimportação explícita, proteção depois de remover testes e troca futura de ACS
  sem modificar o restante do XLSX.
- O ensaio PostgreSQL usa somente tabelas temporárias em `endemias_teste`.
  Cobre os novos tipos, “Outros”, complementos, correção, proteção e reimportação.
- PDFs sintéticos com novos alertas foram renderizados e conferidos em A4 retrato.
- Não há nova migração. Nenhum POST/publicação no Kobo ou escrita em produção.
- A integração do código exige reinício autorizado para ativar `1.73.0`.
  O serviço observado durante a preparação continuou em `1.72.4`.

Em console administrativo autorizado, a conferência do cadastro real pode ser
executada com:

```powershell
python scripts/verificar_liraa_prontidao.py --confirmar-leitura "CONFERIR LIRAA SEM ALTERAR DADOS"
```

O script força transações PostgreSQL somente leitura em todas as conexões
internas e compara o ciclo, assinatura, pares localidade/quarteirão, sorteios,
RG e geometrias com o formulário aprovado. Não recalcula sorteios nem grava
cadastros. A sessão de implementação não obteve a credencial protegida;
a conferência real continua pendente e não pode ser declarada concluída.

Antes do campo, falta o ensaio operacional no aparelho usando o formulário
aprovado, período correto, envio offline/online, importação, laboratório e
conferência dos boletins. A limpeza das visitas de teste deve ser planejada
separadamente, preservando todos os dados reais de planejamento.
