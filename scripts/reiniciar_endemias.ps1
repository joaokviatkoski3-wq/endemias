[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$TaskName = "Endemias - Servidor"
$RootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$AppPath = [System.IO.Path]::GetFullPath((Join-Path $RootDir "app.py"))
$Port = 5000

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-EndemiasPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(700, $false)) {
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

function Wait-EndemiasPort {
    param(
        [Parameter(Mandatory=$true)][bool]$Online,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Test-EndemiasPort) -eq $Online) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

function Get-EndemiasListenerProcess {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return $null
    }
    return Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $listener.OwningProcess)
}

function Stop-VerifiedEndemiasListener {
    $process = Get-EndemiasListenerProcess
    if (-not $process) {
        return
    }

    $commandLine = [string]$process.CommandLine
    if (-not $commandLine -or $commandLine.IndexOf($AppPath, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "A porta $Port esta sendo usada por outro programa. Nenhum processo foi encerrado."
    }

    Write-Host ("Encerrando processo Endemias {0}..." -f $process.ProcessId)
    Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
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
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Python nao encontrado. Execute iniciar.bat para verificar a instalacao."
}

if (-not (Test-Administrator)) {
    throw "Execute o reinicio como administrador."
}
if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) {
    throw "app.py nao foi encontrado em $RootDir."
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "Encerrando a tarefa automatica do Endemias..."
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

if (-not (Wait-EndemiasPort -Online $false -TimeoutSeconds 12)) {
    Stop-VerifiedEndemiasListener
    if (-not (Wait-EndemiasPort -Online $false -TimeoutSeconds 8)) {
        throw "O servidor Endemias nao encerrou dentro do tempo esperado."
    }
}

Write-Host "Iniciando a versao atualizada do Endemias..."
if ($task) {
    Start-ScheduledTask -TaskName $TaskName
}
else {
    $pythonPath = Find-EndemiasPython
    Start-Process `
        -FilePath $pythonPath `
        -ArgumentList ('"{0}"' -f $AppPath) `
        -WorkingDirectory $RootDir `
        -WindowStyle Hidden
}

if (-not (Wait-EndemiasPort -Online $true -TimeoutSeconds 30)) {
    throw "O servidor foi iniciado, mas nao respondeu na porta $Port. Consulte endemias.log."
}

Write-Host "Endemias disponivel em http://localhost:$Port"
Start-Process -FilePath "http://localhost:$Port"
exit 0
