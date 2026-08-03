[CmdletBinding()]
param(
    [string]$KeyFile = "C:\ProgramData\Endemias\contaovos.key",
    [string]$StatusFile = "C:\ProgramData\Endemias\contaovos_status.json",
    [string]$PythonPath = "",
    [string]$OutputPath = "",
    [switch]$Worker
)

$ErrorActionPreference = "Stop"
$RootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$VerifierPath = Join-Path $PSScriptRoot "verificar_contaovos.py"
$Confirmation = "CONSULTAR API CONTA OVOS SEM ALTERAR DADOS"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Find-EndemiasPython {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    )
    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Python do Endemias nao foi encontrado."
}

if ($Worker) {
    if (-not $PythonPath -or -not $OutputPath) {
        throw "Worker SYSTEM sem caminhos obrigatorios."
    }
    $env:ENDEMIAS_CONTAOVOS_KEY_FILE = $KeyFile
    $env:ENDEMIAS_CONTAOVOS_STATUS_FILE = $StatusFile
    Remove-Item Env:ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK -ErrorAction SilentlyContinue
    Set-Location $RootDir
    $lines = & $PythonPath $VerifierPath `
        --confirmar-leitura $Confirmation `
        --status-file $StatusFile `
        --json 2>&1
    $exitCode = $LASTEXITCODE
    $payload = @{
        exit_code = $exitCode
        output = @($lines | ForEach-Object { [string]$_ })
        tested_at = [DateTime]::Now.ToString("o")
    } | ConvertTo-Json -Depth 4
    $temporaryOutput = "$OutputPath.tmp"
    try {
        [System.IO.File]::WriteAllText(
            $temporaryOutput,
            $payload,
            (New-Object System.Text.UTF8Encoding($false))
        )
        [System.IO.File]::Move($temporaryOutput, $OutputPath)
    }
    finally {
        Remove-Item -LiteralPath $temporaryOutput -Force -ErrorAction SilentlyContinue
    }
    exit $exitCode
}

if (-not (Test-Administrator)) {
    throw "Execute este teste como administrador."
}
if (-not (Test-Path -LiteralPath $KeyFile -PathType Leaf)) {
    throw "Credencial Conta Ovos nao encontrada."
}
if (-not (Test-Path -LiteralPath $VerifierPath -PathType Leaf)) {
    throw "verificar_contaovos.py nao foi encontrado."
}
if (-not $PythonPath) {
    $PythonPath = Find-EndemiasPython
}

$id = [guid]::NewGuid().ToString("N")
$taskName = "Endemias - Teste Conta Ovos $id"
$programDataDir = Split-Path -Parent $KeyFile
$OutputPath = Join-Path $programDataDir ("validacao_contaovos_{0}.json" -f $id)
$powershellPath = (Get-Process -Id $PID).Path
$arguments = @(
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy Bypass",
    ('-File "{0}"' -f $PSCommandPath),
    "-Worker",
    ('-KeyFile "{0}"' -f $KeyFile),
    ('-StatusFile "{0}"' -f $StatusFile),
    ('-PythonPath "{0}"' -f $PythonPath),
    ('-OutputPath "{0}"' -f $OutputPath)
) -join " "

try {
    $action = New-ScheduledTaskAction `
        -Execute $powershellPath `
        -Argument $arguments `
        -WorkingDirectory $RootDir
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5)
    $principal = New-ScheduledTaskPrincipal `
        -UserId "SYSTEM" `
        -LogonType ServiceAccount `
        -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
        -MultipleInstances IgnoreNew
    $task = New-ScheduledTask `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Teste temporario somente leitura da API Conta Ovos."
    Register-ScheduledTask -TaskName $taskName -InputObject $task | Out-Null
    Start-ScheduledTask -TaskName $taskName

    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "A tarefa SYSTEM nao produziu resultado dentro do prazo."
        }
        Start-Sleep -Milliseconds 500
    }
    $result = Get-Content -LiteralPath $OutputPath -Raw | ConvertFrom-Json
    foreach ($line in $result.output) {
        Write-Host $line
    }
    if ([int]$result.exit_code -ne 0) {
        throw "A conta SYSTEM nao validou a API privada Conta Ovos."
    }
    Write-Host "Credencial Conta Ovos validada realmente como SYSTEM."
}
finally {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask `
        -TaskName $taskName `
        -Confirm:$false `
        -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
}
