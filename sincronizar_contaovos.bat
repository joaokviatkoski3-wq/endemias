@echo off
setlocal
title Sincronizar contagens Conta Ovos
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo  Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

set "PGPASSFILE=C:\ProgramData\Endemias\pgpass.conf"
for /f %%Y in ('powershell -NoProfile -Command "(Get-Date).Year"') do set "ANO_ATUAL=%%Y"
for /f %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "HOJE=%%D"
for /f %%D in ('powershell -NoProfile -Command "Get-Date (Get-Date).AddDays(-45) -Format yyyy-MM-dd"') do set "ROTINA_INICIAL=%%D"
set "DATA_INICIAL=%ROTINA_INICIAL%"
set "DATA_FINAL=%HOJE%"
set "MODO_PERIODO=--max-paginas 100"

echo.
echo  Este processo faz somente consultas GET na API Conta Ovos.
echo  [1] Rotina: ultimos 45 dias, com sobreposicao segura.
echo  [2] Reconciliacao: ano corrente inteiro, mais demorada.
echo.
choice /C 12 /N /M "Escolha 1 ou 2: "
if errorlevel 2 (
    set "DATA_INICIAL=%ANO_ATUAL%-01-01"
    set "MODO_PERIODO=--dividir-por-mes"
)

echo.
echo  Primeiro sera conferido o periodo %DATA_INICIAL% a %DATA_FINAL%.
echo  Nenhum dado local sera alterado durante essa conferencia.
echo.

python scripts\sincronizar_contagens_contaovos.py ^
  --database endemias ^
  --data-inicial %DATA_INICIAL% ^
  --data-final %DATA_FINAL% ^
  %MODO_PERIODO% ^
  --confirmar-leitura "CONSULTAR CONTAGENS CONTA OVOS SOMENTE LEITURA"
if errorlevel 1 goto :falha

echo.
choice /M "Atualizar o historico local com os registros conferidos"
if errorlevel 2 exit /b 1

python scripts\sincronizar_contagens_contaovos.py ^
  --database endemias ^
  --data-inicial %DATA_INICIAL% ^
  --data-final %DATA_FINAL% ^
  %MODO_PERIODO% ^
  --aplicar ^
  --confirmar-leitura "CONSULTAR CONTAGENS CONTA OVOS SOMENTE LEITURA" ^
  --autorizar-atualizacao-local "ATUALIZAR HISTORICO LOCAL CONTA OVOS" ^
  --confirmar-banco endemias
if errorlevel 1 goto :falha

echo.
echo  Sincronizacao local concluida. Nenhum POST foi enviado ao Conta Ovos.
echo.
pause
exit /b 0

:falha
echo.
echo  A sincronizacao nao foi concluida. Verifique a mensagem acima.
echo  Nenhum POST foi enviado ao Conta Ovos.
echo.
pause
exit /b 1
