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

O configurador cria a tarefa **Endemias - Servidor** no Agendador de Tarefas e o
atalho **Endemias** na área de trabalho pública.

No servidor oficial, a tarefa usa PostgreSQL e o arquivo
`C:\ProgramData\Endemias\postgresql.enabled` impede que o modo SQLite seja
aberto por engano. O configurador protege esse marcador com escrita restrita a
`SYSTEM` e Administradores; usuarios comuns possuem apenas leitura.

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
