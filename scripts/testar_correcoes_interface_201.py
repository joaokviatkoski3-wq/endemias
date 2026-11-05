"""Ensaio visual isolado: filtros, detalhes, paginação e texto literal."""
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
    if ROOT == Path('C:/endemias'):
        raise ValueError('Execute somente na worktree de testes.')
    runtime=Path(tempfile.mkdtemp(prefix='interface-201-',dir=ROOT/'.venv'))
    database=runtime/'ficticio.db'
    shutil.copyfile(ROOT/'.venv/seed.db', database)
    os.environ.update(ENDEMIAS_DB_BACKEND='sqlite',ENDEMIAS_DB_PATH=str(database),
        ENDEMIAS_INSTANCE_DIR=str(runtime),ENDEMIAS_SECRET_KEY_PATH=str(runtime/'secret.key'),
        ENDEMIAS_LOG_PATH=str(runtime/'ensaio.log'),ENDEMIAS_ANEXOS_DIR=str(runtime/'anexos'),
        ENDEMIAS_UPLOAD_TEMP=str(runtime/'uploads'),ENDEMIAS_KOBO_CONFIG_PATH=str(runtime/'kobo.json'),
        ENDEMIAS_BACKUP_DIR=str(runtime/'backups'),ENDEMIAS_BACKUP_COMPLETO_DIR=str(runtime/'completos'),
        ENDEMIAS_AMBIENTE='teste',ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1')
    from app import create_app
    from waitress import create_server
    from playwright.sync_api import sync_playwright
    from app_core import pontos_estrategicos
    with sqlite3.connect(database) as c:
        c.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=1")
        c.execute("UPDATE localidades SET nome='Localidade <em>fictícia</em>' WHERE id_localidade=1")
        c.execute("UPDATE recolhimentos SET localidade='Localidade <em>fictícia</em>'")
        c.execute("UPDATE bri_registros SET qual_imovel_extra='Imóvel <em>adicional</em>',quantidade_carga=2.5,local_tratamento='Escola <em>fictícia</em>',logradouro=NULL,numero=NULL")
        c.execute("INSERT INTO coletas(id_coleta,id_visita,num_tubo,tipo_deposito) VALUES('coleta-ficticia','ficticio-visitas','T-FICTICIO','B')")
        c.execute("INSERT INTO resultados_laboratorio(id_coleta,num_tubo,data_coleta,outra_larvas) VALUES('coleta-ficticia','T-FICTICIO','2026-06-01',3)")
        for table,key in [('bri_registros','id_bri'),('recolhimentos','id_recolhimento'),('amostras_animais','id_amostra')]:
            c.executemany(f"INSERT INTO {table} ({key},data,processado_em,localidade) VALUES (?,'2026-06-01','2026-06-01','Localidade Ficticia')",[(f'pagina-{n:04d}',) for n in range(101)])
        pontos_estrategicos.ensure_schema(c)
        c.execute("INSERT INTO pontos_estrategicos(codigo_pe,nome,situacao,id_localidade,quarteirao,logradouro,criado_em,atualizado_em) VALUES('PE-FICTICIO','Ponto <em>fictício</em>',1,1,1,'Rua Ficticia','2026-06-01','2026-06-01')")
    applications={s:create_app(dict(SETORES_ENABLED=True,SETOR=s,SESSION_COOKIE_NAME=s+'_201',
        TERMOS_USO_ENABLED=False,CSP_REPORT_ONLY=False)) for s in ('endemias','ambiental')}
    servers=[]; errors=[]; checks={}
    try:
        urls={}
        for sector,application in applications.items():
            server=create_server(application,host='127.0.0.1',port=0,threads=4,map={})
            servers.append(server); threading.Thread(target=server.run,daemon=True).start()
            urls[sector]='http://localhost:'+str(server.effective_port)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1365,'height':900})
            page.on('pageerror',lambda error:errors.append(str(error)))
            for sector,url in urls.items():
                page.goto(url+'/login')
                page.locator('[name=usuario]').fill('admin')
                page.locator('[name=senha]').fill('SenhaSomenteDeTeste123!')
                page.locator('button[type=submit]').click(); page.wait_for_url(url+'/')
                paths=['/bri','/recolhimentos','/laboratorio','/pontos-estrategicos'] if sector=='endemias' else ['/amostras-animais']
                for path in paths:
                    response=page.goto(url+path+'?d_ini=2026-06-01&d_fim=2026-06-30')
                    assert response.status==200
                    page.locator('table tbody tr').first.wait_for()
                    assert page.locator('table tbody tr').count()>0,(path,errors)
                    if path in ['/laboratorio','/pontos-estrategicos','/recolhimentos']:
                        assert "script-src-attr 'none'" in response.headers.get('content-security-policy','')
                        assert page.locator('table tbody em').count()==0,path
                    if path=='/laboratorio':
                        assert '<em>fictícia</em>' in page.locator('table tbody').inner_text()
                        page.locator('[data-lab-tab="lt-evolucao"]').click()
                        page.locator('[data-lab-tab="lt-tabela"]').click()
                        page.locator('[data-lab-acao="buscar"]').click()
                    elif path=='/pontos-estrategicos':
                        assert '<em>fictício</em>' in page.locator('#pe-body').inner_text()
                        page.locator('[data-pe-acao="abrirPE"]').click()
                        assert page.locator('#pe-modal').evaluate("e=>e.classList.contains('open')")
                        page.locator('[data-pe-acao="fecharPE"]').first.click()
                        page.locator('[data-pe-acao="tab"][data-valor="aliases"]').click()
                    else:
                        prefix={'/bri':'bri','/recolhimentos':'rec','/amostras-animais':'am'}[path]
                        if path=='/bri':
                            local=page.locator('#bri-body tr').first.locator('td').nth(6)
                            assert 'Escola <em>fictícia</em>' in local.inner_text()
                            assert 'Logradouro não informado' in local.inner_text()
                            assert local.locator('em').count()==0
                        page.locator('#'+prefix+'-paginacao').get_by_role('button',name='Próxima').click()
                        page.wait_for_timeout(250)
                        assert page.locator('#'+prefix+'-body tr').count()==2
                        page.locator('#'+prefix+'-paginacao').get_by_role('button',name='Anterior').click()
                        page.wait_for_timeout(250)
                        if path!='/recolhimentos':
                            page.locator('#'+prefix+'-body [data-detalhes-operacionais]').first.click()
                            assert page.locator('dialog[open]').count()==1
                            page.screenshot(path=str(runtime/(path.strip('/')+'-detalhes.png')),full_page=True)
                            page.locator('dialog').get_by_role('button',name='Fechar',exact=True).click()
                        with page.expect_download() as download:
                            page.locator('#'+prefix+'-exportar').click()
                        assert download.value.failure() is None
                    page.screenshot(path=str(runtime/(path.strip('/')+'-desktop.png')),full_page=True)
                    page.set_viewport_size({'width':390,'height':844})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),path
                    page.set_viewport_size({'width':1365,'height':900})
                    checks[sector+path]=True
            assert not errors,errors
            browser.close()
        result={'ok':True,'checks':checks,'errors':errors,'evidencias':str(runtime)}
        (ROOT/'.venv/interface-201-resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True))
    finally:
        for server in servers:
            for channel in list(server._map.values()): channel.close()
            server.task_dispatcher.shutdown()


if __name__=='__main__':main()
