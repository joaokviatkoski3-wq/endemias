"""Fronteira de setor independente do nivel; ativada explicitamente na implantacao."""
from flask import current_app, has_app_context, jsonify, render_template, request

SETORES = ('endemias','ambiental','geo')
TITULOS = {
    'endemias':'Setor de Endemias',
    'ambiental':'Vigilância Ambiental',
    'geo':'GeoVSATT',
}
TIPOS_KOBO = {
    'ambiental': frozenset({'ESPOROTRICOSE','AMOSTRA_ANIMAIS'}),
    'endemias': frozenset({'PE','TB','TBO','PVE','LIRAA','LARVAS','BRI','RECOLHIMENTO'}),
}
COMPARTILHADOS = frozenset({'home','dashboard','meteorologia','agenda','mapa','processar','usuarios','controle_pessoal','auditoria','sistema'})
AMBIENTAL = frozenset({'esporotricose','amostras_animais','vigiagua','relatorios_ambientais'})


def _ampliar_setor_eventos_sqlite(conn, tabela):
    """Inclui Geo em tabelas de histórico sem atribuir contas ou agendas ao Geo."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
    ).fetchone()
    definition = row[0] if row else ""
    if not definition or "'geo'" in definition:
        return
    allowed = "'endemias','ambiental','legado'"
    if allowed not in definition:
        raise ValueError(f"Restrição de setor inesperada em {tabela}.")
    updated = definition.replace(allowed, allowed + ",'geo'")
    indexes = [
        item[0]
        for item in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
            (tabela,),
        )
    ]
    columns = [item[1] for item in conn.execute(f'PRAGMA table_info("{tabela}")')]
    quoted = ",".join(f'"{column}"' for column in columns)
    previous = tabela + "_antes_geo"
    conn.execute(f'ALTER TABLE "{tabela}" RENAME TO "{previous}"')
    conn.execute(updated)
    conn.execute(f'INSERT INTO "{tabela}" ({quoted}) SELECT {quoted} FROM "{previous}"')
    conn.execute(f'DROP TABLE "{previous}"')
    for sql in indexes:
        conn.execute(sql)


def atual():
    if not has_app_context() or not current_app.config.get('SETORES_ENABLED'):
        return None
    return current_app.config['SETOR']


def pode_entrar(usuario, setor=None):
    setor = setor or atual()
    if setor is None:
        return True
    if setor == 'geo':
        return bool(usuario)
    return bool(usuario) and (usuario.get('nivel') in {'admin','superadmin'}
        or usuario.get('setor','endemias') == setor)


def url_portal(usuario):
    if not atual() or not usuario:return None
    from app_core.dominios import dominio_base
    return 'https://'+dominio_base(current_app.config)


def url_setor(usuario, setor):
    """Destino canônico externo, ou a mesma máquina na entrada LAN independente."""
    if not atual() or setor not in {'ambiental','endemias'} or not pode_entrar(usuario,setor):return None
    if current_app.config.get('ACESSO_EXTERNO'):
        from app_core.dominios import dominio_base
        return 'https://'+setor+'.'+dominio_base(current_app.config)
    else:
        from ipaddress import ip_address
        from urllib.parse import urlsplit
        host=urlsplit(request.host_url).hostname
        if host!='localhost':
            try:
                address=ip_address(host)
                if address.version!=4 or not address.is_private or address.is_unspecified:return None
            except ValueError:return None
        key='AMBIENTAL_LOCAL_PORT' if setor=='ambiental' else 'ENDEMIAS_LOCAL_PORT'
        port=int(current_app.config.get(key,5004 if setor=='ambiental' else 5000))
        return f'http://{host}:{port}'


def atalho_outro_setor(usuario):
    if atual() not in {'ambiental','endemias'}:return None
    outro='ambiental' if atual()=='endemias' else 'endemias'
    url=url_setor(usuario,outro)
    return {'url':url,'titulo':TITULOS[outro],'curto':'Ambiental' if outro=='ambiental' else 'Endemias'} if url else None


def permite_modulo(chave):
    setor=atual()
    if setor == 'geo':
        return False
    if chave=='formularios':return True
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
    if setor == 'geo':
        return blueprint in {'static','auth','ajuda','home','geovsatt'}
    if blueprint=='formularios_kobo' or endpoint=='formularios.page':return True
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
    if setor == 'geo':
        return frozenset()
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
    for tabela in ('importacoes', 'auditoria_eventos'):
        _ampliar_setor_eventos_sqlite(conn, tabela)
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
