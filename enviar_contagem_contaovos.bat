@echo off
setlocal
title Enviar uma contagem ao Conta Ovos
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo  Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

set "PGPASSFILE=C:\ProgramData\Endemias\pgpass.conf"
echo.
echo  FILA CONTA OVOS - ENVIO UNITARIO SUPERVISIONADO
echo  A operacao abaixo pode criar uma leitura irreversivel no Conta Ovos.
echo  Nenhuma exclusao ou correcao remota e automatica.
echo.
python scripts\enviar_contagem_contaovos.py ^
  --database endemias ^
  --interativo
if errorlevel 1 goto :falha

echo.
echo  Operacao concluida. Confira a mensagem de confirmacao acima.
echo.
pause
exit /b 0

:falha
echo.
echo  A operacao nao foi concluida. Nao repita se o resultado foi informado como incerto.
echo.
pause
exit /b 1
