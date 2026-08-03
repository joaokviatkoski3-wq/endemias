@echo off
setlocal
title Configurar API Conta Ovos do Endemias
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo  Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

set "SUBSTITUIR="
if exist "C:\ProgramData\Endemias\contaovos.key" (
    echo.
    echo  Ja existe uma credencial Conta Ovos instalada.
    choice /M "Substituir a credencial existente"
    if errorlevel 2 exit /b 1
    set "SUBSTITUIR=-Substituir"
)

echo.
echo  A chave sera solicitada em entrada mascarada.
echo  Depois sera feita uma unica consulta privada, somente leitura.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configurar_credencial_contaovos_system.ps1" %SUBSTITUIR%
if errorlevel 1 goto :falha

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\testar_credencial_contaovos_system.ps1"
if errorlevel 1 goto :falha

echo.
echo  API Conta Ovos configurada e validada em modo somente leitura.
echo.
pause
exit /b 0

:falha
echo.
echo  A configuracao nao foi concluida. Nenhuma chamada de escrita foi feita.
echo.
pause
exit /b 1
