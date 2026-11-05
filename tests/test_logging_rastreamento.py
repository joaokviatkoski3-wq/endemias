import io
import json
import logging
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import openpyxl
from flask import Flask, Response, g

import app
from app_core import audit, auth, db, sessoes, dominios
from app_core import logging_rastreamento as core
from app_core.logging_seguranca import limitar_detalhes, FormatoTecnicoSeguro, OCULTO
from scripts.preparar_massa_web_teste import preparar

ROOT = Path(__file__).resolve().parents[1]


class TrilhaSeguraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.application = Flask(__name__)
        self.application.config.update(SECRET_KEY="segredo-de-teste", LOG_PATH=str(self.root/"app.log"), SETORES_ENABLED=True, SETOR="endemias")
        core.registrar(self.application)
        self.writer = self.application.extensions["rastreamento"]

    def rows(self):
        return self.writer.consultar({}, limite=10000)["registros"]

    def test_requisicao_usa_rota_padrao_sem_query_corpo_cookie_ou_valor_secreto(self):
        @self.application.post('/ensaio/<token>')
        def ensaio(token):
            g._auth_usuario={"id_usuario":7,"usuario":"operador-ficticio"}
            return "ok"
        response = self.application.test_client().post('/ensaio/segredo-no-path?token=segredo-query',json={'senha':'segredo-corpo'}, headers={'Authorization':'Bearer segredo-header','X-Request-ID':'segredo-cliente'})
        self.assertRegex(response.headers['X-Request-ID'],r'^[a-f0-9]{32}$')
        raw=self.writer.path.read_text(encoding='utf-8')
        for segredo in ('segredo-no-path','segredo-query','segredo-corpo','segredo-header','segredo-cliente'):
            self.assertNotIn(segredo,raw)
        row=next(r for r in self.rows() if r['tipo']=='requisicao')
        self.assertEqual('/ensaio/<token>',row['rota']);self.assertEqual(7,row['ator_id'])
        self.assertEqual('127.0.0.1',row['ip']);self.assertEqual(200,row['status'])
        self.assertEqual(core.APP_VERSION,row['versao']);self.assertIsInstance(row['pid'],int)

    def test_ids_validos_sao_distintos_de_nome_caminho_e_token(self):
        @self.application.get('/consulta/<int:id>/<nome>/<token>')
        def consulta(id,nome,token):return 'ok'
        self.application.test_client().get('/consulta/14/nome-sigiloso/token-sigiloso')
        row=self.rows()[0]
        self.assertEqual({'id':14},row['alvos'])
        self.assertNotIn('sigiloso',json.dumps(row))

    def test_erro_tecnico_nao_expoe_mensagem_excecao_args_ou_sql(self):
        @self.application.get('/falha')
        def falha():
            g._auth_usuario={"id_usuario":7,"usuario":"tecnico-ficticio","nivel":"superadmin"}
            try:raise ValueError('senha e dados sigilosos')
            except ValueError:logging.exception('SQL com senha=%s','segredo-argumento')
            return 'erro',500
        self.application.test_client().get('/falha')
        rows=self.rows();diag=next(r for r in rows if r['tipo']=='diagnostico')
        self.assertEqual('ValueError',diag['erro_tipo']);self.assertTrue(diag['frames'])
        self.assertEqual('ERROR',diag['nivel_log'])
        self.assertEqual('superadmin',diag['nivel'])
        self.assertNotIn('sigilosos',json.dumps(rows));self.assertNotIn('segredo-argumento',json.dumps(rows))
        record=logging.LogRecord('app',logging.ERROR,'app.py',1,'senha=%s',('segredo-textual',),None)
        self.assertNotIn('segredo-textual',FormatoTecnicoSeguro().format(record))

    def test_rotacao_retencao_e_linha_corrompida_sao_explicitas(self):
        self.assertTrue(core.provar_rotacao(self.application.config)['ok'])
        velho={'id':'antigo','instante':(datetime.now(timezone.utc)-timedelta(days=60)).isoformat(),'tipo':'antigo'}
        self.writer.path.write_text(json.dumps(velho)+'\n{linha incompleta\n',encoding='utf-8')
        self.writer._limpeza=0;self.writer.gravar({'tipo':'novo'})
        result=self.writer.consultar({})
        self.assertTrue(result['incompleto']);self.assertEqual(1,result['linhas_invalidas'])
        self.assertNotIn('antigo',[r['tipo'] for r in result['registros']])

    def test_falha_de_arquivo_nao_interrompe_resposta(self):
        @self.application.get('/normal')
        def normal():return 'ok'
        with mock.patch.object(self.writer,'_exclusivo',side_effect=PermissionError('mensagem privada')):
            response=self.application.test_client().get('/normal')
        self.assertEqual(200,response.status_code);self.assertEqual(1,self.writer.falhas)
        self.assertEqual('PermissionError',self.writer.ultima_falha)

    def test_retencao_preserva_json_incompleto_sem_bloquear_gravacao(self):
        self.writer.path.write_text('[]\n{}\nnull\n{"id":"incompleto"}\n',encoding='utf-8')
        self.writer._limpeza=0
        self.assertTrue(self.writer.gravar({'tipo':'depois_da_linha_invalida'}))
        result=self.writer.consultar({})
        self.assertTrue(result['incompleto'])
        self.assertEqual(4,result['linhas_invalidas'])
        self.assertEqual(1,result['total'])

    def test_polling_presenca_resumido_mas_negacao_sempre_registrada(self):
        counter=[200]
        self.application.add_url_rule('/presenca',endpoint='auth.presenca',view_func=lambda:('ok',counter[0]),methods=['POST'])
        client=self.application.test_client()
        for _ in range(5):client.post('/presenca')
        self.assertEqual(1,len([r for r in self.rows() if r['tipo']=='requisicao']))
        counter[0]=403
        for _ in range(2):client.post('/presenca')
        self.assertEqual(2,len([r for r in self.rows() if r.get('status')==403]))

    def test_fluxo_tem_inicio_termino_e_download_tem_rastro(self):
        @self.application.get('/stream')
        def stream():return Response(iter(['data: ok\n\n']),mimetype='text/event-stream')
        @self.application.get('/download')
        def download():return Response('conteudo',headers={'Content-Disposition':'attachment; filename=arquivo-privado.csv'})
        client=self.application.test_client();response=client.get('/stream');list(response.response);response.close();client.get('/download')
        rows=self.rows();fim=next(r for r in rows if r['tipo']=='fluxo_encerrado')
        self.assertTrue(fim['completo']);self.assertTrue(any(r['tipo']=='fluxo_iniciado' for r in rows))
        self.assertTrue(any(r['tipo']=='download' for r in rows));self.assertNotIn('arquivo-privado',json.dumps(rows))

    def test_portal_tem_rastro_sem_sessao_ou_banco(self):
        portal=dominios.portal_application('vsatt.com.br',external=False,logging_config=self.application.config)
        response=portal.test_client().get('/',headers={'Host':'vsatt.com.br'})
        self.assertEqual(200,response.status_code)
        result=core.trilha(self.application.config,'portal').consultar({})
        self.assertTrue(any(r.get('rota')=='/' for r in result['registros']))
        self.assertNotIn('Set-Cookie',response.headers)

    def test_sanitizador_preserva_enum_datas_numeros_e_esconde_valores_sensiveis(self):
        for chave in ('antes','depois','valor','valor_novo','valor_antigo','valor_anterior','valor_ant'):
            result=limitar_detalhes({'campo':'endereco',chave:'Endereco sigiloso'})
            self.assertEqual(OCULTO,result[chave])
            self.assertEqual('admin',limitar_detalhes({'campo':'nivel',chave:'admin'})[chave])
        result=limitar_detalhes({'token':'segredo','data':'2026-11-05','quantidade_carga':2.5,'descricao':'saude privada','motivo':{'codigo':'ajuste_cadastro','texto':'saude privada'}})
        self.assertEqual('2026-11-05',result['data']);self.assertEqual(2.5,result['quantidade_carga'])
        self.assertEqual('ajuste_cadastro',result['motivo']['codigo']);self.assertNotIn('saude privada',json.dumps(result))


class TelaLogsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT/'.venv');cls.base=Path(cls.temp.name);cls.seed=cls.base/'seed.db';preparar(cls.seed)

    @classmethod
    def tearDownClass(cls):
        for handler in list(logging.getLogger().handlers):
            name = getattr(handler, 'baseFilename', None)
            if name and Path(name).resolve().is_relative_to(cls.base.resolve()):
                handler.close();logging.getLogger().removeHandler(handler)
        assert cls.base.resolve().is_relative_to((ROOT/'.venv').resolve())
        cls.temp.cleanup()

    def setUp(self):
        self.directory=Path(tempfile.mkdtemp(dir=self.base));self.path=self.directory/'ficticio.db';shutil.copyfile(self.seed,self.path)
        self.application=app.create_app(dict(TESTING=True,WTF_CSRF_ENABLED=False,DB_PATH=str(self.path),LOG_PATH=str(self.directory/'app.log'),SETORES_ENABLED=True,SETOR='endemias',TERMOS_USO_ENABLED=False))
        con=db.connect(self.path);con.execute("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em) SELECT 9,'superficticio','Super Ficticio',senha_hash,'superadmin','2026-11-05' FROM usuarios WHERE id_usuario=1");con.commit();con.close()

    def login(self,uid=1):
        client=self.application.test_client();user=db.query_one(str(self.path),'SELECT * FROM usuarios WHERE id_usuario=?',(uid,))
        with self.application.app_context(),client.session_transaction() as s:s.update(uid=uid,nome=user['nome'],auth_token=auth.token_sessao(user['senha_hash']),sessao_id=sessoes.criar(str(self.path),user))
        return client

    def test_permissoes_fontes_e_setores(self):
        admin=self.login();superadmin=self.login(9);usuario=self.login(4)
        self.assertEqual(200,admin.get('/admin/auditoria').status_code)
        self.assertEqual(403,admin.get('/admin/auditoria?origem=tecnico').status_code)
        self.assertEqual(403,admin.get('/admin/auditoria/exportar?origem=tecnico').status_code)
        self.assertEqual(403,usuario.get('/admin/auditoria').status_code)
        self.assertEqual(200,superadmin.get('/admin/auditoria?origem=tecnico').status_code)
        self.assertEqual(403,superadmin.get('/admin/auditoria?origem=tecnico&area=ambiental').status_code)

    def test_auditoria_paginacao_total_exporta_mais_de_500_e_sem_ddl_na_consulta(self):
        con=db.connect(self.path)
        con.executemany("INSERT INTO auditoria_eventos(acao,criado_em,setor,detalhes_json) VALUES('teste_logs','2026-11-05','endemias','{}')",[()]*601);con.commit();con.close()
        client=self.login();response=client.get('/admin/auditoria?acao=teste_logs&por_pagina=25&pagina=2')
        self.assertIn('26–50 de 601',response.get_data(as_text=True))
        response=client.get('/admin/auditoria/exportar?acao=teste_logs')
        self.assertEqual(200,response.status_code)
        wb=openpyxl.load_workbook(io.BytesIO(response.data),read_only=True);self.assertEqual(602,wb.active.max_row);wb.close()
        with mock.patch.object(audit,'garantir_tabela_auditoria',side_effect=AssertionError('DDL em leitura')):
            with self.application.app_context():self.assertEqual(601,audit.consultar_eventos(lambda:db.connect(str(self.path)),{'acao':'teste_logs'})['total'])

    def test_exportacao_recusa_excesso_e_arquivo_incompleto(self):
        client=self.login(9)
        con=db.connect(self.path)
        con.executemany("INSERT INTO auditoria_eventos(acao,criado_em,setor,detalhes_json) VALUES('limite_real','2026-11-05','endemias','{}')",[()]*10002)
        con.commit();con.close()
        response=client.get('/admin/auditoria/exportar?acao=limite_real')
        self.assertEqual(400,response.status_code)
        self.assertIn('10002',response.get_data(as_text=True))
        with mock.patch('blueprints.admin._consultar_logs',return_value={'total':10001,'registros':[]}):
            response=client.get('/admin/auditoria/exportar');self.assertEqual(400,response.status_code);self.assertNotIn('Content-Disposition',response.headers)
        writer=self.application.extensions['rastreamento'];writer.path.write_text('{incompleto\n',encoding='utf-8')
        response=client.get('/admin/auditoria/exportar?origem=tecnico');self.assertEqual(503,response.status_code)

    def test_exportacao_tecnica_preserva_diagnostico_e_termino_fluxo(self):
        writer=self.application.extensions['rastreamento']
        writer.gravar({'tipo':'diagnostico','erro_tipo':'ValueError','frames':[{'arquivo':'modulo.py','linha':20}]})
        writer.gravar({'tipo':'fluxo_encerrado','completo':False,'bytes_resposta':100})
        response=self.login(9).get('/admin/auditoria/exportar?origem=tecnico')
        self.assertEqual(200,response.status_code)
        wb=openpyxl.load_workbook(io.BytesIO(response.data),read_only=True);rows=list(wb.active.values);wb.close()
        raw=json.dumps(rows)
        for text in ('ValueError','frames','modulo.py','completo','bytes_resposta'):self.assertIn(text,raw)
