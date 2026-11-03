@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Ambiente de desenvolvimento nao encontrado. Avise o responsavel.
    pause
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\piloto_web.py"
pause
