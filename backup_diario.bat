@echo off
chcp 65001 >nul
REM ==========================================
REM  Backup + Limpeza Diária — Endemias
REM  Execute este arquivo diariamente ou
REM  agende no Agendador de Tarefas do Windows
REM ==========================================

echo.
echo ==========================================
echo  Backup e Limpeza — Sistema Endemias
echo ==========================================
echo.

REM Ajuste o caminho do Python se necessário
set PYTHON="C:\Users\SMS - ATT\AppData\Local\Programs\Python\Python38\python.exe"

REM Verificar se Python existe
if not exist %PYTHON% (
    echo ERRO: Python nao encontrado em %PYTHON%
    echo Ajuste o caminho neste arquivo .bat
    pause
    exit /b 1
)

cd /d "%~dp0"

echo [1/3] Criando backup do banco...
%PYTHON% scripts\backup_banco.py --manter 20
if errorlevel 1 (
    echo [ERRO] Falha ao criar backup!
    pause
    exit /b 1
)

echo.
echo [2/3] Limpando arquivos temporários...
%PYTHON% scripts\limpeza_diaria.py --manter-backups 20 --upload-horas 24
if errorlevel 1 (
    echo [AVISO] Limpeza retornou erro, mas backup foi feito.
)

echo.
echo [3/3] Verificando banco...
%PYTHON% -c "import sqlite3; c=sqlite3.connect('endemias.db'); ok=c.execute('PRAGMA integrity_check').fetchone()[0]; print('Integridade do banco:', ok); c.close()"

echo.
echo ==========================================
echo  Concluido! Backup e limpeza finalizados.
echo ==========================================
echo.
pause
