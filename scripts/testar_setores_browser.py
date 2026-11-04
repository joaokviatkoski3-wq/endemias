"""Homologacao Chromium/CSRF com contas ficticias e escutas apenas em loopback."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if ROOT == Path(r'C:\endemias'):
        raise ValueError('Execute na worktree de homologacao.')
    runtime = Path(tempfile.mkdtemp(prefix='browser-setores-', dir=ROOT / '.venv'))
    database = runtime / 'ficticio.db'
    shutil.copyfile(ROOT / '.venv/seed.db', database)
    os.environ.update(ENDEMIAS_DB_BACKEND='sqlite', ENDEMIAS_DB_PATH=str(database),
                      ENDEMIAS_INSTANCE_DIR=str(runtime), ENDEMIAS_LOG_PATH=str(runtime / 'browser.log'),
                      ENDEMIAS_BACKUP_DIR=str(runtime / 'backups'),
                      ENDEMIAS_BACKUP_COMPLETO_DIR=str(runtime / 'completos'),
                      ENDEMIAS_AMBIENTE='teste',ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1')
    from app import create_app
    from app_core import dominios
    from waitress import create_server
    from playwright.sync_api import sync_playwright

    applications = {}
    for sector in ('endemias', 'ambiental'):
        applications[sector] = create_app(dict(SETORES_ENABLED=True, SETOR=sector,
            SESSION_COOKIE_NAME=sector+'_local', REQUIRE_SESSION_TOKEN=True,
            TERMOS_USO_ENABLED=False, CSP_REPORT_ONLY=False))
    connection = sqlite3.connect(database)
    try:
        connection.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=1")
        connection.commit()
    finally:
        connection.close()
    applications['portal'] = dominios.portal_application('localhost', external=False)
    servers = []
    errors = []
    checks = {}
    try:
        urls = {}
        for index, (name, application) in enumerate(applications.items()):
            port = 5012 + index
            server = create_server(application, host='127.0.0.1', port=port, threads=4, map={})
            servers.append(server)
            threading.Thread(target=server.run, daemon=True).start()
            urls[name] = f'http://localhost:{port}'
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width':1365,'height':900})
            page = context.new_page()
            page.on('pageerror', lambda error:errors.append(str(error)))
            for sector in ('endemias','ambiental'):
                url = urls[sector]
                page.goto(url+'/login')
                page.locator('[name=usuario]').fill('admin')
                page.locator('[name=senha]').fill('SenhaSomenteDeTeste123!')
                page.locator('button[type=submit]').click()
                page.wait_for_url(url+'/')
                checks[sector+'_login_csrf'] = True
                for path in ('/dashboard','/processar','/agenda','/mapa','/admin/usuarios'):
                    response = page.goto(url+path)
                    assert response.status == 200, (sector,path,response.status)
                    page.wait_for_timeout(500)
                    if path=='/mapa' and sector=='ambiental':
                        page.wait_for_function("document.getElementById('mapa-status').textContent.includes('registro(s) no período')")
                    if path=='/processar' and sector=='ambiental':
                        assert page.locator('[data-kobo-asset]').count()==2
                        assert page.locator('.consolidados-list').count()==0
                if sector=='endemias':
                    response=page.goto(url+'/relatorio-agente?agente=Agente+Ficticio&d_ini=2026-06-01&d_fim=2026-06-03')
                    assert response.status==200
                    page.wait_for_timeout(800)
                if sector=='ambiental':
                    for path in ('/esporotricose','/amostras-animais','/relatorios','/vigiagua'):
                        response=page.goto(url+path)
                        assert response.status==200,(path,response.status)
                        page.wait_for_timeout(300)
                    page.goto(url+'/dashboard')
                    page.screenshot(path=str(runtime/'ambiental-desktop.png'),full_page=True)
                    page.set_viewport_size({'width':390,'height':844})
                    page.reload()
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Overflow no celular'
                    page.screenshot(path=str(runtime/'ambiental-celular.png'),full_page=True)
                    page.set_viewport_size({'width':1365,'height':900})
                checks[sector+'_paginas'] = True
            # Duas sessoes locais convivem no mesmo navegador, apesar de portas compartilharem cookies.
            assert page.goto(urls['endemias']+'/dashboard').status==200
            checks['sessoes_locais_independentes'] = True
            page.goto(urls['portal'])
            assert page.get_by_role('link',name='Setor de Endemias',exact=False).count()==1
            page.screenshot(path=str(runtime/'portal.png'),full_page=True)
            assert not errors, errors
            checks['sem_erros_javascript'] = True
            browser.close()
        result={'ok':True,'checks':checks,'evidencias':str(runtime)}
        (ROOT/'.venv/setores-browser-resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True))
    finally:
        for server in servers:
            for channel in list(server._map.values()):
                channel.close()
            server.task_dispatcher.shutdown()


if __name__=='__main__':
    main()
