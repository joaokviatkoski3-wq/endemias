# Diário Kobo do LIRAa

Estado em 06/10/2026: código `1.66.0` integrado à `master`, migração
PostgreSQL `0025_liraa_visitas_kobo.sql` aplicada e serviço oficial reiniciado.
`/login` respondeu HTTP 200 com `Endemias v1.66.0`; `/liraa` redirecionou
ao login sem sessão. Nenhuma visita real foi importada nessa implantação.

## Regra de campo

- Cada envio do formulário LIRAa corresponde a um imóvel aberto registrado.
  Fechados e recusas não são preenchidos nesse diário e não devem ser
  inventados na importação.
- `Dados_visita/Quarteir_o` é o número municipal do quarteirão sorteado,
  digitado manualmente no Kobo. O campo XLSForm é `decimal`; `408.1` e `408,1`
  são convertidos para a mesma chave `408.1`. Inteiros continuam padronizados
  para a chave territorial com quatro dígitos, por exemplo `408` → `0408`.
- Capivara dos Manfron é área rural e não faz parte deste LIRAa. Se um envio
  futuro indicar essa localidade, ficará sem vínculo amostral.
- O grupo repetido `group_jr1vc40` contém tubitos com número, código e
  descrição do depósito. Não registrar tubito não equivale a resultado
  laboratorial negativo. Resultados e índices dependem de etapa posterior.

## Fluxo na página LIRAa

`Importar Kobo` é uma aba exclusivamente administrativa. Nela, o administrador
configura o UID do formulário LIRAa, seleciona um ciclo e um intervalo de
datas de **envio ao Kobo** (até 91 dias), consulta a prévia e então confirma
uma importação separada. O token e URL são os já configurados no Kobo do
Endemias. O formulário LIRAa não entra na importação automática geral.

A consulta aborta se o Kobo devolver uma página incompleta. A importação é
transacional, única por `_uuid` e nunca altera envios já importados. A prévia
identifica o vínculo com ciclo/estrato/sorteio pelo par localidade + número
municipal. Visitas fora do período, sem estrato ou fora do sorteio ficam
marcadas para revisão; não são tratadas como selecionadas. A aba `Visitas LIRAa`
recalcula o vínculo exibido conforme o plano/sorteio atual e tem filtros,
paginação, detalhes e exclusão administrativa. O vínculo gravado na visita
permanece como referência do momento da importação.

Excluir uma visita remove seus tubitos **somente do Endemias**, audita a
operação e guarda uma lápide por UUID; a visita permanece no Kobo, mas não
volta em importações posteriores. Ciclo ou estrato com visitas vinculadas não
pode ser excluído. Não apagar o cadastro Kobo nem presumir que um ensaio seja
dado oficial. Ainda não há restauração automática de visitas excluídas.

## Campos e limites atuais

O formulário analisado contém `Data`, `Hora_inicio`, `Agentes`, `ACS`,
`Dados_visita/Localidade`, `Dados_visita/Quarteir_o`, `Imovel`, `Logradouro`,
`Numero`, `Sequencia`, `Morador`, `Observa_es` e o repetidor de tubitos.
O importador usa os **nomes técnicos** do XLSForm, não os cabeçalhos rotulados
do Excel. As opções de localidade do formulário são mapeadas para os nomes
oficiais, inclusive `centro` → `Sede` e códigos sem acento. Alterações futuras
no XLSForm podem exigir atualização desse mapeamento.

Ainda não há lançamento de resultados laboratoriais do LIRAa, cálculo de
índices, seleção de imóveis dentro do quarteirão ou geração de `.lira`. O
sorteio geográfico continua experimental até homologação operacional.

Validação de desenvolvimento: 773 testes SQLite isolados passaram (5 ignorados),
incluindo 32 testes focados LIRAa após os últimos ajustes. A migração foi
aplicada após o backup PostgreSQL validado
`D:\BackupsEndemias\backups_banco\endemias_pre_liraa_0025_20261006_160900.dump`.
Ainda não houve acesso ao Kobo real nem importação de visitas em produção.
Próximo passo: configurar o UID, conferir a prévia com envios de teste,
importar poucos registros com confirmação administrativa e validar na interface.
