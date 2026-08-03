@echo off
setlocal
title Configurar backups PostgreSQL do Endemias
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo  Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

echo.
echo  Configurando backup diario e backup completo semanal...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configurar_backup_automatico_postgresql.ps1" -Database endemias -ExecutarAgora
set "RESULTADO=%errorlevel%"

echo.
if "%RESULTADO%"=="0" (
    echo  Backups PostgreSQL configurados e validados com sucesso.
) else (
    echo  A configuracao nao foi concluida. Avise o responsavel pelo sistema.
)
echo.
pause
exit /b %RESULTADO%
