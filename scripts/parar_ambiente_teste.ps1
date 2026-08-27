param(
    [int]$Port = 5002
)

$ErrorActionPreference = "Stop"

if ($Port -eq 5000) {
    Write-Host "[BLOQUEADO] A porta 5000 pertence ao sistema oficial." -ForegroundColor Red
    exit 10
}

try {
    $connections = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
} catch {
    Write-Host "[ATENCAO] Nao foi possivel consultar a porta $Port." -ForegroundColor Yellow
    exit 2
}

if ($connections.Count -eq 0) {
    Write-Host "[OK] Nenhum ambiente de teste esta aberto na porta $Port." -ForegroundColor Green
    exit 0
}

$processIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
$processes = @()
foreach ($processId in $processIds) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
    if (
        $null -eq $process -or
        $process.Name -notmatch '^python(?:\.exe)?$' -or
        $process.CommandLine -notmatch '(?i)(^|[\\/\s"])app\.py([\s"]|$)'
    ) {
        Write-Host "[BLOQUEADO] A porta $Port pertence a outro programa." -ForegroundColor Red
        Write-Host "Nenhum processo foi encerrado."
        exit 4
    }
    $processes += $process
}

foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -ErrorAction Stop
}

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 100
    $remaining = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
    if ($remaining.Count -eq 0) {
        Write-Host "[OK] Ambiente de teste encerrado. Porta $Port liberada." -ForegroundColor Green
        exit 0
    }
}

Write-Host "[ATENCAO] O processo foi encerrado, mas a porta $Port continua ocupada." -ForegroundColor Yellow
exit 5
