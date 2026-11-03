# LIRAa — correções e preparação para novembro de 2026

Atualização posterior: a solicitação de logradouros RG em `1.74.0` autoriza
revisar esse campo no modelo aprovado. Ver `LIRAA_LOGRADOUROS_RG.md`; as
garantias de preservação do plano e flexibilidade futura dos ACS continuam.

Código `1.73.0`, preparado em 30/10/2026 a partir de `ad5e05f`.
O reinício autorizado terminou em 30/10/2026 às 17h46, confirmado em 03/11
por HTTP 200 em `/login`. As assinaturas das 11 tabelas LIRAa e o SQLite
congelado permaneceram preservados. Isso não substitui a homologação em campo.

## Ampliação autorizada — 1.73.1

Em 03/11, o usuário confirmou que acrescentou manualmente seis quarteirões e
decidiu trabalhar mais do que o sorteio original. Eles permanecem no XLSX:

| Localidade | Quarteirões adicionais |
|---|---|
| Rosana | 1030, 1032 |
| São João Batista | 613, 619 |
| Tranqueira | 518, 548 |

O registro `app_core/data/liraa_adicionais.json` conserva essa autorização,
ciclo e assinatura. Os adicionais são vinculados aos estratos existentes;
o plano de campo reúne **261 sorteados + 6 adicionais = 267**. Não é um novo
sorteio: não modifica N, n, intervalo, IC, universo/seleção congelados ou
histórico. A assinatura embutida no formulário permanece válida e o arquivo
XLSX aprovado não muda. A lista de ACS continua editável.

`adicionais_conn` valida ciclo/assinatura e pertencimento ao estrato, impede
repetição e impede marcar como adicional um quarteirão já sorteado. Importação
e correção reconhecem o vínculo `adicional`, preservando todas as demais
verificações de período/plano. Qualquer outro quarteirão não autorizado
continua fora do sorteio/plano.

Os adicionais são visíveis no plano de campo, mapa com contorno tracejado e
rótulo (+), KML, PDFs, visitas e laboratório. O boletim inclui seus imóveis,
tubitos e positivos nos totais, com detalhamento dos adicionais, sem recalcular
a amostra programada original. As tabelas de sorteio continuam sendo o registro
dos 261 selecionados originalmente. Nenhuma migração é necessária.

A prévia do código em transações somente leitura no PostgreSQL oficial em
03/11 confirmou: assinatura correta, 5 sorteios, 6 adicionais nos estratos
existentes, os 267 quarteirões do formulário correspondentes ao plano de campo,
nenhum quarteirão sem RG ou geometria e nenhuma visita no ciclo. Não houve
inserção de visita de teste ou publicação no Kobo.

Validação da ampliação: 853 testes gerais sem falhas (5 ignorados), 68 testes
LIRAa focados finais, 2 testes JavaScript, ensaio PostgreSQL 18 em cluster
descartável com importação/leitura/boletim adicional e PDFs A4 renderizados.
Os testes conferem que as tabelas e a assinatura do sorteio não mudam.

**Ativação de `1.73.1` concluída em 03/11/2026 às 08h30**, após integração do
commit `47afeef` e reinício autorizado. `/login` respondeu HTTP 200 exibindo
`Endemias v1.73.1`. A comparação somente leitura antes/depois confirmou
contagens/assinaturas iguais nas 11 tabelas LIRAa, e o hash do SQLite congelado
foi preservado. O verificador do plano retornou código 0 e confirmou os 267
quarteirões do formulário (261 sorteados + 6 adicionais), 5 sorteios, assinatura
original válida, nenhum quarteirão sem RG/geometria e nenhuma visita no ciclo.
Não houve migração, regravação de sorteios, importação, leitura, limpeza de
registros ou alteração do formulário/Kobo. Os ACS continuam configuráveis.

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
Na versão `1.73.x`, o ciclo aprovado atualizava somente as linhas da lista ACS.
Em `1.74.0`, também gera a escolha de logradouros RG e o complemento de Outro,
com nova versão do formulário, por solicitação expressa do usuário.
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
- `1.73.0` foi ativada em 30/10 às 17h46. A correção `1.73.1` foi ativada
  em 03/11 às 08h30; os registros de produção foram conferidos e preservados.

Em console administrativo autorizado, a conferência do cadastro real pode ser
executada com:

```powershell
python scripts/verificar_liraa_prontidao.py --confirmar-leitura "CONFERIR LIRAA SEM ALTERAR DADOS"
```

O script força transações PostgreSQL somente leitura em todas as conexões
internas e compara o ciclo, assinatura, pares localidade/quarteirão, sorteios,
RG e geometrias com o formulário aprovado. Não recalcula sorteios nem grava
cadastros. A sessão de implementação inicial não obteve a credencial protegida;
a conferência posterior foi concluída em contexto administrativo autorizado,
sem copiar credenciais ou alterar permissões. A diferença inicial 261/267
foi esclarecida pelo usuário como ampliação intencional e incorporada ao plano.

Antes do campo, falta o ensaio operacional no aparelho usando o formulário
aprovado, período correto, envio offline/online, importação, laboratório e
conferência dos boletins. A limpeza das visitas de teste deve ser planejada
separadamente, preservando todos os dados reais de planejamento.
