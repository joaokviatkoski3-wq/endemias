@echo off
setlocal
title Reiniciar Endemias
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo  Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

echo.
echo  Reiniciando o Sistema Endemias...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\reiniciar_endemias.ps1"
set "RESULTADO=%errorlevel%"

if not "%RESULTADO%"=="0" (
    echo.
    echo  Nao foi possivel reiniciar o sistema.
    echo  Avise o responsavel e informe a mensagem acima.
    echo.
    pause
    exit /b %RESULTADO%
)

echo.
echo  Sistema reiniciado com sucesso.
timeout /t 3 /nobreak >nul
exit /b 0
