"""Definições e envios fictícios; não lê credenciais nem respostas reais."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from uuid import uuid4

from app_core import formularios_kobo as core,formularios as forms,db


def definicao(tipo='BRI'):
    def field(name,kind='text',**kw):return {'name':name,'type':kind,'label':[name],**kw}
    return {'tipo':tipo,'sector':'endemias','survey':[
        field('Digite_a_data','date',required=True),field('Digite_a_hora','time'),
        field('Onde_vai_ser_realizado_o_trata','select_one',required=True,select_from_list_name='destino'),
        field('group_pt6ft99','begin_group',relevant="${Onde_vai_ser_realizado_o_trata} = 'outro'"),
        field('localidade_001'),field('Logradouro_001'),field('Quarteir_o'),field('N_mero','integer'),field('','end_group'),
        field('group_rb5ho54','begin_group'),field('Quantidade_de_carga','decimal'),field('','end_group'),
        field('group_jr1vc40','begin_repeat'),field('N_mero_do_tubito','integer'),field('','end_repeat')],
        'choices':[{'list_name':'destino','name':'outro','label':['Outro']}]}


def preenchimento(tree):
    return {'versao':tree['versao'],'values':{'Digite_a_data':'2026-06-03','Digite_a_hora':'08:00',
        'Onde_vai_ser_realizado_o_trata':'outro','group_pt6ft99/localidade_001':'Localidade Ficticia',
        'group_pt6ft99/Logradouro_001':'Rua Ficticia','group_pt6ft99/Quarteir_o':'42','group_pt6ft99/N_mero':'12',
        'group_rb5ho54/Quantidade_de_carga':'2.5'},'repeats':{}}


class ValidacaoFormularioTests(unittest.TestCase):
    def setUp(self):self.tree=core.compilar(definicao());self.payload=preenchimento(self.tree)

    def test_dez_tipos_compativeis_registrados(self):
        for tipo in core.TITULOS:self.assertIsNotNone(forms.formulario_por_tipo('kobo_'+tipo))

    def test_tipo_condicoes_e_registro_com_identificacao_propria(self):
        self.payload.update(inicio='2026-06-03T08:00:00-03:00',fim='2026-06-03T08:20:00-03:00')
        record=core.registro(self.tree,self.payload,str(uuid4()))
        self.assertEqual(record['group_rb5ho54/Quantidade_de_carga'],2.5)
        self.assertEqual(record['group_pt6ft99/N_mero'],12)
        self.assertTrue(record['_uuid'].startswith('vsatt-'))
        self.assertEqual(record['end'],'2026-06-03T08:20:00-03:00')

    def test_opcao_falsa_versao_antiga_e_campo_desconhecido(self):
        for mutate in (lambda p:p.update(versao='antiga'),lambda p:p['values'].update(erro='x'),
                       lambda p:p['values'].update(Onde_vai_ser_realizado_o_trata='invalido')):
            payload=copy.deepcopy(self.payload);mutate(payload)
            with self.assertRaises(ValueError):core.validar(self.tree,payload)

    def test_repeticoes_e_obrigatoriedade(self):
        self.payload['repeats']={'group_jr1vc40':[{'group_jr1vc40/N_mero_do_tubito':'99'}]}
        self.assertEqual(core.validar(self.tree,self.payload)['group_jr1vc40'][0]['group_jr1vc40/N_mero_do_tubito'],99)
        self.payload['values']['Digite_a_data']=''
        with self.assertRaises(ValueError):core.validar(self.tree,self.payload)
        core.validar(self.tree,self.payload,publicar=False)

    def test_tipo_finito_negativo_e_quantidade_de_repeticoes(self):
        for value in ('nan','inf','-1',True,[],{}):
            with self.subTest(value=value):
                self.payload['values']['group_rb5ho54/Quantidade_de_carga']=value
                with self.assertRaises(ValueError):core.validar(self.tree,self.payload)

    def test_catalogo_acs_usado_pelo_envio_respeita_transacao(self):
        import sqlite3
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        self.addCleanup(conn.close)
        conn.execute('CREATE TABLE acs_catalogo(acs_codigo TEXT PRIMARY KEY,nome TEXT,atualizado_em TEXT)');conn.commit()
        tree={'nodes':[{'name':'Qual_quais_ACS','path':'grupo/Qual_quais_ACS','options':[
            {'value':'acs-ficticio','label':'ACS Fictício'},{'value':'acs-nao-selecionado','label':'Outro Fictício'}]}]}
        core.sincronizar_acs(conn,tree,{'grupo/Qual_quais_ACS':'acs-ficticio'})
        self.assertEqual(conn.execute('SELECT nome FROM acs_catalogo').fetchone()[0],'ACS Fictício')
        conn.rollback()
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM acs_catalogo').fetchone()[0],0)

    def test_texto_que_parece_formula_nao_some_na_leitura_do_importador(self):
        import pandas as pd
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'intermediario.xlsx'
            pd.DataFrame([{'Observações':'=1+1','Quantidade':2.5}]).to_excel(path,index=False)
            core.preservar_textos_planilhas([path])
            book=load_workbook(path,data_only=True)
            try:
                self.assertEqual(book.active['A2'].value,'=1+1')
                self.assertEqual(book.active['B2'].value,2.5)
            finally:book.close()


class ApiFormularioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_setores import SetoresTests
        cls.fixture=SetoresTests;cls.fixture.setUpClass()

    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()

    def setUp(self):
        self.f=self.fixture('test_migracao_preserva_contas_senhas_e_historico_dos_agentes');self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.tree=core.compilar(definicao());self.payload=preenchimento(self.tree)
        self.patch=mock.patch.object(core,'carregar',side_effect=lambda tipo:definicao(tipo));self.patch.start();self.addCleanup(self.patch.stop)
        self.client=self.f.client('endemias',5)

    def send(self):
        return self.client.post('/api/formularios/kobo/BRI',json={'usuario':5,'uuid':str(uuid4()),'status':'enviado',
            'payload':self.payload,'captura':{'versao':1,'revisao':1,'dispositivo':str(uuid4())}})

    def test_captura_revisao_aplicacao_atomica_e_repeticao(self):
        response=self.send();self.assertEqual(response.status_code,200,response.json);ident=response.json['id']
        item=self.client.get(f'/api/formularios/kobo/BRI/{ident}').json
        review=self.client.post(f'/api/formularios/kobo/BRI/{ident}/revisar',json={'payload':item['payload'],'etag':item['etag'],'decisao':'aprovado'})
        self.assertEqual(review.status_code,200,review.json)
        before=db.scalar(str(self.f.path),'SELECT COUNT(*) FROM bri_registros')
        response=self.client.post(f'/api/formularios/kobo/BRI/{ident}/oficializar',json={})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(db.scalar(str(self.f.path),'SELECT COUNT(*) FROM bri_registros'),before+1)
        self.assertEqual(forms.obter(str(self.f.path),ident)['status'],'oficializado')
        self.assertEqual(self.client.post(f'/api/formularios/kobo/BRI/{ident}/oficializar',json={}).status_code,200)
        self.assertEqual(db.scalar(str(self.f.path),'SELECT COUNT(*) FROM bri_registros'),before+1)

    def test_setor_conta_e_api_legada_nao_burlam_validacao(self):
        response=self.send();ident=response.json['id']
        self.assertEqual(self.f.client('ambiental',5).get(f'/api/formularios/kobo/BRI/{ident}').status_code,403)
        self.assertEqual(self.f.client('endemias',3).get(f'/api/formularios/kobo/BRI/{ident}').status_code,404)
        self.assertEqual(self.client.post('/api/formularios',json={'tipo':'kobo_BRI','payload':self.payload}).status_code,400)
        self.assertEqual(self.client.get(f'/api/formularios/{ident}').status_code,404)

    def test_laboratorio_exclusivo_e_visualizador_sem_permissao(self):
        self.assertEqual(self.f.client('endemias',2).get('/api/formularios/kobo/BRI/esquema').status_code,403)
        self.f.sql('UPDATE usuarios SET acesso_laboratorio=1,somente_laboratorio=1 WHERE id_usuario=2')
        client=self.f.client('endemias',2)
        self.assertEqual(client.get('/api/formularios/kobo/LARVAS/esquema').status_code,200)
        self.assertEqual(client.get('/api/formularios/kobo/PE/esquema').status_code,403)

    def test_fila_filtra_situacao_e_mostra_pendencias_mais_antigas_primeiro(self):
        actor={'id_usuario':5,'nome':'Gestor fictício'}
        a=forms.salvar(str(self.f.path),'kobo_BRI',self.payload,actor,uuid_cliente=str(uuid4()))
        b=forms.salvar(str(self.f.path),'kobo_BRI',self.payload,actor,uuid_cliente=str(uuid4()))
        approved=forms.salvar(str(self.f.path),'kobo_BRI',self.payload,actor,uuid_cliente=str(uuid4()))
        forms.revisar(str(self.f.path),approved,self.payload,'aprovado',actor)
        rows=self.client.get('/api/formularios/kobo/BRI?status=enviado').json['itens']
        self.assertEqual([r['id'] for r in rows],[a,b])
        self.assertEqual(self.client.get('/api/formularios/kobo/BRI?status=invalido').status_code,400)

    def test_perfil_basico_nao_recebe_codigo_nominal_de_colega_adicionado_na_revisao(self):
        self.f.sql("UPDATE usuarios SET nivel='usuario',id_agente=1 WHERE id_usuario=3")
        definition=definicao()
        definition['survey'].append({'name':'Nome_do_s_agente_s','type':'select_multiple','select_from_list_name':'agentes'})
        definition['choices'] += [{'list_name':'agentes','name':'ficticio','label':['Agente Ficticio']},
                                  {'list_name':'agentes','name':'outro-colega','label':['Outro Agente Ficticio']}]
        tree=core.compilar(definition);payload=preenchimento(tree);payload['values']['Nome_do_s_agente_s']='ficticio outro-colega'
        ident=forms.salvar(str(self.f.path),'kobo_BRI',payload,{'id_usuario':3,'nome':'Autor fictício'},uuid_cliente=str(uuid4()))
        with mock.patch.object(core,'carregar',return_value=definition):
            response=self.f.client('endemias',3).get(f'/api/formularios/kobo/BRI/{ident}')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['payload']['values']['Nome_do_s_agente_s'],'ficticio')
