"""Ensaio real de XSS/CSRF/logout apenas em massa sintetica e loopback."""
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
        raise ValueError('Exige worktree isolada')
    runtime=Path(tempfile.mkdtemp(prefix='browser-seguranca-',dir=ROOT/'.venv'))
    database=runtime/'ficticio.db'
    shutil.copyfile(ROOT/'.venv/seguranca-seed.db', database)
    os.environ.update(ENDEMIAS_DB_BACKEND='sqlite',ENDEMIAS_DB_PATH=str(database),
        ENDEMIAS_INSTANCE_DIR=str(runtime), ENDEMIAS_LOG_PATH=str(runtime/'browser.log'),
        ENDEMIAS_BACKUP_DIR=str(runtime/'backups'),ENDEMIAS_BACKUP_COMPLETO_DIR=str(runtime/'completos'),
        ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1')
    from app import create_app
    from playwright.sync_api import sync_playwright
    from waitress import create_server
    application=create_app({'REQUIRE_SESSION_TOKEN':True,'CSP_REPORT_ONLY':False})
    connection=sqlite3.connect(database)
    connection.execute("UPDATE usuarios SET nivel='superadmin' WHERE usuario='admin'")
    connection.commit();connection.close()
    from app_core import backup
    backup_info=backup.criar_backup_sqlite(database,destino_dir=runtime/'backups',manter=10)
    backup_path=Path(backup_info['arquivo'])
    server=create_server(application,host='127.0.0.1',port=5007,threads=4)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    url='http://127.0.0.1:5007'
    payload='<img src=x onerror="window.__xss=1"><svg onload="window.__xss=2">&\"\''
    errors=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            for bypass in (True,False):
                context=browser.new_context(bypass_csp=bypass)
                page=context.new_page()
                page.on('pageerror',lambda error: errors.append(str(error)))
                page.goto(url+'/login')
                page.locator('[name=usuario]').fill('admin')
                page.locator('[name=senha]').fill('SenhaSomenteDeTeste123!')
                page.locator('button[type=submit]').click();page.wait_for_url(url+'/')
                def api(route):
                    fieldnames=('data','sispncd','agentes','localidade','logradouro','numero','numero_ovitrampa','tratou_imovel_extra','codigo_pe','ponto_estrategico','motivo_visita','animal_capturado','ocorrencia_residencia','houve_acidente','houve_captura')
                    row={k:payload for k in fieldnames}
                    row.update(destino_tratamento='Ponto Estratégico',pe_vinculos=1,quantidade=1)
                    route.fulfill(json={'total':1,'registros':[row], 'totais':{},'por_destino':[{'destino':payload}], 'por_localidade':[{'localidade':payload}], 'por_motivo':[{'motivo_visita':payload}], 'por_tipo':[{'tipo_animal':payload}]})
                page.route('**/api/bri**',api)
                page.route('**/api/amostras-animais**',api)
                for path,body,button in (('/bri','#bri-body','#bri-acao-1'),('/amostras-animais','#am-body','#amostras_animais-acao-1')):
                    response=page.goto(url+path)
                    page.locator(body).get_by_text(payload,exact=True).first.wait_for()
                    page.locator(button).click()
                    assert page.locator(body+' img, '+body+' svg').count()==0
                    assert page.evaluate('window.__xss || 0')==0
                    if not bypass:
                        assert "script-src-attr 'none'" in response.headers['content-security-policy']
                        page.evaluate("document.body.insertAdjacentHTML('beforeend', '<img src=x onerror=\"window.__xss=3\">')")
                        page.wait_for_timeout(150)
                        assert page.evaluate('window.__xss || 0')==0
                page.goto(url+'/mapa')
                safe=page.evaluate('''payload => {
                    const el=document.createElement('div');
                    el.innerHTML=oviPopup({localidade:payload,rua:payload,numero:payload,ovitrampa_id:payload,quarteirao:payload});
                    mostrarDetalhe({Localidade:payload,id_quart:payload});
                    return !el.querySelector('img,svg') && !document.getElementById('sel-info').querySelector('img,svg');
                }''',payload)
                assert safe
                if not bypass:
                    page.goto(url+'/admin/sistema/backups/baixar/'+backup_path.name)
                    phrase='Frase inteiramente ficticia de transporte!'
                    page.locator('[name=senha_backup]').fill(phrase)
                    page.locator('[name=confirmar]').fill(phrase)
                    with page.expect_download() as event:
                        page.locator('button[type=submit]').filter(has_text='Preparar e baixar').click()
                    encrypted=runtime/'copia-ficticia.7z'
                    event.value.save_as(encrypted)
                    import py7zr
                    with py7zr.SevenZipFile(encrypted,'r',password=phrase) as archive:
                        archive.extractall(runtime/'restaurado')
                    assert (runtime/'restaurado'/backup_path.name).read_bytes()==backup_path.read_bytes()
                state=context.storage_state()
                token=page.locator('meta[name=csrf-token]').get_attribute('content')
                result=context.request.post(url+'/logout',form={'csrf_token':token},max_redirects=0)
                assert result.status==302
                stolen=browser.new_context(storage_state=state)
                denied=stolen.request.get(url+'/api/bri',max_redirects=0)
                assert denied.status in (302,401)
                stolen.close();context.close()
            assert not errors, errors
            browser.close()
        result={'ok':True,'xss_escapado_sem_csp':True,'csp_bloqueia_eventos_injetados':True,'mapa_escapado':True,
                'cookie_copiado_revogado_no_logout':True,'csrf_real':True,'download_criptografado_restaurado':True,'javascript_errors':errors}
        (ROOT/'.venv/browser-seguranca-resultado.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally:
        server.close();thread.join(timeout=3)


if __name__=='__main__':
    main()
