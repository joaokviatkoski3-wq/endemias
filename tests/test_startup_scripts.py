import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StartupScriptsTests(unittest.TestCase):
    def test_configurador_registra_tarefa_segura_no_inicio_do_windows(self):
        script = (ROOT / "scripts" / "configurar_inicializacao_automatica.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn('$TaskName = "Endemias - Servidor"', script)
        self.assertIn("New-ScheduledTaskTrigger -AtStartup", script)
        self.assertIn('-UserId "SYSTEM"', script)
        self.assertIn("-LogonType ServiceAccount", script)
        self.assertIn("-WorkingDirectory $RootDir", script)
        self.assertIn("-Execute $powershellPath", script)
        self.assertIn("-Argument $actionArguments", script)
        self.assertIn("iniciar_servidor.ps1", script)
        self.assertIn("-RestartCount 5", script)
        self.assertIn("Start-ScheduledTask -TaskName $TaskName", script)

        wrapper = (ROOT / "configurar_inicializacao_automatica.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("-Backend postgresql -Database endemias", wrapper)

    def test_configurador_cria_atalho_e_pode_ser_desfeito(self):
        script = (ROOT / "scripts" / "configurar_inicializacao_automatica.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn('"Endemias.lnk"', script)
        self.assertIn('"Reiniciar Endemias.lnk"', script)
        self.assertIn('$RestartPath = Join-Path $RootDir "reiniciar.bat"', script)
        self.assertIn("Unregister-ScheduledTask", script)
        self.assertIn("Remove-Item -LiteralPath $shortcutPath", script)

    def test_configurador_marca_backend_postgresql_de_forma_atomica(self):
        script = (
            ROOT / "scripts" / "configurar_inicializacao_automatica.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('"Endemias\\postgresql.enabled"', script)
        self.assertIn("function Set-PostgreSQLMarker", script)
        self.assertIn("[System.IO.File]::WriteAllText", script)
        self.assertIn('"S-1-5-18"', script)
        self.assertIn('"S-1-5-32-544"', script)
        self.assertIn('"S-1-5-32-545"', script)
        self.assertIn("ReadAndExecute", script)
        self.assertIn("Set-Acl -LiteralPath $BackendMarkerPath", script)
        self.assertIn("Move-Item `", script)
        self.assertIn('if ($Backend -eq "postgresql")', script)
        self.assertIn("Set-PostgreSQLMarker -Enabled $true", script)
        self.assertIn("Set-PostgreSQLMarker -Enabled $false", script)

    def test_atalho_inteligente_bloqueia_fallback_sqlite_apos_virada(self):
        abrir = (ROOT / "abrir_endemias.bat").read_text(encoding="utf-8")
        iniciar = (ROOT / "iniciar.bat").read_text(encoding="utf-8")

        self.assertIn('schtasks /run /tn "Endemias - Servidor"', abrir)
        self.assertIn("postgresql.enabled", abrir)
        self.assertIn('start "" "%~dp0reiniciar.bat"', abrir)
        self.assertIn('call "%~dp0iniciar.bat"', abrir)
        self.assertIn("http://localhost:5000", abrir)
        self.assertLess(
            abrir.index("postgresql.enabled"),
            abrir.index('call "%~dp0iniciar.bat"'),
        )
        self.assertIn("postgresql.enabled", iniciar)
        self.assertIn("O modo SQLite foi bloqueado", iniciar)

    def test_iniciar_abre_navegador_quando_servidor_ja_esta_ativo(self):
        iniciar = (ROOT / "iniciar.bat").read_text(encoding="utf-8")

        self.assertIn('start "" http://localhost:5000', iniciar)
        self.assertNotIn("O sistema ja parece estar aberto", iniciar)

    def test_testar_isola_worktree_e_recusa_pasta_oficial(self):
        testar = (ROOT / "testar.bat").read_text(encoding="utf-8")

        self.assertIn('if /I "%ENDEMIAS_TEST_ROOT%"=="C:\\endemias"', testar)
        self.assertIn("[BLOQUEADO] O testar.bat nunca pode rodar em C:\\endemias", testar)
        self.assertLess(testar.index("[BLOQUEADO]"), testar.index("python --version"))
        self.assertIn('set "ENDEMIAS_AMBIENTE=teste"', testar)
        self.assertIn('set "ENDEMIAS_PORT=5002"', testar)
        self.assertIn('set "ENDEMIAS_DB_BACKEND=sqlite"', testar)
        for nome in (
            "ENDEMIAS_DB_PATH", "ENDEMIAS_ANEXOS_DIR", "ENDEMIAS_UPLOAD_TEMP",
            "ENDEMIAS_LOG_PATH", "ENDEMIAS_SECRET_KEY_PATH",
            "ENDEMIAS_KOBO_CONFIG_PATH", "ENDEMIAS_BACKUP_DIR",
            "ENDEMIAS_BACKUP_COMPLETO_DIR",
        ):
            self.assertIn(f'set "{nome}=%~dp0', testar)
        self.assertIn("A porta 5002 ja esta em uso", testar)
        self.assertIn("connect_ex(('127.0.0.1', 5002))", testar)

    def test_testar_oferece_massa_real_somente_de_forma_opcional(self):
        testar = (ROOT / "testar.bat").read_text(encoding="utf-8")

        self.assertIn("[DADOS REAIS DE SAUDE]", testar)
        self.assertIn("devera ser apagada quando o", testar)
        self.assertIn("O arquivo de origem e somente leitura", testar)
        self.assertIn('choice /C CN /N /M "Copiar a massa real', testar)
        self.assertIn('copy /Y "C:\\endemias\\endemias.db" "%ENDEMIAS_DB_PATH%"', testar)
        self.assertIn("python criar_banco.py", testar)
        self.assertLess(testar.index("choice /C CN"), testar.index("copy /Y"))

    def test_testar_tem_segunda_barreira_por_identidade_do_banco(self):
        testar = (ROOT / "testar.bat").read_text(encoding="utf-8")

        definicao = 'set "ENDEMIAS_DB_PATH=%~dp0endemias.db"'
        verificacao = (
            'python scripts\\validar_banco_teste.py "%ENDEMIAS_DB_PATH%" '
            '"C:\\endemias\\endemias.db"'
        )
        self.assertIn(verificacao, testar)
        self.assertLess(testar.index(definicao), testar.index(verificacao))
        self.assertLess(testar.index(verificacao), testar.index("ENDEMIAS_ANEXOS_DIR"))
        self.assertIn("O banco de teste resolve para o SQLite oficial", testar)
        self.assertIn("exit /b 4", testar)

    def test_testar_recusa_subir_com_sqlite_incompleto(self):
        testar = (ROOT / "testar.bat").read_text(encoding="utf-8")

        schema = 'python scripts\\validar_banco_teste.py --schema "%ENDEMIAS_DB_PATH%"'
        arquivar = (
            'python scripts\\validar_banco_teste.py --arquivar-invalido '
            '"%ENDEMIAS_DB_PATH%"'
        )
        self.assertIn(schema, testar)
        self.assertIn(arquivar, testar)
        self.assertIn("vazio, corrompido ou incompleto", testar)
        self.assertIn("ENDEMIAS_PREPARAR_BANCO=1", testar)
        self.assertLess(testar.index(schema), testar.index("python app.py"))
        self.assertLess(testar.index(arquivar), testar.index("python app.py"))

    def test_parar_test_encerra_somente_python_app_na_porta_5002(self):
        batch = (ROOT / "parar_test.bat").read_text(encoding="utf-8")
        script = (ROOT / "scripts" / "parar_ambiente_teste.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("parar_ambiente_teste.ps1", batch)
        self.assertIn("-Port 5002", batch)
        self.assertIn("porta 5000 nao sera alterada", batch)
        self.assertIn("if ($Port -eq 5000)", script)
        self.assertIn("Get-NetTCPConnection", script)
        self.assertIn("Get-CimInstance Win32_Process", script)
        self.assertIn("app\\.py", script)
        self.assertIn("Stop-Process -Id", script)
        self.assertNotIn("taskkill", batch.lower())
        self.assertNotIn("taskkill", script.lower())

    def test_reiniciar_valida_processo_e_reabre_tarefa_automatica(self):
        reiniciar_bat = (ROOT / "reiniciar.bat").read_text(encoding="utf-8")
        reiniciar_ps1 = (ROOT / "scripts" / "reiniciar_endemias.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("-Verb RunAs", reiniciar_bat)
        self.assertIn("reiniciar_endemias.ps1", reiniciar_bat)
        self.assertIn('Get-ScheduledTask -TaskName $TaskName', reiniciar_ps1)
        self.assertIn('Stop-ScheduledTask -TaskName $TaskName', reiniciar_ps1)
        self.assertIn('Start-ScheduledTask -TaskName $TaskName', reiniciar_ps1)
        self.assertIn("Get-EndemiasListenerProcess", reiniciar_ps1)
        self.assertIn("$commandLine.IndexOf($AppPath", reiniciar_ps1)
        self.assertIn('Start-Process -FilePath "http://localhost:$Port"', reiniciar_ps1)


if __name__ == "__main__":
    unittest.main()
