@echo off
setlocal
cd /d "%~dp0"
echo Protecao do servidor local com conta limitada.
echo Requer administrador. Preserva a versao atual e nao publica na internet.
echo Cria backup previo e testa a nova identidade antes de substituir a tarefa.
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\endurecer_web_windows.py" --aplicar
set "RESULTADO=%errorlevel%"
echo.
echo Resultado: C:\ProgramData\EndemiasWeb\resultado.json
echo Se falhar antes da preparacao: C:\ProgramData\EndemiasWeb\falha-preparacao.json
pause
exit /b %RESULTADO%
