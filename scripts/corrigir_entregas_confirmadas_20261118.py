"""Aplica somente as correções de entregas confirmadas pelo operador em 18/11.

Caramelo e Peralta não receberam; Suelen/Pitoquinha receberam medicamento
municipal dispensado do ZooMed; duas identidades de tutores foram confirmadas.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.reconciliar_entregas_zoomed import TABLES, snapshot, signatures, digest, totals

LOTE='zoomed-20261118-confirmacoes'
FONTE_SHA256='251232802c0ced42d4980c65671d0a4c2f110cd708be1efe31f98a3b30a79bf4'
# entrega: receita, animal, data, quantidade, fonte, baixa anterior
ESPERADOS={
    45:(37,35,'2026-06-03',30,'SESA','Sim'),
    91:(68,52,'2026-10-21',30,'Município','Não'),
    88:(79,58,'2026-11-08',30,'Município','Não'),
    96:(87,62,'2026-11-12',30,'Município','Não'),
    31:(24,22,'2026-04-01',30,'SESA','Sim'),
    43:(35,33,'2026-05-29',30,'SESA','Sim'),
    44:(36,34,'2026-05-29',30,'SESA','Sim'),
}


def validar(conn):
    before=snapshot(conn)
    es={e['id_entrega']:e for e in before['entregas']}
    rs={r['id_receita']:r for r in before['receitas']}
    for ident,wanted in ESPERADOS.items():
        e=es.get(ident)
        if not e:
            raise ValueError('Entrega ausente; lote já aplicado ou estado modificado.')
        actual=(e['id_receita'],rs[e['id_receita']]['id_animal_doente'],str(e['data_entrega']),
                e['quantidade'],e['fonte_medicacao'],e['baixa_zoomed'])
        if actual!=wanted:raise ValueError('Entrega diferente da confirmada: '+str(ident))
    if 75 not in rs or rs[75]['id_animal_doente']!=56:
        raise ValueError('Receita da Mika diferente da conferida.')
    if any(rs[e['id_receita']]['id_animal_doente']==56 and str(e['data_entrega'])=='2026-10-27'
           for e in es.values()):raise ValueError('Entrega da Mika já existe.')
    return before


def aplicar(conn):
    with conn:
        before=validar(conn)
        expected=json.loads(json.dumps(before,default=str))
        by_id={e['id_entrega']:e for e in expected['entregas']}
        recipes={r['id_receita']:r for r in expected['receitas']}
        em=datetime.now().isoformat(timespec='seconds')
        changes=[]
        for ident in ESPERADOS:
            old=dict(by_id[ident]);new=dict(old)
            if ident in (45,91):
                conn.execute('DELETE FROM esporotricose_doentes_entregas WHERE id_entrega=?',(ident,))
                expected['entregas'].remove(by_id[ident]);new=None
                reason='Operador confirmou que a entrega não ocorreu; animal faleceu antes de receber.'
            else:
                field,value=('data_entrega','2026-04-04') if ident==31 else (
                    ('fonte_medicacao','Município') if ident in (43,44) else ('baixa_zoomed','Não se aplica'))
                conn.execute('UPDATE esporotricose_doentes_entregas SET '+field+'=? WHERE id_entrega=?',(value,ident))
                by_id[ident][field]=value;new=dict(by_id[ident])
                reason=('Entrega municipal efetiva, dispensada de registro no ZooMed por acordo confirmado pelo operador.'
                        if ident in (88,96) else 'Identidade da tutora confirmada pelo operador; correção conforme planilha ZooMed.')
            changes.append({'id_entrega':ident,'id_animal_doente':ESPERADOS[ident][1],
                            'antes':old,'depois':new,'motivo':reason})
        # Aplica o mesmo acordo a eventuais lançamentos municipais feitos
        # durante a preparação, sem reclassificar baixas já realizadas.
        for ident,row in by_id.items():
            if ident in ESPERADOS or row['fonte_medicacao']!='Município' or row['baixa_zoomed']!='Não':continue
            if not row['data_entrega'] or str(row['data_entrega'])<'2026-11-08':continue
            old=dict(row)
            row['baixa_zoomed']='Não se aplica'
            conn.execute("UPDATE esporotricose_doentes_entregas SET baixa_zoomed='Não se aplica' WHERE id_entrega=?",(ident,))
            changes.append({'id_entrega':ident,'id_animal_doente':recipes[row['id_receita']]['id_animal_doente'],
                            'antes':old,'depois':dict(row),'motivo':'Entrega municipal desde 08/11/2026 dispensada de baixa conforme acordo do operador.'})
        new={'id_receita':75,'quantidade':30,'data_entrega':'2026-10-27','baixa_zoomed':'Sim',
             'fonte_medicacao':'SESA','observacoes':'Conferência ZooMed: identidade do tutor confirmada pelo operador.', 'criado_em':em}
        row=conn.execute('INSERT INTO esporotricose_doentes_entregas '
                         '(id_receita,quantidade,data_entrega,baixa_zoomed,fonte_medicacao,observacoes,criado_em) '
                         'VALUES(?,?,?,?,?,?,?) RETURNING id_entrega',tuple(new.values())).fetchone()
        new['id_entrega']=row[0];expected['entregas'].append(new)
        changes.append({'id_entrega':row[0],'id_animal_doente':56,'antes':None,'depois':new,
                        'motivo':'Identidade do tutor da Mika confirmada; entrega conforme linha 65 do ZooMed.'})
        for change in changes:
            aid=change['id_animal_doente']
            conn.execute('UPDATE esporotricose_doentes_animais SET atualizado_em=? WHERE id_animal_doente=?',(em,aid))
            next(a for a in expected['animais'] if a['id_animal_doente']==aid)['atualizado_em']=em
            conn.execute('INSERT INTO auditoria_eventos '
                         '(acao,entidade,entidade_id,usuario_nome,detalhes_json,criado_em,setor) '
                         "VALUES('entrega_corrigida_confirmacao','esporotricose_entrega',?,'Operação VSATT',?,?,'ambiental')",
                         (str(change['id_entrega']),json.dumps({**change,'lote':LOTE,'fonte_sha256':FONTE_SHA256},ensure_ascii=False,default=str),em))
        after=snapshot(conn)
        if signatures(expected)!=signatures(after):raise ValueError('Conteúdo após correção diverge do previsto; lote desfeito.')
        return {'status':'aplicado','lote':LOTE,'em':em,'antes':totals(before['entregas']),
                'depois':totals(after['entregas']),'mudancas':changes,'assinaturas_depois':signatures(after)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aplicar',action='store_true')
    parser.add_argument('--fonte',type=Path,required=True)
    parser.add_argument('--resultado',type=Path,required=True)
    args=parser.parse_args()
    if hashlib.sha256(args.fonte.read_bytes()).hexdigest()!=FONTE_SHA256:
        raise ValueError('Planilha diferente da conferida.')
    from app_core import db,esporotricose
    from scripts.ativar_acesso_externo_windows import connect
    from scripts.endurecer_web_windows import backup_before_change
    cfg=json.loads(Path('C:/ProgramData/EndemiasWeb/config.json').read_text(encoding='utf-8'))
    if cfg['env']['ENDEMIAS_PG_DATABASE']!='endemias':raise ValueError('Banco diferente do oficial.')
    raw=connect(cfg,readonly=True);conn=db.PostgreSQLConnection(raw)
    try:before=validar(conn);conn.rollback()
    finally:conn.close()
    if not args.aplicar:
        result={'status':'validado_somente_leitura','antes':totals(before['entregas'])}
    else:
        private=Path('C:/ProgramData/EndemiasWeb')/('confirmacoes-zoomed-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        private.mkdir()
        backup=backup_before_change(cfg,private)
        shutil.copy2(args.fonte,private/'zoomed.xlsx')
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
            conn.rollback()
        finally:conn.close()
        result['verificado_nova_conexao']=True
        result['estoque']=esporotricose.estoque_medicacao(db.DatabaseTarget('postgresql','endemias'))['totais']
        (private/'resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    args.resultado.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    return result


if __name__=='__main__':main()
