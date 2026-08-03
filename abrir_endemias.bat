@echo off
setlocal
title Endemias
cd /d "%~dp0"

call :servidor_ativo
if not errorlevel 1 goto abrir

rem Tenta iniciar a tarefa automatica instalada no computador servidor.
schtasks /run /tn "Endemias - Servidor" >nul 2>nul
call :aguardar_servidor
if not errorlevel 1 goto abrir

rem Depois da virada, nunca use o fallback SQLite. Solicita elevacao para
rem reiniciar a tarefa PostgreSQL quando o usuario comum nao puder dispara-la.
if exist "C:\ProgramData\Endemias\postgresql.enabled" (
    start "" "%~dp0reiniciar.bat"
    exit /b 0
)

rem Plano de emergencia: inicia pelo metodo manual existente.
start "Servidor Endemias" cmd /c call "%~dp0iniciar.bat"
call :aguardar_servidor
if not errorlevel 1 goto abrir

echo.
echo  Nao foi possivel iniciar o Endemias.
echo  Avise o responsavel pelo sistema.
echo.
pause
exit /b 1

:abrir
start "" http://localhost:5000
exit /b 0

:aguardar_servidor
for /l %%I in (1,1,15) do (
    timeout /t 1 /nobreak >nul
    call :servidor_ativo
    if not errorlevel 1 exit /b 0
)
exit /b 1

:servidor_ativo
python -c "import socket, sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1', 5000)) == 0 else 1)" >nul 2>nul
exit /b %errorlevel%
