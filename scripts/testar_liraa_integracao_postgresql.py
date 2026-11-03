"""Ensaio do fluxo comum LIRAa em tabelas temporárias, nunca em produção."""

import argparse
from datetime import date
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from flask import Flask

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app_core import db,liraa,liraa_kobo,liraa_laboratorio,liraa_operacional,visitas,laboratorio,boletim_mensal,relatorio_visitas_completo
from app_core import visitas_integradas
from scripts.testar_liraa_operacao_postgresql import Shared


def executar(database):
    if database!='endemias_teste':
        raise ValueError('Este ensaio aceita somente endemias_teste.')
    target=db.DatabaseTarget('postgresql',database)
    conn=db.connect(target)
    try:
        assert conn.execute('SELECT current_database()').fetchone()[0]=='endemias_teste'
        conn.execute('CREATE TEMPORARY TABLE isolamento_liraa(id integer)')
        conn.execute('SET search_path TO pg_temp')
        inicial=(ROOT/'migrations/postgresql/0001_schema_inicial.sql').read_text(encoding='utf-8')
        conn.execute(inicial.replace('CREATE TABLE ','CREATE TEMPORARY TABLE '))
        for versao in ('0009','0010','0011','0023','0024','0025','0026','0029'):
            sql=next((ROOT/'migrations/postgresql').glob(versao+'_*')).read_text(encoding='utf-8')
            conn.execute(sql.replace('CREATE TABLE ','CREATE TEMPORARY TABLE '))
        conn.execute("INSERT INTO localidades(id_localidade,nome) VALUES(1,'Sede')")
        conn.execute("INSERT INTO agentes(id_agente,nome,nome_completo) VALUES(1,'João','João Silva')")
        conn.execute("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em,id_agente) VALUES(1,'teste','João','sem-senha','admin','2026-11-03',1)")
        conn.commit()
        territorio={'quarteiroes':[{'id_localidade':1,'localidade':'Sede','quarteirao':str(i).zfill(4),'quarteirao_exibicao':str(i),
            'unidades_rg':30,'tem_rg':True,'registros_rg':30,'pe_rg':0} for i in range(1,6)],
            'localidades':[{'id_localidade':1,'nome':'Sede','quarteiroes':5}],'fonte':'ensaio'}
        with patch.object(db,'connect',return_value=Shared(conn)),patch.object(liraa,'inventario',return_value=territorio):
            ciclo=liraa.criar_ciclo(target,{'ano':date.today().year,'nome':'Ensaio temporário'})
            estrato=liraa.salvar_estrato(target,ciclo,{'numero':1,'tipo':'normal','imoveis_confirmados':9000,'localidades':[1]})
            sorteio=liraa.sortear(target,estrato,seed=42)
            q=sorteio['selecionados'][0]['quarteirao']
            dia=date.today().isoformat()
            r={'_uuid':'liraa-integracao-temporaria','Data':dia,'Hora_inicio':'08:30','Agentes':'jo_o',
                'endemias_ciclo':str(ciclo),'endemias_plano':liraa_operacional.plano_hash_conn(conn,ciclo),
                'Dados_visita':{'Localidade':'centro','Quarteir_o':q,'Imovel':'residencia','Logradouro':'RUA DO ENSAIO','Numero':1},
                'tratamento_001':{'foi_tratado':'sim','Quantidade_carga_gr':2,'Quantidade_dep_sitos_tratados':3},
                'group_jr1vc40':[{'N_mero_do_tubito':123,'C_digo_do_dep_sito':'B'}]}
            assert liraa_kobo.importar(target,ciclo,[r])==1
            filtros={'d_ini':dia,'d_fim':dia}
            rows=visitas.listar(target,filtros)
            assert rows['total']==1 and rows['registros'][0]['tipo']=='LIRAA'
            id_visita=rows['registros'][0]['id_visita']
            detalhe=visitas.detalhar(target,id_visita)
            assert detalhe['visita']['agentes']=='João'
            assert detalhe['tratamentos'][0]['qtd_depositos_tratados']==3
            t=liraa_laboratorio.listar(target)[0]
            payload={'data_leitura':dia,**{c:'0' for c in liraa_laboratorio.CAMPOS},'aegypt_larvas':'2'}
            liraa_laboratorio.salvar(target,t['id_tubito'],payload,{'id_usuario':1,'nivel':'admin','nome':'João'})
            assert laboratorio.listar(target,filtros)['total']==1
            foco=conn.execute('SELECT * FROM focos_positivos WHERE id_visita_liraa=?',(int(id_visita[len(visitas_integradas.PREFIXO):]),)).fetchone()
            assert foco['gera_notificacao']==1
            assert len(relatorio_visitas_completo.coletar(target,'João',dia,dia)['visitas'])==1
            mensal=boletim_mensal.linhas_automaticas(target,dia[:7])
            assert next(l for l in mensal if l['chave']=='visitas_liraa')['quantidade']==1
            import gerar_consolidado
            from blueprints import relatorio_agente
            app=Flask(__name__)
            app.secret_key='ensaio'
            app.config.update(DB_TARGET=target)
            with app.test_request_context('/'):
                setor=relatorio_agente._obter_dados_setor(dia,dia)
                individual=relatorio_agente._obter_dados('João',dia,dia)
                assert setor['visitas_setor']
                assert individual['por_tipo'][0]['tipo']=='LIRAA'
            with tempfile.TemporaryDirectory(prefix='liraa_integracao_pg_') as pasta:
                exportado=gerar_consolidado.gerar_todos(banco_dados=target,pasta_saida=pasta,tipos=['LIRAA'])
                assert exportado[0].get('visitas')==1,exportado
            import etl
            outro={**r,'_uuid':'leitura-kobo-pg','group_jr1vc40':[{'N_mero_do_tubito':124,'C_digo_do_dep_sito':'B'}]}
            assert liraa_kobo.importar(target,ciclo,[outro])==1
            tubito=conn.execute("SELECT id_tubito FROM liraa_visita_tubitos WHERE numero='124'").fetchone()[0]
            novo,_=etl.inserir_resultado_larva(conn.cursor(),'liraa-t-'+str(tubito),{'Número do tubito':'124','Data da coleta':dia,
                'Data da leitura':dia,'Nome do laboratorista':'João','Aegypt Larvas':1,'_uuid':'larvas-kobo-pg'})
            assert novo
            conn.commit()
            assert conn.execute('SELECT COUNT(*) FROM visitas').fetchone()[0]==0
            assert conn.execute('SELECT COUNT(*) FROM resultados_laboratorio').fetchone()[0]==0
            conn.execute("INSERT INTO visitas(id_visita,kobo_uuid,tipo,data,id_localidade,quarteirao,processado_em) VALUES('rotina','rotina','TB',?,1,1,?)",(dia,dia))
            conn.execute("INSERT INTO coletas(id_coleta,id_visita,num_tubo) VALUES('rotina','rotina','200')")
            conn.commit()
            from blueprints.auth import bp as auth_bp
            from blueprints.laboratorio_lancamentos import bp as lab_bp,CAMPOS_CONTAGEM
            app.register_blueprint(auth_bp);app.register_blueprint(lab_bp)
            client=app.test_client()
            with client.session_transaction() as sessao:sessao['uid']=1
            resposta=client.post('/api/laboratorio/lancamentos/rotina/resultado',json={**{c:0 for c in CAMPOS_CONTAGEM},'aegypt_larvas':1})
            assert resposta.status_code==200,resposta.get_data(as_text=True)
            assert visitas.listar(target,filtros)['total']==3
            assert conn.execute('SELECT COUNT(*) FROM resultados_laboratorio').fetchone()[0]==1
            visitas.excluir(target,id_visita)
            for restante in visitas.listar(target,filtros)['registros']:
                visitas.excluir(target,restante['id_visita'])
            assert conn.execute('SELECT COUNT(*) FROM focos_positivos').fetchone()[0]==0
        print('[OK] PostgreSQL: importação LIRAa, consultas, tratamentos, leitura, notificação, relatórios e exclusão integrada, sem copiar visitas.')
    finally:
        conn.rollback();conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',default='endemias_teste')
    executar(parser.parse_args().database)
