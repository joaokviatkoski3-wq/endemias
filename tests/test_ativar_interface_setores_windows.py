import copy
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import ativar_interface_setores_windows as installer


class InterfaceInstallerTests(unittest.TestCase):
    def original(self):
        return {'version':installer.ORIGIN,'root':str(installer.OFFICIAL),'server':'waitress',
            'probe_only':False,'sid':'SID-FICTICIO','read_files':['FICTICIO'],'write_dirs':['FICTICIO'],
            'env':{'ENDEMIAS_DB_BACKEND':'postgresql','ENDEMIAS_PG_DATABASE':'endemias',
                'ENDEMIAS_PG_HOST':'127.0.0.1','ENDEMIAS_PG_PORT':'5432','ENDEMIAS_SETORES_ENABLED':'1',
                'ENDEMIAS_DOMINIO_BASE':'vsatt.com.br','ENDEMIAS_ALLOWED_HOSTS':'endemias.vsatt.com.br',
                'ENDEMIAS_LOCAL_PORT':'5000','ENDEMIAS_AMBIENTAL_LOCAL_PORT':'5004','ENDEMIAS_TUNNEL_PORT':'5001',
                'ENDEMIAS_LOCAL_BIND':'192.168.1.175','ENDEMIAS_BACKUP_COMPLETO_DIR':'BACKUP-FICTICIO',
                'SEGREDO_EXEMPLO':'SOMENTE-FICTICIO'}}

    def test_proposta_muda_somente_versao(self):
        before=self.original();snapshot=copy.deepcopy(before)
        proposed=installer.proposed_config(before)
        self.assertEqual(before,snapshot)
        self.assertEqual(proposed,{**snapshot,'version':installer.TARGET})

    def test_origem_ou_esquema_de_entradas_diferente_recusados(self):
        for key,value in [('version','1.80.0'),('root','C:/outro'),('probe_only',True)]:
            original=self.original();original[key]=value
            with self.assertRaises(ValueError):installer.proposed_config(original)
        for key in ('ENDEMIAS_PG_DATABASE','ENDEMIAS_SETORES_ENABLED','ENDEMIAS_AMBIENTAL_LOCAL_PORT'):
            original=self.original();original['env'][key]='INESPERADO'
            with self.assertRaises(ValueError):installer.proposed_config(original)

    def simulate(self,fail_probe=False,pending=False,origin=installer.ORIGIN,target=installer.TARGET,marker=installer.MARKER):
        from app_core import postgresql_migrations,backup_completo
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        base=Path(tmp.name);official=base/'official';home=base/'home';source=base/'source'
        for path in (official,home,source,source/'app_core'):path.mkdir(exist_ok=True)
        old='a'*40;new='b'*40;head=[old];calls=[]
        original=self.original();original['root']=str(official);original['version']=origin
        (home/'config.json').write_text(json.dumps(original),encoding='utf-8')
        (home/'servico_web_windows.py').write_bytes(b'BOOTSTRAP-FICTICIO')
        for name in ('secret.key','config.json','endemias.db','kobo_config.json','kobo_ambiental.json'):
            (official/name).write_bytes(b'CONTEUDO-FICTICIO-PRESERVAR')
        (source/'app_core/version.py').write_text(f'APP_VERSION = "{target}"',encoding='utf-8')
        archive=base/'backup.zip';archive.write_bytes(b'BACKUP-FICTICIO')
        task=FakeTask();auto=SimpleNamespace(Enabled=True,State=3)
        win=SimpleNamespace(web=None,protect=lambda *a,**k:None,folder=SimpleNamespace(GetTask=lambda n:task),
            sec=SimpleNamespace(ConvertStringSidToSid=lambda s:s,ConvertSidToStringSid=lambda s:s,
                                LookupAccountName=lambda *a:('SID-FICTICIO',)))
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
            stack.enter_context(mock.patch.object(installer,'wait_closed',return_value=True))
            stack.enter_context(mock.patch.object(installer,'http_login',return_value=True))
            stack.enter_context(mock.patch.object(installer,'origin_portal',return_value=True))
            stack.enter_context(mock.patch.object(installer,'database_fingerprints',return_value={'ficticio':{'count':1}}))
            stack.enter_context(mock.patch.object(installer,'operational_files',return_value={'anexo-ficticio':'hash-ficticio'}))
            stack.enter_context(mock.patch.object(installer,'backup_before_change',return_value={'catalogo_validado':True}))
            stack.enter_context(mock.patch.object(backup_completo,'criar_backup_completo',return_value={'arquivo':str(archive)}))
            stack.enter_context(mock.patch.object(postgresql_migrations,'status',return_value=[{'state':'pending' if pending else 'applied'}]))
            migration=stack.enter_context(mock.patch.object(postgresql_migrations,'apply_pending',side_effect=AssertionError('Pacote sem DDL')))
            stack.enter_context(mock.patch.object(installer,'await_probe',side_effect=RuntimeError('Falha fictícia') if fail_probe else None))
            if pending:
                with self.assertRaises(ValueError):installer.apply(SimpleNamespace(release=new,expected_current=old),origin,target,marker)
                self.assertFalse(task.stopped)
                return
            result=installer.apply(SimpleNamespace(release=new,expected_current=old),origin,target,marker)
            migration.assert_not_called()
        report=json.loads((home/(marker+'-resultado.json')).read_text(encoding='utf-8'))
        self.assertTrue(auto.Enabled);self.assertEqual(task.State,4)
        self.assertFalse(report['database_restored_or_deleted'])
        self.assertEqual(report['migrations_applied'],[])
        for name in ('secret.key','config.json','endemias.db','kobo_config.json','kobo_ambiental.json'):
            self.assertEqual((official/name).read_bytes(),b'CONTEUDO-FICTICIO-PRESERVAR')
        self.assertEqual((home/'servico_web_windows.py').read_bytes(),b'BOOTSTRAP-FICTICIO')
        cfg=json.loads((home/'config.json').read_text(encoding='utf-8'))
        if fail_probe:
            self.assertEqual(result,1);self.assertEqual(cfg,original)
            self.assertTrue(report['rollback_login_ok']);self.assertTrue(any(c[0]=='restore' for c in calls))
        else:
            self.assertEqual(result,0);self.assertEqual(cfg,{**original,'version':target})
            self.assertEqual(report['status'],'aplicado')

    def test_atualizacao_sem_ddl_preserva_ambos_kobo_bootstrap_e_tarefa(self):self.simulate()
    def test_falha_na_prova_retorna_codigo_config_sem_restaurar_banco(self):self.simulate(fail_probe=True)
    def test_migracao_pendente_recusada_antes_de_parar_servidor(self):self.simulate(pending=True)

    def test_rc3_exige_origem_rc2_e_preserva_configuracao(self):
        before=self.original();before['version']='2.0.0-rc.2'
        result=installer.proposed_config(before,'2.0.0-rc.2','2.0.0-rc.3')
        self.assertEqual(result,{**before,'version':'2.0.0-rc.3'})
        with self.assertRaises(ValueError):installer.proposed_config(before)

    def test_rc3_sucesso_sem_migracao_e_sem_mudar_kobo(self):
        self.simulate(origin='2.0.0-rc.2',target='2.0.0-rc.3',marker='ativacao-mapa-portal200rc3')

    def test_rc3_falha_retorna_rc2_preservando_dados(self):
        self.simulate(fail_probe=True,origin='2.0.0-rc.2',target='2.0.0-rc.3',marker='ativacao-mapa-portal200rc3')

    def test_promocao_200_estavel_sem_migracao_preserva_dados(self):
        self.simulate(origin='2.0.0-rc.3',target='2.0.0',marker='ativacao200estavel')

    def test_falha_promocao_estavel_retorna_rc3(self):
        self.simulate(fail_probe=True,origin='2.0.0-rc.3',target='2.0.0',marker='ativacao200estavel')

    def test_correcoes_201_preservam_dados_e_configuracoes(self):
        self.simulate(origin='2.0.0',target='2.0.1',marker='ativacao-correcoes201')

    def test_falha_correcoes_201_retorna_200_sem_restaurar_dados(self):
        self.simulate(fail_probe=True,origin='2.0.0',target='2.0.1',marker='ativacao-correcoes201')

    def test_bri_202_preserva_dados_recompostos_e_configuracoes(self):
        self.simulate(origin='2.0.1',target='2.0.2',marker='ativacao-bri202')

    def test_falha_bri_202_retorna_201_sem_restaurar_banco(self):
        self.simulate(fail_probe=True,origin='2.0.1',target='2.0.2',marker='ativacao-bri202')

    def test_pwa_220_preserva_dados_contas_e_configuracoes(self):
        self.simulate(origin='2.1.1',target='2.2.0',marker='ativacao-pwarg220')

    def test_formularios_230_preserva_dados_contas_e_configuracoes(self):
        self.simulate(origin='2.2.1',target='2.3.0',marker='ativacao-formularios230')

    def test_formularios_240_preserva_dados_contas_e_configuracoes(self):
        self.simulate(origin='2.3.0',target='2.4.0',marker='ativacao-formularios240')

    def test_falha_formularios_240_retorna_230_sem_restaurar_dados(self):
        self.simulate(fail_probe=True,origin='2.3.0',target='2.4.0',marker='ativacao-formularios240')

    def test_falha_formularios_230_retorna_221_sem_restaurar_dados(self):
        self.simulate(fail_probe=True,origin='2.2.1',target='2.3.0',marker='ativacao-formularios230')

    def test_falha_pwa_220_retorna_211_sem_restaurar_dados(self):
        self.simulate(fail_probe=True,origin='2.1.1',target='2.2.0',marker='ativacao-pwarg220')


class FakeTask:
    State=4
    Definition=SimpleNamespace(Principal=SimpleNamespace(UserId='Conta Fictícia',RunLevel=0))
    stopped=False
    def Stop(self,_):self.State=3;self.stopped=True
    def Run(self,_):self.State=4
