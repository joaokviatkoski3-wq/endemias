"""Fronteiras por setor com dados ficticios, incluindo URLs diretas e cookies."""
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import app
from app_core import auth, db, dominios, import_history, sessoes, usuarios
from scripts.preparar_massa_web_teste import preparar


class SetoresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.venv')
        cls.base = Path(cls.tmp.name)
        cls.seed = cls.base / 'seed.db'
        preparar(cls.seed)
        cls.password = 'SenhaSomenteDeTeste123!'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(dir=self.base))
        self.path = self.directory / 'ensaio.db'
        shutil.copyfile(self.seed, self.path)
        config = dict(DB_PATH=str(self.path), TESTING=True, WTF_CSRF_ENABLED=False,
                      SETORES_ENABLED=True, TERMOS_USO_ENABLED=False,
                      BACKUP_DIR=str(self.directory/'backups'), BACKUP_COMPLETO_DIR=str(self.directory/'completos'),
                      UPLOAD_TEMP=str(self.directory / 'uploads'), KOBO_CONFIG_PATH=str(self.directory / 'kobo_config.json'))
        self.apps = {s: app.create_app({**config, 'SETOR': s}) for s in ('endemias', 'ambiental')}
        self.sql("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=1")
        self.sql("UPDATE usuarios SET setor='ambiental' WHERE id_usuario=4")
        self.sql("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em) SELECT 5,'gestor','Gestor ficticio',senha_hash,'admin',criado_em FROM usuarios WHERE id_usuario=1")

    def sql(self, sql, params=()):
        c=sqlite3.connect(self.path)
        try:
            c.execute(sql,params);c.commit()
        finally:c.close()

    def client(self, area, uid=1):
        application = self.apps[area]
        client = application.test_client()
        user = db.query_one(str(self.path), 'SELECT * FROM usuarios WHERE id_usuario=?', (uid,))
        with application.app_context(), client.session_transaction() as session:
            session.update(uid=uid, nome=user['nome'], auth_token=auth.token_sessao(user['senha_hash']),
                           sessao_id=sessoes.criar(str(self.path), user))
        return client

    def test_migracao_preserva_contas_senhas_e_historico_dos_agentes(self):
        self.assertEqual(db.scalar(str(self.path), 'SELECT COUNT(*) FROM esporotricose_visita_agentes'), 2)
        old = db.query_one(str(self.seed), 'SELECT senha_hash FROM usuarios WHERE id_usuario=2')
        new = db.query_one(str(self.path), 'SELECT senha_hash,setor FROM usuarios WHERE id_usuario=2')
        self.assertEqual(old['senha_hash'], new['senha_hash'])
        self.assertEqual(new['setor'], 'endemias')

    def test_login_recusa_setor_errado_e_aceita_ambos_para_gestores(self):
        for area, login, expected in [('endemias','ficticio2',302),('ambiental','ficticio2',403),
                                      ('endemias','ficticio4',403),('ambiental','ficticio4',302)]:
            with self.subTest(area=area, login=login):
                c = self.apps[area].test_client()
                self.assertEqual(c.post('/login',data={'usuario':login,'senha':self.password}).status_code, expected)
        for uid in (1,5):
            for area in self.apps:
                self.assertEqual(self.client(area,uid).get('/').status_code,200)

    def test_ordinary_account_cannot_cross_boundary_even_with_signed_session(self):
        self.assertEqual(self.client('ambiental',2).get('/api/ambiental/dashboard').status_code,403)
        self.assertEqual(self.client('endemias',4).get('/api/dashboard').status_code,403)

    def test_urls_e_apis_de_outro_setor_bloqueadas_ate_para_superadmin(self):
        for area, urls in {
            'endemias': ['/esporotricose','/amostras-animais','/api/ambiental/dashboard','/relatorios','/vigiagua'],
            'ambiental': ['/visitas','/api/visitas','/laboratorio','/bri','/liraa','/pontos-estrategicos','/api/mapa/ovitrampas','/registro-geografico'],
        }.items():
            client = self.client(area)
            for url in urls:
                with self.subTest(area=area,url=url):
                    self.assertEqual(client.get(url).status_code,403)

    def test_ambiental_telas_resumos_exportacoes_sem_dados_endemias(self):
        client = self.client('ambiental')
        for url in ('/','/dashboard','/relatorios','/mapa','/vigiagua','/processar','/agenda','/admin/usuarios'):
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code,200)
        response = client.get('/api/dashboard')
        self.assertEqual(response.json['registros'],3)
        self.assertEqual(set(response.json['totais']),{'Esporotricose','Amostra de Animais'})
        self.assertEqual(client.get('/api/mapa').json['registros'],3)
        for fmt in ('csv','xlsx','pdf'):
            response = client.get('/relatorios/exportar/'+fmt)
            self.assertEqual(response.status_code,200)
            self.assertGreater(len(response.data),100)
        self.assertEqual(client.get('/api/ambiental/dashboard?d_ini=2026-07-01').json['registros'],0)
        self.assertEqual(client.get('/api/ambiental/dashboard?d_ini=invalida').status_code,400)

    def test_endemias_resumos_sem_consultar_nem_contar_esporo_amostras(self):
        client = self.client('endemias')
        with mock.patch('app_core.dashboard.esporotricose_core.resumo',side_effect=AssertionError('Consulta cruzada')):
            response = client.get('/api/dashboard')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('esporotricose',response.json)
        activities = {r['codigo'] for r in response.json['producao_operacional']['por_atividade']}
        self.assertTrue(activities.isdisjoint({'ESPOROTRICOSE','AMOSTRA_ANIMAIS'}))
        self.assertTrue(all(not r.get('esporo_visitas') for r in client.get('/api/mapa').json.values()))

    def test_agendas_separadas_inclusive_edicao_por_id(self):
        clients = {s:self.client(s) for s in self.apps}
        ids = {}
        for sector, client in clients.items():
            r = client.post('/api/agenda/eventos',json={'titulo':'Evento '+sector,'data_inicio':'2026-06-01T09:00','tipo':'reuniao'})
            self.assertEqual(r.status_code,201)
            ids[sector] = r.json['id_evento']
        for sector, client in clients.items():
            other = 'ambiental' if sector=='endemias' else 'endemias'
            r=client.get('/api/agenda/eventos?start=2026-06-01&end=2026-06-03')
            self.assertEqual(r.status_code,200)
            text = json.dumps(r.json,ensure_ascii=False)
            self.assertIn('Evento '+sector,text)
            self.assertNotIn('Evento '+other,text)
            if sector=='endemias':
                self.assertNotIn('Esporotricose',text)
                self.assertNotIn('Amostra de animais',text)
            for method in ('put','delete'):
                self.assertEqual(getattr(client,method)('/api/agenda/eventos/'+str(ids[other]),json={}).status_code,404)

    def test_kobo_config_jobs_historico_e_operacoes_separados(self):
        from blueprints import processar
        for sector, application in self.apps.items():
            other='ambiental' if sector=='endemias' else 'endemias'
            client = self.client(sector)
            config = client.get('/api/kobo/config').json
            expected = {'ESPOROTRICOSE','AMOSTRA_ANIMAIS'}
            self.assertEqual(set(config['assets']) & expected, expected if sector=='ambiental' else set())
            bad = 'TB' if sector=='ambiental' else 'ESPOROTRICOSE'
            with mock.patch.object(processar.kobo_api,'fetch_submissions') as fetch:
                for url in ('/api/kobo/previa','/api/kobo/importar-formulario/iniciar'):
                    self.assertEqual(client.post(url,json={'tipo':bad}).status_code,400)
                fetch.assert_not_called()
            with application.app_context():
                job_id=str(uuid.uuid4())
                folder=Path(processar._job_dir(job_id));folder.mkdir(parents=True)
                processar.registrar_importacao(job_id,[sector+'.xlsx'],usuario='Pessoa ficticia')
            self.assertEqual(self.client(other).post('/processar/cancelar/'+job_id).status_code,200)
            self.assertTrue(folder.exists())
        with self.apps['ambiental'].app_context():
            rows=processar.listar_importacoes_recentes()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['arquivos'],['ambiental.xlsx'])
        self.assertEqual(self.client('ambiental').post('/api/kobo/lote-vetores-larvas',json={}).status_code,403)

    def test_mudar_setor_revoga_sessao_sem_trocar_senha(self):
        c=self.client('endemias',2)
        self.assertEqual(c.get('/').status_code,200)
        password=db.scalar(str(self.path),'SELECT senha_hash FROM usuarios WHERE id_usuario=2')
        usuarios.editar(str(self.path),2,'setor','ambiental',usuario_atual_id=1)
        self.assertEqual(c.get('/').status_code,302)
        self.assertEqual(db.scalar(str(self.path),'SELECT senha_hash FROM usuarios WHERE id_usuario=2'),password)
        self.assertEqual(self.client('ambiental',2).get('/').status_code,200)

    def test_cookie_nao_reutilizavel_no_outro_setor_e_portal_fail_closed(self):
        end=self.apps['endemias'];amb=self.apps['ambiental']
        client=self.client('endemias')
        cookie=client.get_cookie(end.config['SESSION_COOKIE_NAME']).value
        other=amb.test_client();other.set_cookie(amb.config['SESSION_COOKIE_NAME'],cookie)
        self.assertEqual(other.get('/').status_code,302)
        portal=dominios.portal_application('vsatt.com.br',external=False).test_client()
        r=portal.get('/',base_url='https://vsatt.com.br')
        self.assertIn(b'https://endemias.vsatt.com.br',r.data)
        self.assertIn(b'https://ambiental.vsatt.com.br',r.data)
        self.assertNotIn('Set-Cookie',r.headers)
        dispatcher=dominios.application(end)
        from werkzeug.test import Client
        r=Client(dispatcher).get('/',base_url='https://geo.vsatt.com.br')
        self.assertEqual(r.status_code,400)

    def test_link_recuperacao_aponta_setor_da_conta(self):
        r=self.client('endemias').post('/admin/usuarios/4/recuperacao-senha')
        self.assertEqual(r.status_code,200)
        self.assertTrue(r.json['url'].startswith('https://ambiental.vsatt.com.br/'))

    def test_auditoria_registra_setor_e_oculta_historico_misto(self):
        from app_core import audit
        for sector, application in self.apps.items():
            with application.test_request_context():
                audit.registrar_evento(lambda:db.connect(str(self.path)),'acao_'+sector,detalhes={'ficticio':True})
        self.sql("INSERT INTO auditoria_eventos(acao,criado_em) VALUES('legado_misto','2026-11-04')")
        for sector, application in self.apps.items():
            with application.app_context():
                events=audit.listar_eventos(lambda:db.connect(str(self.path)))
                self.assertEqual([e['acao'] for e in events],['acao_'+sector])
                self.assertEqual(len(audit.listar_eventos(lambda:db.connect(str(self.path)),todos_setores=True)),3)

    def test_upload_e_etl_rejeitam_planilha_de_outro_setor_antes_de_gravar(self):
        from openpyxl import Workbook
        from blueprints import processar
        import etl
        for sector, wrong in [('endemias','ESPOROTRICOSE'),('ambiental','TB')]:
            book=Workbook();stream=io.BytesIO();book.save(stream);book.close();stream.seek(0)
            response=self.client(sector).post('/processar/iniciar',data={'arquivos':(stream,wrong+'_ficticio.xlsx')})
            self.assertEqual(response.status_code,403)
        with mock.patch.object(etl.db_core,'connect',side_effect=AssertionError('Banco nao deve abrir')):
            ok, summary=etl.processar_upload(['TB_ficticio.xlsx'],[],str(self.path),str(Path(__file__).resolve().parents[1]/'config.json'),
                etl.Logger(callback=lambda *args:None),tipos_permitidos={'ESPOROTRICOSE','AMOSTRA_ANIMAIS'})
        self.assertFalse(ok)
        self.assertEqual(summary,[])

    def test_configuracoes_kobo_independentes_e_sem_uid_livre(self):
        from app_core import setores
        from blueprints import processar
        original={'server_url':'https://kobo.invalid','api_token':'TOKEN-SOMENTE-FICTICIO',
                  'assets':{'TB':'uid-end','ESPOROTRICOSE':'uid-amb'},'last_sync':{'TB':'ficticio'}}
        divided=setores.dividir_kobo(original)
        self.assertEqual(divided['ambiental']['assets'],{'ESPOROTRICOSE':'uid-amb'})
        self.assertEqual(original['assets']['TB'],'uid-end')
        for sector, tipo, uid in [('endemias','TB','uid-end'),('ambiental','ESPOROTRICOSE','uid-amb')]:
            client=self.client(sector)
            r=client.post('/api/kobo/config',json={'api_token':'TOKEN-SOMENTE-FICTICIO','assets':{tipo:uid}})
            self.assertEqual(r.status_code,200)
            self.assertNotIn('api_token',r.json['config'])
            with mock.patch.object(processar.kobo_api,'fetch_submissions') as fetch:
                r=client.post('/api/kobo/previa',json={'tipo':tipo,'asset_uid':'uid-intruso'})
                self.assertEqual(r.status_code,403)
                fetch.assert_not_called()
        self.assertEqual(self.client('ambiental').get('/api/kobo/config').json['assets']['ESPOROTRICOSE'],'uid-amb')
        self.assertEqual(self.client('endemias').get('/api/kobo/config').json['assets']['TB'],'uid-end')

    def test_dispatcher_externo_preserva_hostname_e_recusa_cookie_cruzado(self):
        from werkzeug.test import Client
        config=dict(self.apps['endemias'].config)
        config.update(ACESSO_EXTERNO=True,TRUSTED_HOSTS=['endemias.vsatt.com.br'])
        application=app.create_app(config)
        client=Client(dominios.application(application),use_cookies=True)
        from functools import partial
        client.open=partial(client.open,environ_overrides={'REMOTE_ADDR':'127.0.0.1'})
        headers={'CF-Connecting-IP':'203.0.113.24','X-Forwarded-Proto':'https'}
        for domain, text in [('endemias.vsatt.com.br','Setor de Endemias'),('ambiental.vsatt.com.br','Vigilância Ambiental')]:
            response=client.get('/login',base_url='https://'+domain,headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertIn(text,response.get_data(as_text=True))
        self.assertEqual(client.get('/',base_url='https://vsatt.com.br',headers=headers).status_code,200)
        self.assertEqual(client.get('/api/dashboard',base_url='https://ambiental.vsatt.com.br',headers=headers).status_code,401)
        response=client.post('/login',base_url='https://endemias.vsatt.com.br',headers=headers,data={'usuario':'admin','senha':self.password})
        self.assertEqual(response.status_code,302)
        cookie=client.get_cookie('__Host-endemias',domain='endemias.vsatt.com.br')
        self.assertTrue(cookie.secure)
        self.assertTrue(cookie.origin_only)
        client.set_cookie('__Host-endemias',cookie.value,domain='ambiental.vsatt.com.br')
        self.assertEqual(client.get('/api/dashboard',base_url='https://ambiental.vsatt.com.br',headers=headers).status_code,401)

    def test_nova_rota_sem_setor_fica_fechada_e_meteorologia_ambos(self):
        for sector, application in self.apps.items():
            application.add_url_rule('/rota-sem-setor','rota_sem_setor',lambda:'nao expor')
            client=self.client(sector)
            self.assertEqual(client.get('/rota-sem-setor').status_code,403)
            from app_core import modules
            with application.app_context():
                keys={m.key for m in modules.visible_modules({'nivel':'visualizador','setor':sector})}
                self.assertIn('meteorologia',keys)
                self.assertEqual('esporotricose' in keys,sector=='ambiental')


    def test_relatorios_legados_nao_reintroduzem_dados_ambientais(self):
        from app_core import boletim_mensal,relatorio_visitas_completo
        client=self.client('endemias')
        url='/api/relatorio-agente?agente=Agente+Ficticio&d_ini=2026-06-01&d_fim=2026-06-03'
        with mock.patch('blueprints.relatorio_agente.esporotricose_core.resumo',side_effect=AssertionError('Consulta cruzada')):
            r=client.get(url)
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json['esporotricose']['totais'])
        with self.apps['endemias'].app_context():
            rows=relatorio_visitas_completo.coletar(str(self.path),'Agente Ficticio','2026-06-01','2026-06-03')
            self.assertEqual(rows['totais'],{'vetores':1,'esporotricose':0})
            result=boletim_mensal.boletim(str(self.path),'2026-06',usar_salvos=False)
            self.assertTrue(all(row['chave'] not in boletim_mensal.AMBIENTAIS for row in result['linhas']))
        self.assertEqual(client.get('/relatorio-agente/pdf?agente=Agente+Ficticio&d_ini=2026-06-01&d_fim=2026-06-03').status_code,200)

    def test_salvar_boletim_endemias_preserva_indicador_ambiental_antigo(self):
        from app_core import boletim_mensal
        boletim_mensal.salvar(str(self.path),'2026-06',[{'chave':'esporotricose_visitas','origem':'auto','indicador':'Historico ambiental','quantidade':7}])
        with self.apps['endemias'].app_context():
            self.assertNotIn('esporotricose_visitas',{r['chave'] for r in boletim_mensal.boletim(str(self.path),'2026-06')['linhas']})
            boletim_mensal.salvar(str(self.path),'2026-06',[{'chave':'manual_ficticio','indicador':'Indicador Endemias','quantidade':1}])
        self.assertEqual(db.scalar(str(self.path),"SELECT quantidade FROM boletim_mensal_itens WHERE chave='esporotricose_visitas'"),7)

    def test_kobo_automatico_seleciona_somente_formularios_do_setor(self):
        from app_core import kobo_auto
        cfg={'api_token':'TOKEN-FICTICIO','assets':{'TB':'uid-end','ESPOROTRICOSE':'uid-amb','AMOSTRA_ANIMAIS':'uid-amostra'}}
        with mock.patch.object(kobo_auto.kobo_api,'fetch_submissions',return_value=([],{'count':0})) as fetch:
            result, totals=kobo_auto._buscar_novos(cfg,None,'2026-06-01','2026-06-02',tipos_permitidos={'ESPOROTRICOSE','AMOSTRA_ANIMAIS'})
        self.assertEqual(set(result),{'ESPOROTRICOSE','AMOSTRA_ANIMAIS'})
        self.assertEqual({call.args[1] for call in fetch.call_args_list},{'uid-amb','uid-amostra'})
        with mock.patch.dict('os.environ',{'ENDEMIAS_SETORES_ENABLED':'1'}):
            with self.assertRaises(kobo_auto.ImportacaoAutomaticaErro):
                kobo_auto.executar(target=None,config_path='nao_ler',kobo_config_path='nao_ler',migracoes_dir='nao_ler')

    def test_importacao_ambiental_completa_sem_tocar_visitas_endemias(self):
        from blueprints import processar
        client=self.client('ambiental')
        client.post('/api/kobo/config',json={'api_token':'TOKEN-FICTICIO','assets':{'AMOSTRA_ANIMAIS':'uid-ficticio'}})
        record={'_uuid':str(uuid.uuid4()),'_id':42,'_submission_time':'2026-08-05T10:00:00',
                'start':'2026-08-05T08:00:00','end':'2026-08-05T08:30:00','motivo_da_visita':'Reclamação',
                'Data':'2026-08-05','Hora':'08:00','tipo_animal':'Serpente','Quantidade':1}
        before=db.query(str(self.path),'SELECT * FROM visitas ORDER BY id_visita')
        with mock.patch.object(processar.kobo_api,'fetch_submissions',return_value=([record],{'count':1})):
            response=client.post('/api/kobo/importar-formulario/iniciar',json={'tipo':'AMOSTRA_ANIMAIS'})
        self.assertEqual(response.status_code,200)
        job=response.json['job_id']
        other=self.client('endemias')
        self.assertEqual(other.post('/processar/confirmar/'+job).status_code,404)
        preview=client.post('/processar/stream/'+job).get_data(as_text=True)
        self.assertIn('"ok": true',preview)
        self.assertIsNone(db.query_one(str(self.path),'SELECT 1 FROM amostras_animais WHERE kobo_uuid=?',(record['_uuid'],)))
        commit=client.post('/processar/confirmar/'+job).get_data(as_text=True)
        self.assertIn('"ok": true',commit)
        self.assertIsNotNone(db.query_one(str(self.path),'SELECT 1 FROM amostras_animais WHERE kobo_uuid=?',(record['_uuid'],)))
        self.assertEqual(before,db.query(str(self.path),'SELECT * FROM visitas ORDER BY id_visita'))

    def test_tres_entradas_waitress_respondem_sem_portas_de_producao(self):
        import socket
        import threading
        from urllib.request import Request,urlopen
        import servir
        sockets=[]
        for _ in range(3):
            sock=socket.socket();sock.bind(('127.0.0.1',0));sockets.append(sock)
        ports=[s.getsockname()[1] for s in sockets]
        for sock in sockets:sock.close()
        config=dict(self.apps['endemias'].config)
        config.update(ACESSO_EXTERNO=True,TRUSTED_HOSTS=['endemias.vsatt.com.br'])
        external=app.create_app(config)
        local=servir.local_application(external,'127.0.0.1')
        env={'ENDEMIAS_ACESSO_LOCAL':'1','ENDEMIAS_LOCAL_BIND':'127.0.0.1',
             'ENDEMIAS_LOCAL_PORT':str(ports[0]),'ENDEMIAS_TUNNEL_PORT':str(ports[1]),
             'ENDEMIAS_AMBIENTAL_LOCAL_PORT':str(ports[2])}
        server,locals=servir.create_dual_servers(external,local,env)
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        try:
            for port,title in [(ports[0],'Setor de Endemias'),(ports[2],'Vigilância Ambiental')]:
                with urlopen(f'http://127.0.0.1:{port}/login',timeout=10) as response:
                    self.assertIn(title,response.read().decode())
            for host,path,text in [('endemias.vsatt.com.br','/login','Setor de Endemias'),
                                    ('ambiental.vsatt.com.br','/login','Vigilância Ambiental'),
                                    ('vsatt.com.br','/','Vigilância em Saúde')]:
                request=Request(f'http://127.0.0.1:{ports[1]}{path}',headers={'Host':host,'CF-Connecting-IP':'203.0.113.24','X-Forwarded-Proto':'https'})
                with urlopen(request,timeout=10) as response:self.assertIn(text,response.read().decode())
        finally:
            for channel in list(server._map.values()):channel.close()
            locals.close();server.close();server.task_dispatcher.shutdown();thread.join(2)
