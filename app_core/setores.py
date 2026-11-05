"""Fronteira de setor independente do nivel; ativada explicitamente na implantacao."""
from flask import current_app, has_app_context, jsonify, render_template, request

SETORES = ('endemias','ambiental')
TITULOS = {'endemias':'Setor de Endemias','ambiental':'Vigilância Ambiental'}
TIPOS_KOBO = {
    'ambiental': frozenset({'ESPOROTRICOSE','AMOSTRA_ANIMAIS'}),
    'endemias': frozenset({'PE','TB','TBO','PVE','LIRAA','LARVAS','BRI','RECOLHIMENTO'}),
}
COMPARTILHADOS = frozenset({'home','dashboard','meteorologia','agenda','mapa','processar','usuarios','controle_pessoal','auditoria','sistema'})
AMBIENTAL = frozenset({'esporotricose','amostras_animais','vigiagua','relatorios_ambientais'})


def atual():
    if not has_app_context() or not current_app.config.get('SETORES_ENABLED'):
        return None
    return current_app.config['SETOR']


def pode_entrar(usuario, setor=None):
    setor = setor or atual()
    if setor is None:
        return True
    return bool(usuario) and (usuario.get('nivel') in {'admin','superadmin'}
        or usuario.get('setor','endemias') == setor)


def url_portal(usuario):
    if not atual() or not usuario:return None
    from app_core.dominios import dominio_base
    return 'https://'+dominio_base(current_app.config)


def atalho_outro_setor(usuario):
    """Destino canônico externo, ou a mesma máquina na entrada LAN independente."""
    if not atual():return None
    outro='ambiental' if atual()=='endemias' else 'endemias'
    if not pode_entrar(usuario,outro):return None
    if current_app.config.get('ACESSO_EXTERNO'):
        from app_core.dominios import dominio_base
        url='https://'+outro+'.'+dominio_base(current_app.config)
    else:
        from ipaddress import ip_address
        from urllib.parse import urlsplit
        host=urlsplit(request.host_url).hostname
        if host!='localhost':
            try:
                address=ip_address(host)
                if address.version!=4 or not address.is_private or address.is_unspecified:return None
            except ValueError:return None
        key='AMBIENTAL_LOCAL_PORT' if outro=='ambiental' else 'ENDEMIAS_LOCAL_PORT'
        port=int(current_app.config.get(key,5004 if outro=='ambiental' else 5000))
        url=f'http://{host}:{port}'
    return {'url':url,'titulo':TITULOS[outro],'curto':'Ambiental' if outro=='ambiental' else 'Endemias'}


def permite_modulo(chave):
    setor=atual()
    if setor is None and chave in {'vigiagua','relatorios_ambientais'}:
        return False
    if setor is None or chave in COMPARTILHADOS:
        return True
    return chave in AMBIENTAL if setor=='ambiental' else chave not in AMBIENTAL


def permite_endpoint(endpoint):
    setor=atual()
    if not setor or not endpoint:
        return True
    blueprint=endpoint.split('.')[0]
    if blueprint in {'static','auth','ajuda','home','meteorologia','agenda','admin','controle_pessoal','processar'}:
        return True
    if setor=='endemias':
        return blueprint in {'acoes_setor','bri','boletim_mensal','conta_ovos_sispncd',
            'consultas','exportacoes','formularios','laboratorio_lancamentos','liraa','mapa',
            'notificacoes','ovitrampas','pontos_estrategicos','recolhimentos','registro_geografico','relatorio_agente'}
    return (blueprint in {'esporotricose','amostras_animais','ambiental'}
        or endpoint in {'consultas.dashboard','consultas.api_dashboard','mapa.page','mapa.api_mapa'})


def tipos_kobo():
    setor=atual()
    return TIPOS_KOBO[setor] if setor else frozenset().union(*TIPOS_KOBO.values())


def ensure_schema(conn):
    if getattr(conn,'backend','sqlite')=='postgresql':
        for table in ('usuarios','agenda_eventos','importacoes','auditoria_eventos'):
            conn.execute('SELECT setor FROM '+table+' LIMIT 0')
        return
    from app_core import import_history,audit
    audit.garantir_tabela_auditoria(lambda:conn,conn)
    import_history.garantir_tabela_importacoes(lambda:conn,conn)
    for tabela in ('usuarios','agenda_eventos','importacoes','auditoria_eventos'):
        cols={r[1] for r in conn.execute('PRAGMA table_info('+tabela+')')}
        if cols and 'setor' not in cols:
            default='legado' if tabela in {'importacoes','auditoria_eventos'} else 'endemias'
            allowed="'endemias','ambiental','legado'" if tabela in {'importacoes','auditoria_eventos'} else "'endemias','ambiental'"
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN setor TEXT NOT NULL DEFAULT '{default}' CHECK(setor IN ({allowed}))")
    conn.commit()
    from app_core import sessoes
    sessoes.ensure_schema(conn)


def configurar(app):
    if not app.config.get('SETORES_ENABLED'):return
    if app.config.get('SETOR') not in SETORES:
        raise ValueError('Setor invalido; nao iniciar area sem fronteira definida.')
    @app.before_request
    def fronteira():
        if request.endpoint in {'static','auth.login','auth.esqueci_senha','auth.recuperar_senha','auth.logout'}:
            return None
        from app_core import auth,db
        user=auth.usuario_atual(lambda sql,p=(): db.query_one(db.configured_target(app.config),sql,p))
        if user and (not pode_entrar(user) or not permite_endpoint(request.endpoint)):
            if request.path.startswith('/api/'):
                return jsonify({'erro':'Acesso não permitido neste setor.'}),403
            return render_template('403.html'),403


def dividir_kobo(config):
    """Prepara duas configuracoes em memoria; nao le/grava segredos nem chama o Kobo."""
    from copy import deepcopy
    result={}
    for sector,types in TIPOS_KOBO.items():
        value=deepcopy(config)
        for key in ('assets','last_sync'):
            value[key]={k:v for k,v in (config.get(key) or {}).items() if k in types}
        result[sector]=value
    return result
