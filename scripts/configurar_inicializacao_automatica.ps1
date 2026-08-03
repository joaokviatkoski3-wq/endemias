[CmdletBinding()]
param(
    [switch]$Remover,
    [ValidateSet("sqlite", "postgresql")]
    [string]$Backend = "sqlite",
    [string]$Database = "",
    [string]$PgHost = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$PgPort = 5432,
    [string]$PgUser = "endemias_app",
    [ValidateSet("disable", "allow", "prefer", "require", "verify-ca", "verify-full")]
    [string]$PgSslMode = "prefer",
    [string]$PgPassFile = "C:\ProgramData\Endemias\pgpass.conf",
    [switch]$NaoIniciar,
    [switch]$ValidarSomente
)

$ErrorActionPreference = "Stop"
$TaskName = "Endemias - Servidor"
$RootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$AppPath = Join-Path $RootDir "app.py"
$LauncherPath = Join-Path $PSScriptRoot "iniciar_servidor.ps1"
$OpenPath = Join-Path $RootDir "abrir_endemias.bat"
$RestartPath = Join-Path $RootDir "reiniciar.bat"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-EndemiasPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect("127.0.0.1", 5000, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(1000, $false)) {
            return $false
        }
        $client.EndConnect($result)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Find-EndemiasPython {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
    )

    try {
        $command = Get-Command python.exe -ErrorAction Stop
        $candidates += $command.Source
    }
    catch {
        # Os caminhos conhecidos ainda serao verificados.
    }

    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        & $candidate -c "import flask, flask_wtf, pandas, openpyxl" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "Python com os componentes do Endemias nao foi encontrado. Execute iniciar.bat antes de configurar."
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
                $versionText = if ($_.Name.Contains(".")) {
                    $_.Name
                }
                else {
                    "$($_.Name).0"
                }
                [version]$versionText
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

function Get-ShortcutPath {
    param([Parameter(Mandatory=$true)][string]$FileName)
    $desktop = [Environment]::GetFolderPath("CommonDesktopDirectory")
    if (-not $desktop) {
        $desktop = [Environment]::GetFolderPath("DesktopDirectory")
    }
    return (Join-Path $desktop $FileName)
}

function New-EndemiasShortcut {
    param(
        [Parameter(Mandatory=$true)][string]$FileName,
        [Parameter(Mandatory=$true)][string]$TargetPath,
        [Parameter(Mandatory=$true)][string]$Description
    )

    $shortcutPath = Get-ShortcutPath -FileName $FileName
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $RootDir
    $shortcut.Description = $Description
    $favicon = Join-Path $RootDir "static\img\favicon.png"
    if (Test-Path -LiteralPath $favicon) {
        $shortcut.IconLocation = "$favicon,0"
    }
    $shortcut.Save()
    return $shortcutPath
}

function New-EndemiasShortcuts {
    return @(
        (New-EndemiasShortcut -FileName "Endemias.lnk" -TargetPath $OpenPath -Description "Abrir o Sistema Endemias"),
        (New-EndemiasShortcut -FileName "Reiniciar Endemias.lnk" -TargetPath $RestartPath -Description "Reiniciar o servidor do Sistema Endemias")
    )
}

if (-not (Test-Administrator)) {
    throw "Execute este configurador como administrador."
}

if ($Remover) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Tarefa automatica removida."
    }
    else {
        Write-Host "A tarefa automatica nao estava instalada."
    }

    foreach ($shortcutName in @("Endemias.lnk", "Reiniciar Endemias.lnk")) {
        $shortcutPath = Get-ShortcutPath -FileName $shortcutName
        if (Test-Path -LiteralPath $shortcutPath) {
            Remove-Item -LiteralPath $shortcutPath -Force
            Write-Host "Atalho removido: $shortcutPath"
        }
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) {
    throw "app.py nao foi encontrado em $RootDir."
}
if (-not (Test-Path -LiteralPath $LauncherPath -PathType Leaf)) {
    throw "iniciar_servidor.ps1 nao foi encontrado em $PSScriptRoot."
}
if ($Backend -eq "postgresql") {
    if (-not $Database.Trim()) {
        throw "Informe -Database para configurar o backend PostgreSQL."
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
    if (-not (Test-Path -LiteralPath $PgPassFile -PathType Leaf)) {
        throw "Credencial SYSTEM nao encontrada em $PgPassFile."
    }
    $null = Find-PostgreSQLTool -Name "pg_dump.exe"
    $null = Find-PostgreSQLTool -Name "pg_restore.exe"
}

$pythonPath = Find-EndemiasPython
$powershellPath = (Get-Process -Id $PID).Path
$actionArguments = @(
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy Bypass",
    ('-File "{0}"' -f $LauncherPath),
    ('-Backend "{0}"' -f $Backend),
    ('-Database "{0}"' -f $Database),
    ('-HostName "{0}"' -f $PgHost),
    ('-Port {0}' -f $PgPort),
    ('-UserName "{0}"' -f $PgUser),
    ('-SslMode "{0}"' -f $PgSslMode),
    ('-PgPassFile "{0}"' -f $PgPassFile),
    ('-PythonPath "{0}"' -f $pythonPath)
) -join " "

Write-Host "Validacao operacional concluida."
Write-Host "Backend planejado: $Backend"
if ($Backend -eq "postgresql") {
    Write-Host "Banco planejado: $Database"
    Write-Host "Credencial protegida: $PgPassFile"
}
if ($ValidarSomente) {
    Write-Host "Nenhuma tarefa foi criada ou alterada."
    exit 0
}

$action = New-ScheduledTaskAction `
    -Execute $powershellPath `
    -Argument $actionArguments `
    -WorkingDirectory $RootDir

$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = "PT20S"

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Inicia o Sistema Endemias automaticamente com backend $Backend."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
$shortcutPaths = New-EndemiasShortcuts

Write-Host "Tarefa '$TaskName' instalada."
Write-Host "Python: $pythonPath"
Write-Host "Backend: $Backend"
foreach ($shortcutPath in $shortcutPaths) {
    Write-Host "Atalho: $shortcutPath"
}

if ($NaoIniciar) {
    Write-Host "A tarefa foi preparada, mas nao iniciada."
    exit 0
}

if (-not (Test-EndemiasPort)) {
    Start-ScheduledTask -TaskName $TaskName
    $ready = $false
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-EndemiasPort) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        throw "A tarefa foi instalada, mas o servidor nao respondeu na porta 5000. Consulte endemias.log."
    }
}

Write-Host "Endemias disponivel em http://localhost:5000"
