# Execucao local com conta limitada

Aplicado em 03/11/2026, mediante pedido expresso do usuario para trocar a
identidade e proteger codigo/chaves. Confirmado HTTP 200/1.75.0 as 16h05
(America/Sao_Paulo). Ver fechamento abaixo e resultado administrativo privado.

## Escopo desta etapa

- Preservar a master `f7a98a0`, codigo/versao 1.75.0 e o banco PostgreSQL real.
- Alterar somente a tarefa `Endemias - Servidor` para uma identidade local
  dedicada, sem administrador, com logon em lote e negacao de logon
  interativo, RDP e logon de rede do Windows. Isso nao bloqueia as conexoes
  TCP da aplicacao ou o login dos usuarios pelo navegador.
- Nao integrar o codigo 1.76.0, executar migracao, alterar plano LIRAa,
  mudar o servico PostgreSQL/firewall/DNS ou publicar o Tunnel nesta etapa.
- Preservar o iniciador web atual e acesso local. Waitress/perfil externo
  continuam na preparacao 1.76.0, cuja ativacao sera uma etapa separada.

## Pacote preparado

- `scripts/preparar_python_web_windows.py`: copia runtime padrao para
  `C:\ProgramData\EndemiasWeb\base-python`, sem site-packages do usuario,
  e vincula a venv dedicada a essa copia. Nao altera o Python compartilhado.
- `requirements-web-windows.lock`: versoes dos componentes do ambiente
  ensaiado; instalacao independente em `C:\ProgramData\EndemiasWeb\python`.
  Sem pywin32 nessa venv: ele e necessario somente no Python administrativo
  da worktree, onde foi instalado como ferramenta de preparacao.
- `scripts/endurecer_web_windows.py`: sem argumentos apenas valida; com
  `--aplicar` cria conta, prepara permissoes, backup e ensaio, e somente
  depois troca a tarefa. `--reverter` restaura tarefa/ACL anteriores depois
  de uma aplicacao concluida, sem restaurar nem apagar dados operacionais.
- `scripts/servico_web_windows.py`: entrada nativa com Python isolado (`-I`),
  sem executar PowerShell ou alterar sua politica. Confere o SID esperado,
  limpa variaveis de ambiente herdadas da aplicacao e carrega a configuracao
  privada. Usa o mesmo codigo oficial. Nao aceita execucao como administrador.
- `fortalecer_servidor.bat`: atalho de aplicacao; requer executar como
  administrador. Senha de servico aleatoria nao e impressa, passada na linha
  de comando nem gravada em arquivo; registro usa a API do Agendador.

## Permissoes e caminhos

Codigo, templates, scripts, Python e dependencias ficam somente para leitura
e execucao pela conta web. A conta de manutencao conserva acesso ao codigo.
As regras sao explicitas e protegidas, removendo heranca de grupos amplos;
SYSTEM/administradores mantem controle. Os caminhos sao fixos e a rotina
recusa reparse points para nao modificar destinos fora do escopo.

`secret.key`, pgpass e chave Conta Ovos ficam legiveis somente para
SYSTEM/administradores e a conta web. A conta web nao pode modifica-los. A
configuracao Kobo permanece no caminho atual, para preservar importacao
agendada/backups existentes, com leitura/escrita somente na identidade web
e administradores; a conta web nao pode substituir o arquivo pelo diretorio
pai. O token e a chave existente sao preservados, sem regeneracao.

Anexos, uploads temporarios, notificacoes geradas e saida permitem alteracoes
pela conta web. Log e estado sanitizado Conta Ovos ficam em
`C:\ProgramData\EndemiasWeb\runtime`; temporarios em `runtime\temp`. Assim,
rotacao de log e substituicao atomica do status nao exigem escrever no codigo
ou no diretorio das credenciais. A copia atual do status e preservada para
consulta; outros processos mantem o caminho anterior.

Os backups manuais da interface passam a usar
`D:\BackupsEndemias\backups_web\banco` e `completos`, com permissoes proprias.
As tarefas automaticas e os historicos em `backups_banco`/`backups_completos`
permanecem nos caminhos anteriores, sem permissao nova para a conta web.
Consequencia: a listagem de arquivos da interface usa o novo destino; os
arquivos automaticos antigos continuam preservados fora dessa listagem. Isso
evita conceder ao processo web a capacidade de apagar todas as copias.
Nao equivale a backup externo/offline; essa protecao adicional segue pendente.

## Ensaios e retorno

Antes de alterar permissoes, a rotina guarda a tarefa original e as ACLs em
`C:\ProgramData\EndemiasWeb\rollback\<data-hora>`, acessivel somente por
SYSTEM/administradores. Cria backup PostgreSQL previo e valida seu catalogo.
Captura todas as ACLs antes de mudar heranca dos pais. Nao copia conteudo
real para fixtures ou para o Git: os dumps reais sao backups privados de
protecao da operacao autorizada.

A tarefa temporaria roda com a identidade final, sem parar o servidor atual.
Confere negacao de escrita/criacao em codigo, Python e chave; leitura das
credenciais sem exibi-las; escrita nas pastas operacionais; acesso negado a
area privada de retorno; conexao SQL somente leitura e ausencia de privilegios
SQL de superusuario/criacao de papeis/bancos; XLSX/PDF sinteticos; rotacao de
log; pagina de login com a versao atual; e backup real com catalogo validado
usando a identidade limitada. Nenhum usuario ficticio ou aceite e inserido no
banco oficial.

Depois, confere hashes de app/chave/Kobo/config/SQLite congelado, para a tarefa
oficial, verifica que a porta realmente foi liberada e registra/inicia a
tarefa limitada. Confirma HTTP 200/1.75.0. Se o ensaio ou a troca falhar, tenta
restaurar ACLs e tarefa anteriores; o resultado informa erros de retorno, sem
restaurar banco ou sobrescrever configuracao que tenha mudado legitimamente.

Resultados sanitizados em `C:\ProgramData\EndemiasWeb\resultado.json`;
progresso em `progresso.json`; falha anterior ao resultado em
`falha-preparacao.json`. Nao tratar existencia do pacote como implantacao.
Interrupcao abrupta do Windows exige conferir o estado real e os arquivos
privados de retorno; retorno automatico cobre falhas capturadas pela rotina.

Limitacoes: a conta ainda precisa acessar dados e credenciais operacionais;
um comprometimento do processo pode usar esses acessos. O usuario de manutencao
e administradores continuam confiaveis. A protecao nao corrige falhas do Windows
nem substitui o piloto do Tunnel, firewall, revisao de usuarios e backups externos.

## Validacao do pacote

Validacao do pacote: 900 testes gerais passaram (seis ignorados) sobre massa
sintetica, usando os componentes da venv dedicada. Seis testes de endurecimento
passaram na ferramenta administrativa, incluindo aplicacao e retorno de ACL
em arquivo ficticio, sem criar conta. Este ultimo teste foi acrescentado apos
a regressao geral e passou separadamente. `pip check` sem conflitos e auditoria
da venv dedicada sem vulnerabilidades conhecidas apos atualizar pip para 26.3.
Runtime independente conferido depois da copia. Nenhum desses resultados
substitui o ensaio administrativo com a identidade real antes da troca.
Depois do ajuste do registro da tarefa de ensaio, sete testes de endurecimento
passaram separadamente, incluindo a configuracao independente da tarefa
temporaria (sem copiar triggers/reinicios da tarefa oficial).

## Fechamento administrativo — aplicado

- Tarefa oficial alterada para `EndemiasWeb`, com RunLevel limitado. O processo
  novo conferiu seu SID antes de carregar a aplicacao. Nao roda mais como SYSTEM.
- Python e componentes dedicados em `C:\ProgramData\EndemiasWeb`, independentes
  do perfil pessoal. Codigo oficial permanece 1.75.0; sem merge/migracao.
- Ensaio real retornou todos os checks verdadeiros: negacao de escrita nos
  arquivos protegidos/Python, acesso aos recursos operacionais, SQL sem
  privilegios administrativos, XLSX/PDF/rotacao, login e backup pela conta final.
- Backup previo da tentativa concluida: 7.523.819 bytes, catalogo validado,
  privado em `C:\ProgramData\EndemiasWeb\rollback\20261103-160333` junto da
  tarefa e das ACLs anteriores. O dump da conta limitada tambem teve catalogo
  validado. Nenhum backup foi enviado ao Git ou copiado para fixtures.
- Hashes de app/chave/Kobo/config/SQLite congelado iguais antes/depois, conforme
  relatorio administrativo. Hash do SQLite reconfirmado na sessao comum:
  `964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.
- Sessao Windows comum agora recebe acesso negado ao tentar abrir chave de
  sessao/Kobo, sem ler seu conteudo; aplicacao continua podendo utiliza-los.
- Login respondeu HTTP 200/1.75.0 por loopback e pelo IP privado. Usuario
  confirmou que abriu a tela de login por outro aparelho na rede do setor.
  Isso valida acesso local; nao e ensaio de carga ou de todas as funcoes.
- Firewall do Windows e regras de outros programas nao foram alterados. A
  analise identificou regras antigas do Python, mas o teste real confirmou
  acesso entre aparelhos; nao foi necessario adicionar regra nesta etapa.
- Primeira tentativa foi interrompida no registro COM da tarefa de ensaio;
  restaurou as ACLs com zero erros e nao trocou o servidor. A tentativa final
  usou definicao independente para o ensaio e concluiu a troca. O relatorio
  atual declara `status=aplicado`, sem erro de retorno ou limpeza pendente.
- Tarefas automaticas de backup/importacao e servico PostgreSQL preservados.
  A identidade web pode ter visibilidade limitada do estado de tarefas SYSTEM;
  isso nao significa falha dos backups. Nao foram ampliadas permissoes dessas
  tarefas apenas para a consulta da interface.
- Configuracao de retorno e dados privados permanecem fora do Git. Para
  retorno, executar o helper administrativo com `--reverter`; ele restaura
  tarefa/ACLs, confirma a versao anterior e nao restaura banco automaticamente.

Atualizacao de 04/11: codigo/Waitress 1.76.0 ativo localmente, somente 0030
aplicada, PostgreSQL somente localhost, mesma conta/tarefa e dados preservados.
O retorno antigo --reverter descrito acima foi superado e agora recusa esta
configuracao; eventual retorno tardio exige plano proprio sem restaurar banco.
Falta encaminhar `endemias.vsatt.com.br` para HTTP 127.0.0.1:5001, validar
HTTPS oficial e reinicio. Ver `CLOUDFLARE_VALIDACAO_EXTERNA.md`. Nao repetir
a criacao da conta nem o instalador antigo SYSTEM.
Windows atual mantido conforme decisao do usuario; VPS permanece futura.

## Referencias tecnicas oficiais

- [Microsoft - contexto de seguranca das tarefas](https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks)
- [Microsoft - registro da tarefa](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskfolder-registertaskdefinition)
- [Microsoft - direitos de logon](https://learn.microsoft.com/en-us/windows/win32/secauthz/account-rights-constants)
