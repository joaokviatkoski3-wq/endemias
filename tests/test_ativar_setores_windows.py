import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import tempfile
from contextlib import ExitStack

from scripts import ativar_setores_windows as installer


class InstalacaoSetoresTests(unittest.TestCase):
    def original(self):
        return {'version':'1.80.0','root':str(installer.OFFICIAL),'server':'waitress','probe_only':False,
            'sid':'SID-FICTICIO','read_files':['ARQUIVO-FICTICIO'],'write_dirs':['PASTA-FICTICIA'],
            'env':{'ENDEMIAS_DB_BACKEND':'postgresql','ENDEMIAS_PG_DATABASE':'endemias',
                'ENDEMIAS_PG_HOST':'127.0.0.1','ENDEMIAS_PG_PORT':'5432',
                'ENDEMIAS_ALLOWED_HOSTS':'endemias.vsatt.com.br','ENDEMIAS_LOCAL_BIND':'192.168.1.175',
                'ENDEMIAS_LOCAL_PORT':'5000','ENDEMIAS_TUNNEL_PORT':'5001','OUTRO_SEGREDO':'FICTICIO'}}

    def test_proposta_preserva_identidade_ambiente_e_nao_altera_origem(self):
        original=self.original();before=copy.deepcopy(original)
        result=installer.proposed_config(original)
        self.assertEqual(original,before)
        self.assertEqual(result['sid'],before['sid'])
        self.assertEqual(result['write_dirs'],before['write_dirs'])
        for name,value in before['env'].items():self.assertEqual(result['env'][name],value)
        self.assertEqual(set(result['env'])-set(before['env']),{
            'ENDEMIAS_SETORES_ENABLED','ENDEMIAS_DOMINIO_BASE','ENDEMIAS_AMBIENTAL_LOCAL_PORT'})
        self.assertEqual(result['read_files'][:-1],before['read_files'])
        self.assertTrue(result['read_files'][-1].endswith('kobo_ambiental.json'))

    def test_origem_versao_bind_ou_hostname_inesperados_sao_recusados(self):
        for key,value in [('version','1.79.0'),('root','C:\\outro'),('server','werkzeug'),('probe_only',True)]:
            c=self.original();c[key]=value
            with self.assertRaises(ValueError):installer.proposed_config(c)
        for key,value in [('ENDEMIAS_PG_DATABASE','outro'),('ENDEMIAS_ALLOWED_HOSTS','outro.example'),
            ('ENDEMIAS_LOCAL_BIND','0.0.0.0'),('ENDEMIAS_LOCAL_BIND','8.8.8.8'),('ENDEMIAS_LOCAL_BIND','127.0.0.1'),
            ('ENDEMIAS_LOCAL_PORT','5001'),('ENDEMIAS_KOBO_CONFIG_PATH','C:\\outro\\kobo_config.json')]:
            c=self.original();c['env'][key]=value
            with self.assertRaises(ValueError):installer.proposed_config(c)

    def test_kobo_sem_token_impresso_e_sem_perda_de_formularios(self):
        original={'server_url':'https://kobo.invalid','api_token':'TOKEN-SOMENTE-FICTICIO',
            'assets':{'TB':'uid-end','ESPOROTRICOSE':'uid-esp','AMOSTRA_ANIMAIS':'uid-am'},'last_sync':{'TB':'antes','ESPOROTRICOSE':'antes'}}
        before=copy.deepcopy(original)
        result=installer.divided_kobo(original)
        self.assertEqual(original,before)
        merged={**result['endemias']['assets'],**result['ambiental']['assets']}
        self.assertEqual(merged,before['assets'])
        self.assertTrue(set(result['endemias']['assets']).isdisjoint(result['ambiental']['assets']))
        for value in result.values():self.assertEqual(value['api_token'],original['api_token'])
        original['assets']['DESCONHECIDO']='preservar'
        with self.assertRaises(ValueError):installer.divided_kobo(original)
        with self.assertRaises(ValueError):installer.divided_kobo({'assets':[]})

    def test_retorno_nao_remove_regra_que_foi_alterada_por_outro_operador(self):
        values=installer.rule_values('192.168.1.175')
        policy=SimpleNamespace(Rules=[SimpleNamespace(**{**values,'RemoteAddresses':'*'})])
        with mock.patch.object(installer,'firewall_policy',return_value=policy):
            with self.assertRaises(ValueError):installer.remove_own_firewall('192.168.1.175')

    def test_prova_da_identidade_limitada_checa_aplicacoes_e_arquivos(self):
        # A prova integrada roda com dados ficticios no ensaio de setores; aqui
        # verifica-se que um arquivo de outro setor e recusado antes de acessar app.
        import tempfile
        from scripts.provar_setores_windows import verificar
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            cfg={'api_token':'FICTICIO','assets':{'ESPOROTRICOSE':'nao_pertence_a_endemias'}}
            (root/'kobo_config.json').write_text(json.dumps(cfg),encoding='utf-8')
            with self.assertRaises(AssertionError):
                verificar({'env':{'ENDEMIAS_SETORES_ENABLED':'1'}},root,None)

    def simulated_install(self, fail_probe=False):
        from app_core import postgresql_migrations,backup_completo
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        base=Path(tmp.name);official=base/'official';home=base/'home';source=base/'candidate'
        for p in (official,home,source,official/'scripts',source/'app_core',source/'scripts'):p.mkdir(exist_ok=True)
        old='a'*40;new='b'*40;head=[old];calls=[]
        original=self.original();original['root']=str(official)
        original['env']['ENDEMIAS_KOBO_CONFIG_PATH']=str(official/'kobo_config.json')
        original['env']['ENDEMIAS_BACKUP_COMPLETO_DIR']=str(base/'backups')
        original['env']['ENDEMIAS_ANEXOS_DIR']=str(official/'anexos')
        original['env']['ENDEMIAS_LOCAL_BIND']='192.168.1.175'
        kobo={'server_url':'https://kobo.invalid','api_token':'FICTICIO','assets':{'TB':'uid-end','ESPOROTRICOSE':'uid-amb'}}
        (official/'kobo_config.json').write_text(json.dumps(kobo),encoding='utf-8')
        for name in ('secret.key','config.json','endemias.db'):(official/name).write_bytes(b'FICTICIO-IMUTAVEL')
        (home/'config.json').write_text(json.dumps(original),encoding='utf-8')
        (home/'servico_web_windows.py').write_bytes(b'bootstrap-anterior')
        (official/'scripts/servico_web_windows.py').write_bytes(b'bootstrap-novo')
        (source/'app_core/version.py').write_text('APP_VERSION = "2.0.0-rc.1"\n',encoding='utf-8')
        archive=base/'ficticio.zip';archive.write_bytes(b'FICTICIO')
        task=SimpleNamespace(State=4,Definition=SimpleNamespace(Principal=SimpleNamespace(UserId='FICTICIO',RunLevel=0)))
        task.Stop=lambda _:setattr(task,'State',0)
        task.Run=lambda _:setattr(task,'State',4)
        auto=SimpleNamespace(Enabled=True,State=3)
        win=mock.MagicMock();win.folder.GetTask.return_value=task
        win.sec.LookupAccountName.return_value=('SID-FICTICIO',None,None)
        win.sec.ConvertSidToStringSid.return_value='SID-FICTICIO'
        def fake_git(*args):
            calls.append(args)
            if args==('rev-parse','HEAD'):return head[0]
            if args==('branch','--show-current'):return 'master'
            if args[:2]==('merge','--ff-only'):head[0]=new
            if args and args[0]=='commit':head[0]=old
            return ''
        with ExitStack() as stack:
            for key,value in [('OFFICIAL',official),('HOME',home),('SOURCE',source)]:stack.enter_context(mock.patch.object(installer,key,value))
            stack.enter_context(mock.patch.object(installer.ctypes.windll.shell32,'IsUserAnAdmin',return_value=1))
            stack.enter_context(mock.patch.object(installer,'git',side_effect=fake_git))
            stack.enter_context(mock.patch.object(installer.subprocess,'check_output',side_effect=[new,'']))
            stack.enter_context(mock.patch.object(installer,'connect',return_value=mock.MagicMock()))
            stack.enter_context(mock.patch.object(installer,'Windows',return_value=win))
            stack.enter_context(mock.patch.object(installer,'scheduled_import',return_value=auto))
            stack.enter_context(mock.patch.object(installer,'firewall_policy',return_value=SimpleNamespace(Rules=[])))
            add=stack.enter_context(mock.patch.object(installer,'add_firewall'))
            stack.enter_context(mock.patch.object(installer,'remove_own_firewall'))
            stack.enter_context(mock.patch.object(installer,'wait_closed',return_value=True))
            stack.enter_context(mock.patch.object(installer,'http_login',return_value=True))
            stack.enter_context(mock.patch.object(installer,'origin_portal',return_value=True))
            stack.enter_context(mock.patch.object(installer,'database_fingerprints',return_value={'ficticio':{'columns':['id'],'count':1,'sha256':'ficticio'}}))
            stack.enter_context(mock.patch.object(installer,'backup_before_change',return_value={'catalogo_validado':True}))
            stack.enter_context(mock.patch.object(backup_completo,'criar_backup_completo',return_value={'arquivo':str(archive)}))
            stack.enter_context(mock.patch.object(postgresql_migrations,'status',return_value=[{'name':installer.MIGRATION,'state':'pending'}]))
            migration=stack.enter_context(mock.patch.object(postgresql_migrations,'apply_pending',return_value=[installer.MIGRATION]))
            stack.enter_context(mock.patch.object(installer,'await_probe',side_effect=RuntimeError('Falha ficticia') if fail_probe else None))
            result=installer.apply(SimpleNamespace(release=new,expected_current=old))
            migration.assert_called_once()
            if fail_probe:add.assert_not_called()
            else:add.assert_called_once_with('192.168.1.175')
        report=json.loads((home/(installer.MARKER+'-resultado.json')).read_text(encoding='utf-8'))
        self.assertTrue(auto.Enabled)
        self.assertEqual(task.State,4)
        self.assertEqual((official/'endemias.db').read_bytes(),b'FICTICIO-IMUTAVEL')
        self.assertFalse(report['database_restored_or_deleted'])
        if fail_probe:
            self.assertEqual(result,1)
            self.assertEqual(json.loads((home/'config.json').read_text(encoding='utf-8')),original)
            self.assertEqual(json.loads((official/'kobo_config.json').read_text(encoding='utf-8')),kobo)
            self.assertEqual((home/'servico_web_windows.py').read_bytes(),b'bootstrap-anterior')
            self.assertFalse((official/'kobo_ambiental.json').exists())
            self.assertTrue((Path(report['state'])/'kobo-ambiental-pos-falha.json').exists())
            self.assertTrue(report['rollback_login_ok'])
            self.assertTrue(any(c[0]=='restore' for c in calls))
        else:
            self.assertEqual(result,0)
            cfg=json.loads((home/'config.json').read_text(encoding='utf-8'))
            self.assertEqual(cfg['version'],installer.TARGET)
            self.assertFalse(cfg['probe_only'])
            self.assertEqual(set(json.loads((official/'kobo_config.json').read_text(encoding='utf-8'))['assets']),{'TB'})
            self.assertEqual(set(json.loads((official/'kobo_ambiental.json').read_text(encoding='utf-8'))['assets']),{'ESPOROTRICOSE'})
            self.assertEqual(report['status'],'aplicado')

    def test_retorno_de_falha_restaura_configuracoes_e_preserva_banco_e_importacao_agendada(self):
        self.simulated_install(fail_probe=True)

    def test_ativacao_finaliza_configuracoes_e_retorna_a_mesma_tarefa_kobo(self):
        self.simulated_install()
