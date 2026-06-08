@echo off
title Endemias - Sistema de Gestao Integrado v3

rem ============================================================
rem  INICIAR.BAT - Servidor do Sistema de Endemias
rem
rem  Este script deve rodar em apenas UM computador.
rem  Os outros computadores acessam pelo navegador usando o IP
rem  mostrado nesta tela.
rem ============================================================

cd /d "%~dp0"
cls

echo.
echo  ===================================================
echo  ENDEMIAS - Sistema de Gestao Integrado v3
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

if not exist "endemias.db" (
    echo  Banco de dados nao encontrado.
    echo  Criando banco inicial...
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

python -c "import socket, sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', 5000)) == 0 else 1)" >nul 2>nul
if not errorlevel 1 (
    echo  O sistema ja parece estar aberto neste computador.
    echo  Use o navegador em: http://localhost:5000
    echo.
    pause
    exit /b 0
)

echo  Iniciando o sistema...
echo.
echo  Mantenha esta janela aberta enquanto o sistema estiver em uso.
echo.

python app.py

echo.
echo  Sistema encerrado.
pause
