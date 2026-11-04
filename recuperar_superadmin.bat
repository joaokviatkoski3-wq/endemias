@echo off
setlocal
echo Recuperacao local da conta superadmin.
echo Execute com o botao direito - Executar como administrador.
"C:\ProgramData\EndemiasWeb\python\Scripts\python.exe" -I -B "%~dp0scripts\recuperar_superadmin_windows.py" --usuario joao
pause
