"""Executa apenas copias temporarias com Python ficticio, sem conectar ao banco."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name=='nt','Executor especifico de Windows')
class ExecutorKoboSetoresTests(unittest.TestCase):
    def run_example(self, divided, end_failure=False):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);scripts=base/'scripts';scripts.mkdir()
            context=base/'contexto-ficticio.json'
            context.write_text(json.dumps({'env':{'ENDEMIAS_SETORES_ENABLED':'1' if divided else '0'}}),encoding='utf-8')
            runner=(ROOT/'scripts/executar_importacao_kobo_automatica.ps1').read_text(encoding='utf-8')
            runner=runner.replace("'C:\\ProgramData\\EndemiasWeb\\config.json'", "'"+str(context)+"'")
            path=scripts/'runner.ps1';path.write_text(runner,encoding='utf-8-sig')
            (base/'pgpass-ficticio.conf').write_text('APENAS-FICTICIO',encoding='utf-8')
            (base/'kobo_ambiental.json').write_text('{}',encoding='utf-8')
            code='''import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with (root/'chamadas.jsonl').open('a',encoding='utf-8') as out:out.write(json.dumps(sys.argv[1:])+'\\n')
'''
            if end_failure:code+="raise SystemExit(7 if '--setor' in sys.argv and sys.argv[-1]=='endemias' else 0)\n"
            (scripts/'importar_kobo_automatico.py').write_text(code,encoding='utf-8')
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                '-File',str(path),'-PythonPath',sys.executable,'-PgPassFile',str(base/'pgpass-ficticio.conf')],capture_output=True,timeout=30)
            calls=[json.loads(line) for line in (base/'chamadas.jsonl').read_text(encoding='utf-8').splitlines()]
            return result.returncode,calls

    def test_agendamento_legado_continua_com_uma_chamada(self):
        code,calls=self.run_example(False)
        self.assertEqual(code,0);self.assertEqual(len(calls),1)
        self.assertNotIn('--setor',calls[0])

    def test_agendamento_dividido_chama_cada_setor_com_selecao_explicita(self):
        code,calls=self.run_example(True)
        self.assertEqual(code,0);self.assertEqual(len(calls),2)
        self.assertEqual([c[-2:] for c in calls],[['--setor','endemias'],['--setor','ambiental']])
        self.assertTrue(all('--confirmar-banco' in c for c in calls))

    def test_falha_em_endemias_nao_impede_ambiental_e_falha_global_e_visivel(self):
        code,calls=self.run_example(True,end_failure=True)
        self.assertEqual(code,1);self.assertEqual(len(calls),2)
        self.assertEqual(calls[-1][-1],'ambiental')
