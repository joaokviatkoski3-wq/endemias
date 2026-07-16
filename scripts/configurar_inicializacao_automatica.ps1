[CmdletBinding()]
param(
    [switch]$Remover
)

$ErrorActionPreference = "Stop"
$TaskName = "Endemias - Servidor"
$RootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$AppPath = Join-Path $RootDir "app.py"
$OpenPath = Join-Path $RootDir "abrir_endemias.bat"

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

function Get-ShortcutPath {
    $desktop = [Environment]::GetFolderPath("CommonDesktopDirectory")
    if (-not $desktop) {
        $desktop = [Environment]::GetFolderPath("DesktopDirectory")
    }
    return (Join-Path $desktop "Endemias.lnk")
}

function New-EndemiasShortcut {
    $shortcutPath = Get-ShortcutPath
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $OpenPath
    $shortcut.WorkingDirectory = $RootDir
    $shortcut.Description = "Abrir o Sistema Endemias"
    $favicon = Join-Path $RootDir "static\img\favicon.png"
    if (Test-Path -LiteralPath $favicon) {
        $shortcut.IconLocation = "$favicon,0"
    }
    $shortcut.Save()
    return $shortcutPath
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

    $shortcutPath = Get-ShortcutPath
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
        Write-Host "Atalho removido."
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) {
    throw "app.py nao foi encontrado em $RootDir."
}

$pythonPath = Find-EndemiasPython
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument ('"{0}"' -f $AppPath) `
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
    -Description "Inicia o Sistema Endemias automaticamente com o Windows."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
$shortcutPath = New-EndemiasShortcut

Write-Host "Tarefa '$TaskName' instalada."
Write-Host "Python: $pythonPath"
Write-Host "Atalho: $shortcutPath"

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
