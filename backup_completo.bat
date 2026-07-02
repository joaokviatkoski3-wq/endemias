@echo off
chcp 65001 >nul
REM ==========================================
REM  Backup completo local - Sistema Endemias
REM  Destino padrao: D:\BackupsEndemias
REM ==========================================

set DESTINO=D:\BackupsEndemias
set MANTER=10

cd /d "%~dp0"

echo.
echo ==========================================
echo  Backup completo - Sistema Endemias
echo ==========================================
echo Destino: %DESTINO%
echo.

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 scripts\backup_completo.py --destino "%DESTINO%" --manter %MANTER%
    goto fim
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python scripts\backup_completo.py --destino "%DESTINO%" --manter %MANTER%
    goto fim
)

echo ERRO: Python nao encontrado no PATH.
echo Instale o Python ou ajuste este arquivo .bat com o caminho correto.
pause
exit /b 1

:fim
if errorlevel 1 (
    echo.
    echo ERRO: Backup completo falhou.
    pause
    exit /b 1
)

echo.
echo Backup completo finalizado.
echo Pasta de destino: %DESTINO%
echo.
pause
