import hashlib
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from flask import Flask
from openpyxl import load_workbook
from app_core import db, liraa, liraa_kobo, liraa_operacional as op, liraa_xlsform, liraa_boletim, liraa_laboratorio as lab, liraa_relatorios
from tests import test_liraa as fixtures
from blueprints.liraa import bp
from blueprints.auth import bp as auth_bp
from blueprints.laboratorio_lancamentos import bp as lab_bp


class OperacaoTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LiraaTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.target, self.base = self.fixture.db, self.fixture.temp.name
        self.ciclo = self.fixture.criar()
        self.estrato = self.fixture.estrato(self.ciclo)
        self.draw = liraa.sortear(self.target, self.estrato, self.base, seed=42)
        conn = db.connect(self.target)
        lab.ensure_schema(conn)
        conn.close()
        self.user = {"nivel":"admin", "id_usuario":1,"nome":"Laboratorista teste"}

    def registro(self, uuid="teste", tubitos=1, **extra):
        q = self.draw["selecionados"][0]
        return {"_uuid":uuid,"Data":"2026-10-01","Agentes":"jo_o", "Dados_visita":{
            "Localidade":q["localidade"],"Quarteir_o":q["quarteirao"],"Imovel":"rco", "Logradouro":"Rua Teste", "Numero":1},
            "group_jr1vc40":[{"N_mero_do_tubito":100+i,"C_digo_do_dep_sito":"B"} for i in range(tubitos)], **extra}

    def payload(self, **counts):
        return {"data_leitura":"2026-10-01", **{f:"0" for f in lab.CAMPOS}, **counts}

    def test_ic_validado_e_ordem_numerica(self):
        for value in ("0", "-1", "nan", "Infinity", "100", "x"):
            with self.assertRaises(liraa.LiraaError):
                liraa._calcular_sorteio(9000, self.draw["selecionados"], "normal",42,value)
        result = liraa._calcular_sorteio(9000, self.draw["selecionados"], "normal",42,"0,7")
        self.assertEqual(result["inicio_casual"], .7)
        self.assertEqual(sorted(["0410","0408.1","0409","0408"],key=liraa._ordem_quarteirao), ["0408","0408.1","0409","0410"])

    def test_ressorteio_historico_hash_e_auditoria_atomicos(self):
        before = op.plano(self.target,self.ciclo,self.base)["plano_hash"]
        result = liraa.sortear(self.target,self.estrato,self.base,inicio_casual="1.2",ressortear=True,id_sorteio_esperado=self.draw["id_sorteio"])
        old = op.historico_sorteios(self.target,self.estrato)
        self.assertEqual(old[0]["selecionados"],self.draw["selecionados"])
        self.assertNotEqual(before,op.plano(self.target,self.ciclo,self.base)["plano_hash"])
        with self.assertRaisesRegex(liraa.LiraaError,"mudou"):
            liraa.sortear(self.target,self.estrato,self.base,ressortear=True,id_sorteio_esperado=self.draw["id_sorteio"])
        def fail(conn,details):
            raise RuntimeError("audit fail")
        with self.assertRaisesRegex(RuntimeError,"audit fail"):
            liraa.sortear(self.target,self.estrato,self.base,ressortear=True,id_sorteio_esperado=result["id_sorteio"],auditar=fail)
        self.assertEqual(len(op.historico_sorteios(self.target,self.estrato)),1)
        self.assertEqual(liraa.painel(self.target,self.base)["ciclos"][0]["estratos"][0]["sorteio"]["id_sorteio"],result["id_sorteio"])

    def test_ressorteio_bloqueado_apos_importacao(self):
        liraa_kobo.importar(self.target,self.ciclo,[self.registro()])
        with self.assertRaisesRegex(liraa.LiraaError,"possui visitas"):
            liraa.sortear(self.target,self.estrato,self.base,ressortear=True,id_sorteio_esperado=self.draw["id_sorteio"])

    def test_formulario_errado_e_antigo_nao_consolida(self):
        for values,status in (({"endemias_ciclo":"999"},"formulario_de_outro_ciclo"),
                              ({"endemias_plano":"hash-antigo"},"plano_formulario_desatualizado")):
            v = liraa_kobo.previa(self.target,self.ciclo,[self.registro(**values)])[0]
            self.assertEqual(v["situacao_vinculo"],status)
        self.assertEqual(liraa_kobo._localidade("São_Francisco"),"São Francisco")
        self.assertEqual(liraa_kobo._tubitos({"group_jr1vc40":[{}]}),[])
        data = self.registro(endemias_ciclo=str(self.ciclo),endemias_plano=op.plano(self.target,self.ciclo,self.base)["plano_hash"],group_rb5ho54={"Quantidade_dep_sitos_tratados":3})
        liraa_kobo.importar(self.target,self.ciclo,[data])
        stored=liraa_kobo.listar(self.target)[0]
        self.assertEqual(json.loads(stored["tratamento_json"])["Quantidade_dep_sitos_tratados"],3)
        self.assertEqual(stored["situacao_vinculo"],"sorteado")
        prefix={"group_jr1vc40":[{"group_jr1vc40/N_mero_do_tubito":100,"group_jr1vc40/C_digo_do_dep_sito":"B"}],
                "group_rb5ho54/Quantidade_dep_sitos_tratados":0}
        self.assertEqual(liraa_kobo._tubitos(prefix)[0]["numero"],"100")
        self.assertEqual(json.loads(liraa_kobo._tratamento(prefix))["Quantidade_dep_sitos_tratados"],0)

    def test_kml_filtro_cores_e_ausencia_geometria(self):
        data=op.plano(self.target,self.ciclo,self.base)
        self.assertEqual(data["sem_rg"],len(data["quarteiroes"]))
        root=ET.fromstring(op.kml(self.target,self.ciclo,self.base))
        ns={"k":"http://www.opengis.net/kml/2.2"}
        self.assertEqual(len(root.findall('.//k:Placemark',ns)),len(self.draw["selecionados"]))
        self.assertTrue(root.find('.//k:PolyStyle/k:color',ns).text.startswith('99'))
        loc=self.draw["selecionados"][0]["id_localidade"]
        filtered=op.geojson(self.target,self.ciclo,self.base,id_localidade=loc)
        self.assertTrue(all(f["properties"]["id_localidade"] ==loc for f in filtered["features"]))
        self.fixture.importar(fixtures.camada(("0009","0008","0007","0006","0010")))
        with self.assertRaisesRegex(liraa.LiraaError,"sem geometria"):
            op.kml(self.target,self.ciclo,self.base)

    def test_cond20_conta_um_no_plano_mapa_kml_boletim_sem_alterar_hash(self):
        before = op.plano(self.target, self.ciclo, self.base)
        self.fixture.adicionar_rg((("R", 20),))
        for tipo in ("normal", "reduzido"):
            with self.subTest(tipo=tipo):
                # O tipo é alterado somente nesta base sintética para verificar 20%/50%.
                conn = db.connect(self.target)
                with conn:
                    conn.execute("UPDATE liraa_estratos SET tipo=?", (tipo,))
                conn.close()
                current_hash = op.plano(self.target, self.ciclo, self.base)["plano_hash"]
                data = op.plano(self.target, self.ciclo, self.base)
                escolhido = next(q for q in data["quarteiroes"] if q["quarteirao"] == "0001")
                self.assertEqual(escolhido["unidades_rg"], 1)
                self.assertEqual(escolhido["meta_rg"], 1)
                self.assertEqual(sum(g["unidades_rg"] for g in data["grupos"]), 1)
                self.assertEqual(data["ciclo"]["estratos"][0]["imoveis_confirmados"], 9000)
                self.assertEqual(data["ciclo"]["estratos"][0]["sorteio"]["selecionados"], self.draw["selecionados"])
                feature = next(f for f in op.geojson(self.target, self.ciclo, self.base)["features"]
                               if f["properties"]["id_Q"] == "0001")
                self.assertEqual(feature["properties"]["imoveis_rg"], 1)
                self.assertEqual(feature["properties"]["meta_rg"], 1)
                root = ET.fromstring(op.kml(self.target, self.ciclo, self.base))
                ns = {"k": "http://www.opengis.net/kml/2.2"}
                pm = next(p for p in root.findall('.//k:Placemark', ns)
                          if p.find('k:ExtendedData/k:Data[@name="id_Q"]/k:value', ns).text == "0001")
                self.assertEqual(pm.find('k:ExtendedData/k:Data[@name="imoveis_rg"]/k:value', ns).text, "1")
                summary = liraa_boletim.resumir(self.target, self.ciclo, self.base)
                self.assertEqual(summary["grupos"][0]["referencia_rg"], 1)
                self.assertEqual(summary["grupos"][0]["programados"], 429)
                self.assertEqual(op.plano(self.target, self.ciclo, self.base)["plano_hash"], current_hash)
                if tipo == "normal":
                    self.assertEqual(data["plano_hash"], before["plano_hash"])

    def test_xlsform_cascata_e_acs_selecionados_preserva_modelo(self):
        before=hashlib.sha256(op.BASE_XLSFORM.read_bytes()).hexdigest()
        with self.assertRaisesRegex(liraa.LiraaError,"ACS participantes"):
            liraa_xlsform.gerar(self.target,self.ciclo,self.base)
        op.salvar_configuracao(self.target,self.ciclo,["ACS-006"],"asset123")
        content=liraa_xlsform.gerar(self.target,self.ciclo,self.base)
        book=load_workbook(BytesIO(content))
        try:
            rows=liraa_xlsform._rows(book["survey"])
            names={r["name"]:r for r in rows}
            self.assertEqual(names["Quarteir_o"]["choice_filter"],"localidade=${Localidade}")
            self.assertEqual(names["Data"]["required"],"true")
            self.assertEqual(names["endemias_plano"]["default"],op.plano(self.target,self.ciclo,self.base)["plano_hash"])
            self.assertFalse(any("${Visita}" in str(r) for r in rows))
            self.assertGreater(rows.index(names["group_rb5ho54"]),next(i for i,r in enumerate(rows) if r["type"]=="end_repeat"))
            acs_list=names["ACS"]["type"].split()[1]
            acs=[r["name"] for r in liraa_xlsform._rows(book["choices"]) if r["list_name"]==acs_list]
            self.assertEqual(set(acs),{"ACS-006","no-acs"})
        finally:
            book.close()
        self.assertEqual(hashlib.sha256(op.BASE_XLSFORM.read_bytes()).hexdigest(),before)
        op.salvar_configuracao(self.target,self.ciclo,[],"")
        self.assertTrue(liraa_xlsform.gerar(self.target,self.ciclo,self.base).startswith(b'PK'))

    def test_laboratorio_nao_negativa_pendentes_e_imovel_unico(self):
        liraa_kobo.importar(self.target,self.ciclo,[self.registro(tubitos=3)])
        tubes=lab.listar(self.target,self.ciclo)
        self.assertEqual(len(tubes),3)
        lab.salvar(self.target,tubes[0]["id_tubito"],self.payload(aegypt_larvas="2",albopictus_pupas="1"),self.user)
        lab.salvar(self.target,tubes[1]["id_tubito"],self.payload(aegypt_pupas="5"),self.user)
        g=liraa_boletim.resumir(self.target,self.ciclo,self.base)["grupos"][0]
        self.assertEqual(g["trabalhados"],1)
        self.assertEqual(g["programados"],429)
        self.assertEqual(g["referencia_rg"],0)
        self.assertEqual(g["aegypt_outros"],1)
        self.assertEqual(g["aegypt_total"],2)
        self.assertEqual(g["aegypt_recipientes"]["B"],2)
        self.assertEqual(g["albopictus_total"],1)
        self.assertEqual(g["pendentes"],1)
        self.assertTrue(g["parcial"])
        self.assertEqual(liraa_boletim.resumir(self.target,self.ciclo,self.base,agrupar="localidade")["grupos"][0]["aegypt_outros"],1)
        lab.salvar(self.target,tubes[2]["id_tubito"],self.payload(),self.user)
        self.assertFalse(liraa_boletim.resumir(self.target,self.ciclo,self.base)["grupos"][0]["parcial"])

    def test_laboratorio_permissoes_valores_e_cascata_exclusao(self):
        liraa_kobo.importar(self.target,self.ciclo,[self.registro()])
        tube=lab.listar(self.target,self.ciclo)[0]["id_tubito"]
        for field,value in (("aegypt_larvas","-1"),("aegypt_larvas","1.5"),("aegypt_larvas","")):
            with self.assertRaises(liraa.LiraaError):
                lab.salvar(self.target,tube,self.payload(**{field:value}),self.user)
        with self.assertRaisesRegex(liraa.LiraaError,"permissão"):
            lab.salvar(self.target,tube,self.payload(),{"nivel":"visualizador"})
        payload=self.payload()
        lab.salvar(self.target,tube,payload,{**self.user,"nivel":"visualizador","acesso_laboratorio":1})
        with self.assertRaisesRegex(liraa.LiraaError,"Somente administrador"):
            lab.salvar(self.target,tube,payload,{**self.user,"nivel":"visualizador","acesso_laboratorio":1})
        with self.assertRaisesRegex(liraa.LiraaError,"alterada"):
            lab.salvar(self.target,tube,payload,self.user)
        row=lab.listar(self.target,self.ciclo)[0]
        lab.salvar(self.target,tube,{**payload,"versao":row["atualizado_em"]},self.user)
        v=liraa_kobo.listar(self.target)[0]
        liraa_kobo.excluir(self.target,v["id_visita"])
        conn=db.connect(self.target)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM liraa_leituras").fetchone()[0],0)
        conn.close()

    def test_boletim_codigo_invalido_e_fora_plano(self):
        good=self.registro(uuid='bom')
        good['group_jr1vc40'][0]['C_digo_do_dep_sito']='B2'
        outside=self.registro(uuid='fora')
        outside['Dados_visita']['Quarteir_o']='9999'
        liraa_kobo.importar(self.target,self.ciclo,[good,outside])
        for t in lab.listar(self.target,self.ciclo):
            lab.salvar(self.target,t['id_tubito'],self.payload(aegypt_larvas='1'),self.user)
        result=liraa_boletim.resumir(self.target,self.ciclo,self.base)
        self.assertEqual(result['excluidas'],1)
        self.assertEqual(result['grupos'][0]['trabalhados'],1)
        self.assertEqual(result['grupos'][0]['depositos_invalidos'],1)
        self.assertEqual(result['grupos'][0]['aegypt_total'],1)
        self.assertTrue(result['grupos'][0]['parcial'])
        correct=next(t for t in lab.listar(self.target,self.ciclo) if t['quarteirao']!='9999')
        lab.salvar(self.target,correct['id_tubito'],self.payload(aegypt_larvas='1',codigo_deposito='B',versao=correct['atualizado_em']),self.user)
        self.assertEqual(liraa_boletim.resumir(self.target,self.ciclo,self.base)['grupos'][0]['depositos_invalidos'],0)

    def test_pdf_retrato_texto_e_sem_rg(self):
        import re
        original=liraa_relatorios.SimpleDocTemplate
        with patch.object(liraa_relatorios,'SimpleDocTemplate',side_effect=lambda *a,**kw: original(*a,**kw,pageCompression=0)):
            plan=liraa_relatorios.plano_pdf(self.target,self.ciclo,self.base)
            self.assertTrue(plan.startswith(b'%PDF'))
            self.assertIn(b'Sem RG',plan)
            box=re.search(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)',plan)
            self.assertLess(float(box[1]),float(box[2]))
        liraa_kobo.importar(self.target,self.ciclo,[self.registro()])
        with patch.object(liraa_relatorios,'SimpleDocTemplate',side_effect=lambda *a,**kw: original(*a,**kw,pageCompression=0)):
            summary=liraa_relatorios.boletim_pdf(self.target,self.ciclo,self.base)
        self.assertIn(b'PARCIAL',summary)
        self.assertIn(b'Aedes albopictus',summary)

    def test_rotas_permissoes_downloads_e_telas(self):
        liraa_kobo.importar(self.target,self.ciclo,[self.registro()])
        conn=db.connect(self.target)
        conn.execute("CREATE TABLE usuarios(id_usuario INTEGER PRIMARY KEY,login TEXT,nome TEXT,nivel TEXT,ativo INTEGER,acesso_laboratorio INTEGER)")
        conn.execute("INSERT INTO usuarios VALUES(1,'teste','Teste','admin',1,1)")
        conn.commit();conn.close()
        app=Flask(__name__,template_folder=str(fixtures.ROOT/'templates'))
        app.secret_key='teste'
        app.config.update(DB_PATH=self.target,DB_BACKEND='sqlite',BASE_DIR=self.base)
        for blueprint in (auth_bp,lab_bp,bp):
            app.register_blueprint(blueprint)
        app.jinja_env.globals.update(csrf_token=lambda:'teste')
        @app.context_processor
        def context():
            return {"TIPO_CORES":{},"TIPO_LABELS":{},"AGENDA_TIPO_LABELS":{},"sidebar_groups":[],"APP_VERSION_LABEL":"Teste"}
        op.salvar_configuracao(self.target,self.ciclo,[],"")
        client=app.test_client()
        with client.session_transaction() as session:
            session['uid']=1
        for path in (f'/liraa?ciclo={self.ciclo}',f'/liraa/laboratorio?ciclo={self.ciclo}',
                     '/laboratorio/lancamentos?modulo=liraa',
                     f'/liraa/ciclos/{self.ciclo}/plano.kml',f'/liraa/ciclos/{self.ciclo}/plano.pdf',
                     f'/liraa/ciclos/{self.ciclo}/boletim.pdf',f'/liraa/ciclos/{self.ciclo}/formulario.xlsx'):
            self.assertEqual(client.get(path).status_code,200,path)
        page=client.get('/laboratorio/lancamentos?modulo=liraa').get_data(as_text=True)
        self.assertIn('Tubos · LIRAA',page)
        self.assertIn('LIRAA · 1 tubo(s) aguardando leitura',page)
        tube=lab.listar(self.target,self.ciclo)[0]['id_tubito']
        response=client.post(f'/liraa/laboratorio/{tube}',data={**self.payload(), 'integrado':'1','ciclo':self.ciclo})
        self.assertEqual(response.status_code,302)
        self.assertTrue(response.location.startswith('/laboratorio/lancamentos?modulo=liraa'))
        self.assertEqual(lab.painel(self.target,{})['total_pendentes'],0)
        conn=db.connect(self.target)
        conn.execute("UPDATE usuarios SET nivel='visualizador',acesso_laboratorio=0")
        conn.commit();conn.close()
        self.assertEqual(client.get(f'/liraa/ciclos/{self.ciclo}/formulario.xlsx').status_code,403)
        self.assertEqual(client.get('/liraa/laboratorio').status_code,403)
        conn=db.connect(self.target)
        conn.execute("UPDATE usuarios SET acesso_laboratorio=1")
        conn.commit();conn.close()
        self.assertEqual(client.get('/laboratorio/lancamentos?modulo=liraa').status_code,200)
        self.assertEqual(client.get('/liraa/laboratorio?pendentes=0').status_code,200)
        self.assertEqual(client.get(f'/liraa/ciclos/{self.ciclo}/formulario.xlsx').status_code,403)

    def test_painel_laboratorio_contador_paginacao_e_schema_ausente(self):
        liraa_kobo.importar(self.target,self.ciclo,[self.registro(tubitos=3)])
        conn=db.connect(self.target)
        original=conn.execute('SELECT * FROM liraa_visita_tubitos LIMIT 1').fetchone()
        with conn:
            for i in range(102):
                conn.execute('INSERT INTO liraa_visita_tubitos(id_visita,ordem,numero,codigo_deposito,deposito) VALUES(?,?,?,?,?)',
                             (original['id_visita'],10+i,str(1000+i),'B','Teste'))
        conn.close()
        first=lab.painel(self.target,{})
        self.assertEqual(first['total_pendentes'],105)
        self.assertEqual(len(first['rows']),100)
        self.assertTrue(first['proxima'])
        self.assertEqual(len(lab.painel(self.target,{'pagina':'2'})['rows']),5)
        self.assertIsNotNone(lab.painel(self.target,{'ciclo':'invalido'})['erro'])
        conn=db.connect(self.target)
        conn.execute('DROP TABLE liraa_leituras');conn.commit();conn.close()
        self.assertIn('0026',lab.painel(self.target,{})['erro'])
        conn=db.connect(self.target)
        self.assertFalse(db.table_exists(conn,'liraa_leituras'))
        conn.close()


if __name__ == '__main__':
    unittest.main()
