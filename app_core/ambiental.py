"""Consultas ambientais: fontes exclusivas, sem visitas/focos de arboviroses."""
from app_core import db

FONTES=(('esporotricose_visitas','esporotricose_visita_agentes','id_visita','Esporotricose'),
        ('amostras_animais','amostra_animais_agentes','id_amostra','Amostra de Animais'))


def linhas(target,args):
    result=[]
    conn=db.connect(target)
    try:
        for table,links,key,label in FONTES:
            where=[];params=[]
            for field,op,arg in (('data','>=','d_ini'),('data','<=','d_fim'),('localidade','=','localidade')):
                value=args.get(arg,'')
                if value:
                    where.append(('COALESCE(l.nome,v.localidade)' if field=='localidade' else 'v.'+field)+op+'?');params.append(value)
            agent=args.get('agente','')
            if agent:
                where.append(f'EXISTS(SELECT 1 FROM {links} x JOIN agentes a ON a.id_agente=x.id_agente WHERE x.{key}=v.{key} AND a.nome=?)')
                params.append(agent)
            sql=f'''SELECT v.data,v.id_localidade,COALESCE(l.nome,v.localidade,'Não informada') AS localidade,
                v.quarteirao,COUNT(*) AS registros FROM {table} v
                LEFT JOIN localidades l ON l.id_localidade=v.id_localidade'''
            if where:sql+=' WHERE '+' AND '.join(where)
            sql+=' GROUP BY v.data,v.id_localidade,l.nome,v.localidade,v.quarteirao ORDER BY v.data DESC,localidade'
            for row in conn.execute(sql,params):
                result.append({**db.serialize_row(row),'fonte':label})
        return sorted(result,key=lambda r:(str(r['data']),r['fonte']),reverse=True)
    finally:conn.close()


def resumo(target,args):
    rows=linhas(target,args)
    totals={label:sum(r['registros'] for r in rows if r['fonte']==label) for *_,label in FONTES}
    return {'totais':totals,'registros':sum(totals.values()),'linhas':rows}
