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
        self.assertIn("-Argument ('\"{0}\"' -f $AppPath)", script)
        self.assertIn("-RestartCount 5", script)
        self.assertIn("Start-ScheduledTask -TaskName $TaskName", script)

    def test_configurador_cria_atalho_e_pode_ser_desfeito(self):
        script = (ROOT / "scripts" / "configurar_inicializacao_automatica.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn('"Endemias.lnk"', script)
        self.assertIn('"Reiniciar Endemias.lnk"', script)
        self.assertIn('$RestartPath = Join-Path $RootDir "reiniciar.bat"', script)
        self.assertIn("Unregister-ScheduledTask", script)
        self.assertIn("Remove-Item -LiteralPath $shortcutPath", script)

    def test_atalho_inteligente_tenta_tarefa_e_fallback_manual(self):
        abrir = (ROOT / "abrir_endemias.bat").read_text(encoding="utf-8")

        self.assertIn('schtasks /run /tn "Endemias - Servidor"', abrir)
        self.assertIn('call "%~dp0iniciar.bat"', abrir)
        self.assertIn("http://localhost:5000", abrir)

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
