# Importação automática Kobo (preparada, não ativada)

A rotina consulta diariamente os envios ao Kobo com `_submission_time` entre
hoje menos 6 dias e hoje (7 datas inclusivas). Consulta cada formulário com
UID configurado, até 5.000 registros. Se o Kobo indicar mais registros ou uma
próxima página, o lote é interrompido sem gravar: faça a importação manual em
intervalos menores. Apenas UUIDs ainda não presentes no banco são processados.

Antes da gravação, a rotina verifica o estado das migrações PostgreSQL e executa
o ETL completo em dry-run. O lote real é uma transação; uma falha o reverte.
Importações manuais continuam disponíveis e disputam um bloqueio transacional
com a automática, de modo que apenas uma grave de cada vez. Falhas de catálogo
ACS são avisos após a gravação, sem desfazer visitas já importadas.

## Ativação acompanhada

Não ative a tarefa sem conferir que a migração 0020 e as demais estão aplicadas,
que os backups estão válidos e que o formulário de Esporotricose está acessível.
Em PowerShell elevado, com credencial PostgreSQL protegida para a conta
autorizada, primeiro execute somente a simulação:

```powershell
$env:PGPASSFILE='C:\ProgramData\Endemias\pgpass.conf'
& 'C:\Users\Geoprocessamento\AppData\Local\Python\bin\python.exe' 'C:\endemias\scripts\importar_kobo_automatico.py' --database endemias --confirmar-leitura 'CONSULTAR KOBO E BANCO SOMENTE LEITURA'
```

Confira as quantidades por formulário e as pendências na página Processar.
Para o piloto assistido, execute uma única gravação:

```powershell
& 'C:\Users\Geoprocessamento\AppData\Local\Python\bin\python.exe' 'C:\endemias\scripts\importar_kobo_automatico.py' --database endemias --aplicar --confirmar-banco endemias
```

Depois de conferir o histórico e os dados importados, instale a tarefa diária
sob SYSTEM. Este comando não executa uma importação imediata:

```powershell
& 'C:\endemias\scripts\configurar_importacao_kobo_automatica.ps1'
```

A tarefa chama `executar_importacao_kobo_automatica.ps1` todos os dias às 12h30,
inclusive fins de semana. `StartWhenAvailable` recupera a tarefa perdida quando
o computador voltar a ligar, mas uma interrupção superior a sete dias requer
conferência manual do intervalo anterior. O histórico fica em Processar,
identificado como `Kobo automático`; o Agendador também registra o último
código de saída. O histórico de importação manual não é apagado.

Para pausar sem excluir a configuração, desative a tarefa
`Endemias - Importacao Kobo 1230` pelo Agendador de Tarefas. Não edite as
credenciais nem rode a rotina automática contra `endemias.db`.
