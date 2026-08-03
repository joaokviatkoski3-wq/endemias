[CmdletBinding()]
param(
    [string]$Destino = "C:\ProgramData\Endemias\contaovos.key",
    [switch]$Substituir
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

if (-not (Test-Administrator)) {
    throw "Execute este configurador como administrador."
}

$target = [System.IO.Path]::GetFullPath($Destino)
if ((Test-Path -LiteralPath $target) -and -not $Substituir) {
    throw "A credencial Conta Ovos ja existe. Use -Substituir somente para rotacao planejada."
}

$secureKey = Read-Host "Chave privada da API Conta Ovos" -AsSecureString
$pointer = [IntPtr]::Zero
$plainKey = $null
$temporary = $null
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if (-not $plainKey -or $plainKey -match "[`r`n]") {
        throw "A chave privada Conta Ovos e invalida."
    }

    $directory = Split-Path -Parent $target
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = Join-Path $directory (".contaovos.{0}.tmp" -f [guid]::NewGuid())
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($temporary, $plainKey, $utf8)

    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $systemSid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-18")
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
    $plainKey = $null
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    if ($temporary -and (Test-Path -LiteralPath $temporary)) {
        Remove-Item -LiteralPath $temporary -Force
    }
}

Write-Host "Credencial Conta Ovos instalada para SYSTEM/Administradores."
Write-Host "A chave nao foi exibida, registrada em argumentos ou salva no repositorio."
