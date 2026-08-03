# Inicialização automática do Endemias

## Funcionamento normal

O computador servidor deve permanecer ligado. Depois da configuração inicial, o
Endemias inicia automaticamente cerca de 20 segundos após o Windows ligar.

Para usar o sistema neste computador, dê dois cliques no atalho **Endemias** da
área de trabalho. Nos demais computadores, use o endereço de rede já configurado
no navegador.

Não é necessário abrir a pasta `C:\endemias` nem manter uma janela preta aberta.

## Configuração, feita uma única vez

1. Abra a pasta `C:\endemias`.
2. Execute `configurar_inicializacao_automatica.bat`.
3. Aceite a solicitação de administrador do Windows.
4. Aguarde a mensagem de conclusão.

O configurador oficial registra explicitamente `-Backend postgresql -Database
endemias`, cria a tarefa **Endemias - Servidor** no Agendador de Tarefas e o
atalho **Endemias** na área de trabalho pública. Para um ambiente SQLite de
desenvolvimento, chame o script PowerShell diretamente com `-Backend sqlite`;
não use o `.bat` oficial.

No servidor oficial, a tarefa usa PostgreSQL e o arquivo
`C:\ProgramData\Endemias\postgresql.enabled` impede que o modo SQLite seja
aberto por engano. O configurador protege esse marcador com escrita restrita a
`SYSTEM` e Administradores; usuarios comuns possuem apenas leitura.

## Backups PostgreSQL automaticos

Depois da revisao tecnica do lote de backups, execute como administrador:

```text
C:\endemias\configurar_backup_postgresql.bat
```

O configurador cria duas tarefas independentes, sem reiniciar o servidor:

- **Endemias - Backup PostgreSQL Diario**, todos os dias as 02:00, mantendo 30
  dumps em `D:\BackupsEndemias\backups_banco`;
- **Endemias - Backup Completo PostgreSQL**, aos domingos as 03:00, mantendo 8
  ZIPs em `D:\BackupsEndemias\backups_completos`.

As duas tarefas rodam como `SYSTEM`, usam apenas o caminho do `pgpass.conf` e
nunca colocam a senha nos argumentos. O `.bat` executa ambas imediatamente na
primeira configuracao e so conclui depois de validar catalogo, SHA-256, ZIP e
manifesto. Se o computador estiver desligado no horario, o Agendador usa
**StartWhenAvailable** na proxima oportunidade.

O instalador tambem remove a heranca permissiva antiga das duas pastas de
destino. Somente `SYSTEM` e Administradores recebem acesso aos dumps, metadados
e ZIPs completos. Isso e necessario porque o backup completo inclui dados
reais e configuracoes sensiveis.

Para conferir os arquivos sem conectar ao banco:

```powershell
Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command "cd C:\endemias; python scripts\verificar_backups_postgresql.py"'
```

Para apenas validar a configuracao, sem criar pastas ou tarefas:

```powershell
powershell -ExecutionPolicy Bypass -File `
  scripts\configurar_backup_automatico_postgresql.ps1 `
  -Database endemias -ValidarSomente
```

## Alternativa de emergência

Se o atalho não conseguir recuperar o servidor, use **Reiniciar Endemias** e
aceite a solicitação de administrador. Não execute `iniciar.bat` no servidor
oficial: após a virada para PostgreSQL, esse script recusa o modo SQLite para
evitar que os dois bancos recebam dados diferentes.

## Como desfazer

Execute `remover_inicializacao_automatica.bat` como administrador. A tarefa e o
atalho serão removidos, sem apagar o banco de dados ou qualquer arquivo do sistema.
Esse comando também remove o bloqueio do modo SQLite e, portanto, só deve ser
usado num rollback expressamente autorizado.

## Verificação rápida

Abra `http://localhost:5000` neste computador. Se a tela de login aparecer, o
servidor está funcionando. Erros internos permanecem registrados em
`C:\endemias\endemias.log`.
