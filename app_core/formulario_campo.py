"""Apoios de campo: identidade autenticada e referências territoriais sem dados de moradores."""
import re
import unicodedata

from app_core import db,escopo_agente


def chave(value):
    value=unicodedata.normalize('NFKD',str(value or '')).casefold()
    return re.sub('[^a-z0-9]','',value)


def equipe(node):
    return node.get('kind') in ('select_one','select_multiple') and any(k in chave(node['name']) for k in ('agente','laboratorista'))


def preparar(tree,usuario,target):
    from app_core.formularios_kobo import percorrer
    own=escopo_agente.agente_proprio(target,usuario)
    names={chave(own[k]) for k in ('nome','nome_completo')} if own else set()
    fields={}
    for node in percorrer(tree['nodes']):
        if equipe(node):
            node['equipe']=True
            matches=[o['value'] for o in node['options'] if chave(o['label']) in names]
            if len(matches)==1:fields[node['path']]=matches[0]
        name=chave(node['name'])
        node['geo']='localidade' if name.startswith('localidade') else 'quarteirao' if name.startswith(('quarteir','quarteiro')) else 'logradouro' if name.startswith('logradouro') else ''
    tree['responsavel']={'usuario_id':usuario['id_usuario'],'nome':usuario.get('nome') or usuario.get('usuario'),
        'id_agente':own['id_agente'] if own else None,'agente':own['nome'] if own else None,'campos':fields}
    return tree


def conferir_responsavel(tree,payload,publicar=False):
    """O responsável vem do servidor; nunca de um nome enviado pelo navegador."""
    from app_core.formularios_kobo import percorrer
    responsible=tree['responsavel']
    for node in percorrer(tree['nodes']):
        if not equipe(node):continue
        code=responsible['campos'].get(node['path'])
        if not code:
            if publicar:raise ValueError('Vincule sua conta a um agente ativo compatível com este formulário antes de enviar. O rascunho pode ser salvo.')
            continue
        value=str(payload.get('values',{}).get(node['path'],''))
        selected=value.split() if node['kind']=='select_multiple' else [value]
        if code not in selected:raise ValueError('O agente responsável pelo envio deve permanecer selecionado.')
    payload['responsavel']=responsible


def referencias(target,localidade,quarteirao=''):
    """Somente nomes de ruas e números de quadra, sem imóveis ou produção nominal."""
    from app_core import registro_geografico as rg
    conn=db.connect(target)
    try:
        rows=[dict(r) for r in conn.execute('SELECT id_localidade,nome FROM localidades')]
        matches=[r for r in rows if chave(r['nome'])==chave(localidade)]
        if len(matches)!=1:return {'quarteiroes':[],'logradouros':[]}
        ident=matches[0]['id_localidade'];blocks=set();streets=set()
        for table in ('registro_geografico_quarteiroes',):
            if db.table_exists(conn,table):
                for row in conn.execute('SELECT DISTINCT quarteirao FROM '+table+' WHERE id_localidade=?',(ident,)):
                    if row[0]:blocks.add(rg._quarteirao_display(str(row[0])))
        if db.table_exists(conn,'registro_geografico_quarteiroes_geometrias'):
            for row in conn.execute('SELECT DISTINCT g.quarteirao FROM registro_geografico_quarteiroes_geometrias g JOIN registro_geografico_geojson_importacoes i ON i.id_importacao=g.id_importacao WHERE g.id_localidade=? AND i.ativo=?',(ident,True)):
                if row[0]:blocks.add(rg._quarteirao_display(str(row[0])))
        if quarteirao and db.table_exists(conn,'registro_geografico_imoveis'):
            for row in conn.execute("SELECT DISTINCT logradouro FROM registro_geografico_imoveis WHERE id_localidade=? AND quarteirao=? AND TRIM(COALESCE(logradouro,''))<>''",(ident,rg._quarteirao(quarteirao))):
                streets.add(row[0])
        return {'quarteiroes':sorted(blocks,key=lambda q:(not q.isdigit(),int(q) if q.isdigit() else 0,q)),
                'logradouros':sorted(streets,key=chave)}
    finally:conn.close()
