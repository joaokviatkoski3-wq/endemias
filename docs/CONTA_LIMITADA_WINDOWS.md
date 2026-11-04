# Servidor local com conta limitada — estado vigente

Versão vigente **1.79.0**, ativa em 04/11 às 11h58 com superadmin e gestão delegada.
Mesma tarefa/identidade/ambiente e proteções. Ver `SUPERADMIN_PERMISSOES.md`;
os registros 1.75/1.76 abaixo descrevem as etapas anteriores.

Conta limitada aplicada em 03/11/2026. **Atualização de 04/11:** produção local
agora 1.76.0/Waitress, com a mesma tarefa/identidade e credencial preservada.
LAN/loopback:5000, origem Tunnel só 127.0.0.1:5001, PostgreSQL só localhost.
Backup, migração 0030 e preservação das 90 tabelas conferidos. Publicação
oficial pendente; ver `CLOUDFLARE_VALIDACAO_EXTERNA.md`. As evidências 1.75.0
abaixo registram a etapa anterior de instalação da conta, não a versão vigente.

## Estado confirmado

- Tarefa `Endemias - Servidor`: conta local dedicada `EndemiasWeb`, RunLevel
  limitado, logon em lote e negação de logon interativo/RDP/rede do Windows.
  Acesso ao sistema pelo navegador continua funcionando.
- Runtime independente do perfil pessoal em `C:\ProgramData\EndemiasWeb`:
  `base-python` contém o Python padrão; `python` contém a venv; entrada nativa
  `servico_web_windows.py`, configuração de caminhos/SID em `config.json`.
  Senha aleatória da conta não foi colocada em arquivo/comando/chat/Git; fica
  sob tratamento do Agendador. Não redefini-la sem atualizar a tarefa.
- Código oficial, templates, scripts e Python sem escrita pela identidade web.
  A conta de manutenção preserva acesso ao código. `secret.key`/Kobo/pgpass/
  chave Conta Ovos têm acesso delimitado; sessão Windows comum não lê os
  segredos. A conta web lê as chaves e pode gravar a configuração Kobo pelo
  sistema; não pode substituir código ou chave. Tokens e chave preservados.
- Anexos, uploads temporários, notificações geradas e saída continuam nos
  caminhos oficiais, com escrita delimitada. Logs/status e temporários da
  aplicação ficam em `C:\ProgramData\EndemiasWeb\runtime` e `runtime\temp`.
- Backups manuais da interface agora em `D:\BackupsEndemias\backups_web\banco`
  e `completos`. Os backups automáticos/históricos continuam em `backups_banco`
  e `backups_completos`, com as tarefas existentes, fora do alcance de exclusão
  da conta web. A listagem da interface passa a refletir o novo destino; isso
  não apaga o histórico automático. O estado de tarefas SYSTEM pode aparecer
  como não verificável na interface limitada; não equivale a backup falhando.

## Validação e preservação

900 testes gerais sobre dados fictícios passaram (seis ignorados) com os
componentes dedicados. Sete testes de endurecimento passaram separadamente,
incluindo ACL real em arquivo fictício/retorno e configuração própria da
tarefa de ensaio. Auditoria dos componentes sem vulnerabilidades conhecidas;
`pip check` sem conflitos. Esses testes não certificam ausência de falhas.

Antes de trocar o servidor, uma tarefa temporária com a identidade final
confirmou leitura das credenciais sem exibi-las, negação de escrita em
código/chave/Python e de acesso ao retorno privado, operações de arquivos,
SQL somente leitura sem privilégios de superusuário/criação de papéis/bancos,
XLSX/PDF fictícios, rotação de logs, login da versão atual e backup PostgreSQL
real com catálogo validado. Não inseriu dados fictícios/aceites no banco real.

Backup prévio da troca concluída: 7.523.819 bytes, catálogo validado; definição
original da tarefa/ACLs e dump em
`C:\ProgramData\EndemiasWeb\rollback\20261103-160333`, acessível somente a
SYSTEM/administradores. Relatório sanitizado em
`C:\ProgramData\EndemiasWeb\resultado.json` declara `status=aplicado` e todos
os checks verdadeiros. Hashes de app/chave/Kobo/config/SQLite congelado iguais
antes/depois. SQLite reconfirmado com SHA-256
`964152E21DE44B4FFF985F72A0D7945E8E7DCF260BBB019708B868C3B3A7A025`.

Login HTTP 200/1.75.0 por loopback e IP privado; usuário confirmou a tela em
outro aparelho da LAN. Não houve alteração do firewall: a confirmação real
demonstrou que não foi necessário criar uma regra adicional nesta etapa.

## Manutenção e retorno

- Não executar o configurador histórico de inicialização, que reinstala a
  tarefa como SYSTEM. Reiniciar a tarefa registrada preserva a identidade.
- Instalador/testes/lockfile estão versionados na branch
  `codex/preparar-cloudflare`, worktree `C:\endemias-cloudflare`.
  O retorno `scripts/endurecer_web_windows.py --reverter` é exclusivo da
  instalação original 1.75.0/Werkzeug e agora recusa a configuração posterior.
  Não usá-lo após a ativação 1.76.0. Eventual retorno tardio exige plano próprio,
  preservando dados novos/0030/aceites, sem restaurar banco automaticamente.
- A rotina exige a master de origem sem alterações para uma aplicação nova;
  não executá-la novamente sobre esta instalação já concluída. Não recriar
  a conta ou alterar sua senha para repetir o ensaio.
- Se realocar configurações no futuro, atualizar também backup/importação
  agendados; não criar cópias editáveis divergentes. Preservar os arquivos de
  retorno e separar uma cópia de backup externa/offline quando disponível.

## Próximas etapas

1.76.0 já integrada e ativa localmente, com 0030 aplicada e PostgreSQL restrito
a localhost. Falta encaminhar o hostname oficial, conferir HTTPS/uso real e
reinício completo. Não repetir instalação da conta/migração nem usar dados
reais como fixture. Tarefas automáticas mantêm suas identidades anteriores.

O Windows atual continua com a limitação de atualizações registrada pelo
usuário; antivírus/Tunnel/conta limitada não substituem suas correções. VPS é
intenção futura, sem contratação ou migração autorizada nesta etapa.
