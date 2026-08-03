[CmdletBinding()]
param(
    [ValidateSet("sqlite", "postgresql")]
    [string]$Backend = "sqlite",
    [string]$Database = "",
    [string]$HostName = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 5432,
    [string]$UserName = "endemias_app",
    [ValidateSet("disable", "allow", "prefer", "require", "verify-ca", "verify-full")]
    [string]$SslMode = "prefer",
    [string]$PgPassFile = "C:\ProgramData\Endemias\pgpass.conf",
    [Parameter(Mandatory=$true)]
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$RootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$AppPath = Join-Path $RootDir "app.py"

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python configurado para o servidor nao foi encontrado."
}
if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) {
    throw "app.py nao foi encontrado em $RootDir."
}

$env:ENDEMIAS_DB_BACKEND = $Backend
if ($Backend -eq "postgresql") {
    if (-not $Database) {
        throw "O nome do banco PostgreSQL e obrigatorio."
    }
    if ($Database -notmatch '^[A-Za-z0-9_.-]+$') {
        throw "O nome do banco PostgreSQL contem caracteres nao permitidos."
    }
    if ($HostName -notmatch '^[A-Za-z0-9.:-]+$') {
        throw "O host PostgreSQL contem caracteres nao permitidos."
    }
    if ($UserName -notmatch '^[A-Za-z0-9_.-]+$') {
        throw "O usuario PostgreSQL contem caracteres nao permitidos."
    }
    if (-not (Test-Path -LiteralPath $PgPassFile -PathType Leaf)) {
        throw "Credencial PostgreSQL da conta de servico nao encontrada."
    }
    $env:ENDEMIAS_PG_DATABASE = $Database
    $env:ENDEMIAS_PG_HOST = $HostName
    $env:ENDEMIAS_PG_PORT = [string]$Port
    $env:ENDEMIAS_PG_USER = $UserName
    $env:ENDEMIAS_PG_SSLMODE = $SslMode
    $env:PGPASSFILE = $PgPassFile
}
else {
    Remove-Item Env:ENDEMIAS_PG_DATABASE -ErrorAction SilentlyContinue
    Remove-Item Env:PGPASSFILE -ErrorAction SilentlyContinue
}

& $PythonPath $AppPath
exit $LASTEXITCODE
