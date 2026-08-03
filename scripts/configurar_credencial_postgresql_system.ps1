[CmdletBinding()]
param(
    [string]$HostName = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 5432,
    [Parameter(Mandatory=$true)]
    [string]$Database,
    [string]$UserName = "endemias_app",
    [string]$Destino = "C:\ProgramData\Endemias\pgpass.conf",
    [switch]$Substituir
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

function Escape-PgPassValue {
    param([Parameter(Mandatory=$true)][string]$Value)
    return $Value.Replace("\", "\\").Replace(":", "\:")
}

if (-not (Test-Administrator)) {
    throw "Execute este configurador como administrador."
}
if (-not $Database.Trim()) {
    throw "O nome do banco PostgreSQL e obrigatorio."
}
foreach ($value in @($HostName, $Database, $UserName)) {
    if ($value -match "[`r`n]") {
        throw "Host, banco e usuario nao podem conter quebras de linha."
    }
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

$target = [System.IO.Path]::GetFullPath($Destino)
if ((Test-Path -LiteralPath $target) -and -not $Substituir) {
    throw "A credencial ja existe. Use -Substituir somente para rotacao planejada."
}

$securePassword = Read-Host "Senha PostgreSQL de $UserName" -AsSecureString
$pointer = [IntPtr]::Zero
$plainPassword = $null
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
        $securePassword
    )
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
        $pointer
    )
    if (-not $plainPassword) {
        throw "A senha PostgreSQL nao pode ser vazia."
    }

    $directory = Split-Path -Parent $target
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = Join-Path $directory (".pgpass.{0}.tmp" -f [guid]::NewGuid())
    $line = @(
        (Escape-PgPassValue $HostName),
        (Escape-PgPassValue ([string]$Port)),
        (Escape-PgPassValue $Database),
        (Escape-PgPassValue $UserName),
        (Escape-PgPassValue $plainPassword)
    ) -join ":"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        $temporary,
        $line + [Environment]::NewLine,
        $utf8
    )

    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $systemSid = New-Object System.Security.Principal.SecurityIdentifier(
        "S-1-5-18"
    )
    $administratorsSid = New-Object System.Security.Principal.SecurityIdentifier(
        "S-1-5-32-544"
    )
    foreach ($sid in @($systemSid, $administratorsSid)) {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $sid,
            [System.Security.AccessControl.FileSystemRights]::FullControl,
            [System.Security.AccessControl.AccessControlType]::Allow
        )
        $acl.AddAccessRule($rule)
    }
    $acl.SetOwner($administratorsSid)
    Set-Acl -LiteralPath $temporary -AclObject $acl
    Move-Item -LiteralPath $temporary -Destination $target -Force
    Set-Acl -LiteralPath $target -AclObject $acl
}
finally {
    $plainPassword = $null
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    if ($temporary -and (Test-Path -LiteralPath $temporary)) {
        Remove-Item -LiteralPath $temporary -Force
    }
}

Write-Host "Credencial PostgreSQL instalada para uso exclusivo de SYSTEM/Administradores."
Write-Host "Destino: $target"
Write-Host "A senha nao foi exibida nem gravada em argumentos da tarefa."
