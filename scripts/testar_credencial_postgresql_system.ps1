[CmdletBinding()]
param(
    [string]$Database = "endemias",
    [string]$PgPassFile = "C:\ProgramData\Endemias\pgpass.conf",
    [string]$PythonPath = "",
    [string]$OutputPath = "",
    [switch]$Worker
)

$ErrorActionPreference = "Stop"
$RootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$VerifierPath = Join-Path $PSScriptRoot "verificar_postgresql.py"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Find-EndemiasPython {
    $candidates = @(
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

if ($Database -notmatch '^[A-Za-z0-9_.-]+$') {
    throw "O nome do banco PostgreSQL contem caracteres nao permitidos."
}

if ($Worker) {
    if (-not $PythonPath -or -not $OutputPath) {
        throw "Worker SYSTEM sem caminhos obrigatorios."
    }
    $env:PGPASSFILE = $PgPassFile
    Set-Location $RootDir
    $lines = & $PythonPath $VerifierPath `
        --database $Database `
        --somente-leitura 2>&1
    $exitCode = $LASTEXITCODE
    $payload = @{
        database = $Database
        exit_code = $exitCode
        output = @($lines | ForEach-Object { [string]$_ })
        tested_at = [DateTime]::Now.ToString("o")
    } | ConvertTo-Json -Depth 3
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
        Remove-Item `
            -LiteralPath $temporaryOutput `
            -Force `
            -ErrorAction SilentlyContinue
    }
    exit $exitCode
}

if (-not (Test-Administrator)) {
    throw "Execute este teste como administrador."
}
if (-not (Test-Path -LiteralPath $PgPassFile -PathType Leaf)) {
    throw "Credencial SYSTEM nao encontrada em $PgPassFile."
}
if (-not (Test-Path -LiteralPath $VerifierPath -PathType Leaf)) {
    throw "verificar_postgresql.py nao foi encontrado."
}
if (-not $PythonPath) {
    $PythonPath = Find-EndemiasPython
}

$id = [guid]::NewGuid().ToString("N")
$taskName = "Endemias - Teste PostgreSQL $id"
$programDataDir = Split-Path -Parent $PgPassFile
$OutputPath = Join-Path $programDataDir ("validacao_system_{0}.json" -f $id)
$powershellPath = (Get-Process -Id $PID).Path
$arguments = @(
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy Bypass",
    ('-File "{0}"' -f $PSCommandPath),
    "-Worker",
    ('-Database "{0}"' -f $Database),
    ('-PgPassFile "{0}"' -f $PgPassFile),
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
        -ExecutionTimeLimit (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew
    $task = New-ScheduledTask `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Teste temporario da credencial PostgreSQL do Endemias."
    Register-ScheduledTask -TaskName $taskName -InputObject $task | Out-Null
    Start-ScheduledTask -TaskName $taskName

    $deadline = [DateTime]::UtcNow.AddSeconds(45)
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
        throw "A conta SYSTEM nao conseguiu autenticar no PostgreSQL."
    }
    Write-Host "Credencial PostgreSQL validada realmente como SYSTEM."
}
finally {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask `
        -TaskName $taskName `
        -Confirm:$false `
        -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
}
