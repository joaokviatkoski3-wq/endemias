@echo off
setlocal

for %%I in ("%~dp0.") do set "ENDEMIAS_TEST_ROOT=%%~fI"
if /I "%ENDEMIAS_TEST_ROOT%"=="C:\endemias" (
    cls
    echo.
    echo  ==============================================================
    echo  [BLOQUEADO] O testar.bat nunca pode rodar em C:\endemias.
    echo  Essa pasta e a instalacao oficial de producao.
    echo  Execute este arquivo somente dentro de outro worktree.
    echo  ==============================================================
    echo.
    pause
    exit /b 2
)

cd /d "%~dp0"
cls

set "ENDEMIAS_AMBIENTE=teste"
set "ENDEMIAS_PORT=5002"
set "ENDEMIAS_DB_BACKEND=sqlite"
set "ENDEMIAS_INSTANCE_DIR=%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ATENCAO] Python nao encontrado.
    echo  Instale o Python e tente novamente.
    echo.
    pause
    exit /b 1
)

set "ENDEMIAS_DB_PATH=%~dp0endemias.db"
python scripts\validar_banco_teste.py "%ENDEMIAS_DB_PATH%" "C:\endemias\endemias.db" >nul
if errorlevel 1 (
    echo.
    echo  ==============================================================
    echo  [BLOQUEADO] O banco de teste resolve para o SQLite oficial.
    echo  O arquivo C:\endemias\endemias.db e rollback congelado.
    echo  Nenhuma inicializacao ou escrita foi realizada.
    echo  ==============================================================
    echo.
    pause
    exit /b 4
)

set "ENDEMIAS_ANEXOS_DIR=%~dp0anexos"
set "ENDEMIAS_UPLOAD_TEMP=%~dp0uploads_temp"
set "ENDEMIAS_LOG_PATH=%~dp0endemias.log"
set "ENDEMIAS_SECRET_KEY_PATH=%~dp0secret.key"
set "ENDEMIAS_KOBO_CONFIG_PATH=%~dp0kobo_config.json"
set "ENDEMIAS_BACKUP_DIR=%~dp0backups\banco"
set "ENDEMIAS_BACKUP_COMPLETO_DIR=%~dp0backups\completos"

echo.
echo  ==============================================================
echo  *** AMBIENTE DE TESTE - DADOS NAO OFICIAIS ***
echo  Worktree: %ENDEMIAS_TEST_ROOT%
echo  Acesso:   http://localhost:%ENDEMIAS_PORT%
echo  Banco:    %ENDEMIAS_DB_PATH%
echo  ==============================================================
echo.

python -c "import socket, sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1', 5002)) == 0 else 1)" >nul 2>nul
if not errorlevel 1 (
    echo  [ATENCAO] A porta 5002 ja esta em uso.
    echo  Feche o outro ambiente de teste antes de iniciar este worktree.
    echo  Nenhum servidor foi iniciado.
    echo.
    pause
    exit /b 3
)

set "ENDEMIAS_PREPARAR_BANCO="
if exist "%ENDEMIAS_DB_PATH%" (
    python scripts\validar_banco_teste.py --schema "%ENDEMIAS_DB_PATH%" >nul
    if errorlevel 1 (
        echo  [ATENCAO] O banco local existe, mas esta vazio, corrompido ou incompleto.
        echo  Ele sera arquivado nesta pasta antes de preparar um banco valido.
        python scripts\validar_banco_teste.py --arquivar-invalido "%ENDEMIAS_DB_PATH%"
        if errorlevel 1 (
            echo  [ATENCAO] Nao foi possivel arquivar o banco local invalido.
            echo  Nenhum servidor foi iniciado.
            echo.
            pause
            exit /b 5
        )
        set "ENDEMIAS_PREPARAR_BANCO=1"
    )
) else (
    set "ENDEMIAS_PREPARAR_BANCO=1"
)

if defined ENDEMIAS_PREPARAR_BANCO (
    call :preparar_banco
    if errorlevel 1 (
        echo.
        echo  [ATENCAO] Nao foi possivel preparar o banco local de teste.
        echo.
        pause
        exit /b 1
    )
)

if not exist ".deps_ok" (
    echo  Verificando componentes do sistema...
    python -c "import flask, flask_wtf, openpyxl, pandas, docx, werkzeug" >nul 2>nul
    if errorlevel 1 (
        echo  Instalando componentes. Aguarde...
        pip install -r requirements.txt >nul 2>nul
        if errorlevel 1 (
            echo.
            echo  [ATENCAO] Nao foi possivel instalar os componentes.
            echo  Verifique a internet ou avise o responsavel pelo sistema.
            echo.
            pause
            exit /b 1
        )
    )
    echo ok > .deps_ok
    echo.
)

echo  Iniciando o ambiente de teste na porta %ENDEMIAS_PORT%...
echo  Mantenha esta janela aberta enquanto o teste estiver em uso.
echo.
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:5002'"
python app.py

echo.
echo  Ambiente de teste encerrado.
pause
exit /b 0

:preparar_banco
echo  Nenhum banco local existe neste worktree.
echo.
echo  Por padrao sera criado um banco vazio e isolado.
echo  Opcionalmente, voce pode copiar C:\endemias\endemias.db como massa de teste.
echo.
echo  [DADOS REAIS DE SAUDE]
echo  A copia ficara restrita a esta pasta e devera ser apagada quando o
echo  worktree for descartado. O arquivo de origem e somente leitura e nunca
echo  sera alterado por este script.
echo.
choice /C CN /N /M "Copiar a massa real somente para este teste? [C=Copiar/N=Banco vazio]: "
if errorlevel 2 goto banco_vazio

if not exist "C:\endemias\endemias.db" (
    echo  [ATENCAO] A origem C:\endemias\endemias.db nao foi encontrada.
    exit /b 1
)
copy /Y "C:\endemias\endemias.db" "%ENDEMIAS_DB_PATH%" >nul
if errorlevel 1 exit /b 1
echo  Copia local criada. A origem oficial permaneceu inalterada.
exit /b 0

:banco_vazio
echo  Criando banco SQLite vazio neste worktree...
python criar_banco.py
exit /b %ERRORLEVEL%
