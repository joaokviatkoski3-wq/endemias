# Auditoria e rastreamento do sistema

Implementação preparada em novembro de 2026. A instrumentação só começa após
a implantação; não recompõe operações anteriores e não constitui auditoria
forense do Windows. Contas, setores, dados e esquema do banco são preservados.

## Duas fontes complementares

Antes, a página de auditoria mostrava até 200 eventos e a exportação limitava
silenciosamente o resultado a 500. O registro dependia das chamadas explícitas
dos módulos; o arquivo técnico tradicional guardava mensagens e exceções livres.

Agora `/admin/auditoria` oferece filtros, total, intervalo e páginas de
25/50/100 eventos. Admin e superadmin continuam consultando somente a auditoria
do setor atual. Os eventos explícitos continuam na tabela existente, sob as
mesmas transações; falha na auditoria obrigatória continua revertendo a operação.
Nenhuma migração, limpeza ou truncamento do histórico SQL foi acrescentada.
As consultas da auditoria usam SELECT, sem criar tabelas ou índices.

As novas entradas acrescentam o ID de correlação, método, endpoint e padrão da
rota. Campos e antes/depois dependem do que cada operação já audita: não existe
captura automática de todas as alterações do banco. Datas, quantidades, códigos,
categorias e motivos estruturados são preservados quando seguros. Senhas,
segredos, endereços, descrições livres e dados clínicos são omitidos. O detalhe
novo fica limitado a 32 KiB; excesso e coleções limitadas são sinalizados.
A apresentação/exportação também reduz detalhes sensíveis antigos, sem alterar
o conteúdo original armazenado.

`/admin/auditoria?origem=tecnico` é exclusivo do superadmin. Mostra a trilha
JSONL do setor atual; Portal e Aplicação sem setor podem ser escolhidos
explicitamente. O outro setor deve ser consultado no próprio domínio.
Admin e demais perfis não podem ler ou exportar a fonte técnica.

## O que a trilha técnica registra

- Requisições de Endemias, Ambiental e Portal: horário UTC, ator/ID quando
  disponível, origem da identidade, nível, setor, IP validado, método, endpoint,
  padrão da rota, status HTTP, duração, tamanho declarado da resposta e correlação.
  Versão do aplicativo e processo de origem acompanham cada evento.
- IDs inteiros/UUID presentes nos argumentos `id`, `uid` ou `id_*`; nomes,
  caminhos, nomes de arquivos e argumentos livres não são copiados.
- Downloads pela resposta de anexo, sem registrar conteúdo ou nome do arquivo.
- Rejeições e erros, inclusive de arquivos estáticos. Arquivos estáticos sem
  erro ficam de fora. Presença rotineira e GET/HEAD de saúde sem erro são
  resumidos no máximo uma vez por minuto/endpoint/processo; erros não são resumidos.
- Início e encerramento observado dos fluxos SSE de importação, com indicação
  de encerramento completo ou interrupção. Duração inicial não é tratada como
  duração total. Referências de auditoria no HTTP são correlação, não prova de
  commit: a fonte de confirmação de negócio continua sendo a tabela de auditoria.
- WARNING/ERROR: nível, módulo, função, linha, classe da exceção e até dez
  frames com nome de arquivo, função e linha. Não há mensagem da exceção,
  argumentos, linha de código, SQL ou DSN. O arquivo técnico tradicional usa
  o mesmo formato seguro daqui em diante; arquivos antigos não são reescritos.
  No evento técnico, `nivel_log` identifica a gravidade; `nivel` continua sendo
  o perfil da conta, quando disponível. Esses dois dados não se sobrescrevem.
- Inicialização por processo/área e encerramento normal, quando observado.

O cabeçalho `X-Request-ID` é gerado pelo servidor. IDs fornecidos pelo cliente
não são reutilizados. Query strings, corpos, cookies, autorização e tokens não
são capturados. Rotas desconhecidas ficam sem o caminho livre enviado pelo
cliente. Não há SQL novo por consulta de negócio para registrar os acessos.

## Armazenamento, retenção e desempenho

Arquivos em `<pasta de LOG_PATH>/logs_privados/<área>/requisicoes.jsonl`, onde
LOG_PATH respeita `ENDEMIAS_LOG_PATH`. Áreas possíveis: endemias, ambiental,
portal e sistema. A pasta deve herdar as permissões privadas da instância;
modo 0700/0600 é aplicado quando suportado. Em Windows, a proteção depende
também da ACL conferida no procedimento de implantação. Arquivos não são
servidos diretamente por HTTP.

Cada área mantém arquivo de até 5 MiB e cinco rotações: até 30 MiB, além do
pequeno lock e de espaço temporário durante a manutenção. Por hora, na próxima
gravação, a manutenção remove registros de mais de 30 dias, inclusive de um
arquivo ativo de baixo volume. A consulta já exclui esses registros antes da
manutenção. Volume alto pode reduzir o período disponível. Não há crescimento
do banco provocado por GETs, presença, downloads ou erros técnicos; o histórico
SQL de negócio mantém a política existente e requer decisão própria de retenção.

Gravação usa exclusão entre threads/processos, append de linha limitada e
rotação. Falha de armazenamento não derruba a operação: o processo conta as
falhas e a tela técnica mostra aviso. Isso implica possível perda de eventos,
sem promessa de trilha inviolável. Leitura faz snapshot do conjunto limitado de
arquivos; linha inválida/arquivo ilegível é sinalizado e impede exportação.

## Exportação

`/admin/auditoria/exportar` preserva os filtros e exporta o conjunto completo
dentro de 10.000 registros e 16 MiB por requisição. A fonte técnica usa
`?origem=tecnico`. Acima dos limites, ou diante de leitura incompleta/célula
excessiva, o servidor recusa com orientação para reduzir o período; não gera
arquivo cortado silenciosamente. O XLSX técnico inclui o evento completo
seguro em Detalhes, além das colunas legíveis. Células são protegidas contra
interpretação como fórmulas.

## Limites e prova operacional

Um download gerado não comprova recebimento pelo aparelho. Encerramento forçado,
falta de energia ou perda do disco podem impedir o registro final. Sessão/ator
podem estar ausentes em falhas precoces; a origem da identidade fica explícita.
Logs de threads sem contexto HTTP vão para sistema sem atribuir setor/usuário.
Rotinas Kobo agendadas continuam registrando o histórico próprio de importações;
seu ciclo completo não recebeu nova instrumentação nesta entrega. Falhas antes
do Flask, Tunnel, roteador WSGI, navegador e sistema operacional ficam fora.

`app_core.logging_rastreamento.provar_rotacao(config)` usa somente uma subpasta
temporária na pasta de LOG_PATH para conferir criação, escrita, rotação e
remoção, sem consultar dados reais. A implantação deve executar essa prova
com a mesma identidade limitada do servidor. Os testes usam dados fictícios;
a evidência de produção deve ser conferida pelo operador antes de declarar
a trilha ativa.
