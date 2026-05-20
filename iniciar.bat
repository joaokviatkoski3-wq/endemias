@echo off
chcp 65001 >nul
title Endemias — Sistema de Gestão Integrado v3

:: ============================================================
::  INICIAR.BAT — Servidor do Sistema de Endemias
::
::  Este script roda UMA VEZ, em UM computador.
::  Os outros computadores acessam pelo navegador via IP.
::
::  ⚠ NÃO copie este arquivo para outros computadores.
::     Eles devem acessar http://IP_DESTE_PC:5000
:: ============================================================

cd /d "%~dp0"
cls

echo.
echo  ===================================================
echo  ENDEMIAS -- Sistema de Gestao Integrado v3
echo  Setor de Endemias -- Almirante Tamandare-PR
echo  ===================================================
echo.

:: Verificar se Python está disponível
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python não encontrado.
    echo  Instale o Python em python.org e tente novamente.
    pause
    exit /b 1
)

:: Verificar banco de dados
if not exist "endemias.db" (
    echo  [AVISO] Banco de dados não encontrado.
    echo  Criando banco inicial...
    python criar_banco.py
    if errorlevel 1 (
        echo  [ERRO] Falha ao criar o banco de dados.
        pause
        exit /b 1
    )
    echo.
)

:: Instalar dependências se necessário
if not exist ".deps_ok" (
    echo  Verificando dependências Python...
    pip install -r requirements.txt 2>nul
    echo. > .deps_ok
    echo.
)

:: Obter IP local
for /f "tokens=*" %%i in ('python -c "import socket; print(socket.gethostbyname(socket.gethostname()))"') do set LOCAL_IP=%%i

:: Data/hora sem vírgula para o nome do backup
set DATA=%date:~6,4%%date:~3,2%%date:~0,2%
set HORA=%time:~0,2%%time:~3,2%%time:~6,2%
set HORA=%HORA: =0%

echo  ════════════════════════════════════════════════════
echo  Banco de dados : endemias.db (local neste computador)
echo  Acesso na rede : http://%LOCAL_IP%:5000
echo  Este computador: http://localhost:5000
echo  ════════════════════════════════════════════════════
echo.
echo  Pressione Ctrl+C para encerrar o servidor.
echo.

:: Iniciar Flask
python app.py

echo.
echo  Servidor encerrado.
pause
