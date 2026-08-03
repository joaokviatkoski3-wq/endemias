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
