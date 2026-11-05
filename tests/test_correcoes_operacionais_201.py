"""Regressões com contas, registros e arquivos exclusivamente fictícios."""
import csv
import io
import sqlite3
import unittest
from unittest import mock
from openpyxl import load_workbook
from app_core import bri, recolhimentos, amostras_animais, db, rg_formulario
from app_core import formularios, registro_geografico, boletim_mensal
from tests import test_setores as fixtures


class Operacionais201Tests(unittest.TestCase):
    setUpClass = classmethod(fixtures.SetoresTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.SetoresTests.tearDownClass.__func__)
    setUp = fixtures.SetoresTests.setUp
    sql = fixtures.SetoresTests.sql
    client = fixtures.SetoresTests.client

    def test_paginacao_total_real_ordem_estavel_e_exportacao_completa(self):
        for module, table, chave, area, path in [
            (bri,'bri_registros','id_bri','endemias','bri'),
            (recolhimentos,'recolhimentos','id_recolhimento','endemias','recolhimentos'),
            (amostras_animais,'amostras_animais','id_amostra','ambiental','amostras-animais')]:
            with self.subTest(table=table):
                conn=sqlite3.connect(self.path)
                conn.executemany(f"INSERT INTO {table} ({chave},data,processado_em,localidade) VALUES (?,'2026-06-01','2026-06-01','Localidade Ficticia')",
                                 [(f'linha-{n:04d}',) for n in range(503)])
                conn.commit(); conn.close()
                pagina=module.listar(str(self.path),{'pagina':2,'por_pagina':500})
                self.assertEqual(pagina['total'],504)
                self.assertEqual(len(pagina['registros']),4)
                primeira=module.listar(str(self.path),{'pagina':1,'por_pagina':500})
                self.assertTrue({r[chave] for r in pagina['registros']}.isdisjoint(r[chave] for r in primeira['registros']))
                self.assertEqual(module.listar(str(self.path),{'pagina':999})['pagina'],6)
                client=self.client(area)
                export=client.get('/api/'+path+'/exportar?por_pagina=1&pagina=2')
                self.assertEqual(export.status_code,200)
                linhas=list(csv.reader(io.StringIO(export.data.decode('utf-8-sig')),delimiter=';'))
                self.assertEqual(len(linhas),505)
                if table=='bri_registros':
                    self.assertIn('Local de tratamento',linhas[0])
                filtrado=client.get('/api/'+path+'/exportar?busca=InexistenteFicticio')
                self.assertEqual(len(list(csv.reader(io.StringIO(filtrado.data.decode('utf-8-sig')),delimiter=';'))),1)

    def test_catalogos_nao_embutem_identidade_de_colegas(self):
        self.sql('UPDATE usuarios SET id_agente=1 WHERE id_usuario=4')
        for area, paths in [('endemias',['/bri','/recolhimentos','/ovitrampas','/formularios/rg-campo']),
                            ('ambiental',['/esporotricose','/amostras-animais'])]:
            self.sql('UPDATE usuarios SET setor=? WHERE id_usuario=4',(area,))
            for path in paths:
                with self.subTest(path=path):
                    response=self.client(area,4).get(path)
                    self.assertEqual(response.status_code,200)
                    self.assertNotIn('Outro Agente Ficticio',response.data.decode())
        contexto=rg_formulario.contexto(str(self.path),{'nivel':'usuario','id_agente':1})
        self.assertEqual([a['id_agente'] for a in contexto['agentes']],[1])
        self.assertEqual(rg_formulario.contexto(str(self.path),{'nivel':'usuario'})['agentes'],[])

    def test_xlsx_rg_aplica_escopo_nominal(self):
        self.sql("UPDATE usuarios SET id_agente=1,setor='endemias' WHERE id_usuario=4")
        self.sql('INSERT INTO registro_geografico_imovel_agentes(id_imovel,id_agente) VALUES(1,2)')
        self.sql("UPDATE registro_geografico_imoveis SET agentes_texto='Agente Ficticio, Outro Agente Ficticio' WHERE id_imovel=1")
        response=self.client('endemias',4).get('/registro-geografico/exportar.xlsx?localidade=1&quarteirao=0001')
        self.assertEqual(response.status_code,200)
        wb=load_workbook(io.BytesIO(response.data),data_only=True)
        try:
            celulas=' '.join(str(c.value or '') for row in wb.active for c in row)
            self.assertIn('Agente Ficticio',celulas)
            self.assertNotIn('Outro Agente Ficticio',celulas)
        finally: wb.close()

    def test_oficializacao_rg_desfaz_tudo_se_marcacao_falhar(self):
        payload={'id_localidade':1,'quarteirao':'0001','linhas':[{'logradouro':'Rua Nova Ficticia','numero':'20','tipo':'R'}]}
        user={'id_usuario':1,'nome':'Gestor ficticio','nivel':'superadmin'}
        id_form=formularios.salvar(str(self.path),'rg_atualizacao',payload,user)
        formularios.revisar(str(self.path),id_form,payload,formularios.STATUS_APROVADO,user)
        with mock.patch.object(formularios,'marcar_oficializado',side_effect=RuntimeError('Falha fictícia de gravação')):
            with self.assertRaises(RuntimeError): rg_formulario.oficializar(str(self.path),id_form,user)
        self.assertEqual(formularios.obter(str(self.path),id_form)['status'],formularios.STATUS_APROVADO)
        self.assertEqual(db.scalar(str(self.path),'SELECT logradouro FROM registro_geografico_imoveis WHERE id_imovel=1'),'Rua Ficticia')
        self.assertEqual(db.scalar(str(self.path),'SELECT COUNT(*) FROM registro_geografico_imoveis'),1)
        rg_formulario.oficializar(str(self.path),id_form,user)
        self.assertEqual(formularios.obter(str(self.path),id_form)['status'],formularios.STATUS_OFICIALIZADO)
        with self.assertRaises(ValueError): rg_formulario.oficializar(str(self.path),id_form,user)

    def test_mes_invalido_retorna_400_em_todas_saidas(self):
        client=self.client('endemias')
        for mes in ['2026-13','0000-01','texto','2026-00']:
            for path in ['/api/boletim-mensal','/boletim-mensal/pdf','/api/boletim-mensal/exportar']:
                with self.subTest(path=path,mes=mes):
                    self.assertEqual(client.get(path+'?mes='+mes).status_code,400)
        self.assertEqual(boletim_mensal.periodo_mes('9999-12')['d_fim'],'9999-12-31')

    def test_ajuda_so_oferece_links_do_setor(self):
        client=self.client('ambiental')
        for query in ['ovitrampas','bri','registro','inicio','']:
            response=client.get('/api/ajuda',query_string={'q':query,'limite':120})
            self.assertEqual(response.status_code,200)
            for artigo in response.json['artigos']:
                self.assertNotEqual(client.get(artigo['link']).status_code,403,artigo['link'])
        inicio=client.get('/api/ajuda?q=tela+inicial').json['artigos']
        self.assertTrue(any('atalhos' in a['resumo'] for a in inicio))

    def test_filtro_notificacao_usa_vinculo_e_nome_inteiro_no_legado(self):
        for chave,nome in [('legado-proprio','Agente Ficticio'),('legado-colega','Outro Agente Ficticio')]:
            self.sql("INSERT INTO focos_positivos(id_foco,data,agentes,logradouro,gera_notificacao,status_notificacao) VALUES(?,'2026-06-01',?,?,1,'pendente')",(chave,nome,chave))
        response=self.client('endemias').get('/notificacoes?agente=Agente+Ficticio')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'legado-proprio',response.data)
        self.assertNotIn(b'legado-colega',response.data)
        self.assertIn(b'Rua Ficticia',response.data)

    def test_telas_com_listeners_recusam_manipuladores_inline(self):
        client=self.client('endemias')
        for path in ['/laboratorio','/recolhimentos','/pontos-estrategicos']:
            response=client.get(path)
            self.assertEqual(response.status_code,200)
            csp=response.headers.get('Content-Security-Policy-Report-Only','')+response.headers.get('Content-Security-Policy','')
            self.assertIn("script-src-attr 'none'",csp)
