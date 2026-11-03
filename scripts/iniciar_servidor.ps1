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
    [string]$PythonPath,
    [ValidateSet("werkzeug", "waitress")]
    [string]$Servidor = "werkzeug",
    [switch]$AcessoExterno,
    [string[]]$AllowedHosts = @(),
    [ValidateRange(4, 64)]
    [int]$Threads = 16,
    [switch]$AcessoLocal,
    [string]$LocalBind = "",
    [ValidateRange(1, 65535)]
    [int]$LocalPort = 5000,
    [ValidateRange(1, 65535)]
    [int]$TunnelPort = 5001,
    [switch]$ValidarSomente
)

$ErrorActionPreference = "Stop"
$RootDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$AppPath = Join-Path $RootDir "app.py"
if ($Servidor -eq "waitress") {
    $AppPath = Join-Path $RootDir "servir.py"
}
if ($AcessoExterno -and ($Servidor -ne "waitress" -or $AllowedHosts.Count -eq 0)) {
    throw "Acesso externo exige Waitress e AllowedHosts explicitos."
}
if ($ValidarSomente -and $Servidor -ne "waitress") {
    throw "ValidarSomente exige Waitress."
}
if ($AcessoLocal -and (-not $AcessoExterno -or -not $LocalBind)) {
    throw "AcessoLocal exige AcessoExterno e LocalBind explicito."
}
if ($AcessoLocal) {
    $env:ENDEMIAS_ACESSO_LOCAL = "1"
    $env:ENDEMIAS_LOCAL_BIND = $LocalBind
    $env:ENDEMIAS_LOCAL_PORT = [string]$LocalPort
    $env:ENDEMIAS_TUNNEL_PORT = [string]$TunnelPort
}
else {
    Remove-Item Env:ENDEMIAS_ACESSO_LOCAL -ErrorAction SilentlyContinue
}
if ($AcessoExterno) {
    $env:ENDEMIAS_ACESSO_EXTERNO = "1"
    $env:ENDEMIAS_ALLOWED_HOSTS = ($AllowedHosts -join ',')
    $env:ENDEMIAS_BIND = "127.0.0.1"
    $env:ENDEMIAS_THREADS = [string]$Threads
}
else {
    Remove-Item Env:ENDEMIAS_ACESSO_EXTERNO -ErrorAction SilentlyContinue
    Remove-Item Env:ENDEMIAS_ALLOWED_HOSTS -ErrorAction SilentlyContinue
}

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

if ($ValidarSomente) {
    & $PythonPath $AppPath --validar
}
else {
    & $PythonPath $AppPath
}
exit $LASTEXITCODE
