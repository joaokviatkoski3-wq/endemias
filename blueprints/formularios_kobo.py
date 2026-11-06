"""Captura online em piloto, revisão humana e aplicação pelos importadores existentes."""
import hashlib
from pathlib import Path

from flask import Blueprint,jsonify,render_template,request,current_app
from app_core import auth,blueprint_helpers as bh,formularios as forms,formularios_kobo as core
from app_core import audit,db,permissoes,campo_protocolo,formulario_campo

bp=Blueprint('formularios_kobo',__name__)


def user():return bh.usuario_atual() or {}


def tree(tipo):return core.esquema(tipo,user(),bh.db_target())


def item(tipo,ident):
    if not core.permitido(tipo,user()):return None
    row=forms.obter(bh.db_target(),ident)
    if not row or row['tipo_formulario']!=core.KIND_PREFIX+tipo:return None
    if row['usuario_id']!=user().get('id_usuario') and not permissoes.gerencia(user()):return None
    return row


def etag(row):return hashlib.sha256((row['payload_json']+'|'+row['status']).encode()).hexdigest()


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
    return render_template('formulario_kobo.html',tipo=tipo,titulo=core.TITULOS[tipo],revisao=False)


@bp.get('/formularios/kobo/<tipo>/revisao')
def revisao(tipo):
    if not permissoes.gerencia(user()):return jsonify({'erro':'Revisão reservada à gestão.'}),403
    return render_template('formulario_kobo.html',tipo=tipo,titulo=core.TITULOS[tipo],revisao=True)


@bp.get('/api/formularios/kobo/<tipo>/esquema')
def esquema(tipo):
    try:return jsonify(tree(tipo))
    except (OSError,KeyError):return jsonify({'erro':'Definições ainda não instaladas. Avise o responsável pelo sistema.'}),503


@bp.get('/api/formularios/kobo/<tipo>/sessao')
def sessao(tipo):
    from flask_wtf.csrf import generate_csrf
    return jsonify({'usuario':user()['id_usuario'],'csrf':generate_csrf()})


@bp.get('/api/formularios/kobo/<tipo>')
def listar(tipo):
    actor=user()
    if request.args.get('proprios')=='1':actor={**actor,'nivel':'usuario'}
    status=request.args.get('status') or None
    if status is not None and status not in forms.STATUS_VALIDOS:raise ValueError('Filtro de situação inválido.')
    rows=forms.listar(bh.db_target(),tipo=core.KIND_PREFIX+tipo,usuario=actor,status=status,
        mais_antigos=permissoes.gerencia(actor) and status in ('enviado','aprovado'))
    return jsonify({'itens':[{'id':r['id_formulario'],'status':r['status'],'criado_em':r['criado_em'],
        'autor':r['agente_nome'],'motivo':r.get('motivo_devolucao')} for r in rows]})


@bp.get('/api/formularios/kobo/<tipo>/<int:ident>')
def obter(tipo,ident):
    row=item(tipo,ident)
    if not row:return jsonify({'erro':'Envio não encontrado.'}),404
    meta=row['payload'].pop('_captura_campo',{})
    return jsonify({'id':ident,'uuid':row['uuid_cliente'],'payload':row['payload'],'status':row['status'],
        'autor':{'usuario_id':row['usuario_id'],'nome':row['agente_nome'],'enviado_em':row['enviado_em']},'captura':meta,'etag':etag(row),'motivo':row['motivo_devolucao']})


@bp.post('/api/formularios/kobo/<tipo>')
def salvar(tipo):
    body=request.get_json(silent=True)
    if not isinstance(body,dict):raise ValueError('Envio inválido.')
    if not isinstance(body.get('captura'),dict):raise ValueError('Identificação da captura ausente.')
    if body.get('usuario')!=user()['id_usuario']:return jsonify({'erro':'A conta mudou. Reabra o formulário.'}),403
    status=body.get('status')
    if status not in ('rascunho','enviado'):raise ValueError('Situação de envio inválida.')
    payload=body.get('payload');definition=tree(tipo)
    if not isinstance(payload,dict):raise ValueError('Preenchimento inválido.')
    formulario_campo.conferir_responsavel(definition,payload,publicar=status=='enviado')
    core.validar(definition,payload,publicar=status=='enviado')
    def event(conn,ident,metadata):
        audit.registrar_evento(bh.get_db,'formulario_interno_salvo',entidade='formularios',entidade_id=ident,
            detalhes={'tipo':tipo,'status':status,'revisao':metadata['revisao']},conn=conn)
    ident=forms.salvar(bh.db_target(),core.KIND_PREFIX+tipo,payload,user(),uuid_cliente=body.get('uuid'),
        status=status,captura=body.get('captura'),auditar=event)
    return jsonify({'ok':True,'id':ident,'revisao':body['captura']['revisao']})


@bp.post('/api/formularios/kobo/<tipo>/<int:ident>/revisar')
def revisar(tipo,ident):
    if not permissoes.gerencia(user()):return jsonify({'erro':'Revisão reservada à gestão.'}),403
    row=item(tipo,ident)
    if not row:return jsonify({'erro':'Envio não encontrado.'}),404
    body=request.get_json(silent=True)
    if not isinstance(body,dict):raise ValueError('Revisão inválida.')
    payload=body.get('payload');decision=body.get('decisao')
    if not isinstance(body.get('etag'),str) or not body['etag']:raise ValueError('Reabra o envio antes de revisar.')
    if row['status'] not in ('enviado','aprovado'):raise ValueError('Aguarde o envio para revisão pelo agente.')
    definition=tree(tipo)
    if not isinstance(payload,dict):raise ValueError('Preenchimento inválido.')
    original=row['payload'].get('responsavel')
    if original:
        definition['responsavel']=original
        formulario_campo.conferir_responsavel(definition,payload,publicar=decision=='aprovado')
    else:payload.pop('responsavel',None)
    core.validar(definition,payload,publicar=decision=='aprovado')
    def event(conn):
        audit.registrar_evento(bh.get_db,'formulario_interno_revisado',entidade='formularios',entidade_id=ident,detalhes={'tipo':tipo,'decisao':decision},conn=conn)
    forms.revisar(bh.db_target(),ident,payload,decision,user(),motivo=body.get('motivo'),esperado=body.get('etag'),auditar=event)
    return jsonify({'ok':True})


@bp.post('/api/formularios/kobo/<tipo>/<int:ident>/oficializar')
def oficializar(tipo,ident):
    if not permissoes.gerencia(user()):return jsonify({'erro':'Aplicação reservada à gestão.'}),403
    row=item(tipo,ident)
    if not row:return jsonify({'erro':'Envio não encontrado.'}),404
    if row['status']=='oficializado':return jsonify({'ok':True,'ja_aplicado':True})
    if row['status']!='aprovado':raise ValueError('Revise e aprove antes de aplicar.')
    definition=tree(tipo)
    def event(conn,summary):
        audit.registrar_evento(bh.get_db,'formulario_interno_oficializado',entidade='formularios',entidade_id=ident,
            detalhes={'tipo':tipo,'itens':len(summary)},conn=conn)
    config=Path(current_app.config.get('CONFIG_PATH',Path(current_app.root_path)/'config.json'))
    temp=Path(current_app.config['UPLOAD_TEMP']);temp.mkdir(parents=True,exist_ok=True)
    summary=core.aplicar(bh.db_target(),row,definition,user(),config,temp,event,backup_dir=current_app.config.get('BACKUP_DIR'))
    from app_core.app_setup import invalidar_cache_globals
    invalidar_cache_globals()
    return jsonify({'ok':True,'resumo':summary})


@bp.get('/api/formularios/kobo/<tipo>/referencias')
def referencias(tipo):
    localidade=request.args.get('localidade','');quarteirao=request.args.get('quarteirao','')
    if len(localidade)>200 or len(quarteirao)>40:raise ValueError('Seleção territorial inválida.')
    return jsonify(formulario_campo.referencias(bh.db_target(),localidade,quarteirao))
