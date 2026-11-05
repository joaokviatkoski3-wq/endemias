"""Checks adicionais executados pela identidade limitada, sem autenticar pessoas."""
from pathlib import Path
import json


def verificar(config, root, endemias):
    from app_core import dominios, setores
    from werkzeug.test import Client
    env = config['env']
    assert env.get('ENDEMIAS_SETORES_ENABLED') == '1'
    paths = {'endemias':Path(env.get('ENDEMIAS_KOBO_CONFIG_PATH',str(root/'kobo_config.json')))}
    paths['ambiental'] = paths['endemias'].with_name('kobo_ambiental.json')
    values = {}
    for sector, path in paths.items():
        # Abrir sem escrever/truncar confere a permissao real da conta do servidor.
        with path.open('r+b') as stream:
            values[sector] = json.load(stream)
        assert set(values[sector]['assets']).issubset(setores.TIPOS_KOBO[sector])
    assert values['endemias']['api_token'] == values['ambiental']['api_token']
    dispatcher = dominios.application(endemias)
    client = Client(dispatcher)
    headers = {'CF-Connecting-IP':'203.0.113.21','X-Forwarded-Proto':'https'}
    request_options = {'headers':headers,'environ_overrides':{'REMOTE_ADDR':'127.0.0.1'}}
    domain = dominios.dominio_base(endemias.config)
    for sector, title in setores.TITULOS.items():
        base = 'https://'+sector+'.'+domain
        response = client.get('/login',base_url=base,**request_options)
        assert response.status_code == 200 and title in response.get_data(as_text=True)
        assert config['version'] in response.get_data(as_text=True)
        assert client.get('/api/dashboard',base_url=base,**request_options).status_code == 401
    response = client.get('/',base_url='https://'+domain,**request_options)
    assert response.status_code == 200 and 'Set-Cookie' not in response.headers
    assert config['version'] in response.get_data(as_text=True)
    assert client.get('/',base_url='https://nao-configurado.'+domain,**request_options).status_code == 400
    assert endemias.secret_key != dispatcher.applications['ambiental.'+domain].secret_key
    # Conferir leitura dos novos arquivos e consultas na identidade real, sem login
    # fictício nem escrita operacional na produção.
    ambiental=dispatcher.applications['ambiental.'+domain]
    for template in ('ambiental_home.html','ambiental_painel.html','ambiental_relatorios.html','ambiental_filtros.html','ambiental_mapa.html'):
        ambiental.jinja_env.get_template(template)
    for relative in ('css/ambiental.css','js/ambiental_dashboard.js','icons/agua.svg',
                     'vendor/fullcalendar/index.global.min.js','vendor/fullcalendar/pt-br.global.min.js'):
        assert (Path(ambiental.static_folder)/relative).read_bytes()
    from app_core import ambiental as indicadores,db
    target=db.configured_target(ambiental.config)
    indicadores.resumo(target,{'d_ini':'9999-01-01'})
    indicadores.opcoes(target)
    return {'kobo_ambiental_leitura_gravacao':True,'kobo_formularios_separados':True,
        'logins_dos_setores':True,'apis_anonimas_negadas':True,'portal_sem_sessao':True,
        'host_desconhecido_negado':True,'chaves_por_setor_distintas':True,
        'interface_ambiental_leitura':True,'indicadores_ambientais_consulta':True,'portal_versao_atual':True}
