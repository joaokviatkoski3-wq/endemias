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

## Alternativa de emergência

Se o atalho não conseguir recuperar o servidor, execute `iniciar.bat`. Essa forma
continua disponível e exige que a janela permaneça aberta.

## Como desfazer

Execute `remover_inicializacao_automatica.bat` como administrador. A tarefa e o
atalho serão removidos, sem apagar o banco de dados ou qualquer arquivo do sistema.

## Verificação rápida

Abra `http://localhost:5000` neste computador. Se a tela de login aparecer, o
servidor está funcionando. Erros internos permanecem registrados em
`C:\endemias\endemias.log`.
