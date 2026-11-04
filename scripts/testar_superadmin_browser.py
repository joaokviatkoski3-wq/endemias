"""Fluxo de gestao e administracao tecnica em usuarios sinteticos/CSRF real."""

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
        raise ValueError('Somente worktree separada.')
    runtime = Path(tempfile.mkdtemp(prefix='browser-superadmin-', dir=ROOT / '.venv'))
    database = runtime / 'sintetico.db'
    shutil.copyfile(ROOT / '.venv/superadmin-seed.db', database)
    os.environ.update(ENDEMIAS_DB_BACKEND='sqlite', ENDEMIAS_DB_PATH=str(database),
        ENDEMIAS_INSTANCE_DIR=str(runtime), ENDEMIAS_LOG_PATH=str(runtime / 'browser.log'),
        ENDEMIAS_BACKUP_DIR=str(runtime / 'backups'), ENDEMIAS_BACKUP_COMPLETO_DIR=str(runtime / 'completos'),
        ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1')
    from app_core import auth
    conn = sqlite3.connect(database)
    conn.execute("INSERT INTO usuarios(id_usuario,usuario,nome,senha_hash,nivel,criado_em) VALUES(10,'super-ficticio','Super Ficticio',?,'superadmin','2026-11-04')", (auth.hash_senha('SenhaSomenteDeTeste123!'),))
    conn.commit(); conn.close()
    from app import create_app
    from playwright.sync_api import sync_playwright
    from waitress import create_server
    application = create_app({'REQUIRE_SESSION_TOKEN': True})
    server = create_server(application, host='127.0.0.1', port=5006, threads=4)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    stage = 'login'
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            manager, owner = browser.new_context(), browser.new_context()
            a, s = manager.new_page(), owner.new_page()
            errors = []
            for page in (a,s):
                page.on('pageerror', lambda e: errors.append(type(e).__name__))
            base = 'http://127.0.0.1:5006'
            for page, login in ((a,'admin'),(s,'super-ficticio')):
                page.goto(base + '/login')
                page.locator('[name="usuario"]').fill(login)
                page.locator('[name="senha"]').fill('SenhaSomenteDeTeste123!')
                page.get_by_role('button', name='Entrar', exact=True).click()
                page.wait_for_url(base + '/')
            stage = 'gestao_delegada'
            a.goto(base + '/admin/usuarios')
            assert a.locator('#row-10').get_by_text('Conta protegida').count() == 1
            assert a.locator('#row-1').get_by_text('Conta protegida').count() == 1
            assert a.locator('#row-10 select:enabled').count() == 0
            assert a.locator('form[action="/admin/usuarios/criar"] option[value="admin"]').count() == 0
            assert a.locator('form[action="/admin/usuarios/criar"] option[value="superadmin"]').count() == 0
            assert a.locator('#row-2').get_by_role('button', name='Gerar link de recuperação').count() == 1
            # POSTs diretos com CSRF valido, sem depender de controles ocultos.
            codes = a.evaluate("""async () => {
              const csrf = document.querySelector('meta[name="csrf-token"]').content;
              const requests = [
                ['/admin/usuarios/10/editar', new URLSearchParams({campo:'nivel',valor:'usuario'})],
                ['/admin/usuarios/10/resetar-senha', new URLSearchParams()],
                ['/admin/usuarios/10/recuperacao-senha', new URLSearchParams()],
                ['/api/kobo/config', new URLSearchParams()],
                ['/admin/sistema/backups-completos/criar', new URLSearchParams()]
              ];
              const out=[];
              for (const [url,body] of requests) out.push((await fetch(url,{method:'POST',body,headers:{'X-CSRFToken':csrf}})).status);
              return out;
            }""")
            assert codes == [400,400,400,403,403]
            a.screenshot(path=str(runtime / 'admin-delegado.png'), full_page=True)
            stage = 'integracoes'
            a.goto(base + '/processar')
            assert a.locator('#kobo-token').count() == 0
            s.goto(base + '/processar')
            assert s.locator('#kobo-token').count() == 1
            assert (await_response := s.request.get(base + '/api/kobo/config')).status == 200
            assert 'api_token' not in await_response.json()
            stage = 'superadmin'
            s.goto(base + '/admin/usuarios')
            assert s.locator('form[action="/admin/usuarios/criar"] option[value="admin"]').count() == 1
            assert s.locator('#row-10').get_by_text('Conta protegida').count() == 1
            assert s.locator('#row-1 select:enabled').count() > 0
            s.set_viewport_size({'width':390,'height':844})
            assert s.evaluate('document.documentElement.scrollWidth <= innerWidth')
            s.screenshot(path=str(runtime / 'superadmin-celular.png'), full_page=True)
            assert not errors
            browser.close()
        result = {'ok': True,'csrf_real': True,'gestao_delegada': True,'conta_superadmin_protegida': True,
            'integracoes_tecnicas_separadas': True,'mobile_sem_overflow': True,'javascript_errors':0,'artefatos':str(runtime)}
    except Exception as error:
        result = {'ok':False,'stage':stage,'error_type':type(error).__name__,'artefatos':str(runtime)}
    finally:
        server.close(); server.task_dispatcher.shutdown(); thread.join(timeout=5)
    (ROOT / '.venv/browser-superadmin-resultado.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
