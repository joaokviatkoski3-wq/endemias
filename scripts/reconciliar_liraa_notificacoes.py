"""Prévia de notificações LIRAa; gravação exige confirmação explícita."""

import argparse
from datetime import datetime
import getpass
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app_core import db,focos_positivos,liraa,liraa_integracao


CONFIRMACAO='RECONCILIAR NOTIFICACOES LIRAA'


def executar(database='endemias_teste',aplicar=False,confirmar='',confirmar_banco=''):
    if database not in ('endemias','endemias_teste'):
        raise ValueError('Banco não permitido para esta operação.')
    if aplicar and (confirmar!=CONFIRMACAO or (database=='endemias' and confirmar_banco!='endemias')):
        raise ValueError('Confirme a reconciliação e o banco antes de aplicar.')
    conn=db.connect(db.DatabaseTarget('postgresql',database))
    try:
        if not aplicar:conn.execute('SET TRANSACTION READ ONLY')
        assert conn.execute('SELECT current_database()').fetchone()[0]==database
        if not aplicar:assert conn.execute('SHOW transaction_read_only').fetchone()[0]=='on'
        rows=conn.execute("""SELECT v.id_visita,v.id_ciclo,v.tipo_imovel,
            SUM(CASE WHEN COALESCE(l.aegypt_larvas,0)+COALESCE(l.aegypt_pupas,0)>0 THEN 1 ELSE 0 END) AS positivos
            FROM liraa_visitas v LEFT JOIN liraa_visita_tubitos t ON t.id_visita=v.id_visita
            LEFT JOIN liraa_leituras l ON l.id_tubito=t.id_tubito
            GROUP BY v.id_visita,v.id_ciclo,v.tipo_imovel ORDER BY v.id_ciclo,v.id_visita""").fetchall()
        pronta=db.column_exists(conn,'focos_positivos','id_visita_liraa')
        resultado=dict(banco=database,aplicado=False,modelo_pronto=pronta,visitas=len(rows),
            imoveis_positivos=sum(bool(r['positivos']) for r in rows),
            notificacoes_previstas=sum(bool(r['positivos']) and focos_positivos.deve_gerar_notificacao('LIRAA',r['tipo_imovel']) for r in rows))
        if aplicar:
            if not pronta:raise ValueError('Aplique a migração 0029 antes da reconciliação.')
            with conn:
                for ciclo in sorted({r['id_ciclo'] for r in rows}):liraa._bloquear_ciclo(conn,ciclo)
                for r in rows:liraa_integracao.sincronizar_foco(conn,r['id_visita'])
                if db.table_exists(conn,'auditoria_eventos'):
                    conn.execute("""INSERT INTO auditoria_eventos(acao,entidade,usuario_nome,detalhes_json,criado_em)
                        VALUES('liraa_notificacoes_reconciliadas','liraa','Windows: '||?,?,?)""",
                        (getpass.getuser(),json.dumps(dict(resultado,aplicado=True),ensure_ascii=False),datetime.now().isoformat()))
            resultado['aplicado']=True
        if pronta:
            row=conn.execute("SELECT COUNT(*) AS focos,COALESCE(SUM(gera_notificacao),0) AS notificacoes FROM focos_positivos WHERE id_visita_liraa IS NOT NULL").fetchone()
            resultado.update(focos_existentes=int(row['focos']),notificacoes_existentes=int(row['notificacoes']))
        return resultado
    finally:
        conn.rollback();conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',default='endemias_teste')
    parser.add_argument('--aplicar',action='store_true')
    parser.add_argument('--confirmar',default='')
    parser.add_argument('--confirmar-banco',default='')
    args=parser.parse_args()
    print(json.dumps(executar(args.database,args.aplicar,args.confirmar,args.confirmar_banco),ensure_ascii=False,indent=2))
