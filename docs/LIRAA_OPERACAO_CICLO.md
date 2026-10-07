# LIRAa — plano de campo, formulário e boletins

Atualização preparada em 07/10/2026, código `1.67.0`. Exige a migração
PostgreSQL **0026_liraa_operacao_ciclo.sql**. Não presumir que a migração ou
o reinício oficial aconteceram: conferir `ESTADO_ATUAL_PROJETO.md` e o estado
vivo. A produção foi confirmada anteriormente em `1.66.0`, com a 0025 aplicada.

## Fluxo

1. Criar ciclo, compor os estratos e conferir N confirmado, localidades e
   ordem municipal dos quarteirões. O sorteio continua em homologação operacional.
2. Sortear; os detalhes mostram também os totais por localidade. Se necessário,
   informar o início casual no sorteio ou em **Ressortear**. Aceita vírgula ou
   ponto decimal, valor maior que zero e até o intervalo amostral. Valor vazio
   sorteia o IC. Comparar com o programa oficial exige os mesmos parâmetros,
   ordem de localidades e tradução de posição local para quarteirão municipal;
   o IC sozinho não garante coincidência.
3. **Plano de campo e exportação**: selecionar ciclo, estrato e/ou localidade;
   conferir mapa com etiquetas, ruas/satélite, lista, exportar KML com cores
   e PDF A4 retrato. Quarteirões sem geometria impedem exportação cartográfica,
   em vez de serem omitidos. Multipartes e anéis internos são preservados.
4. **Formulário do ciclo**: selecionar ACS participantes e salvar, mesmo
   quando não houver nenhum. Gerar XLSForm, fazer upload manual no Kobo e
   cadastrar o UID específico do ciclo. O token/servidor existentes continuam
   sendo usados; não há publicação automática. O UID específico prevalece
   sobre o UID geral antigo na consulta/importação.
5. **Importar Kobo**: consultar prévia e importar manualmente; continua
   separado da automação geral. Visitas fora do plano/período ou com metadados
   de outro ciclo/sorteio ficam para revisão e **não entram no boletim**.
6. **Lançamentos Laboratório → Tubos · LIRAA**: os tubos importados aparecem
   identificados como LIRAA, com contador global de pendências, filtro por ciclo,
   situação e paginação. Salvar mantém essa aba e atualiza as pendências.
   A consulta direta `/liraa/laboratorio` também permanece disponível.
   Lançar larvas e pupas de
   Ae. aegypti, Ae. albopictus e outros, por tubito. Exige admin ou permissão
   de laboratório já existente. Contas exclusivas de laboratório recebem acesso
   apenas às duas rotas de leitura LIRAa, sem liberar planejamento ou exportações.
   A assinatura vem da conta autenticada, sem exigir um vínculo com ACE.
   O laboratório de rotina continua funcionando mesmo antes da migração 0026;
   a nova aba informa a migração necessária sem criar tabelas nessa abertura.
7. **Boletins**: consultar e gerar PDF por estrato ou localidade dentro do
   estrato. Resultados com pendências ficam marcados como parciais.

## Sorteio e histórico

Não foi alterada a fórmula validada contra os cinco estratos do LIRAa/LIA:
o comportamento amostral e a distribuição por localidade permanecem iguais.
Para novos sorteios, a ordenação municipal é numérica também para decimais:
408, 408.1, 409. Sorteios antigos conservam a seleção e o universo congelados.

Ressortear substitui a seleção atual, mas arquiva o registro anterior completo
em `liraa_sorteios_historico`, mostrado na tela. A operação e sua auditoria
são transacionais, exigem o ID de sorteio esperado e são bloqueadas depois
de **qualquer visita importada no ciclo**. Importação e sorteio compartilham
bloqueios para evitar alterações simultâneas do plano. Após o ressorteio,
gerar e publicar novamente o formulário antes das visitas. Excluir o ciclo
ou estrato também remove seu histórico de sorteios, como parte da exclusão
administrativa já confirmada; ciclos com visitas continuam protegidos.

## XLSForm gerado

Modelo versionado: `app_core/data/liraa_kobo_base.xlsx`, cópia do formulário
enviado pelo usuário, sem respostas, tokens ou credenciais. O original não
é alterado. A lista ACS utiliza os mesmos códigos do modelo e nomes do
catálogo municipal, quando disponíveis. ACE permanecem conforme o modelo.

- `Dados_visita/Localidade`: somente localidades com quarteirões sorteados.
- `Dados_visita/Quarteir_o`: `select_one`, obrigatório, filtrado pela localidade;
  valores são os números municipais, incluindo decimais. O importador antigo
  de número digitado (`408.1` / `408,1`) continua compatível.
- ACS: apenas participantes + `no-acs`; “Nenhum” não pode ser combinado com nomes.
- `Houve_coleta` / `Quantidade_coletas`: controlam repetição de tubitos,
  evitando uma coleta vazia quando não houve coleta.
- Número de tubito positivo e obrigatório; depósitos A1, A2, B, C, D1, D2, E.
- Tratamento fica fora do repetidor, associado ao imóvel; foi retirada a
  condição antiga que citava o campo inexistente `Visita`.
- Data obrigatória e limitada ao período do ciclo, se definido.
- Campos ocultos `endemias_ciclo` e `endemias_plano` identificam ciclo e
  hash do sorteio. Formulários legados sem esses campos ainda são aceitos.

O XLSForm contempla o **ciclo inteiro**, não só o filtro visual atual.
Não oferece fechados/recusas nem Capivara rural. Os nomes técnicos anteriores
são preservados. O importador aceita grupos achatados do Kobo e repetidos
com prefixo `group_jr1vc40/`, preserva tratamento no formato novo e legado.
Reimportação continua idempotente; não reescreve envios já gravados.

## Como interpretar os totais

Fonte metodológica: [Manual LIRAa 2013, Ministério da Saúde, itens 6.1 e 6.3](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/svsa/dengue/manual_liraa_2013.pdf).

- **Programados** do resumo oficial = `n` calculado no plano do estrato.
  Na consulta por localidade, esse número é identificado como sendo do estrato
  inteiro; não é inventada uma repartição oficial de `n` por localidade.
- **Referência operacional RG** = 20%/50% das unidades de cada quarteirão
  sorteado, arredondadas para cima. É estimativa para orientar campo, não
  substitui `n`. Exclui PE/REF e expande condomínios residenciais como o RG.
  Mostra dados atuais do RG; o sorteio mantém seu snapshot anterior.
- **Trabalhados** = submissões de imóveis abertos vinculadas ao plano/período.
  Não se unem endereços automaticamente. Conferir retornos/visitas duplicadas
  e excluir testes antes do uso oficial. Ausência de tubito não representa
  leitura negativa, mas o imóvel aberto continua contado como trabalhado.
- Um **tubito** representa um recipiente; positividade depende de larvas/pupas.
  Vários tubitos positivos da mesma visita contam apenas um imóvel positivo
  por espécie. Um recipiente com ambas as espécies conta uma vez para cada.
- Sem leitura é **pendente**, não zero/negativo. Falta de tipo de imóvel ou
  código de depósito aegypti válido deixa o resumo parcial. Código legado como
  `B2` não é convertido silenciosamente para `B`.
- Admin pode corrigir leituras e classificação do depósito local, com auditoria.
  Somente admin corrige leitura já salva; versão desatualizada é recusada.
  Correções não são enviadas ao Kobo. Excluir visita remove também leituras,
  mantém bloqueio de reimportação por UUID e não apaga o envio remoto.

O PDF copia as categorias do modelo enviado e inclui avisos de incompletude,
programados/trabalhados, positivos TB/outros por espécie e recipientes por código.
Ainda não calcula índices finais, CV, classificação de risco ou encerramento
oficial; não gera `.lira`. O fechamento administrativo e a janela de geração
do arquivo continuam no programa oficial conforme decisão do usuário.

## Validação e implantação

- Regressão SQLite isolada: 786 testes passaram (5 ignorados).
- Exemplos PDF renderizados e inspecionados, A4 retrato.
- XLSForm convertido com `pyxform 4.5.0`, sem avisos de estrutura; falta teste
  real de upload/uso Kobo/Enketo. ODK Validate não foi executado (Java ausente).
  O compilador é ferramenta temporária de QA, não dependência do sistema.
- UI testada em `127.0.0.1:5002`, somente SQLite descartável: mapa, abas,
  participantes, leitura salva, boletim atualizado e agrupamento por localidade.
  A aba Tubos · LIRAA em Lançamentos Laboratório manteve o filtro e o contador
  passou de 3 para 2 após salvar; nenhuma leitura foi gravada em banco real.
- `scripts/testar_liraa_operacao_postgresql.py`: recusa qualquer banco diferente
  de `endemias_teste`; usa apenas tabelas temporárias, com `public` fora do
  search_path, e descarta tudo ao fechar a sessão. Credencial PostgreSQL deve
  ser acessada apenas pelo contexto autorizado, sem copiar senha ou mudar ACL.
- Ensaio PostgreSQL 18 concluído em cluster temporário próprio, localhost:55432:
  migração, histórico, ressorteio, XLSForm, importação, leitura, contador,
  boletim e exclusão em cascata passaram. Instância encerrada após o teste;
  credenciais e banco oficial não foram utilizados.
- Produção: backup validado, migração 0026 e reinício **somente com autorização**.
  Não executar scripts de QA em `endemias`, nem alterar o SQLite congelado.
