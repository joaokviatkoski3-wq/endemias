"""Corrige somente a entrega 99 de 29 para 30, conforme confirmação do operador."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.reconciliar_entregas_zoomed import TABLES,snapshot,signatures

LOTE='entrega99-20261118-30-capsulas'


def validar(conn):
    before=snapshot(conn)
    delivery=next((e for e in before['entregas'] if e['id_entrega']==99),None)
    recipe=next((r for r in before['receitas'] if r['id_receita']==73),None)
    if not delivery or not recipe or recipe['id_animal_doente']!=54:
        raise ValueError('Vínculo da entrega diferente do conferido.')
    actual=(delivery['id_receita'],str(delivery['data_entrega']),delivery['fonte_medicacao'],delivery['baixa_zoomed'])
    if actual!=(73,'2026-11-18','Município','Não se aplica') or delivery['quantidade'] not in (29,30):
        raise ValueError('Entrega diferente da confirmada pelo operador.')
    return before,delivery


def aplicar(conn):
    with conn:
        before,old=validar(conn)
        if old['quantidade']==30:
            return {'status':'ja_corrigido','lote':LOTE,'assinaturas_depois':signatures(before)}
        expected=json.loads(json.dumps(before,default=str))
        em=datetime.now().isoformat(timespec='seconds')
        conn.execute('UPDATE esporotricose_doentes_entregas SET quantidade=30 WHERE id_entrega=99')
        conn.execute('UPDATE esporotricose_doentes_animais SET atualizado_em=? WHERE id_animal_doente=54',(em,))
        new={**old,'quantidade':30}
        conn.execute('INSERT INTO auditoria_eventos '
                     '(acao,entidade,entidade_id,usuario_nome,detalhes_json,criado_em,setor) '
                     "VALUES('entrega_quantidade_corrigida','esporotricose_entrega','99','Operação VSATT',?,?,'ambiental')",
                     (json.dumps({'lote':LOTE,'antes':old,'depois':new,
                                  'motivo':'Operador confirmou explicitamente corrigir a entrega de Amarelo de 29 para 30 cápsulas.'},ensure_ascii=False,default=str),em))
        next(e for e in expected['entregas'] if e['id_entrega']==99)['quantidade']=30
        next(a for a in expected['animais'] if a['id_animal_doente']==54)['atualizado_em']=em
        after=snapshot(conn)
        if signatures(expected)!=signatures(after):raise ValueError('Resultado fora do escopo; correção desfeita.')
        return {'status':'aplicado','lote':LOTE,'em':em,'id_entrega':99,'quantidade_anterior':29,
                'quantidade_atual':30,'assinaturas_depois':signatures(after)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aplicar',action='store_true')
    parser.add_argument('--resultado',type=Path,required=True)
    args=parser.parse_args()
    from app_core import db,esporotricose
    from scripts.ativar_acesso_externo_windows import connect
    from scripts.endurecer_web_windows import backup_before_change
    cfg=json.loads(Path('C:/ProgramData/EndemiasWeb/config.json').read_text(encoding='utf-8'))
    if cfg['env']['ENDEMIAS_PG_DATABASE']!='endemias':raise ValueError('Banco diferente do oficial.')
    raw=connect(cfg,readonly=True);conn=db.PostgreSQLConnection(raw)
    try:
        before,row=validar(conn);conn.rollback()
    finally:conn.close()
    result={'status':'validado_somente_leitura','quantidade_atual':row['quantidade']}
    if args.aplicar:
        private=Path('C:/ProgramData/EndemiasWeb')/('correcao-entrega99-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        private.mkdir()
        backup=backup_before_change(cfg,private)
        (private/'antes.json').write_text(json.dumps(before,ensure_ascii=False,default=str),encoding='utf-8')
        raw=connect(cfg);conn=db.PostgreSQLConnection(raw)
        try:
            conn.execute("SET LOCAL lock_timeout='5s'")
            conn.execute('LOCK TABLE '+','.join(TABLES.values())+' IN SHARE ROW EXCLUSIVE MODE')
            result=aplicar(conn)
        finally:conn.close()
        result['backup']=backup
        raw=connect(cfg,readonly=True);conn=db.PostgreSQLConnection(raw)
        try:
            if signatures(snapshot(conn))!=result['assinaturas_depois']:raise ValueError('Conferência pós-commit divergente.')
            row=conn.execute('SELECT quantidade,baixa_zoomed FROM esporotricose_doentes_entregas WHERE id_entrega=99').fetchone()
            if row['quantidade']!=30 or row['baixa_zoomed']!='Não se aplica':raise ValueError('Entrega não confere após gravação.')
            conn.rollback()
        finally:conn.close()
        result['verificado_nova_conexao']=True
        result['estoque']=esporotricose.estoque_medicacao(db.DatabaseTarget('postgresql','endemias'))['totais']
        (private/'resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    args.resultado.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


if __name__=='__main__':main()
