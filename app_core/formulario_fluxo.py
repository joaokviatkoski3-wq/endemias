"""Retornos e revisão dirigida, conservados no envelope do formulário (sem DDL)."""
from datetime import date,datetime,time,timedelta
import json
import re
from app_core import db,formularios as forms,formularios_kobo as core,permissoes,setores


def correcoes(tree,items):
    if not isinstance(items,list) or len(items)>100:raise ValueError('Até 100 apontamentos de revisão.')
    fields={n['path']:n for n in core.percorrer(tree['nodes']) if 'children' not in n}
    result=[]
    for item in items:
        if not isinstance(item,dict) or item.get('campo') not in fields:raise ValueError('Campo de correção inválido.')
        text=str(item.get('mensagem') or '').strip()
        if not text or len(text)>500:raise ValueError('Explique a correção em até 500 caracteres.')
        result.append({'campo':item['campo'],'mensagem':text})
    return result


def validar_acompanhamento(conn,value,original=None):
    if value is None:value={}
    if not isinstance(value,dict) or set(value)-{'agenda','ocorrencia','retorno','retorno_evento'}:raise ValueError('Acompanhamento inválido.')
    out={}
    ident=value.get('agenda')
    if ident not in (None,''):
        if isinstance(ident,bool) or not isinstance(ident,int):raise ValueError('Evento inválido.')
        row=conn.execute('SELECT * FROM agenda_eventos WHERE id_evento=? AND setor=?',(ident,setores.atual() or 'endemias')).fetchone()
        if not row or row['tipo']!='campo':raise ValueError('Atividade de campo indisponível neste setor.')
        occurrence=str(value.get('ocorrencia') or '')
        try:day=date.fromisoformat(occurrence)
        except ValueError:raise ValueError('Informe a data da atividade agendada.') from None
        from blueprints.agenda import _eventos_manuais_expandido
        try:occurrences=_eventos_manuais_expandido(row,datetime.combine(day,time.min),datetime.combine(day+timedelta(days=1),time.min))
        except OverflowError:raise ValueError('Data da atividade inválida.') from None
        if not any(str(event['start'])[:10]==day.isoformat() for event in occurrences):
            raise ValueError('A data não corresponde a uma ocorrência da atividade.')
        out.update(agenda=ident,ocorrencia=day.isoformat())
    returned=value.get('retorno')
    if returned:
        if not isinstance(returned,dict) or set(returned)-{'data','hora','observacao'}:raise ValueError('Proposta de retorno inválida.')
        try:
            day=date.fromisoformat(str(returned.get('data','')))
            hour=str(returned.get('hora') or '')
            if hour:
                if not re.fullmatch(r'\d{2}:\d{2}',hour):raise ValueError()
                time.fromisoformat(hour)
        except ValueError:raise ValueError('Confira a data e hora do retorno.') from None
        note=str(returned.get('observacao') or '').strip()
        if len(note)>1000:raise ValueError('Observação de retorno muito longa.')
        out['retorno']={'data':day.isoformat(),'hora':hour,'observacao':note}
    if original and original.get('retorno_evento'):
        if returned!=(original.get('retorno') or {}):raise ValueError('O retorno já foi confirmado. Altere o evento na agenda.')
        out['retorno_evento']=original['retorno_evento']
    return out


def preparar(target,tree,payload,original=None):
    conn=db.connect(target)
    try:payload['acompanhamento']=validar_acompanhamento(conn,payload.get('acompanhamento'),(original or {}).get('acompanhamento'))
    finally:conn.close()


def confirmar_retorno(target,ident,usuario,auditar):
    conn=db.connect(target)
    try:
        if getattr(conn,'backend','sqlite')=='postgresql':
            row=conn.execute('SELECT * FROM formularios WHERE id_formulario=? FOR UPDATE',(ident,)).fetchone()
        else:
            conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM formularios WHERE id_formulario=?',(ident,)).fetchone()
        if not row or row['status'] not in ('aprovado','oficializado'):raise ValueError('Aprove o formulário antes de confirmar o retorno.')
        tipo=row['tipo_formulario'][5:]
        if not core.permitido(tipo,usuario) or not permissoes.gerencia(usuario):raise ValueError('Retorno não permitido neste setor/perfil.')
        payload=json.loads(row['payload_json']);flow=payload.get('acompanhamento') or {}
        if flow.get('retorno_evento'):return flow['retorno_evento']
        flow=validar_acompanhamento(conn,flow);proposal=flow.get('retorno')
        if not proposal:raise ValueError('Não há proposta de retorno neste envio.')
        start=proposal['data']+('T'+proposal['hora'] if proposal['hora'] else '')
        event=db.insert_and_get_id(conn,"""INSERT INTO agenda_eventos
            (titulo,descricao,tipo,data_inicio,dia_inteiro,lembrete_min,cor,criado_por,criado_em,recorrencia,atividade_externa,setor)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",('Retorno — '+core.TITULOS[tipo],
            'Retorno do formulário #'+str(ident)+'. '+proposal['observacao'],'campo',start,
            int(not proposal['hora']),60,'#2563eb',usuario.get('nome'),datetime.now().isoformat(),'nenhuma',1,setores.atual() or 'endemias'),'id_evento')
        flow['retorno_evento']=event;payload['acompanhamento']=flow
        conn.execute('UPDATE formularios SET payload_json=? WHERE id_formulario=?',(json.dumps(payload,ensure_ascii=False),ident))
        auditar(conn,event);conn.commit();return event
    except Exception:conn.rollback();raise
    finally:conn.close()


def enriquecer_agenda(target,events,usuario):
    """Só expõe links de envios próprios ou permitidos à gestão; situação não conclui tarefa."""
    wanted={int(e['extendedProps']['id_evento']) for e in events if e.get('extendedProps',{}).get('origem')=='manual' and e['extendedProps'].get('tipo')=='campo'}
    if not wanted:return events
    conn=db.connect(target)
    try:
        rows=conn.execute("SELECT id_formulario,tipo_formulario,usuario_id,status,payload_json FROM formularios WHERE tipo_formulario LIKE 'kobo_%' AND payload_json LIKE ?",('%"acompanhamento"%',)).fetchall() if db.table_exists(conn,'formularios') else []
        index={}
        for row in rows:
            tipo=row['tipo_formulario'][5:]
            if tipo not in setores.tipos_kobo() or not core.permitido(tipo,usuario):continue
            if row['usuario_id']!=usuario.get('id_usuario') and not permissoes.gerencia(usuario):continue
            flow=json.loads(row['payload_json']).get('acompanhamento') or {}
            if flow.get('agenda') not in wanted:continue
            index.setdefault((flow['agenda'],flow.get('ocorrencia')),[]).append({'id':row['id_formulario'],'tipo':tipo,'status':row['status'],
                'href':'/formularios/kobo/'+tipo+('/revisao' if permissoes.gerencia(usuario) else '')+'?envio='+str(row['id_formulario'])})
        for event in events:
            props=event.get('extendedProps',{});ident=props.get('id_evento')
            if ident not in wanted:continue
            day=str(event['start'])[:10]
            props['formularios_vinculados']=index.get((ident,day),[])
            props['formularios_disponiveis']=[{'titulo':v,'href':'/formularios/kobo/'+k+'?agenda='+str(ident)+'&ocorrencia='+day} for k,v in core.TITULOS.items() if core.permitido(k,usuario)]
        return events
    finally:conn.close()
