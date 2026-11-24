"""Captura online em piloto, revisão humana e aplicação pelos importadores existentes."""
from pathlib import Path

from flask import Blueprint,jsonify,render_template,request,current_app,redirect,url_for
from app_core import auth,blueprint_helpers as bh,formularios as forms,formularios_kobo as core
from app_core import audit,db,permissoes,campo_protocolo,formulario_campo,formulario_fluxo,formulario_piloto
from app_core.formulario_revisao import versao as etag
from app_core import campo_release

bp=Blueprint('formularios_kobo',__name__)


def user():return bh.usuario_atual() or {}


def tree(tipo,payload=None):
    return core.esquema(tipo,user(),bh.db_target(),(payload or {}).get('versao'))


def item(tipo,ident):
    if not core.permitido(tipo,user()):return None
    row=forms.obter(bh.db_target(),ident)
    if not row or row['tipo_formulario']!=core.KIND_PREFIX+tipo:return None
    if row['usuario_id']!=user().get('id_usuario') and not permissoes.gerencia(user()):return None
    return row


@bp.before_request
def guard():
    if not user():return jsonify({'erro':'Entre novamente para continuar.'}),401
    tipo=(request.view_args or {}).get('tipo')
    if tipo and not core.permitido(tipo,user()):return jsonify({'erro':'Formulário não permitido neste setor/perfil.'}),403


@bp.errorhandler(ValueError)
def invalid(error):return jsonify({'erro':str(error)}),400


@bp.errorhandler(campo_protocolo.ConflitoCampo)
def conflict(error):return jsonify({'erro':str(error)}),409


@bp.get('/formularios/kobo/<tipo>')
def campo(tipo):
    if tipo=='LARVAS':
        return redirect(url_for('laboratorio_lancamentos.page'))
    offline=tipo in formulario_piloto.TIPOS and formulario_piloto.habilitado(user())
    response=current_app.make_response(render_template(
        'formulario_kobo.html',tipo=tipo,titulo=core.TITULOS[tipo],revisao=False,offline=offline,
        avisos_campo=offline))
    if offline:response.headers['X-Endemias-Campo-Offline']='1'
    return response


@bp.get('/formularios/kobo/<tipo>/revisao')
def revisao(tipo):
    if not permissoes.gerencia(user()):return jsonify({'erro':'Revisão reservada à gestão.'}),403
    return render_template('formulario_kobo.html',tipo=tipo,titulo=core.TITULOS[tipo],revisao=True,
                           embutido=request.args.get('embutido')=='1')


@bp.get('/api/formularios/kobo/<tipo>/esquema')
def esquema(tipo):
    ident=request.args.get('envio',type=int)
    row=item(tipo,ident) if ident else None
    if ident and not row:return jsonify({'erro':'Envio não encontrado.'}),404
    try:return jsonify(tree(tipo,row['payload'] if row else None))
    except (OSError,KeyError):return jsonify({'erro':'Definições ainda não instaladas. Avise o responsável pelo sistema.'}),503


@bp.get('/api/formularios/kobo/<tipo>/sessao')
def sessao(tipo):
    from flask_wtf.csrf import generate_csrf
    return jsonify({'usuario':user()['id_usuario'],'csrf':generate_csrf(),
                    'offline':formulario_piloto.habilitado(user())})


@bp.get('/formularios/campo-offline')
def campo_offline():
    if not formulario_piloto.habilitado(user()):
        return redirect('/formularios')
    response=current_app.make_response(render_template('formularios_offline.html',formularios=[
        {'tipo':tipo,'titulo':core.TITULOS[tipo]} for tipo in formulario_piloto.TIPOS],
        avisos_campo=True))
    response.headers['X-Endemias-Campo-Offline']='1'
    return response


@bp.get('/api/formularios/kobo/pacote-offline')
def pacote_offline():
    if not formulario_piloto.habilitado(user()):
        return jsonify({'erro':'Conta fora do piloto offline.'}),403
    try:
        definitions={tipo:tree(tipo) for tipo in formulario_piloto.TIPOS}
    except (OSError, KeyError):
        return jsonify({'erro':'As definições de campo estão indisponíveis.'}),503
    return jsonify({'usuario':user()['id_usuario'],'esquemas':definitions,
                    'release':campo_release.atual(),
                    'referencias':formulario_piloto.catalogos(bh.db_target())})


@bp.get('/api/formularios/kobo/versao-offline')
def versao_offline():
    if not formulario_piloto.habilitado(user()):
        return jsonify({'erro':'Conta fora do piloto offline.'}),403
    return jsonify({'usuario':user()['id_usuario'], **campo_release.atual()})


@bp.get('/api/formularios/kobo/<tipo>/catalogos')
def catalogos(tipo):
    if tipo not in formulario_piloto.TIPOS:return jsonify({'erro':'Catálogo indisponível.'}),404
    return jsonify(formulario_piloto.catalogos(bh.db_target()))


@bp.get('/api/formularios/kobo/<tipo>')
def listar(tipo):
    actor=user()
    if request.args.get('proprios')=='1':actor={**actor,'nivel':'usuario'}
    status=request.args.get('status') or None
    if status is not None and status not in forms.STATUS_VALIDOS:raise ValueError('Filtro de situação inválido.')
    rows=forms.listar(bh.db_target(),tipo=core.KIND_PREFIX+tipo,usuario=actor,status=status,
        mais_antigos=permissoes.gerencia(actor) and status in ('enviado','aprovado'))
    return jsonify({'itens':[{'id':r['id_formulario'],'status':r['status'],'criado_em':r['criado_em'],
        'autor':r['agente_nome'],'motivo':r.get('motivo_devolucao'),
        'etag_rascunho':etag(r) if forms.rascunho_apagavel(r,actor['id_usuario']) else None} for r in rows]})


@bp.get('/api/formularios/kobo/<tipo>/<int:ident>')
def obter(tipo,ident):
    row=item(tipo,ident)
    if not row:return jsonify({'erro':'Envio não encontrado.'}),404
    meta=row['payload'].pop('_captura_campo',{})
    return jsonify({'id':ident,'uuid':row['uuid_cliente'],'payload':row['payload'],'status':row['status'],
        'autor':{'usuario_id':row['usuario_id'],'nome':row['agente_nome'],'enviado_em':row['enviado_em']},
        'captura':meta,'etag':etag(row),'apagavel':forms.rascunho_apagavel(row,user()['id_usuario']),
        'motivo':row['motivo_devolucao']})


@bp.delete('/api/formularios/kobo/<tipo>/<int:ident>')
def apagar_rascunho(tipo,ident):
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or not isinstance(body.get('etag'),str) or len(body['etag'])!=64:
        raise ValueError('Reabra o rascunho para conferir a versão antes de apagar.')
    if body.get('usuario')!=user()['id_usuario']:
        return jsonify({'erro':'A conta mudou. Reabra o formulário.'}),403

    def event(conn):
        audit.registrar_evento(bh.get_db,'formulario_interno_rascunho_apagado',entidade='formularios',
            entidade_id=ident,detalhes={'tipo':tipo},conn=conn)

    if not forms.excluir_rascunho(bh.db_target(),core.KIND_PREFIX+tipo,ident,user()['id_usuario'],
                                  body['etag'],auditar=event):
        return jsonify({'erro':'Rascunho não encontrado.'}),404
    return jsonify({'ok':True})


@bp.post('/api/formularios/kobo/<tipo>')
def salvar(tipo):
    if tipo=='LARVAS':
        return jsonify({'erro':'Registre a leitura na área do Laboratório.'}),403
    body=request.get_json(silent=True)
    if not isinstance(body,dict):raise ValueError('Envio inválido.')
    if not isinstance(body.get('captura'),dict):raise ValueError('Identificação da captura ausente.')
    if body.get('usuario')!=user()['id_usuario']:return jsonify({'erro':'A conta mudou. Reabra o formulário.'}),403
    status=body.get('status')
    if status not in ('rascunho','enviado'):raise ValueError('Situação de envio inválida.')
    payload=body.get('payload')
    if not isinstance(payload,dict):raise ValueError('Preenchimento inválido.')
    definition=tree(tipo,payload)
    formulario_campo.conferir_responsavel(definition,payload)
    conn=bh.get_db()
    try:
        old=conn.execute('SELECT payload_json FROM formularios WHERE uuid_cliente=? AND usuario_id=? AND tipo_formulario=?',(body.get('uuid'),user()['id_usuario'],core.KIND_PREFIX+tipo)).fetchone() if db.table_exists(conn,'formularios') else None
    finally:conn.close()
    import json
    previous=json.loads(old['payload_json']) if old else {}
    payload['correcoes']=previous.get('correcoes',[])
    preparar(definition,payload,previous,publicar=status=='enviado')
    core.validar(definition,payload,publicar=status=='enviado')
    def event(conn,ident,metadata):
        audit.registrar_evento(bh.get_db,'formulario_interno_salvo',entidade='formularios',entidade_id=ident,
            detalhes={'tipo':tipo,'status':status,'revisao':metadata['revisao']},conn=conn)
    ident=forms.salvar(bh.db_target(),core.KIND_PREFIX+tipo,payload,user(),uuid_cliente=body.get('uuid'),
        status=status,captura=body.get('captura'),auditar=event)
    return jsonify({'ok':True,'id':ident,'revisao':body['captura']['revisao']})


def preparar(definition,payload,previous,publicar):
    if definition.get('campo_v2'):
        flow=payload.setdefault('acompanhamento',{})
        if isinstance(flow,dict):
            for key in ('retorno','retorno_evento'):
                flow.pop(key,None)
    formulario_fluxo.preparar(bh.db_target(),definition,payload,previous)
    formulario_piloto.enriquecer(bh.db_target(),definition,payload,previous,publicar)


@bp.post('/api/formularios/kobo/<tipo>/<int:ident>/revisar')
def revisar(tipo,ident):
    if not permissoes.gerencia(user()):return jsonify({'erro':'Revisão reservada à gestão.'}),403
    row=item(tipo,ident)
    if not row:return jsonify({'erro':'Envio não encontrado.'}),404
    body=request.get_json(silent=True)
    if not isinstance(body,dict):raise ValueError('Revisão inválida.')
    return decidir_revisao(tipo,ident,row,body,rapida=body.get('registrar') is True)


@bp.post('/api/formularios/kobo/<tipo>/<int:ident>/aceitar')
def aceitar(tipo,ident):
    if not permissoes.gerencia(user()):return jsonify({'erro':'Revisão reservada à gestão.'}),403
    row=item(tipo,ident)
    if not row:return jsonify({'erro':'Envio não encontrado.'}),404
    body=request.get_json(silent=True) or {}
    if not isinstance(body,dict):raise ValueError('Revisão inválida.')
    payload={key: value for key,value in row['payload'].items() if key!='_captura_campo'}
    return decidir_revisao(tipo,ident,row,{**body,'payload':payload,'decisao':'aprovado','correcoes':[]},rapida=True)


def decidir_revisao(tipo,ident,row,body,rapida=False):
    payload=body.get('payload');decision=body.get('decisao')
    if row['status']=='oficializado' and decision=='aprovado':
        return jsonify({'ok':True,'ja_aplicado':True})
    if not isinstance(body.get('etag'),str) or not body['etag']:raise ValueError('Reabra o envio antes de revisar.')
    if row['status'] not in ('enviado','aprovado'):raise ValueError('Aguarde o envio para revisão pelo agente.')
    if not isinstance(payload,dict):raise ValueError('Preenchimento inválido.')
    definition=tree(tipo,row['payload'])
    original=row['payload'].get('responsavel')
    if original:
        definition['responsavel']=original
        formulario_campo.conferir_responsavel(definition,payload)
    else:payload.pop('responsavel',None)
    payload['correcoes']=formulario_fluxo.correcoes(definition,body.get('correcoes',[]))
    if decision=='aprovado':payload['correcoes']=[]
    preparar(definition,payload,row['payload'],publicar=decision=='aprovado')
    core.validar(definition,payload,publicar=decision=='aprovado')
    def event(conn):
        audit.registrar_evento(bh.get_db,'formulario_interno_revisado',entidade='formularios',entidade_id=ident,detalhes={'tipo':tipo,'decisao':decision},conn=conn)
    if decision=='aprovado' and (rapida or definition.get('campo_v2')) and tipo!='PE_CADASTRO':
        return gravar(tipo,ident,{**row,'payload':payload},definition,aprovacao=body['etag'])
    forms.revisar(bh.db_target(),ident,payload,decision,user(),motivo=body.get('motivo'),esperado=body.get('etag'),auditar=event)
    return jsonify({'ok':True})


@bp.post('/api/formularios/kobo/<tipo>/<int:ident>/oficializar')
def oficializar(tipo,ident):
    if not permissoes.gerencia(user()):return jsonify({'erro':'Aplicação reservada à gestão.'}),403
    row=item(tipo,ident)
    if not row:return jsonify({'erro':'Envio não encontrado.'}),404
    if row['status']=='oficializado':return jsonify({'ok':True,'ja_aplicado':True})
    if row['status']!='aprovado':raise ValueError('Revise e aprove antes de aplicar.')
    if tipo=='PE_CADASTRO':
        raise ValueError('Proposta de cadastro. Atualize o PE na página Pontos Estratégicos.')
    return gravar(tipo,ident,row,tree(tipo,row['payload']))


def gravar(tipo,ident,row,definition,aprovacao=None):
    def event(conn,summary):
        audit.registrar_evento(bh.get_db,'formulario_interno_oficializado',entidade='formularios',entidade_id=ident,
            detalhes={'tipo':tipo,'itens':len(summary)},conn=conn)
    config=Path(current_app.config.get('CONFIG_PATH',Path(current_app.root_path)/'config.json'))
    temp=Path(current_app.config['UPLOAD_TEMP']);temp.mkdir(parents=True,exist_ok=True)
    summary=core.aplicar(bh.db_target(),row,definition,user(),config,temp,event,
                       backup_dir=current_app.config.get('BACKUP_DIR'),aprovacao=aprovacao)
    from app_core.app_setup import invalidar_cache_globals
    invalidar_cache_globals()
    return jsonify({'ok':True,'resumo':summary})


@bp.get('/api/formularios/kobo/<tipo>/referencias')
def referencias(tipo):
    localidade=request.args.get('localidade','');quarteirao=request.args.get('quarteirao','')
    if len(localidade)>200 or len(quarteirao)>40:raise ValueError('Seleção territorial inválida.')
    return jsonify(formulario_campo.referencias(bh.db_target(),localidade,quarteirao))


@bp.post('/api/formularios/kobo/<tipo>/<int:ident>/confirmar-retorno')
def confirmar_retorno(tipo,ident):
    if not permissoes.gerencia(user()):return jsonify({'erro':'Confirmação reservada à gestão.'}),403
    if not item(tipo,ident):return jsonify({'erro':'Envio não encontrado.'}),404
    def event(conn,evento):
        audit.registrar_evento(bh.get_db,'formulario_retorno_confirmado',entidade='formularios',entidade_id=ident,detalhes={'evento':evento,'tipo':tipo},conn=conn)
    event_id=formulario_fluxo.confirmar_retorno(bh.db_target(),ident,user(),event)
    return jsonify({'ok':True,'id_evento':event_id})
