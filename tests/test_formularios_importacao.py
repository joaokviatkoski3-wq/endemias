"""Contratos de captura -> ETL -> tabelas, com nomes e dados fictícios."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest import mock

from app_core import formularios_kobo as core,formularios as forms,db


def de_registro(tipo,record):
    """Definição mínima fictícia, com os mesmos caminhos do contrato API."""
    survey=[];values={};repeats={}
    def fields(row,prefix=''):
        for key,value in row.items():
            if key.startswith('_') or key in ('start','end'):continue
            parts=key.split('/');name=parts[-1]
            for parent in parts[:-1]:survey.append({'name':parent,'type':'begin_group'})
            path='/'.join(filter(None,[prefix,key]))
            if isinstance(value,list):
                survey.append({'name':name,'type':'begin_repeat'});rows=[]
                for entry in value:
                    rows.append({(k if k.startswith(path+'/') else path+'/'+k):v for k,v in entry.items()})
                repeats[path]=rows
                if value:
                    first={k.removeprefix(path+'/'):v for k,v in value[0].items()}
                    for k,v in first.items():
                        survey.append({'name':k.rsplit('/',1)[-1],'type':'text'})
                survey.append({'name':name,'type':'end_repeat'})
            else:
                survey.append({'name':name,'type':'text'});values[path]=value
            for parent in reversed(parts[:-1]):survey.append({'name':parent,'type':'end_group'})
    fields(record)
    tree=core.compilar({'tipo':tipo,'survey':survey,'choices':[]})
    return tree,{'versao':tree['versao'],'values':values,'repeats':repeats}


class ImportacaoInternaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_setores import SetoresTests
        cls.fixture=SetoresTests;cls.fixture.setUpClass()

    @classmethod
    def tearDownClass(cls):cls.fixture.tearDownClass()

    def setUp(self):
        self.env=self.fixture('test_migracao_preserva_contas_senhas_e_historico_dos_agentes');self.env.setUp()
        self.target=db.DatabaseTarget('sqlite',str(self.env.path))
        self.user={'id_usuario':1,'nome':'Responsável Fictício','nivel':'superadmin'}
        self.root=Path(__file__).resolve().parents[1]

    def apply(self,tipo,record,auditar=lambda *args:None):
        tree,payload=de_registro(tipo,record)
        ident=forms.salvar(self.target,'kobo_'+tipo,payload,self.user,uuid_cliente=str(uuid4()))
        forms.revisar(self.target,ident,payload,'aprovado',self.user)
        row=forms.obter(self.target,ident)
        core.aplicar(self.target,row,tree,self.user,self.root/'config.json',self.env.directory,auditar,
                     backup_dir=self.env.directory/'backups')
        self.assertEqual(forms.obter(self.target,ident)['status'],'oficializado')
        return row['uuid_cliente']

    def test_visitas_pe_tb_tbo_pve_com_coleta(self):
        for tipo in ('PE','TB','TBO','PVE'):
            record={'Data':'2026-06-03','Hora':'08:00','Nome_do_s_agente_s':'Ficticio',
                'Dados/Localidade':'Localidade Ficticia','Dados/Logradouro':'Rua Ficticia',
                'Dados/Quarteir_o':'123','Dados/Numero':'45','Dados/Tipo_do_im_vel':'R','Dados/Visita':'normal',
                'group_jr1vc40':[{'N_mero_do_tubito':str(100+len(tipo)),'C_digo_do_dep_sito':'B'}]}
            uid=self.apply(tipo,record)
            self.assertEqual(db.scalar(self.target,'SELECT COUNT(*) FROM visitas WHERE kobo_uuid=?',('vsatt-'+uid,)),1)

    def test_recolhimento_e_amostras(self):
        uid=self.apply('RECOLHIMENTO',{'Data':'2026-06-03','Hora':'08:00','Localidade':'Localidade Ficticia','Nome_do_s_agente_s':'Ficticio','group_cw8wz69/A1':'2'})
        self.assertEqual(db.scalar(self.target,'SELECT COUNT(*) FROM recolhimentos WHERE kobo_uuid=?',('vsatt-'+uid,)),1)
        uid=self.apply('AMOSTRA_ANIMAIS',{'Data':'2026-06-03','Hora':'08:00',
            'group_zn1kq42/Localidade':'Localidade Ficticia','group_zn1kq42/Logradouro':'Rua Ficticia',
            'group_zn1kq42/N_mero':'45','group_zn1kq42/Visita':'normal','Houve_captura':'sim',
            'group_ny0er64/Tipo_de_animal_001':'aranha','group_qv2dg30/Tipo_de_animal':'escorpiao',
            'group_qv2dg30/Quantidade':'2'})
        self.assertEqual(db.scalar(self.target,'SELECT quantidade FROM amostras_animais WHERE kobo_uuid=?',('vsatt-'+uid,)),2)

    def test_esporotricose_conserva_dois_animais(self):
        uid=self.apply('ESPOROTRICOSE',{'group_su8jh28/Data':'2026-06-03','group_su8jh28/Localidade':'Localidade Ficticia',
            'group_tl0nq13':[{'Escolha_o_animal_a_ser_cadastr':'outro','Nome_do_animal':'Primeiro','Qual_animal':'Gato ficticio','Esp_cie':'Sem raça'},
                             {'Escolha_o_animal_a_ser_cadastr':'outro','Nome_do_animal':'Segundo','Qual_animal':'Gato ficticio','Esp_cie':'Sem raça'}]})
        conn=db.connect(self.target)
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM esporotricose_animais WHERE nome IN (?,?)',('Primeiro','Segundo')).fetchone()[0],2)
        finally:conn.close()

    def test_larvas_se_vincula_a_coleta_interna(self):
        self.apply('TB',{'Data':'2026-06-03','Hora':'08:00','Localidade':'Localidade Ficticia','Visita':'normal',
            'group_jr1vc40':[{'N_mero_do_tubito':'777','C_digo_do_dep_sito':'B'}]})
        uid=self.apply('LARVAS',{'group_we1tn02/Numero_tubo':'777','group_we1tn02/Data_da_coleta':'2026-06-03',
            'group_we1tn02/Data_leitura':'2026-06-04','group_we1tn02/Nome_do_laboratorista':'Laboratorista Ficticio',
            'group_nr95y76/group_mw55v39/Aegypt_Larvas':'3'})
        self.assertTrue(uid)

    def test_falha_auditoria_nao_deixa_dados_parciais(self):
        before=db.scalar(self.target,'SELECT COUNT(*) FROM recolhimentos')
        def fail(*args):raise RuntimeError('Falha fictícia')
        with self.assertRaises(ValueError):self.apply('RECOLHIMENTO',{'Data':'2026-06-03','Localidade':'Localidade Ficticia','A1':'2'},auditar=fail)
        self.assertEqual(db.scalar(self.target,'SELECT COUNT(*) FROM recolhimentos'),before)

    def test_liraa_preserva_ciclo_sorteio_e_tubito(self):
        from tests.test_liraa_operacao import OperacaoTests
        import criar_banco
        from app import create_app
        env=OperacaoTests();env.setUp();self.addCleanup(env.doCleanups)
        with mock.patch.object(criar_banco,'BANCO',str(env.target)),contextlib.redirect_stdout(io.StringIO()):
            criar_banco.main()
        create_app({'DB_PATH':str(env.target),'DB_BACKEND':'sqlite','TESTING':True,'SETORES_ENABLED':False})
        record=env.registro()
        visit=record.pop('Dados_visita')
        record.update({'Dados_visita/'+k:v for k,v in visit.items()})
        record['endemias_ciclo']=str(env.ciclo)
        tree,payload=de_registro('LIRAA',record)
        target=db.DatabaseTarget('sqlite',str(env.target))
        ident=forms.salvar(target,'kobo_LIRAA',payload,self.user,uuid_cliente=str(uuid4()))
        forms.revisar(target,ident,payload,'aprovado',self.user)
        core.aplicar(target,forms.obter(target,ident),tree,self.user,self.root/'config.json',self.env.directory,
            lambda *args:None,backup_dir=self.env.directory/'backups')
        self.assertEqual(db.scalar(target,'SELECT COUNT(*) FROM liraa_visitas'),1)
        self.assertEqual(db.scalar(target,'SELECT COUNT(*) FROM liraa_visita_tubitos'),1)
        self.assertEqual(forms.obter(target,ident)['status'],'oficializado')
