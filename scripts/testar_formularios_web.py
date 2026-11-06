"""Renderiza os dez formulários usando definições privadas e banco fictício.

Só consulta a cópia local de estrutura. Não usa rede Kobo nem respostas reais.
"""
import os
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    if ROOT==Path('C:/endemias'):raise ValueError('Exige worktree de ensaio.')
    private=Path(tempfile.mkdtemp(prefix='formularios-web-',dir=ROOT/'.venv'));database=private/'ficticio.db'
    definitions=json.loads((ROOT/'.venv/formularios-internos/definicoes.json').read_text(encoding='utf-8'))
    # A gravação de ensaio usa participantes/localidade fictícios, sem transformar opções nominais em respostas.
    recol=next(f for f in definitions['forms'] if f['tipo']=='RECOLHIMENTO')
    lists={r.get('name'):r.get('select_from_list_name') for r in recol['survey']}
    for row in recol['choices']:
        if row.get('list_name')==lists.get('Localidade'):
            row.update(name='Localidade Ficticia',label=['Localidade Ficticia']);row['$autovalue']='Localidade Ficticia'
    recol['choices']=[r for r in recol['choices'] if r.get('list_name')!=lists.get('Nome_do_s_agente_s')]+[
        {'list_name':lists['Nome_do_s_agente_s'],'name':'ficticio','label':['Agente Ficticio']},
        {'list_name':lists['Nome_do_s_agente_s'],'name':'colega','label':['Outro Agente Ficticio']}]
    tb=next(f for f in definitions['forms'] if f['tipo']=='TB')
    tb_lists={r.get('name'):r.get('select_from_list_name') for r in tb['survey']}
    tb['choices']=[r for r in tb['choices'] if r.get('list_name') not in (tb_lists['Localidade'],tb_lists['Nome_do_s_agente_s'])]+[
        {'list_name':tb_lists['Localidade'],'name':'Localidade Ficticia','label':['Localidade Ficticia']},
        {'list_name':tb_lists['Nome_do_s_agente_s'],'name':'eu','label':['Agente Ficticio']},
        {'list_name':tb_lists['Nome_do_s_agente_s'],'name':'colega','label':['Outro Agente Ficticio']}]
    schema=private/'definicoes-ficticias.json';schema.write_text(json.dumps(definitions,ensure_ascii=False),encoding='utf-8')
    os.environ.update(ENDEMIAS_DB_BACKEND='sqlite',ENDEMIAS_DB_PATH=str(database),ENDEMIAS_TEST_DB_ISOLATED='1',
        ENDEMIAS_INSTANCE_DIR=str(private),ENDEMIAS_SECRET_KEY_PATH=str(private/'secret.key'),
        ENDEMIAS_LOG_PATH=str(private/'ensaio.log'),ENDEMIAS_ANEXOS_DIR=str(private/'anexos'),
        ENDEMIAS_UPLOAD_TEMP=str(private/'uploads'),ENDEMIAS_KOBO_CONFIG_PATH=str(private/'kobo.json'),
        ENDEMIAS_BACKUP_DIR=str(private/'backups'),ENDEMIAS_BACKUP_COMPLETO_DIR=str(private/'completos'),
        ENDEMIAS_AMBIENTE='teste',ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1',
        ENDEMIAS_FORMULARIOS_KOBO_SCHEMA=str(schema))
    from scripts.preparar_massa_web_teste import preparar
    preparar(database)
    from app_core import db
    with db.connect(str(database)) as conn:
        conn.execute('UPDATE usuarios SET id_agente=1 WHERE id_usuario=1')
        conn.commit()
    from app import create_app
    from waitress import create_server
    from playwright.sync_api import sync_playwright,expect
    servers=[];urls={};errors=[];checks=[]
    try:
        for sector in ('endemias','ambiental'):
            app=create_app(dict(TESTING=True,DB_PATH=str(database),DB_BACKEND='sqlite',SETORES_ENABLED=True,
                SETOR=sector,TERMOS_USO_ENABLED=False,CSP_REPORT_ONLY=False))
            server=create_server(app,host='127.0.0.1',port=0,threads=4,map={});servers.append(server)
            threading.Thread(target=server.run,daemon=True).start();urls[sector]='http://127.0.0.1:'+str(server.effective_port)
        with db.connect(str(database)) as conn:
            conn.execute("INSERT INTO agenda_eventos(id_evento,titulo,tipo,data_inicio,dia_inteiro,criado_em,recorrencia,atividade_externa,setor) VALUES(700,'Campo ficticio','campo','2026-06-03T08:00',0,'2026-06-01','nenhuma',1,'endemias')")
            conn.commit()
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            for sector,types in (('endemias',('PE','TB','TBO','PVE','LIRAA','LARVAS','BRI','RECOLHIMENTO')),('ambiental',('ESPOROTRICOSE','AMOSTRA_ANIMAIS'))):
                context=browser.new_context(viewport={'width':390,'height':844});page=context.new_page()
                page.add_init_script('crypto.randomUUID=undefined')  # Exercita a alternativa compatível com entrada LAN HTTP.
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(urls[sector]+'/login');page.locator('[name=usuario]').fill('admin');page.locator('[name=senha]').fill('SenhaSomenteDeTeste123!')
                page.get_by_role('button',name='Entrar',exact=True).click();page.wait_for_url(urls[sector]+'/')
                page.goto(urls[sector]+'/formularios')
                for tipo in types:
                    assert page.locator(f'a[href="/formularios/kobo/{tipo}"]').count()==1
                for tipo in types:
                    page.goto(urls[sector]+'/formularios/kobo/'+tipo)
                    expect(page.locator('#fk-editor')).to_be_visible()
                    assert page.locator('#fk-campos [data-field]').count()>0
                    assert page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'),tipo
                    assert all(' ' not in v for v in page.locator('.fk-fields').evaluate_all('(els)=>els.map(el=>getComputedStyle(el).gridTemplateColumns)'))
                    if tipo=='TB':
                        expect(page.locator('.fk-team input[value=eu]')).to_be_checked()
                        expect(page.locator('.fk-team input[value=eu]')).to_be_disabled()
                        page.locator('.fk-team input[value=colega]').check()
                        page.locator('select[data-path=Localidade],select[data-path$="/Localidade"]').select_option('Localidade Ficticia')
                        block=page.locator('input[data-geo=quarteirao]');street=page.locator('input[data-geo=logradouro]')
                        pick=page.locator('[data-suggestion="'+block.get_attribute('id')+'"]')
                        expect(pick).to_be_visible();pick.select_option('1')
                        expect(block).to_have_value('1')
                        streets=page.locator('[data-suggestion="'+street.get_attribute('id')+'"]')
                        expect(streets).to_be_visible();streets.select_option('Rua Ficticia')
                        expect(street).to_have_value('Rua Ficticia')
                        block.fill('999');street.fill('Rua digitada manualmente')
                        expect(street).to_have_value('Rua digitada manualmente')
                        page.evaluate('()=>{window.confirmacaoDupla=async()=>true}')
                    if tipo=='PE':
                        loc=page.locator('select[data-path=localidade],select[data-path$="/localidade"]')
                        loc.select_option(loc.locator('option').nth(1).get_attribute('value'))
                        q=page.locator('select[data-path=quarteirao],select[data-path$="/quarteirao"]')
                        choices=q.locator('option:not([hidden]):not([value=""])')
                        assert choices.count()>0
                        q.select_option(choices.first.get_attribute('value'))
                        assert page.locator('select[data-path=logradouro],select[data-path$="/logradouro"]').input_value()
                    page.screenshot(path=str(private/(tipo+'.png')),full_page=True)
                    page.set_viewport_size({'width':1365,'height':900})
                    assert page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'),tipo
                    page.set_viewport_size({'width':390,'height':844});checks.append(tipo)
                if sector=='endemias':
                    # Captura, salvamento automático, devolução, retorno e próxima visita.
                    page.goto(urls[sector]+'/formularios/kobo/RECOLHIMENTO?agenda=700&ocorrencia=2026-06-03')
                    expect(page.locator('#fk-editor')).to_be_visible()
                    page.locator('input[data-path="Data"]').fill('2026-06-03')
                    page.locator('input[data-path="Hora"]').fill('08:00')
                    page.locator('select[data-path="Localidade"]').select_option('Localidade Ficticia')
                    assert page.locator('.fk-multiple input').first.is_checked()
                    assert page.locator('.fk-multiple input').first.is_disabled()
                    for control in page.locator('input[type=number]').all():control.fill('0')
                    page.locator('input[data-path="group_cw8wz69/A1"]').fill('2')
                    page.locator('#fk-retorno-data').fill('2026-12-04')
                    expect(page.locator('#fk-save-status')).to_contain_text('Rascunho salvo no servidor',timeout=15000)
                    ident=page.evaluate("new URL(location.href).searchParams.get('envio')")
                    page.reload();expect(page.locator('input[data-path="group_cw8wz69/A1"]')).to_have_value('2')
                    context.set_offline(True);page.locator('input[data-path="group_cw8wz69/A1"]').fill('3')
                    expect(page.locator('#fk-save-status')).to_contain_text('Sem conexão',timeout=10000)
                    context.set_offline(False)
                    expect(page.locator('#fk-save-status')).to_contain_text('Rascunho salvo no servidor',timeout=15000)
                    lost={'once':False}
                    def lose_receipt(route):
                        if route.request.method=='POST' and not lost['once']:
                            lost['once']=True;route.fetch();route.abort()
                        else:route.continue_()
                    page.route('**/api/formularios/kobo/RECOLHIMENTO',lose_receipt)
                    page.locator('input[data-path="group_cw8wz69/A1"]').fill('4')
                    expect(page.locator('#fk-save-status')).to_contain_text('Não foi possível confirmar',timeout=15000)
                    page.locator('input[data-path="group_cw8wz69/A1"]').fill('5')
                    page.evaluate("()=>window.dispatchEvent(new Event('online'))")
                    page.wait_for_timeout(1200)
                    page.evaluate('()=>{window.confirmacaoDupla=async()=>true}')
                    page.click('[data-action=rascunho]');expect(page.locator('#fk-status')).to_contain_text('Rascunho salvo no servidor')
                    expect(page.locator('input[data-path="group_cw8wz69/A1"]')).to_have_value('5')
                    page.unroute('**/api/formularios/kobo/RECOLHIMENTO',lose_receipt)
                    page.click('[data-action=proxima]');expect(page.locator('#fk-proxima')).to_be_visible()
                    for id in ('fk-reusar-equipe','fk-reusar-data','fk-reusar-local'):page.locator('#'+id).check()
                    page.click('#fk-criar-proxima')
                    expect(page.locator('input[data-path="Data"]')).to_have_value('2026-06-03')
                    expect(page.locator('input[data-path="group_cw8wz69/A1"]')).to_have_value('')
                    expect(page.locator('#fk-retorno-data')).to_have_value('')
                    page.goto(urls[sector]+'/formularios/kobo/RECOLHIMENTO?envio='+ident)
                    expect(page.locator('#fk-editor')).to_be_visible()
                    page.goto(urls[sector]+'/formularios/kobo/RECOLHIMENTO/revisao?envio='+ident)
                    expect(page.locator('#fk-editor')).to_be_visible()
                    page.locator('[data-correction="group_cw8wz69/A1"]').fill('Conferir a quantidade deste material.')
                    page.evaluate("()=>{window.confirmacaoDupla=async()=>true;window.prompt=()=> 'Conferir o campo indicado';}")
                    page.click('[data-action=devolver]');expect(page.locator('#fk-situacao')).to_contain_text('Devolvido')
                    page.goto(urls[sector]+'/formularios/kobo/RECOLHIMENTO?envio='+ident)
                    expect(page.locator('p.fk-correction')).to_contain_text('Conferir a quantidade')
                    page.evaluate('()=>{window.confirmacaoDupla=async()=>true}')
                    page.click('[data-action=enviado]');expect(page.locator('#fk-status')).to_contain_text('Recebido para revisão')
                    ident=page.evaluate("new URL(location.href).searchParams.get('envio')")
                    page.goto(urls[sector]+'/formularios/kobo/RECOLHIMENTO/revisao?envio='+ident)
                    expect(page.locator('#fk-editor')).to_be_visible();page.evaluate('()=>{window.confirmacaoDupla=async()=>true}')
                    page.click('[data-action=aprovar]');expect(page.locator('#fk-situacao')).to_contain_text('Aprovado')
                    page.click('#fk-confirmar-retorno');expect(page.locator('#fk-retorno-situacao')).to_contain_text('Retorno confirmado')
                    page.click('[data-action=aplicar]');expect(page.locator('#fk-situacao')).to_contain_text('Aplicado')
                    from app_core import db
                    assert db.scalar(str(database),"SELECT COUNT(*) FROM recolhimentos WHERE kobo_uuid LIKE 'vsatt-%'")==1
                context.close()
            assert not errors,errors
            browser.close()
        print('OK: dez formulários renderizados, CSP efetiva, sem erro JS/overflow em celular e desktop.')
        print('Evidências privadas: '+str(private))
    finally:
        for server in servers:server.close();server.task_dispatcher.shutdown()


if __name__=='__main__':main()
