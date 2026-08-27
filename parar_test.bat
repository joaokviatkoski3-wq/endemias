@echo off
setlocal
cd /d "%~dp0"
cls

echo.
echo  ==============================================================
echo  ENCERRAR AMBIENTE DE TESTE
echo  Porta reservada: 5002
echo  A producao na porta 5000 nao sera alterada.
echo  ==============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\parar_ambiente_teste.ps1" -Port 5002
set "ENDEMIAS_PARAR_EXIT=%ERRORLEVEL%"

echo.
if "%ENDEMIAS_PARAR_EXIT%"=="0" (
    echo  Operacao concluida.
) else (
    echo  O ambiente nao foi encerrado. Leia a mensagem acima.
)
echo.
pause
exit /b %ENDEMIAS_PARAR_EXIT%
