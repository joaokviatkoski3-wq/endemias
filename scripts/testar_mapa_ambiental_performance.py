"""Compara rc.2 e candidata com polígonos fictícios e CPU 4x mais lenta.

Sem dados/portas/contas de produção. Tiles são substituídos por PNG local para
não misturar velocidade da internet com custo das etiquetas no navegador.
"""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASELINE='f72df550a6f0897c151baa8fe705fba899ae1b4b'


def main():
    if ROOT==Path('C:/endemias'):raise ValueError('Exige worktree de ensaio.')
    runtime=Path(tempfile.mkdtemp(prefix='mapa-performance-',dir=ROOT/'.venv'))
    database=runtime/'ficticio.db';shutil.copyfile(ROOT/'.venv/seed.db',database)
    os.environ.update(ENDEMIAS_DB_BACKEND='sqlite',ENDEMIAS_DB_PATH=str(database),
        ENDEMIAS_INSTANCE_DIR=str(runtime),ENDEMIAS_SECRET_KEY_PATH=str(runtime/'secret.key'),
        ENDEMIAS_LOG_PATH=str(runtime/'ensaio.log'),ENDEMIAS_ANEXOS_DIR=str(runtime/'anexos'),
        ENDEMIAS_UPLOAD_TEMP=str(runtime/'uploads'),ENDEMIAS_KOBO_CONFIG_PATH=str(runtime/'kobo.json'),
        ENDEMIAS_BACKUP_DIR=str(runtime/'backups'),ENDEMIAS_BACKUP_COMPLETO_DIR=str(runtime/'completos'),
        ENDEMIAS_AMBIENTE='teste',ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1')
    from app import create_app
    from waitress import create_server
    from playwright.sync_api import sync_playwright
    app=create_app(dict(SETORES_ENABLED=True,SETOR='ambiental',SESSION_COOKIE_NAME='performance_local',
        TERMOS_USO_ENABLED=False,CSP_REPORT_ONLY=False))
    server=create_server(app,host='127.0.0.1',port=0,threads=4,map={})
    worker=threading.Thread(target=server.run,daemon=True);worker.start()
    url='http://localhost:'+str(server.effective_port)
    geometry={'type':'FeatureCollection','features':[]}
    def add_feature(i):
        x=-49.31+(i%100)*.00015;y=-25.32+(i//100)*.00015;s=.00012
        geometry['features'].append({'type':'Feature',
            'properties':{'Localidade':1,'Localidade_nome':'Localidade Ficticia','id_quart':str(i+1)},
            'geometry':{'type':'Polygon','coordinates':[[[x,y],[x+s,y],[x+s,y+s],[x,y+s],[x,y]]]}})
    for i in range(1500):add_feature(i)
    previous=subprocess.check_output(['git','-C',str(ROOT),'show',BASELINE+':static/js/ambiental_mapa.js'],text=True,encoding='utf-8')
    current=(ROOT/'static/js/ambiental_mapa.js').read_text(encoding='utf-8')
    instrumentation='''
      L.Map.addInitHook(function(){window.__testMap=this;});
      window.__builds=0;
      const __geoJSON=L.geoJSON;
      L.geoJSON=(...args)=>{window.__builds++;return __geoJSON(...args);};
    '''
    tile=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==')
    results={};errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            for variant,script in [('rc2',previous),('candidata',current)]:
                print('Medindo '+variant+' com geometrias fictícias...',flush=True)
                context=browser.new_context(viewport={'width':1365,'height':900},reduced_motion='reduce')
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                context.new_cdp_session(page).send('Emulation.setCPUThrottlingRate',{'rate':4})
                page.route('**/api/ambiental/territorio',lambda route:route.fulfill(json=geometry))
                page.route('https://server.arcgisonline.com/**',lambda route:route.fulfill(body=tile,content_type='image/png'))
                page.route('**/static/js/ambiental_mapa.js*',lambda route:route.fulfill(body=instrumentation+script,content_type='application/javascript'))
                page.goto(url+'/login');page.locator('[name=usuario]').fill('admin')
                page.locator('[name=senha]').fill('SenhaSomenteDeTeste123!')
                page.locator('button[type=submit]').click();page.wait_for_url(url+'/')
                page.goto(url+'/mapa')
                page.wait_for_function("() => document.getElementById('mapa-status').textContent.includes('1500 polígono(s)')")
                page.wait_for_function("() => !document.getElementById('mapa-ambiental').classList.contains('leaflet-zoom-anim')")
                page.evaluate('window.__testMap.setZoom(17,{animate:false})')
                page.wait_for_timeout(250)
                result=page.evaluate('''async () => {
                  const checkbox=document.getElementById('mapa-etiquetas');
                  const original=document.querySelector('.leaflet-overlay-pane path');
                  const builds=window.__builds,start=performance.now();checkbox.click();
                  const clickMs=performance.now()-start;
                  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
                  const canvas=document.querySelector('.ambiental-labels-canvas');
                  return {click_ms:clickMs,settled_ms:performance.now()-start,zoom:window.__testMap.getZoom(),
                    layer_builds:window.__builds-builds,
                    polygon_identity_preserved:original===document.querySelector('.leaflet-overlay-pane path'),
                    dom_labels:document.querySelectorAll('.ambiental-map-label').length,
                    canvas_count:document.querySelectorAll('.ambiental-labels-canvas').length,
                    visible_labels:canvas?Number(canvas.dataset.labelCount):null,
                    candidates:canvas?Number(canvas.dataset.visibleCandidates):null};
                }''')
                if variant=='candidata':
                    assert result['layer_builds']==0 and result['polygon_identity_preserved'],result
                    assert result['dom_labels']==0 and result['canvas_count']==1,result
                    assert 0<result['visible_labels']<=300,result
                    assert result['candidates']<=1500,result
                    page.locator('#mapa-ambiental').screenshot(path=str(runtime/'etiquetas-canvas.png'))
                    for _ in range(6):page.locator('#mapa-etiquetas').click()
                    page.evaluate('window.__testMap.setView([0,0],16,{animate:false})')
                    page.wait_for_function("() => document.querySelector('.ambiental-labels-canvas').hidden")
                    page.evaluate('window.__testMap.setView([-25.316,-49.303],14,{animate:false})')
                    page.wait_for_function("() => document.getElementById('mapa-etiquetas-status').textContent.includes('Amplie')")
                    assert page.locator('.ambiental-labels-canvas').count()==1
                    page.set_viewport_size({'width':390,'height':844})
                    page.evaluate('window.__testMap.setZoom(17,{animate:false})')
                    page.wait_for_timeout(150)
                    canvas=page.locator('.ambiental-labels-canvas')
                    assert 0<int(canvas.get_attribute('data-label-count'))<=300
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    result['pan_zoom_toggle_resize_ok']=True
                    for i in range(1500,6000):add_feature(i)
                    page.set_viewport_size({'width':1365,'height':900});page.reload()
                    page.wait_for_function("() => document.getElementById('mapa-status').textContent.includes('6000 polígono(s)')")
                    page.wait_for_function("() => !document.getElementById('mapa-ambiental').classList.contains('leaflet-zoom-anim')")
                    page.evaluate('window.__testMap.setZoom(17,{animate:false})')
                    stress=page.evaluate('''async () => {
                      const start=performance.now(),builds=window.__builds;
                      document.getElementById('mapa-etiquetas').click();
                      const clickMs=performance.now()-start;
                      await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                      return {click_ms:clickMs,settled_ms:performance.now()-start,
                        layer_builds:window.__builds-builds,
                        visible_labels:Number(document.querySelector('.ambiental-labels-canvas').dataset.labelCount),
                        canvas_count:document.querySelectorAll('.ambiental-labels-canvas').length};
                    }''')
                    assert stress['layer_builds']==0 and 0<stress['visible_labels']<=300,stress
                    assert stress['canvas_count']==1,stress
                    result['stress_6000_poligonos']=stress
                results[variant]=result
                print(json.dumps({'variante':variant,**result},ensure_ascii=True),flush=True)
                context.close()
            assert not errors,errors
            # Compara bloqueio síncrono; tempos absolutos variam conforme a máquina.
            assert results['candidata']['click_ms']<results['rc2']['click_ms'],results
            browser.close()
        report={'ok':True,'poligonos_ficticios':1500,'cpu_throttling':4,'resultados':results,'evidencias':str(runtime)}
        (ROOT/'.venv/mapa-performance-resultado.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True))
    finally:
        server.close();server.task_dispatcher.shutdown();worker.join(timeout=3)


if __name__=='__main__':main()
