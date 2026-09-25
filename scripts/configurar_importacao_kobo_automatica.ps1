[CmdletBinding()]
param(
    [string]$PythonPath = 'C:\Users\Geoprocessamento\AppData\Local\Python\bin\python.exe',
    [switch]$ValidarSomente
)

$ErrorActionPreference = 'Stop'
$taskName = 'Endemias - Importacao Kobo 1230'
$runner = Join-Path $PSScriptRoot 'executar_importacao_kobo_automatica.ps1'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Python não encontrado.' }
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Executor da tarefa não encontrado.' }
if (-not (Test-Path -LiteralPath 'C:\ProgramData\Endemias\pgpass.conf' -PathType Leaf)) {
    throw 'Credencial PostgreSQL não encontrada.'
}
if ($ValidarSomente) {
    Write-Host 'Arquivos para a tarefa encontrados. Nenhuma tarefa foi criada ou alterada.'
    exit 0
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Execute a instalação da tarefa em um PowerShell como administrador.'
}
$actionArgs = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -PythonPath "{1}"' -f $runner, $PythonPath
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $actionArgs
$trigger = New-ScheduledTaskTrigger -Daily -At '12:30'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $taskPrincipal -Force | Out-Null
Write-Host "Tarefa '$taskName' instalada para 12h30 diariamente."
