"""Fluxo integrado LIRAa sem cópias das visitas e leituras de origem."""

import sqlite3
import unittest
from pathlib import Path
from flask import Flask
from unittest.mock import patch

from criar_banco import SQL
from app_core import db, visitas, laboratorio, dashboard, liraa_kobo, liraa_laboratorio
from app_core import visitas_integradas as integradas
from app_core import relatorio_visitas_completo, boletim_mensal, producao_operacional
from tests import test_liraa_operacao as fixtures
from app_core import laboratorio_lancamentos, kobo_api, liraa_operacional
from blueprints.auth import bp as auth_bp
from blueprints.laboratorio_lancamentos import bp as laboratorio_bp


class IntegracaoTests(unittest.TestCase):
    def setUp(self):
        self.env = fixtures.OperacaoTests()
        self.env.setUp()
        self.addCleanup(self.env.doCleanups)
        self.target = self.env.target
        conn = db.connect(self.target)
        conn.executescript(SQL)
        conn.execute("ALTER TABLE agentes ADD COLUMN nome_completo TEXT")
        conn.execute("INSERT INTO agentes(id_agente,nome,ativo) VALUES(1,'João',1)")
        conn.commit()
        conn.close()
        laboratorio_lancamentos.ensure_schema(self.target)
        conn = db.connect(self.target)
        if not db.column_exists(conn,"usuarios","id_agente"):
            conn.execute("ALTER TABLE usuarios ADD COLUMN id_agente INTEGER")
        conn.execute("INSERT INTO usuarios(id_usuario,usuario,senha_hash,nome,nivel,ativo,acesso_laboratorio,id_agente,criado_em) VALUES(1,'teste','sem-senha','João','admin',1,1,1,'2026-10-01')")
        conn.commit();conn.close()
        self.args = {"d_ini":"2026-10-01","d_fim":"2026-10-31"}

    def client(self):
        from app_core import work_types
        from blueprints.consultas import bp as consultas_bp
        app=Flask(__name__,template_folder=str(Path(__file__).resolve().parents[1]/'templates'))
        app.secret_key="teste"
        app.config.update(DB_PATH=self.target, DB_BACKEND="sqlite", BASE_DIR=self.env.base)
        app.register_blueprint(auth_bp);app.register_blueprint(laboratorio_bp);app.register_blueprint(consultas_bp)
        app.jinja_env.globals.update(csrf_token=lambda:'teste')
        app.context_processor(lambda:dict(TIPO_CORES=work_types.WORK_TYPE_COLORS,TIPO_LABELS=work_types.WORK_TYPE_LABELS,
            TIPOS_TRABALHO=work_types.WORK_TYPES,AGENDA_TIPO_LABELS={},sidebar_groups=[],APP_VERSION_LABEL='Teste'))
        client=app.test_client()
        with client.session_transaction() as session:session["uid"]=1
        return client

    def foco(self):
        conn=db.connect(self.target)
        try:return dict(conn.execute("SELECT * FROM focos_positivos WHERE tipo_trabalho='LIRAA'").fetchone())
        finally:conn.close()

    def importar(self, **kw):
        registro = self.env.registro(**kw)
        liraa_kobo.importar(self.target, self.env.ciclo, [registro])
        return liraa_kobo.listar(self.target)[0]

    def test_consultas_mostram_uma_visita_e_um_tubo_sem_copiar(self):
        self.importar()
        lista = visitas.listar(self.target, self.args)
        self.assertEqual(lista["total"], 1)
        self.assertEqual(lista["registros"][0]["tipo"], "LIRAA")
        self.assertEqual(lista["registros"][0]["agentes"], "João")
        detalhe = visitas.detalhar(self.target, lista["registros"][0]["id_visita"])
        self.assertEqual(len(detalhe["coletas"]), 1)
        conn = db.connect(self.target)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM visitas").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM coletas").fetchone()[0], 0)
        finally:
            conn.close()

    def test_relatorio_completo_inclui_liraa_e_leitura(self):
        self.importar()
        tube = liraa_laboratorio.listar(self.target)[0]
        liraa_laboratorio.salvar(self.target, tube["id_tubito"], self.env.payload(aegypt_larvas="2"),
                                 {**self.env.user,"nome":"João"})
        dados = relatorio_visitas_completo.coletar(self.target, "João", "2026-10-01", "2026-10-31")
        self.assertEqual(len(dados["visitas"]), 1)
        self.assertEqual(dados["visitas"][0]["visita"]["tipo"], "LIRAA")
        secoes = {r["titulo"]:r["registros"] for r in dados["visitas"][0]["secoes"]}
        self.assertEqual(secoes["Resultados laboratoriais"][0]["aegypt_larvas"], 2)

    def test_sql_nao_altera_mutacoes_ou_literais(self):
        self.importar()
        conn = integradas.connect(self.target)
        self.addCleanup(conn.close)
        sql = "UPDATE visitas SET observacoes='FROM visitas' WHERE id_visita=?"
        self.assertEqual(conn.sql(sql), sql)
        self.assertEqual(conn.execute("SELECT 'FROM visitas' AS texto").fetchone()[0], "FROM visitas")
        self.assertEqual(conn.execute("WITH x AS (SELECT * FROM visitas) SELECT COUNT(*) FROM x").fetchone()[0], 1)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM "visitas"').fetchone()[0],1)

    def test_fila_comum_lanca_corrige_desativa_notificacao_e_preserva_historico(self):
        self.importar()
        client=self.client()
        pendentes=client.get('/api/laboratorio/lancamentos/pendentes').get_json()["pendentes"]
        self.assertEqual(len(pendentes),1)
        self.assertEqual(pendentes[0]["tipo"],"LIRAA")
        payload={f:0 for f in laboratorio_lancamentos_campos()}
        payload["aegypt_larvas"]=3
        url='/api/laboratorio/lancamentos/'+pendentes[0]["id_coleta"]+'/resultado'
        response=client.post(url,json=payload)
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        self.assertEqual(self.foco()["gera_notificacao"],1)
        self.assertEqual(client.post(url,json=payload).status_code,409)
        conn=db.connect(self.target)
        conn.execute("UPDATE focos_positivos SET status_notificacao='entregue'")
        conn.commit();conn.close()
        registro=client.get('/api/laboratorio/lancamentos/historico').get_json()["registros"][0]
        self.assertTrue(registro["editavel"])
        payload.update(aegypt_larvas=0,versao=registro["atualizado_em"])
        editar=f'/api/laboratorio/lancamentos/resultados/{registro["id_resultado"]}/editar'
        self.assertEqual(client.post(editar,json=payload).status_code,200)
        self.assertEqual(self.foco()["gera_notificacao"],0)
        self.assertEqual(self.foco()["status_notificacao"],"entregue")
        self.assertEqual(client.post(editar,json=payload).status_code,400)
        self.assertEqual(client.get('/api/laboratorio/lancamentos/pendentes').get_json()["pendentes"],[])

    def test_terreno_baldio_positivo_permanece_fora_da_fila_notificacoes(self):
        registro=self.env.registro()
        registro["Dados_visita"]["Imovel"]="terreno_baldio"
        liraa_kobo.importar(self.target,self.env.ciclo,[registro])
        t=liraa_laboratorio.listar(self.target)[0]
        liraa_laboratorio.salvar(self.target,t["id_tubito"],self.env.payload(aegypt_pupas="1"),{**self.env.user,"nome":"João"})
        self.assertEqual(self.foco()["gera_notificacao"],0)
        self.assertEqual(laboratorio.listar(self.target,self.args)["total"],1)

    def test_multiplos_tubos_positivos_geram_uma_notificacao_e_exclusao_remove_vinculos(self):
        visita=self.importar(tubitos=2)
        for t in liraa_laboratorio.listar(self.target):
            liraa_laboratorio.salvar(self.target,t["id_tubito"],self.env.payload(aegypt_larvas="1"),{**self.env.user,"nome":"João"})
        foco=self.foco()
        self.assertIn('100',foco["num_tubo"]);self.assertIn('101',foco["num_tubo"])
        visitas.excluir(self.target,integradas.PREFIXO+str(visita["id_visita"]))
        conn=db.connect(self.target)
        try:
            for tabela in ("liraa_visitas","liraa_leituras","liraa_visita_tubitos","focos_positivos"):
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {tabela}').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM liraa_visitas_excluidas').fetchone()[0],1)
            self.assertGreater(conn.execute('SELECT COUNT(*) FROM liraa_sorteios').fetchone()[0],0)
        finally:conn.close()

    def test_importacao_geral_dry_run_confirmacao_e_repeticao(self):
        import etl
        registro=self.env.registro(endemias_ciclo=str(self.env.ciclo))
        arquivo=kobo_api.write_etl_workbooks({"LIRAA":[registro]},str(Path(__file__).resolve().parents[1]/'config.json'),self.env.base)[0]
        logger=etl.Logger(callback=lambda *args:None)
        argumentos=([arquivo],[],self.target,str(Path(__file__).resolve().parents[1]/'config.json'),logger)
        self.assertTrue(etl.processar_upload(*argumentos,dry_run=True)[0])
        self.assertEqual(liraa_kobo.listar(self.target),[])
        ok,resumo=etl.processar_upload(*argumentos,dry_run=False,backup_confirmado=True)
        self.assertTrue(ok)
        self.assertEqual(resumo[0]["visitas_novas"],1)
        ok,resumo=etl.processar_upload(*argumentos,dry_run=False,backup_confirmado=True)
        self.assertTrue(ok);self.assertEqual(resumo[0]["visitas_novas"],0)

    def test_leitura_kobo_se_vincula_a_origem_liraa_sem_copia(self):
        import etl
        from app_core import larvas
        self.importar()
        conn=db.connect(self.target)
        try:
            resolvidas=larvas.resolver_coletas(conn,{('100','2026-10-01')})
            self.assertEqual(len(resolvidas),1)
            coletaid=resolvidas[('100','2026-10-01')]["id_coleta"]
            novo,resultado=etl.inserir_resultado_larva(conn.cursor(),coletaid,{'Número do tubito':'100','Data da coleta':'2026-10-01',
                'Nome do laboratorista':'João','Data da leitura':'2026-10-01','Aegypt Larvas':2,'_uuid':'leitura-kobo'})
            self.assertTrue(novo);self.assertEqual(resultado[1],2)
            conn.commit()
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM resultados_laboratorio').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT origem FROM liraa_leituras').fetchone()[0],'kobo')
        finally:conn.close()
        self.assertEqual(self.foco()["gera_notificacao"],1)

    def test_boletim_mensal_producao_e_consultas_agregam_sem_duplicar(self):
        self.importar()
        t=liraa_laboratorio.listar(self.target)[0]
        liraa_laboratorio.salvar(self.target,t['id_tubito'],self.env.payload(),{**self.env.user,"nome":"João"})
        linhas=boletim_mensal.linhas_automaticas(self.target,'2026-10')
        self.assertEqual(next(r for r in linhas if r['chave']=='visitas_liraa')['quantidade'],1)
        fontes={r['codigo']:r for r in producao_operacional.resumo(self.target,self.args)['por_atividade']}
        self.assertEqual(fontes['VETORES']['registros'],1)
        self.assertEqual(fontes['LABORATORIO']['registros'],1)

    def test_consulta_kobo_usa_projetos_dos_ciclos_e_recusa_truncamento(self):
        from app_core import liraa_integracao
        liraa_operacional.salvar_configuracao(self.target,self.env.ciclo,[],"projetodociclo")
        registro=self.env.registro()
        cfg={'assets':{}}
        with patch.object(kobo_api,'fetch_submissions',return_value=([registro],{'count':1})) as consulta:
            rows,meta=liraa_integracao.buscar_kobo(cfg,self.target)
        self.assertEqual(rows,[registro]);self.assertEqual(meta['count'],1)
        self.assertEqual(consulta.call_args.args[1],"projetodociclo")
        with patch.object(kobo_api,'fetch_submissions',return_value=([registro],{'count':2,'next':'outra-pagina'})):
            with self.assertRaises(kobo_api.KoboError):liraa_integracao.buscar_kobo(cfg,self.target)

    def test_transporte_preserva_json_longo_e_previa_sinaliza_envio_invalido(self):
        from app_core import liraa_integracao
        registro=self.env.registro()
        registro['campo_de_transporte']='=VALOR ' * 7000
        arquivo=kobo_api.write_etl_workbooks({'LIRAA':[registro]},str(Path(__file__).resolve().parents[1]/'config.json'),self.env.base)[0]
        self.assertEqual(liraa_integracao.ler_arquivo(arquivo),[registro])
        resumo=kobo_api.summarize_submissions([{'_uuid':'invalido','Data':'2026-10-01'}],tipo='LIRAA')
        self.assertEqual(resumo['pendencias'],1)

    def test_exportacao_kobo_nativa_preserva_outro_participantes_e_repeticao(self):
        from openpyxl import Workbook
        from app_core import liraa_integracao
        book=Workbook();s=book.active
        s.append(['_uuid','Data','endemias_ciclo','Dados_visita/Localidade','Dados_visita/Quarteir_o',
                  'Dados_visita/Logradouro','Logradouro_outro','Agentes/João','ACS/ACS-006'])
        s.append(['exportado','2026-10-01',self.env.ciclo,'centro',1,'Outro — digitar','Rua Nova',1,1])
        t=book.create_sheet('Tubitos')
        t.append(['_submission__uuid','N_mero_do_tubito','C_digo_do_dep_sito'])
        t.append(['exportado',123,'B'])
        arquivo=Path(self.env.base)/'LIRAA_exportado.xlsx';book.save(arquivo);book.close()
        rows=liraa_integracao.ler_arquivo(arquivo)
        self.assertEqual(rows[0]['Agentes'],'jo_o')
        self.assertEqual(rows[0]['ACS'],'ACS-006')
        normal=liraa_kobo._normalizar(rows[0])
        self.assertEqual(normal['logradouro'],'Rua Nova')
        self.assertEqual(normal['tubitos'][0]['numero'],'123')

    def test_rotina_e_liraa_agregam_e_tubo_ambiguo_nao_e_associado(self):
        from app_core import larvas
        self.importar()
        conn=db.connect(self.target)
        try:
            conn.execute("INSERT INTO visitas(id_visita,kobo_uuid,tipo,data,processado_em,quarteirao) VALUES('rotina','rotina','TB','2026-10-01','2026-10-01',1)")
            conn.execute("INSERT INTO coletas(id_coleta,id_visita,num_tubo) VALUES('rotina','rotina','100')")
            conn.commit()
            self.assertEqual(larvas.resolver_coletas(conn,{('100','2026-10-01')}),{})
        finally:conn.close()
        lista=visitas.listar(self.target,self.args)
        self.assertEqual(lista['total'],2)
        self.assertEqual({r['tipo'] for r in lista['registros']},{'TB','LIRAA'})

    def test_tela_comum_tem_um_unico_formulario_e_filtros_liraa(self):
        self.importar()
        client=self.client()
        r=client.get('/laboratorio/lancamentos?tipo=LIRAA')
        self.assertEqual(r.status_code,200,r.get_data(as_text=True))
        html=r.get_data(as_text=True)
        self.assertEqual(html.count('name="aegypt_larvas"'),1)
        self.assertNotIn('lab-module-liraa',html)
        self.assertIn('configurarCamposLiraa',html)
        self.assertEqual(client.get('/api/laboratorio/lancamentos/pendentes?tipo=TB').get_json()['total'],0)
        self.assertEqual(client.get('/api/laboratorio/lancamentos/pendentes?tipo=LIRAA').get_json()['total'],1)

    def test_operador_laboratorista_nao_corrige_leitura_ou_visita_liraa(self):
        self.importar()
        t=liraa_laboratorio.listar(self.target)[0]
        liraa_laboratorio.salvar(self.target,t['id_tubito'],self.env.payload(),{**self.env.user,'nome':'João'})
        conn=db.connect(self.target)
        conn.execute("UPDATE usuarios SET nivel='operador' WHERE id_usuario=1")
        conn.commit();conn.close()
        client=self.client()
        history=client.get('/api/laboratorio/lancamentos/historico').get_json()['registros'][0]
        self.assertFalse(history['editavel'])
        self.assertEqual(client.post(f'/api/laboratorio/lancamentos/resultados/{history["id_resultado"]}/editar',json={}).status_code,403)
        vid=visitas.listar(self.target,self.args)['registros'][0]['id_visita']
        self.assertEqual(client.post(f'/api/visitas/{vid}/editar',json={}).status_code,403)

    def test_lote_misto_invalido_reverte_todas_as_visitas_e_mantem_plano(self):
        import etl
        plano=liraa_operacional.plano(self.target,self.env.ciclo,self.env.base)['plano_hash']
        ruim=self.env.registro(endemias_ciclo=str(self.env.ciclo))
        ruim['Dados_visita']['Quarteir_o']=''
        rotina={'_uuid':'rotina-lote','Data':'2026-10-01','Hora':'08:00','Agentes':'jo_o','Visita':'Normal',
                'Dados_visita':{'Localidade':'Sede','Logradouro':'Rua Teste','Numero':2,'Morador':'Morador teste','Imovel':'residencia'}}
        cfg=str(Path(__file__).resolve().parents[1]/'config.json')
        arquivos=kobo_api.write_etl_workbooks({'TB':[rotina],'LIRAA':[ruim]},cfg,self.env.base)
        logger=etl.Logger(callback=lambda *args:None)
        self.assertFalse(etl.processar_upload(arquivos,[],self.target,cfg,logger,dry_run=False,backup_confirmado=True)[0])
        conn=db.connect(self.target)
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM visitas').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM liraa_visitas').fetchone()[0],0)
        finally:conn.close()
        self.assertEqual(liraa_operacional.plano(self.target,self.env.ciclo,self.env.base)['plano_hash'],plano)

    def test_leitura_externa_fracionaria_nao_vira_negativa(self):
        import etl
        self.importar()
        tubo=liraa_laboratorio.listar(self.target)[0]['id_tubito']
        conn=db.connect(self.target)
        try:
            with self.assertRaises(ValueError):
                etl.inserir_resultado_larva(conn.cursor(),'liraa-t-'+str(tubo),{'Aegypt Larvas':0.5})
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM liraa_leituras').fetchone()[0],0)
        finally:conn.close()


def laboratorio_lancamentos_campos():
    return [f'{s}_{f}' for s in ('aegypt','albopictus','outra') for f in ('larvas','pupas','exuvias','adulto')]

