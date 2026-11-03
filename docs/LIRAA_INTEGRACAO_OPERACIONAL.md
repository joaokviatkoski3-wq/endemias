# LIRAa integrado à operação — 1.75.0

Preparado em 03/11/2026 por solicitação do usuário. A integração foi ampliada
para todos os recursos pertinentes às visitas, incluindo relatórios do setor
e individuais. Produção permanece em `1.74.0` até a ativação autorizada.

## Fluxo para a equipe

- **Importação:** LIRAa entra na consulta, prévia, lote de vetores/larvas,
  verificação e confirmação comuns do Kobo, e na importação automática.
  Consulta o UID geral e os UIDs salvos nos ciclos, sem repetir projetos.
  Resposta incompleta interrompe a preparação; UUID é preservado. Exclusões
  locais continuam bloqueadas até liberação administrativa explícita.
- **Arquivo:** aceita o transporte interno sem perder metadados/repetições e
  a exportação XLSX completa do Kobo com Data, UUID e aba de tubitos vinculada
  por UUID ou índice do pai. Escolhas múltiplas devem usar nomes XML ou colunas
  separadas; rótulos compostos ambíguos são recusados, sem inventar códigos.
- **Laboratório:** tubos aparecem na fila comum com tipo **LIRAa**, filtro
  por trabalho e, quando vindo do ciclo, pelo ciclo. O endereço antigo da aba
  LIRAa redireciona para essa fila. Há apenas um formulário de lançamento na
  página: LIRAa mostra larvas/pupas; ao retornar à rotina, os outros campos
  reaparecem. Limites próprios e restrição de datas são preservados.
- **Resultados:** histórico, pendências e consultas comuns enxergam a leitura
  na origem. Correção LIRAa continua exclusiva de administrador, com versão
  para impedir sobrescrita de uma alteração concorrente. A fila comum preserva
  o autor da leitura na correção. Permissões de acesso ao laboratório seguem
  as mesmas verificações dos outros tubos.
- **Notificação:** Aedes aegypti positivo gera um foco por visita, reunindo os
  tubos positivos. Terreno baldio não entra na fila de notificações. Positivos
  de albopictus continuam no laboratório/boletim. Ao retirar o último positivo,
  a notificação é desativada sem apagar seu status/histórico manual.
- **Visitas:** LIRAa aparece em Arboviroses, busca, filtros, detalhes, coletas,
  resultados e exportação. Correção administrativa exige motivo/versão e
  conserva ciclo/plano/tubos/leituras. A exclusão remove os vínculos operacionais
  e mantém a lápide do UUID; não exclui ciclos, estratos ou sorteios.
- **Relatórios:** incluído nos relatórios individuais e do setor, histórico
  completo/PDF, produção operacional, produção do laboratorista, painel,
  página inicial, mapa, positividade, boletim mensal e consolidados XLSX.
  O consolidado identifica ciclo, estrato, tipo de imóvel e vínculo ao plano.

O formulário com logradouros RG continua compatível, assim como o anterior em
texto livre. A integração não publica nem modifica nada no Kobo e não exige
outra alteração do formulário. A publicação da revisão de ruas entregue em
`1.74.0`, se ainda não realizada, continua sendo operação manual.

## Uma fonte de verdade

Visitas, tubitos e leituras permanecem em `liraa_visitas`,
`liraa_visita_tubitos` e `liraa_leituras`. Não há cópia editável em `visitas`,
`coletas` ou `resultados_laboratorio`.

`app_core/visitas_integradas.py` é usado explicitamente pelas conexões de
consulta dos módulos comuns. Acrescenta CTEs somente aos SELECTs que precisam
dos dados integrados. As tabelas físicas são qualificadas pelo schema; não há
views temporárias, alterações globais no adaptador de banco ou tradução de
INSERT/UPDATE/DELETE/SELECT FOR UPDATE. Parâmetros continuam separados do SQL.

IDs comuns identificam a origem: `liraa-v-<id>` para visita,
`liraa-t-<id>` para coleta e ID negativo para leitura. As rotas de alteração
encaminham esses identificadores ao serviço LIRAa. Visita de rotina não pode
ser convertida para LIRAa pelo editor comum, pois faltaria o vínculo ao plano.

Participantes ACE são associados aos nomes do formulário aprovado e ao
cadastro de agentes, priorizando o nome canônico. ACS usam os códigos reais
da resposta, sem congelar a seleção provisória. O complemento de Outro é
preservado. O rótulo legado `LIRA` não foi renomeado para `LIRAA`.

## Particularidades preservadas

- **Planejamento real intacto:** ciclo 4, datas 09–13/11/2026, assinatura,
  N/n, histórico, cinco sorteios, 261 sorteados e seis adicionais (267 no
  campo). Nenhum ressorteio ou limpeza de testes faz parte da integração.
- ACS continuam provisórios e configuráveis depois. A configuração futura
  não altera os participantes das visitas já recebidas.
- Boletins/índices LIRAa continuam usando seu vínculo a ciclo, período, plano,
  estrato e adicionais. A presença no total de produção não torna uma visita
  inválida para a amostra automaticamente válida no boletim.
- Quarteirões decimais são preservados. Não se inventa situação de visita,
  hora final, duração ou quantidade de depósitos inspecionados não coletados
  pelo formulário. Tratamento BTI informado pode compor os relatórios comuns.
- Resultados LARVAS do Kobo podem alimentar a leitura de origem. Para LIRAa,
  exige correspondência exata de tubo/data e uma conta identificável do
  laboratorista; ambiguidade fica pendente, sem usar reparo por data aproximada.
  UUID/origem da leitura são preservados e não há sobrescrita automática.
- A exportação `.lira` e os índices oficiais finais permanecem no fluxo já
  documentado; não são calculados a partir dos indicadores gerais de rotina.

## Banco e ativação

Migração PostgreSQL **0029_liraa_integracao_notificacoes.sql**, aditiva:

- Vínculo único `focos_positivos.id_visita_liraa` e identificação textual
  `quarteirao_liraa`, preservando o tipo/campos antigos das notificações.
- `origem` e `kobo_uuid` nas leituras LIRAa, com unicidade do UUID externo.

Não migra visitas para as tabelas de rotina nem altera o planejamento. SQLite
continua compatível nos ensaios isolados; o banco congelado não recebe escrita.

`scripts/reconciliar_liraa_notificacoes.py` faz prévia somente leitura por
padrão. Gravação requer `--aplicar --confirmar "RECONCILIAR NOTIFICACOES LIRAA"`
e `--confirmar-banco endemias` em produção. A reconciliação mantém status e
histórico, sem criar duas notificações para a mesma visita. Não é executada
automaticamente na abertura de uma tela.

Prévia administrativa somente leitura de 03/11: somente a migração 0029 está
pendente; assinatura do ciclo corresponde à fonte aprovada, cinco sorteios,
**zero visitas LIRAa e zero notificações LIRAa a reconciliar**. As consultas
integradas retornaram os totais existentes (17.452 visitas, 273 coletas e 270
resultados gerais) sem acrescentar registros fictícios.

Ativação exige backup PostgreSQL validado, aplicação exclusiva da migração
esperada, integração com o serviço parado, reinício autorizado e comparação
dos dados reais antes/depois. Não aplicar outras migrações ou publicar Kobo.

## Validação

- Suíte geral: **876 testes, sem falhas, cinco ignorados**.
- Testes adicionais de fluxo verificam importação, simulação/rollback,
  repetição, transporte JSON longo, XLSX completo, seleção provisória de ACS,
  contexto/UIDs de ciclos, tubos ambíguos, fila/histórico, correção concorrente,
  terreno baldio, notificação agrupada, exclusão e preservação do sorteio.
- Três testes JS LIRAa, incluindo a tela renderizada e troca entre os campos
  do LIRAa/rotina, versão enviada na correção e formulário único.
- Ensaio PostgreSQL 18 com tabelas temporárias, sem `public` no search_path:
  migração, consultas, tratamento, leitura, notificação, relatório individual,
  relatório do setor, consolidado XLSX, leitura Kobo e exclusão passaram.
- A fonte XLSX e o SQLite congelado conservaram suas assinaturas originais.

Serviço oficial ainda não ativado nesta preparação. A conferência em campo
deve ser feita com a versão ativa e o formulário correto nos aparelhos.
