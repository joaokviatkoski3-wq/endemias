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
& $PythonPath $scriptPath --database endemias --aplicar --confirmar-banco endemias
exit $LASTEXITCODE
