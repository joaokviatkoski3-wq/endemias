@echo off
title Endemias - Ambiente de Revisao

rem ============================================================
rem  INICIAR.BAT - Servidor do Sistema de Endemias
rem
rem  Este script deve rodar em apenas UM computador.
rem  Os outros computadores acessam pelo navegador usando o IP
rem  mostrado nesta tela.
rem ============================================================

cd /d "%~dp0"
cls

rem Ambiente completamente separado da instalacao oficial em C:\endemias.
set "ENDEMIAS_PORT=5002"
set "ENDEMIAS_DB_BACKEND=sqlite"
set "ENDEMIAS_DB_PATH=%~dp0endemias.db"
set "ENDEMIAS_ANEXOS_DIR=%~dp0anexos"
set "ENDEMIAS_UPLOAD_TEMP=%~dp0uploads_temp"
set "ENDEMIAS_LOG_PATH=%~dp0endemias.log"
set "ENDEMIAS_SECRET_KEY_PATH=%~dp0secret.key"
set "ENDEMIAS_KOBO_CONFIG_PATH=%~dp0kobo_config.json"
set "ENDEMIAS_BACKUP_DIR=%~dp0backups\banco"
set "ENDEMIAS_BACKUP_COMPLETO_DIR=%~dp0backups\completos"

set "APP_VERSION_LABEL=Endemias"
for /f "usebackq delims=" %%V in (`python -c "from app_core.version import APP_VERSION_LABEL; print(APP_VERSION_LABEL)" 2^>nul`) do set "APP_VERSION_LABEL=%%V"
title %APP_VERSION_LABEL%

echo.
echo  ===================================================
echo  ENDEMIAS - Sistema de Gestao Integrado
echo  %APP_VERSION_LABEL%
echo  AMBIENTE DE REVISAO - DADOS DE TESTE
echo  Setor de Endemias - Almirante Tamandare-PR
echo  ===================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ATENCAO] Python nao encontrado.
    echo  Instale o Python e tente novamente.
    echo.
    pause
    exit /b 1
)

if not exist "%ENDEMIAS_DB_PATH%" (
    echo  Banco de revisao nao encontrado.
    echo  Criando banco de teste inicial...
    python criar_banco.py
    if errorlevel 1 (
        echo.
        echo  [ATENCAO] Nao foi possivel criar o banco de dados.
        echo  Avise o responsavel pelo sistema.
        echo.
        pause
        exit /b 1
    )
    echo.
)

if not exist ".deps_ok" (
    echo  Verificando componentes do sistema...
    python -c "import flask, flask_wtf, openpyxl, pandas, docx, werkzeug" >nul 2>nul
    if errorlevel 1 (
        echo  Instalando componentes. Aguarde...
        pip install -r requirements.txt >nul 2>nul
        if errorlevel 1 (
            echo.
            echo  [ATENCAO] Nao foi possivel instalar os componentes do sistema.
            echo  Verifique a internet ou avise o responsavel pelo sistema.
            echo.
            pause
            exit /b 1
        )
    )
    echo ok > .deps_ok
    echo.
)

python -c "import socket, sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', int('%ENDEMIAS_PORT%'))) == 0 else 1)" >nul 2>nul
if not errorlevel 1 (
    echo  O ambiente de revisao ja esta aberto. Abrindo no navegador...
    start "" http://localhost:%ENDEMIAS_PORT%
    exit /b 0
)

echo  Iniciando o ambiente de revisao em http://localhost:%ENDEMIAS_PORT% ...
echo.
echo  Mantenha esta janela aberta enquanto o sistema estiver em uso.
echo.

python app.py

echo.
echo  Sistema encerrado.
pause
