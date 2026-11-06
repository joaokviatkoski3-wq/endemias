"""Definições privadas e validação da captura interna equivalente ao Kobo.

Os catálogos nominais não pertencem ao Git nem ao cache offline do RG.
"""
from datetime import date,time,datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re

from app_core import formulario_condicoes as cond
from app_core import setores,permissoes,rg_formulario

TITULOS={'PE':'Ponto Estratégico','TB':'Tratamento de Bloqueio','TBO':'Tratamento de Bloqueio — Ovitrampas',
    'PVE':'Pesquisa Vetorial Especial','LIRAA':'LIRAa — visita de campo','LARVAS':'Resultados de laboratório',
    'BRI':'BRI','RECOLHIMENTO':'Recolhimento de materiais','ESPOROTRICOSE':'Esporotricose — visita e animais',
    'AMOSTRA_ANIMAIS':'Amostras de Animais'}
KIND_PREFIX='kobo_'


def label(value):
    if isinstance(value,list):return next((label(v) for v in value if label(v)),'')
    if isinstance(value,dict):return next((label(v) for v in value.values() if label(v)),'')
    return str(value or '')


def carregar(tipo):
    path=Path(os.environ.get('ENDEMIAS_FORMULARIOS_KOBO_SCHEMA',r'C:\ProgramData\EndemiasWeb\formularios-kobo.json'))
    data=json.loads(path.read_text(encoding='utf-8'))
    matches=[f for f in data.get('forms',[]) if f['tipo']==tipo]
    if len(matches)!=1:raise ValueError('Definição do formulário indisponível.')
    return matches[0]


def permitido(tipo,usuario):
    if usuario.get('nivel') not in {'usuario','operador','admin','superadmin'} and not (tipo=='LARVAS' and usuario.get('acesso_laboratorio')):return False
    if tipo not in setores.tipos_kobo():return False
    if usuario.get('somente_laboratorio') and not permissoes.gerencia(usuario) and tipo!='LARVAS':return False
    return tipo!='LARVAS' or permissoes.gerencia(usuario) or bool(usuario.get('acesso_laboratorio'))


def catalogo(usuario):
    return [{'tipo':KIND_PREFIX+k,'titulo':v,'descricao':'Piloto online; revisão antes da gravação.',
             'href_campo':'/formularios/kobo/'+k,'href_revisao':'/formularios/kobo/'+k+'/revisao'}
            for k,v in TITULOS.items() if permitido(k,usuario)]


def compilar(definicao):
    """Árvore conserva os caminhos originais de grupos e repetições."""
    nodes=[];stack=[];children=nodes;choices={}
    for row in definicao.get('choices',[]):
        choices.setdefault(str(row.get('list_name','')),[]).append({
            'value':str(row.get('$autovalue') or row.get('name') or ''),
            'label':label(row.get('label')),
            'attrs':{k:str(v) for k,v in row.items() if not k.startswith('$') and k!='label' and not isinstance(v,(dict,list))}})
    for row in definicao['survey']:
        kind=str(row.get('type',''));name=str(row.get('$autoname') or row.get('name') or '')
        if kind in ('end_group','end_repeat'):
            if not stack:raise ValueError('Grupo não balanceado.')
            stack.pop();children=stack[-1]['children'] if stack else nodes;continue
        if kind in ('start','end','note','calculate'):continue
        if not name or '/' in name:raise ValueError('Nome de campo inválido.')
        path='/'.join([n['name'] for n in stack]+[name])
        node={'name':name,'path':path,'kind':kind,'label':label(row.get('label')) or name.replace('_',' '),
              'hint':label(row.get('hint')),'required':cond.analisar(row.get('required') or False),
              'relevant':cond.analisar(row.get('relevant')),'constraint':cond.analisar(row.get('constraint')),
              'constraint_message':label(row.get('constraint_message')),
              'filter':cond.analisar(row.get('choice_filter'))}
        if kind in ('begin_group','begin_repeat'):
            node['children']=[];children.append(node);stack.append(node);children=node['children'];continue
        if kind not in ('integer','decimal','text','date','time','hidden','select_one','select_multiple'):
            raise ValueError('Tipo de campo não suportado: '+kind)
        list_name=row.get('select_from_list_name') or row.get('select_from_list') or ''
        node['options']=choices.get(str(list_name),[])
        node['default']=row.get('default','')
        if kind=='date' and name in {'Data','Digite_a_data','Data_leitura','Data_da_coleta'}:
            node['required']=cond.analisar(True)
        children.append(node)
    if stack:raise ValueError('Grupo não balanceado.')
    version=hashlib.sha256(json.dumps(definicao,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'tipo':definicao['tipo'],'titulo':TITULOS[definicao['tipo']],'versao':version,'nodes':nodes}


def percorrer(nodes):
    for node in nodes:
        yield node
        yield from percorrer(node.get('children',[]))


def esquema(tipo,usuario,target):
    if not permitido(tipo,usuario):raise PermissionError('Formulário não permitido para este perfil/setor.')
    tree=compilar(carregar(tipo))
    # Mesma restrição nominal usada no RG: usuário básico só escolhe o próprio agente.
    if usuario.get('nivel')=='usuario':
        from app_core.agentes import chave_nome
        names={chave_nome(a['nome']) for a in rg_formulario.contexto(target,usuario)['agentes']}
        for node in percorrer(tree['nodes']):
            if 'options' in node and ('agente' in node['name'].lower() or 'laboratorista' in node['name'].lower()):
                allowed=names|{chave_nome(usuario.get('nome',''))} if 'laboratorista' in node['name'].lower() else names
                node['options']=[o for o in node['options'] if chave_nome(o['label']) in allowed]
    return tree


def validar(tree,payload,publicar=True):
    if not isinstance(payload,dict) or set(payload)-{'versao','values','repeats','inicio','fim'}:
        raise ValueError('Conteúdo do formulário inválido.')
    if payload.get('versao')!=tree['versao']:raise ValueError('A definição mudou; reabra e confira o formulário.')
    values=payload.get('values',{});repeats=payload.get('repeats',{})
    if not isinstance(values,dict) or not isinstance(repeats,dict):raise ValueError('Campos inválidos.')
    if len(json.dumps(payload,ensure_ascii=False).encode())>2*1024*1024:raise ValueError('Formulário excede 2 MB.')
    timestamps={}
    for key in ('inicio','fim'):
        if payload.get(key):
            try:
                if not isinstance(payload[key],str) or len(payload[key])>40:raise ValueError()
                timestamps[key]=datetime.fromisoformat(payload[key])
            except (TypeError,ValueError):raise ValueError('Horário de preenchimento inválido.') from None
    if len(timestamps)==2:
        try:
            if timestamps['fim']<timestamps['inicio']:raise ValueError('Fim do preenchimento anterior ao início.')
        except TypeError:raise ValueError('Fusos dos horários de preenchimento inconsistentes.') from None
    fields={n['path'] for n in percorrer(tree['nodes']) if 'children' not in n}
    repeat_paths={n['path'] for n in percorrer(tree['nodes']) if n['kind']=='begin_repeat'}
    if set(values)-fields or set(repeats)-repeat_paths:raise ValueError('Campo desconhecido.')
    context={p.rsplit('/',1)[-1]:v for p,v in values.items()}
    def check(nodes,raw,ctx,parent_active=True):
        clean={}
        for node in nodes:
            active=parent_active and bool(cond.avaliar(node['relevant'],ctx))
            kind=node['kind'];path=node['path']
            if not active:continue
            if kind=='begin_repeat':
                rows=repeats.get(path,[])
                if not isinstance(rows,list) or len(rows)>100:raise ValueError('Até 100 repetições por grupo.')
                allowed={n['path'] for n in percorrer(node['children']) if 'children' not in n}
                out=[]
                for row in rows:
                    if not isinstance(row,dict) or set(row)-allowed:raise ValueError('Repetição inválida.')
                    local={**ctx,**{p.rsplit('/',1)[-1]:v for p,v in row.items()}}
                    out.append(check(node['children'],row,local))
                clean[path]=out;continue
            if kind=='begin_group':clean.update(check(node['children'],raw,ctx));continue
            value=raw.get(path,'')
            if not isinstance(value,(str,int,float)) or isinstance(value,bool):raise ValueError(node['label']+': valor inválido.')
            if value=='':
                if publicar and cond.avaliar(node['required'],ctx,value):raise ValueError(node['label']+': obrigatório.')
                continue
            if len(str(value))>4000:raise ValueError(node['label']+': texto muito longo.')
            if kind in ('integer','decimal'):
                try:
                    number=float(str(value).replace(',','.'))
                    if not math.isfinite(number) or number<0 or kind=='integer' and not number.is_integer():raise ValueError()
                    value=int(number) if kind=='integer' else number
                except (ValueError,TypeError):raise ValueError(node['label']+': número inválido.') from None
            if kind in ('date','time'):
                try:(date if kind=='date' else time).fromisoformat(str(value))
                except (TypeError,ValueError):raise ValueError(node['label']+': data/horário inválido.') from None
            if kind.startswith('select_'):
                options={o['value'] for o in node['options'] if cond.avaliar(node['filter'],ctx,choice=o['attrs'])}
                selected=str(value).split() if kind=='select_multiple' else [str(value)]
                if not set(selected).issubset(options):raise ValueError(node['label']+': escolha indisponível.')
            if publicar and not cond.avaliar(node['constraint'],ctx,value):
                raise ValueError(node['constraint_message'] or node['label']+': confira o valor.')
            clean[path]=value
        return clean
    return check(tree['nodes'],values,context)


def registro(tree,payload,uuid_cliente):
    from uuid import UUID
    uid=str(UUID(uuid_cliente))
    values=validar(tree,payload)
    agora=datetime.now().isoformat()
    return {**values,'_uuid':'vsatt-'+uid,'start':payload.get('inicio') or agora,
            'end':payload.get('fim') or agora,'_submission_time':agora}


def sincronizar_acs(conn,tree,record):
    from app_core import visitas
    catalog=[]
    for node in percorrer(tree['nodes']):
        if node['name'].casefold() not in {'qual_quais_acs','acs_nome','acs'}:continue
        selected=str(record.get(node['path']) or '').split()
        for option in node['options']:
            if option['value'] in selected and option['value'] not in {'no-acs','no_acs','outros','nenhum'}:
                catalog.append({'codigo':option['value'],'nome':option['label']})
    if catalog:visitas.sincronizar_catalogo_acs(conn,catalog)


def preservar_textos_planilhas(paths):
    """Texto digitado continua texto, mesmo quando começa por '='."""
    from openpyxl import load_workbook
    for path in paths:
        book=load_workbook(path)
        try:
            changed=False
            for sheet in book:
                for row in sheet:
                    for cell in row:
                        if cell.data_type=='f':cell.data_type='s';changed=True
            if changed:book.save(path)
        finally:book.close()


def aplicar(target,form,tree,usuario,config_path,temp_root,auditar,backup_dir=None):
    """Importação e recibo oficial se confirmam na mesma transação ETL."""
    import tempfile
    from app_core import formularios as forms,kobo_api,db,backup
    import etl
    payload=form['payload'];payload.pop('_captura_campo',None)
    record=registro(tree,payload,form['uuid_cliente'])
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def lock(conn):
        suffix=' FOR UPDATE' if getattr(conn,'backend','sqlite')=='postgresql' else ''
        row=conn.execute('SELECT status,payload_json FROM formularios WHERE id_formulario=?'+suffix,(form['id_formulario'],)).fetchone()
        if not row or row['status']!=forms.STATUS_APROVADO:raise ValueError('Envio não aprovado ou já aplicado.')
        actual=json.loads(row['payload_json']);actual.pop('_captura_campo',None)
        if hashlib.sha256(json.dumps(actual,sort_keys=True,ensure_ascii=False).encode()).hexdigest()!=digest:
            raise ValueError('Revisão mudou; confira novamente.')
        sincronizar_acs(conn,tree,record)
    def finish(conn,summary):
        total=sum(int(s.get(k) or 0) for s in summary for k in ('visitas_novas','visitas_atualizadas','coletas_novas','resultados_novos','animais_novos','materiais_novos'))
        if not total:raise ValueError('Nenhum dado foi reconhecido para aplicação.')
        forms.marcar_oficializado(conn,form['id_formulario'],usuario,commit=False)
        auditar(conn,summary)
    with backup.operacao_exclusiva(),tempfile.TemporaryDirectory(prefix='formulario-',dir=temp_root) as folder:
        paths=kobo_api.write_etl_workbooks({tree['tipo']:[record]},config_path,folder,prefix='interno')
        preservar_textos_planilhas(paths)
        if not paths:raise ValueError('Não foi possível preparar o envio.')
        if db.is_sqlite(target):backup.criar_backup_sqlite(target.location,destino_dir=backup_dir,prefixo='antes_formulario')
        larvas=[p for p in paths if Path(p).name.startswith('LARVAS_')]
        work=[p for p in paths if p not in larvas]
        ok,summary=etl.processar_upload(work,larvas,target,str(config_path),etl.Logger(callback=lambda *args:None),
            backup_confirmado=True,tipos_permitidos={tree['tipo']},antes_processar=lock,antes_confirmar=finish)
        if not ok:raise ValueError('Aplicação não concluída. Dados preservados; confira o formulário e os vínculos antes de tentar novamente.')
        return summary
