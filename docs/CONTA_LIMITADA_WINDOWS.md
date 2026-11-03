# Servidor local com conta limitada — estado vigente

Aplicado em 03/11/2026 após autorização do usuário, com confirmação HTTP
200/versão 1.75.0 às 16h05 (America/Sao_Paulo). Não é publicação externa.

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
  `scripts/endurecer_web_windows.py --reverter`, executado por administrador,
  restaura tarefa/ACL anteriores após aplicação concluída, confirma acesso
  local e não restaura/apaga o banco automaticamente. Conferir o estado vivo
  antes de um retorno tardio; não sobrescrever mudanças posteriores.
- A rotina exige a master de origem sem alterações para uma aplicação nova;
  não executá-la novamente sobre esta instalação já concluída. Não recriar
  a conta ou alterar sua senha para repetir o ensaio.
- Se realocar configurações no futuro, atualizar também backup/importação
  agendados; não criar cópias editáveis divergentes. Preservar os arquivos de
  retorno e separar uma cópia de backup externa/offline quando disponível.

## Próximas etapas

A preparação 1.76.0 de autenticação/termo/Waitress permanece na worktree,
**não integrada nem ativa**. Ativá-la exige a janela apropriada, migração 0030
aditiva, verificação da escuta PostgreSQL/firewall e piloto Tunnel/HTTPS/cache,
limites e permissões dos usuários. Não repetir migrações já aplicadas, nem
usar os dados reais do LIRAa como fixture. PostgreSQL e tarefas automáticas
permanecem nos seus serviços/identidades anteriores.

O Windows atual continua com a limitação de atualizações registrada pelo
usuário; antivírus/Tunnel/conta limitada não substituem suas correções. VPS é
intenção futura, sem contratação ou migração autorizada nesta etapa.
