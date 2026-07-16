@echo off
setlocal
title Remover inicializacao automatica do Endemias
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo  Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configurar_inicializacao_automatica.ps1" -Remover
set "RESULTADO=%errorlevel%"
echo.
pause
exit /b %RESULTADO%
