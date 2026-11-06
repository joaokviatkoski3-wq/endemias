"""Ensaio Chromium do piloto, em worktree e base inteiramente fictícia.

Não consulta respostas Kobo nem bancos/serviços de produção.
"""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(90)
    if ROOT == Path(r'C:\endemias'):
        raise RuntimeError('Execute somente na worktree de ensaio.')
    private = Path(tempfile.mkdtemp(prefix='pwa-rg-', dir=ROOT/'.venv'))
    database = private/'ficticio.db'
    os.environ.update(ENDEMIAS_DB_BACKEND='sqlite', ENDEMIAS_DB_PATH=str(database), ENDEMIAS_TEST_DB_ISOLATED='1',
        ENDEMIAS_INSTANCE_DIR=str(private), ENDEMIAS_SECRET_KEY_PATH=str(private/'secret.key'),
        ENDEMIAS_LOG_PATH=str(private/'ensaio.log'), ENDEMIAS_ANEXOS_DIR=str(private/'anexos'),
        ENDEMIAS_UPLOAD_TEMP=str(private/'uploads'), ENDEMIAS_KOBO_CONFIG_PATH=str(private/'kobo.json'),
        ENDEMIAS_CONFIG_PATH=str(ROOT/'config.json'), ENDEMIAS_BACKUP_DIR=str(private/'backups'),
        ENDEMIAS_BACKUP_COMPLETO_DIR=str(private/'completos'), ENDEMIAS_AMBIENTE='teste',
        ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1')
    from scripts.preparar_massa_web_teste import preparar
    preparar(database)
    print('Base fictícia preparada.',flush=True)
    from app import create_app
    from app_core import db, formularios
    from waitress import create_server
    from playwright.sync_api import sync_playwright, expect
    app = create_app(dict(DB_PATH=str(database), DB_BACKEND='sqlite', TESTING=True,
        SETORES_ENABLED=True, SETOR='endemias', TERMOS_USO_ENABLED=False, CSP_REPORT_ONLY=False))
    print('Aplicação isolada criada.',flush=True)
    fail_navigation=[False];worker_update=[False]
    def application(environ,start_response):
        if fail_navigation[0] and environ.get('PATH_INFO')=='/formularios/rg-campo':
            start_response('502 Bad Gateway',[('Content-Type','text/plain')]);return [b'Falha ficticia']
        if worker_update[0] and environ.get('PATH_INFO')=='/sw.js':
            start_response('200 OK',[('Content-Type','application/javascript'),('Cache-Control','no-cache')])
            return [(ROOT/'static/sw.js').read_bytes()+b'\n// Atualizacao ficticia de ensaio\n']
        return app(environ,start_response)
    server = create_server(application, host='127.0.0.1', port=0, threads=8)
    threading.Thread(target=server.run, daemon=True).start()
    base='http://127.0.0.1:'+str(server.effective_port)
    errors=[]; checks=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            ctx=browser.new_context(viewport={'width':390,'height':844})
            page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            def login():
                page.goto(base+'/login')
                page.locator('[name=usuario]').fill('admin')
                page.locator('[name=senha]').fill('SenhaSomenteDeTeste123!')
                page.get_by_role('button',name='Entrar',exact=True).click()
                page.wait_for_url(base+'/')
            def loaded():
                page.wait_for_function("()=>document.getElementById('rgc-conexao').textContent!=='Verificando conexão…'")
            def saved():
                page.wait_for_function("()=>document.getElementById('rgc-salvo').textContent.startsWith('Salvo neste aparelho')")
            def rows():return page.evaluate('RGCampoOffline.listarFormularios()')
            def overflow():assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            login();page.goto(base+'/formularios/rg-campo');loaded()
            print('RG autenticado aberto.',flush=True)
            page.evaluate('Promise.race([navigator.serviceWorker.ready,new Promise(resolve=>setTimeout(resolve,10000))])')
            page.wait_for_function('()=>!!navigator.serviceWorker.controller')
            page.wait_for_function("async()=>!!await caches.match('/formularios/rg-campo')")
            manifest=ctx.request.get(base+'/manifest.webmanifest').json()
            assert manifest['start_url']=='/formularios/rg-campo'
            for icon in manifest['icons']: assert ctx.request.get(base+icon['src']).ok
            cdp=ctx.new_cdp_session(page)
            installability=cdp.send('Page.getInstallabilityErrors')
            assert not installability['installabilityErrors'],installability
            checks.append({'installability':installability})
            page.select_option('#rgc-localidade','1')
            page.locator('#rgc-quarteiroes input').first.check()
            page.click('#rgc-baixar')
            page.wait_for_selector('#rgc-grid [data-action=abrir]')
            page.click('#rgc-grid [data-action=abrir]')
            page.locator('#rgc-form-agentes input').first.check()
            # O nome da rua, mesmo sem imóveis completos, deve sobreviver ao fechamento.
            ctx.set_offline(True)
            page.locator('[data-field=logradouro]').fill('Rua Fictícia incompleta')
            saved();assert rows()[0]['payload']['_editor']['lados'][0]['logradouros'][0]['logradouro']=='Rua Fictícia incompleta'
            page.close();page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/formularios/rg-campo');loaded()
            page.click('#rgc-grid [data-action=abrir]')
            assert page.locator('[data-field=logradouro]').input_value()=='Rua Fictícia incompleta'
            page.locator('[data-field=numero]').fill('42')
            page.locator('[data-field=observacao]').fill('Imóvel fictício de teste')
            saved();overflow()
            page.screenshot(path=str(private/'celular-offline.png'),full_page=True)
            uuid=rows()[0]['uuid'];revision=rows()[0]['revisao']
            assert rows()[0]['pendente_envio']
            # Edição em duas abas: gravação concorrente é bloqueada; recibo antigo não limpa revisão nova.
            check=page.evaluate('''async()=>{
                const a=(await RGCampoOffline.listarFormularios())[0];
                const b=await RGCampoOffline.salvarFormulario(a,a.revisao);
                let blocked=false;try{await RGCampoOffline.salvarFormulario(a,a.revisao);}catch(e){blocked=true;}
                const ack=await RGCampoOffline.marcarRecebido(a.uuid,a.revisao,{uuid_cliente:a.uuid,revisao_recebida:a.revisao,id_formulario:77});
                return {blocked,ack,pending:(await RGCampoOffline.listarFormularios())[0].pendente_envio};
            }''')
            assert check=={'blocked':True,'ack':False,'pending':True}
            page.reload();loaded();page.click('#rgc-grid [data-action=abrir]')
            # Voltar a rede não recarrega nem muda o editor. Sincronização recebe uma só cópia.
            marker=page.evaluate('window.__editorTeste=crypto.randomUUID()')
            ctx.set_offline(False)
            page.click('#rgc-sync')
            page.wait_for_function('async()=>!(await RGCampoOffline.listarFormularios())[0].pendente_envio')
            assert page.evaluate('window.__editorTeste')==marker
            assert page.locator('[data-field=numero]').input_value()=='42'
            assert len(formularios.listar(str(database)))==1
            checks.append('autosave, fechamento, offline, CAS, recibo antigo, rede sem reload, sincronização')
            # Envio para revisão pelo fluxo real, inclusive confirmação dupla.
            page.on('dialog',lambda d:d.accept())
            page.evaluate('window.confirmacaoDupla=async()=>true')
            page.click('[data-action=enviar]')
            page.wait_for_function("async()=>{const r=(await RGCampoOffline.listarFormularios())[0];return !r.pendente_envio&&r.servidor_status==='enviado'}")
            expect(page.locator('#rgc-sync')).to_be_enabled()
            ident=rows()[0]['servidor_id']
            original=formularios.obter(str(database),ident)
            reviewed={**original['payload'],'linhas':[{**original['payload']['linhas'][0],'numero':'43'}]}
            formularios.revisar(str(database),ident,reviewed,'devolvido',{'id_usuario':1,'nome':'Gestor fictício'},motivo='Conferir número')
            page.click('#rgc-sync')
            page.wait_for_function("async()=>(await RGCampoOffline.listarFormularios())[0].servidor_status==='devolvido'")
            expect(page.locator('#rgc-sync')).to_be_enabled()
            page.click('[data-view=quarteiroes]');page.click('#rgc-grid [data-action=abrir]')
            expect(page.locator('[data-field=numero]')).to_have_value('43')
            checks.append('envio para revisão e devolução preservando correção do gestor')
            # Falha do servidor na navegação usa a tela preparada, sem apagar o conteúdo local.
            fail_navigation[0]=True
            page.reload();loaded();assert page.locator('#rgc-app').count()==1
            fail_navigation[0]=False
            # Sessão expirada mantém pendência; outra conta não pode receber o rascunho anterior.
            conn=db.connect(str(database));conn.execute('UPDATE usuarios_sessoes SET expira_em=0');conn.commit();conn.close()
            page.click('[data-view=quarteiroes]');page.click('#rgc-grid [data-action=abrir]')
            page.locator('[data-field=numero]').fill('44');saved()
            page.click('#rgc-sync');page.wait_for_selector('#rgc-login',state='visible')
            assert rows()[0]['pendente_envio']
            login();page.goto(base+'/formularios/rg-campo');loaded();page.click('#rgc-sync')
            page.wait_for_function('async()=>!(await RGCampoOffline.listarFormularios())[0].pendente_envio')
            for width,height in ((360,800),(768,1024),(1365,900)):
                page.set_viewport_size({'width':width,'height':height})
                page.click('[data-view=quarteiroes]');page.click('#rgc-grid [data-action=abrir]')
                expect(page.locator('#view-formulario')).to_be_visible()
                expect(page.locator('[data-field=numero]')).to_have_value('44')
                expect(page.locator('#rgc-login')).not_to_be_visible()
                overflow();page.screenshot(path=str(private/f'campo-{width}.png'),full_page=True)
                page.emulate_media(color_scheme='dark');overflow();page.emulate_media(color_scheme='light')
            checks.append('502, sessão expirada sem perda e larguras 360/390/768/1365')
            # Falta de espaço: a gravação anterior permanece e o usuário não recebe falso sucesso.
            page.evaluate("()=>{window.__guardarOriginal=RGCampoOffline.salvarFormulario;RGCampoOffline.salvarFormulario=async()=>{throw new DOMException('Armazenamento cheio no ensaio','QuotaExceededError')}}")
            page.locator('[data-field=numero]').fill('45')
            expect(page.locator('#rgc-salvo')).to_contain_text('Ainda não foi salvo')
            assert rows()[0]['payload']['linhas'][0]['numero']=='44'
            page.evaluate('()=>{RGCampoOffline.salvarFormulario=window.__guardarOriginal}')
            page.click('[data-action=salvar]');saved()
            checks.append('falha de armazenamento sinalizada e recuperação sem apagar versão anterior')
            # Uma versão nova espera o usuário, preservando o último preenchimento antes da recarga.
            worker_update[0]=True
            marker=page.evaluate('window.__antesAtualizacao=crypto.randomUUID()')
            page.evaluate('async()=>{const r=await navigator.serviceWorker.getRegistration();await r.update()}')
            expect(page.locator('#rgc-atualizar')).to_be_visible()
            assert page.evaluate('window.__antesAtualizacao')==marker
            page.locator('[data-field=numero]').fill('46')
            page.click('#rgc-atualizar')
            page.wait_for_function('()=>!window.__antesAtualizacao')
            loaded();assert rows()[0]['payload']['linhas'][0]['numero']=='46'
            checks.append('atualização espera confirmação e grava antes de recarregar')
            assert page.evaluate('''async()=>{const r=(await RGCampoOffline.listarFormularios())[0];
                try{await RGCampoOffline.removerFormulario(r.uuid);return false;}catch(e){return true;}}''')
            assert rows()[0]['payload']['linhas'][0]['numero']=='46'
            # Sair bloqueia a página, mas o banco anterior permanece separado da próxima conta.
            page.evaluate("document.querySelector('form[action=\"/logout\"]').requestSubmit()")
            page.wait_for_url('**/login')
            assert not page.evaluate("async()=>!!await caches.match('/formularios/rg-campo')")
            page.locator('[name=usuario]').fill('ficticio3');page.locator('[name=senha]').fill('SenhaSomenteDeTeste123!')
            page.get_by_role('button',name='Entrar',exact=True).click();page.wait_for_url(base+'/')
            page.goto(base+'/formularios/rg-campo');loaded()
            assert rows()==[]
            checks.append('logout remove página offline e outra conta não vê rascunho anterior')
            assert not errors,errors
            browser.close()
        print(json.dumps({'ok':True,'checks':checks,'evidencias':str(private)},ensure_ascii=False))
    finally:
        faulthandler.cancel_dump_traceback_later()
        server.close();server.task_dispatcher.shutdown()


if __name__=='__main__':main()
