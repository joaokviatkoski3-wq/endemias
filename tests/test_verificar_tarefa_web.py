import json
import unittest
from scripts.verificar_tarefa_web import resumir_tarefa


class VerificarTarefaTests(unittest.TestCase):
    def test_resumo_nao_inclui_argumentos_ou_credenciais(self):
        xml = '''<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <Principals><Principal><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
          <Actions><Exec><Command>powershell.exe</Command><Arguments>-File iniciar_servidor.ps1 -Backend postgresql -Database endemias -Token SEGREDO-FICTICIO -Password NAO-EXPORTAR</Arguments></Exec></Actions>
        </Task>'''
        summary = resumir_tarefa(xml)
        self.assertEqual(summary['identidade'], 'S-1-5-18')
        self.assertTrue(summary['acoes'][0]['banco_oficial'])
        self.assertNotIn('SEGREDO-FICTICIO', json.dumps(summary))
        self.assertNotIn('NAO-EXPORTAR', json.dumps(summary))
