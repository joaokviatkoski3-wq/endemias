@echo off
setlocal
cd /d "%~dp0"
echo Verificacao de infraestrutura: consulta configuracoes e grava relatorio local.
echo Nao altera servicos, banco, usuarios, firewall ou licencas.
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\verificar_tarefa_web.py"
echo.
pause
