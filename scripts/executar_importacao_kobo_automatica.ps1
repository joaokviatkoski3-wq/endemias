[CmdletBinding()]
param(
    [string]$PythonPath = 'C:\Users\Geoprocessamento\AppData\Local\Python\bin\python.exe',
    [string]$PgPassFile = 'C:\ProgramData\Endemias\pgpass.conf'
)

$ErrorActionPreference = 'Stop'
$rootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$scriptPath = Join-Path $rootDir 'scripts\importar_kobo_automatico.py'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Python da tarefa não encontrado.' }
if (-not (Test-Path -LiteralPath $PgPassFile -PathType Leaf)) { throw 'Credencial PostgreSQL da tarefa não encontrada.' }
$env:PGPASSFILE = $PgPassFile
$env:ENDEMIAS_PG_APPLICATION_NAME = 'endemias_kobo_automatico'
$contextPath = 'C:\ProgramData\EndemiasWeb\config.json'
$dividido = $false
if (Test-Path -LiteralPath $contextPath -PathType Leaf) {
    $context = Get-Content -LiteralPath $contextPath -Raw | ConvertFrom-Json
    $dividido = $context.env.ENDEMIAS_SETORES_ENABLED -eq '1'
}
if ($dividido) {
    if (-not (Test-Path -LiteralPath (Join-Path $rootDir 'kobo_ambiental.json') -PathType Leaf)) {
        throw 'Configuracao Ambiental ausente; importacao automatica recusada.'
    }
    & $PythonPath $scriptPath --database endemias --aplicar --confirmar-banco endemias --setor endemias
    $endCode = $LASTEXITCODE
    & $PythonPath $scriptPath --database endemias --aplicar --confirmar-banco endemias --setor ambiental
    $ambientalCode = $LASTEXITCODE
    if ($endCode -ne 0 -or $ambientalCode -ne 0) { exit 1 }
    exit 0
}
& $PythonPath $scriptPath --database endemias --aplicar --confirmar-banco endemias
exit $LASTEXITCODE
