[CmdletBinding()]
param(
    [switch]$Remover,
    [switch]$ValidarSomente,
    [switch]$ExecutarAgora,
    [string]$Database = "endemias",
    [string]$PgHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$PgPort = 5432,
    [string]$PgUser = "endemias_app",
    [ValidateSet("disable", "allow", "prefer", "require", "verify-ca", "verify-full")]
    [string]$PgSslMode = "prefer",
    [string]$PgPassFile = "C:\ProgramData\Endemias\pgpass.conf",
    [string]$BackupDir = "D:\BackupsEndemias\backups_banco",
    [string]$CompleteDir = "D:\BackupsEndemias\backups_completos",
    [ValidateRange(1, 365)]
    [int]$ManterDiarios = 30,
    [ValidateRange(1, 52)]
    [int]$ManterCompletos = 8,
    [ValidatePattern("^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$HorarioDiario = "02:00",
    [ValidatePattern("^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]
    [string]$HorarioCompleto = "03:00",
    [ValidateSet("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")]
    [string]$DiaCompleto = "Sunday",
    [ValidateRange(1, 240)]
    [int]$AguardarMinutos = 60
)

$ErrorActionPreference = "Stop"
$DailyTaskName = "Endemias - Backup PostgreSQL Diario"
$CompleteTaskName = "Endemias - Backup Completo PostgreSQL"
$RootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$DailyScript = Join-Path $PSScriptRoot "backup_banco.py"
$CompleteScript = Join-Path $PSScriptRoot "backup_completo.py"
$VerifyScript = Join-Path $PSScriptRoot "verificar_backups_postgresql.py"

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
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
    )
    try {
        $candidates += (Get-Command python.exe -ErrorAction Stop).Source
    }
    catch {
        # Os caminhos conhecidos ainda serao verificados.
    }
    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        & $candidate -c "import psycopg2" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Python com o driver PostgreSQL do Endemias nao foi encontrado."
}

function Find-PostgreSQLTool {
    param([Parameter(Mandatory=$true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $root = Join-Path $env:ProgramFiles "PostgreSQL"
    if (Test-Path -LiteralPath $root -PathType Container) {
        $candidate = Get-ChildItem -LiteralPath $root -Directory |
            Where-Object { $_.Name -match '^\d+(\.\d+)*$' } |
            Sort-Object {
                $text = if ($_.Name.Contains(".")) { $_.Name } else { "$($_.Name).0" }
                [version]$text
            } -Descending |
            ForEach-Object { Join-Path $_.FullName ("bin\{0}" -f $Name) } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if ($candidate) {
            return $candidate
        }
    }
    throw "$Name nao foi encontrado."
}

function Resolve-SafePath {
    param([Parameter(Mandatory=$true)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full.Contains('"') -or $full.Contains("`r") -or $full.Contains("`n")) {
        throw "Caminho contem caracteres nao permitidos: $Path"
    }
    return $full
}

function Quote-TaskArgument {
    param([Parameter(Mandatory=$true)][string]$Value)
    if ($Value.Contains('"') -or $Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "Argumento contem caracteres nao permitidos."
    }
    return ('"{0}"' -f $Value)
}

function Set-SecureBackupDirectory {
    param([Parameter(Mandatory=$true)][string]$Path)
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $systemSid = New-Object System.Security.Principal.SecurityIdentifier(
        "S-1-5-18"
    )
    $administratorsSid = New-Object System.Security.Principal.SecurityIdentifier(
        "S-1-5-32-544"
    )
    $inheritance = (
        [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
        [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
    )
    foreach ($sid in @($systemSid, $administratorsSid)) {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $sid,
            [System.Security.AccessControl.FileSystemRights]::FullControl,
            $inheritance,
            [System.Security.AccessControl.PropagationFlags]::None,
            [System.Security.AccessControl.AccessControlType]::Allow
        )
        $acl.AddAccessRule($rule)
    }
    $acl.SetOwner($administratorsSid)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Remove-BackupTasks {
    foreach ($taskName in @($DailyTaskName, $CompleteTaskName)) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($task) {
            Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host "Tarefa removida: $taskName"
        }
    }
}

function Wait-BackupTask {
    param(
        [Parameter(Mandatory=$true)][string]$TaskName,
        [Parameter(Mandatory=$true)][datetime]$StartedAt
    )
    $deadline = (Get-Date).AddMinutes($AguardarMinutos)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
        if (
            $info.LastRunTime -ge $StartedAt.AddSeconds(-2) -and
            $task.State -ne "Running"
        ) {
            if ($info.LastTaskResult -ne 0) {
                throw "A tarefa '$TaskName' falhou com codigo $($info.LastTaskResult)."
            }
            Write-Host "Tarefa concluida: $TaskName"
            return
        }
    }
    throw "Tempo esgotado aguardando a tarefa '$TaskName'."
}

if (-not (Test-Administrator)) {
    throw "Execute este configurador como administrador."
}

if ($Remover) {
    Remove-BackupTasks
    Write-Host "Os arquivos de backup existentes foram preservados."
    exit 0
}

if ($Database -notmatch '^[A-Za-z0-9_.-]+$') {
    throw "O nome do banco PostgreSQL contem caracteres nao permitidos."
}
if ($PgHost -notmatch '^[A-Za-z0-9.:-]+$') {
    throw "O host PostgreSQL contem caracteres nao permitidos."
}
if ($PgUser -notmatch '^[A-Za-z0-9_.-]+$') {
    throw "O usuario PostgreSQL contem caracteres nao permitidos."
}
foreach ($script in @($DailyScript, $CompleteScript, $VerifyScript)) {
    if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
        throw "Script obrigatorio nao encontrado: $script"
    }
}
if (-not (Test-Path -LiteralPath $PgPassFile -PathType Leaf)) {
    throw "Credencial SYSTEM nao encontrada em $PgPassFile."
}

$BackupDir = Resolve-SafePath -Path $BackupDir
$CompleteDir = Resolve-SafePath -Path $CompleteDir
$PgPassFile = Resolve-SafePath -Path $PgPassFile
$pythonPath = Find-EndemiasPython
$dumpPath = Find-PostgreSQLTool -Name "pg_dump.exe"
$restorePath = Find-PostgreSQLTool -Name "pg_restore.exe"
$pgBin = Split-Path -Parent $dumpPath
if (-not [string]::Equals(
    (Split-Path -Parent $restorePath),
    $pgBin,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "pg_dump e pg_restore pertencem a instalacoes PostgreSQL diferentes."
}

$dailyAt = [datetime]::ParseExact(
    $HorarioDiario,
    "HH:mm",
    [Globalization.CultureInfo]::InvariantCulture
)
$completeAt = [datetime]::ParseExact(
    $HorarioCompleto,
    "HH:mm",
    [Globalization.CultureInfo]::InvariantCulture
)

$commonArguments = @(
    "--backend", "postgresql",
    "--database", (Quote-TaskArgument $Database),
    "--host", (Quote-TaskArgument $PgHost),
    "--porta", [string]$PgPort,
    "--usuario", (Quote-TaskArgument $PgUser),
    "--sslmode", (Quote-TaskArgument $PgSslMode),
    "--pgpass-file", (Quote-TaskArgument $PgPassFile),
    "--pg-bin", (Quote-TaskArgument $pgBin)
)
$dailyArguments = @(
    (Quote-TaskArgument $DailyScript)
) + $commonArguments + @(
    "--destino", (Quote-TaskArgument $BackupDir),
    "--prefixo", "endemias",
    "--manter", [string]$ManterDiarios
)
$completeArguments = @(
    (Quote-TaskArgument $CompleteScript)
) + $commonArguments + @(
    "--destino", (Quote-TaskArgument $CompleteDir),
    "--manter", [string]$ManterCompletos
)

Write-Host "Validacao do backup automatico concluida."
Write-Host "Banco: $Database"
Write-Host "Dump diario: $HorarioDiario em $BackupDir"
Write-Host "Backup completo: $DiaCompleto as $HorarioCompleto em $CompleteDir"
Write-Host "Credencial protegida: $PgPassFile"
if ($ValidarSomente) {
    Write-Host "Nenhuma tarefa ou pasta foi criada ou alterada."
    exit 0
}

Set-SecureBackupDirectory -Path $BackupDir
Set-SecureBackupDirectory -Path $CompleteDir

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -MultipleInstances IgnoreNew

$dailyTask = New-ScheduledTask `
    -Action (New-ScheduledTaskAction `
        -Execute $pythonPath `
        -Argument ($dailyArguments -join " ") `
        -WorkingDirectory $RootDir) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $dailyAt) `
    -Principal $principal `
    -Settings $settings `
    -Description "Cria e valida o dump diario do PostgreSQL do Endemias."

$completeTask = New-ScheduledTask `
    -Action (New-ScheduledTaskAction `
        -Execute $pythonPath `
        -Argument ($completeArguments -join " ") `
        -WorkingDirectory $RootDir) `
    -Trigger (New-ScheduledTaskTrigger `
        -Weekly `
        -WeeksInterval 1 `
        -DaysOfWeek $DiaCompleto `
        -At $completeAt) `
    -Principal $principal `
    -Settings $settings `
    -Description "Cria e valida o backup completo semanal PostgreSQL do Endemias."

Register-ScheduledTask -TaskName $DailyTaskName -InputObject $dailyTask -Force | Out-Null
Register-ScheduledTask -TaskName $CompleteTaskName -InputObject $completeTask -Force | Out-Null
Write-Host "Tarefa instalada: $DailyTaskName"
Write-Host "Tarefa instalada: $CompleteTaskName"

if ($ExecutarAgora) {
    $started = Get-Date
    Start-ScheduledTask -TaskName $DailyTaskName
    Wait-BackupTask -TaskName $DailyTaskName -StartedAt $started

    $started = Get-Date
    Start-ScheduledTask -TaskName $CompleteTaskName
    Wait-BackupTask -TaskName $CompleteTaskName -StartedAt $started

    & $pythonPath $VerifyScript `
        --backup-dir $BackupDir `
        --completo-dir $CompleteDir `
        --database $Database `
        --pg-bin $pgBin
    if ($LASTEXITCODE -ne 0) {
        throw "Os arquivos foram criados, mas a verificacao final falhou."
    }
}

Write-Host "Backup automatico PostgreSQL configurado."
