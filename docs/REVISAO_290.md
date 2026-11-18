# Revisão Endemias e Ambiental — versão 2.9.0

Pacote preparado em worktree isolada e ativado, após autorização, em
18/11/2026 às 08h11, release 90515bd. Relatório
`C:\ProgramData\EndemiasWeb\ativacao-revisao290-resultado.json` aplicado e
concluído: backup PostgreSQL catalogado de 7.740.896 bytes e backup completo de
311.583.999 bytes, migração 0037, dados de 97 tabelas anteriores e arquivos
operacionais preservados. Prova da conta limitada, retomada Kobo e entradas
dos setores passaram. Portal e logins públicos/locais confirmaram 2.9.0.

A consulta agregada `ativacao-revisao290-estoque.json`, somente leitura, registrou
saldo 650, necessidade ativa quantificada 820 e déficit 170 cápsulas. Há um
animal ativo sem quantidade definida e sete situações para revisão. Os 42 casos
encerrados não apresentaram pendência ativa. Esses números não substituem
contagem física nem estimam tratamentos futuros; referem-se à consulta às 08h11.

- Amostra de Animais: equivalências explícitas de motivos e tipos, preservando
  os textos originais no banco; filtros, contadores e agrupamentos consideram
  as equivalências. Novas categorias não mapeadas continuam visíveis como vieram.
- Anexos: inclusão por operador, listagem e download por usuários autorizados
  no setor Ambiental; arquivos ficam no diretório habitual de anexos. Migração
  PostgreSQL 0037 deve ser aplicada com backup e ativação autorizados.
  O pacote de ativação preparado é `scripts/ativar_revisao_290_windows.py`;
  ele exige commits conferidos, console administrativo e versão de origem 2.8.6.
- Ovitrampas: lote existente não ganha armadilhas posteriores; evento
  com lote não pode ser excluído nem mudar campos que alterem sua identidade.
  Envios sem resposta ficam bloqueados para conferência antes de repetir.
  A data apresentada como conclusão corresponde ao encerramento do lote, não
  necessariamente ao momento exato de leitura de cada armadilha.
- PE: uma visita ou BRI sem vínculo não identifica automaticamente um de
  vários PEs no mesmo quarteirão. Casos ambíguos exigem vinculação correta.
- Privacidade e segurança: equipe de coleta segue o escopo do usuário, CSV de
  ovitrampas neutraliza fórmulas e o relatório por agente trata texto como dados.
- Agenda: recorrências mensais preservam o dia original sempre que possível.
- Esporotricose (17/11): casos encerrados não mostram pendência ativa de
  cápsulas/receita; quantidades históricas e entregas permanecem registradas.
  O cálculo de necessidade ativa considera explicitamente Em tratamento;
  aguardando documentos/medicação e medicação disponível ficam em grupo
  separado. Outro e status sem classificação aparecem para revisão. Há aviso
  de necessidade não quantificada em animais ativos sem receita ou com receita
  pendente, déficit destacado e indicação de conferir o saldo com contagem
  física. Entregas a casos encerrados não representam sobras automaticamente.
  Passaram 65 testes de Esporotricose e 27 regressões selecionadas da suíte de
  segurança; a tela foi ensaiada em Chromium 1440/390 px com dados fictícios.
  A regressão geral registrada abaixo é anterior a este acréscimo, que foi
  verificado pelos testes focados. Sem migração adicional além da 0037 do pacote.
- LIRAa: ciclo encerrado informa bloqueio e correção individual rejeita lista
  de sequências; não reinterpreta dados históricos.

Regressão geral: 1.232 testes executados, sem falhas, dos quais cinco ignorados;
ocorreram avisos de
conexões SQLite abertas durante a bateria. As alterações feitas durante a
execução foram verificadas novamente em testes focados. O simulador do
instalador passou em 26 testes, incluindo a migração 0037. Verificações focadas
usaram SQLite temporário, transporte remoto simulado e PostgreSQL descartável;
a migração e a trava de envio foram ensaiadas no PostgreSQL isolado. Em Chromium,
com dados e conta fictícios, a tela de
Amostras foi conferida em 1440 e 390 px, incluindo listagem e envio de anexo.
Na implantação, o instalador conferiu a 0037, os backups, a conta de serviço
e o retorno das entradas. Não foi feita restauração integral nesta ativação.
A revisão visual
de todas as telas do sistema não foi concluída. A existência de Vigiágua como
área em desenvolvimento e a situação do Windows/ESU exigem decisões próprias.
