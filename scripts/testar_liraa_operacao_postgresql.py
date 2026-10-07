"""Ensaio LIRAa em tabelas temporárias; recusa produção e não consulta o Kobo."""

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_core import db, liraa, liraa_operacional as op, liraa_xlsform, liraa_kobo, liraa_laboratorio as lab, liraa_boletim


class Shared:
    def __init__(self, conn):
        self.conn = conn
        self.backend = 'postgresql'
    def close(self):
        pass
    def __getattr__(self, name):
        return getattr(self.conn, name)
    def __enter__(self):
        self.conn.__enter__()
        return self
    def __exit__(self, *args):
        return self.conn.__exit__(*args)


def executar(database):
    if database != 'endemias_teste':
        raise ValueError('Este ensaio aceita somente endemias_teste.')
    conn = db.connect(db.DatabaseTarget('postgresql', database))
    try:
        if conn.execute('SELECT current_database()').fetchone()[0] != 'endemias_teste':
            raise ValueError('Banco de ensaio incorreto.')
        # Sem public no search_path: nenhum nome desta sessão pode recair numa tabela real.
        conn.execute('CREATE TEMPORARY TABLE localidades(id_localidade bigint PRIMARY KEY,nome text)')
        conn.execute('SET search_path TO pg_temp')
        for version in ('0023','0024','0025','0026'):
            sql = next((ROOT/'migrations/postgresql').glob(version+'_*')).read_text(encoding='utf-8')
            conn.execute(sql.replace('CREATE TABLE ', 'CREATE TEMPORARY TABLE '))
        conn.execute("INSERT INTO localidades VALUES(1,'Sede')")
        conn.commit()
        universe=[{'id_localidade':1,'localidade':'Sede','quarteirao':str(i).zfill(4),
                   'quarteirao_exibicao':str(i),'unidades_rg':30,'tem_rg':True,
                   'registros_rg':30,'pe_rg':0} for i in range(1,6)]
        territory={'quarteiroes':universe,'localidades':[{'id_localidade':1,'nome':'Sede','quarteiroes':5}],'fonte':'ensaio'}
        with patch.object(db,'connect',return_value=Shared(conn)), patch.object(liraa,'inventario',return_value=territory):
            cid=liraa.criar_ciclo(database,{'ano':date.today().year,'nome':'Ensaio descartável'})
            eid=liraa.salvar_estrato(database,cid,{'numero':1,'tipo':'normal','imoveis_confirmados':9000,'localidades':[1]})
            draw=liraa.sortear(database,eid,seed=42)
            op.salvar_configuracao(database,cid,['ACS-006'],'asset123')
            assert liraa_xlsform.gerar(database,cid).startswith(b'PK')
            draw=liraa.sortear(database,eid,ressortear=True,id_sorteio_esperado=draw['id_sorteio'],inicio_casual='0,7')
            assert len(op.historico_sorteios(database,eid))==1
            q=draw['selecionados'][0]['quarteirao']
            payload={'_uuid':'ensaio-temporario','Data':date.today().isoformat(),
                     'Dados_visita':{'Localidade':'centro','Quarteir_o':q,'Imovel':'rco'},
                     'endemias_ciclo':str(cid),'endemias_plano':op.plano(database,cid)['plano_hash'],
                     'group_jr1vc40':[{'group_jr1vc40/N_mero_do_tubito':1,'group_jr1vc40/C_digo_do_dep_sito':'B'}]}
            assert liraa_kobo.importar(database,cid,[payload])==1
            assert lab.painel(database,{})['total_pendentes']==1
            tube=lab.listar(database,cid)[0]['id_tubito']
            lab.salvar(database,tube,{'data_leitura':date.today().isoformat(),**{f:'0' for f in lab.CAMPOS},'aegypt_larvas':'2'},
                       {'nivel':'admin','id_usuario':1,'nome':'Ensaio'})
            group=liraa_boletim.resumir(database,cid)['grupos'][0]
            assert group['aegypt_outros']==1 and group['aegypt_total']==1 and group['pendentes']==0
            assert lab.painel(database,{})['total_pendentes']==0
            visit=liraa_kobo.listar(database,cid)[0]['id_visita']
            liraa_kobo.excluir(database,visit,'Ensaio descartável')
            assert conn.execute('SELECT COUNT(*) FROM liraa_leituras').fetchone()[0]==0
        print('[OK] Migração 0026, ressorteio, histórico, XLSForm, importação, leitura, boletim e exclusão: PostgreSQL temporário.')
    finally:
        conn.close()  # Todas as tabelas e sequências temporárias somem nesta sessão.


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',default='endemias_teste',choices=['endemias_teste'])
    try:
        executar(parser.parse_args().database)
    except Exception as exc:
        print(f'[ERRO] {type(exc).__name__}: {exc}')
        raise SystemExit(1)
