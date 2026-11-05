"""Ensaio aditivo e web em cluster novo, dados ficticios e porta nao oficial."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BIN = Path('C:/Program Files/PostgreSQL/18/bin')
PORT = 55444


def verificar_correcoes_201(target, client, checks, private):
    from app_core import db, formularios, rg_formulario, esporotricose_humanos as humanos
    for path in ('/api/bri/listar?por_pagina=1','/api/recolhimentos/listar?por_pagina=1',
                 '/api/bri/exportar','/api/recolhimentos/exportar',
                 '/notificacoes?agente=Agente+Ficticio'):
        assert client.get(path).status_code==200,path
    assert client.get('/api/bri/listar?por_pagina=1').json['total']==1
    assert client.get('/api/boletim-mensal?mes=2026-13').status_code==400
    assert client.get('/api/agenda/eventos').status_code==400
    usuario={'id_usuario':1,'nome':'Gestor Fictício','nivel':'superadmin'}
    payload={'id_localidade':1,'quarteirao':'0001','linhas':[{'logradouro':'Rua Nova Ficticia','numero':'20','tipo':'R'}]}
    identificador=formularios.salvar(target,'rg_atualizacao',payload,usuario)
    formularios.revisar(target,identificador,payload,formularios.STATUS_APROVADO,usuario)
    before=[dict(r) for r in db.query(target,'SELECT * FROM registro_geografico_imoveis ORDER BY id_imovel')]
    with mock.patch.object(formularios,'marcar_oficializado',side_effect=RuntimeError('Falha fictícia')):
        try:rg_formulario.oficializar(target,identificador,usuario)
        except RuntimeError:pass
        else:raise AssertionError('A falha de ensaio deveria interromper a oficialização')
    assert before==[dict(r) for r in db.query(target,'SELECT * FROM registro_geografico_imoveis ORDER BY id_imovel')]
    assert formularios.obter(target,identificador)['status']==formularios.STATUS_APROVADO
    rg_formulario.oficializar(target,identificador,usuario)
    assert formularios.obter(target,identificador)['status']==formularios.STATUS_OFICIALIZADO
    paciente=humanos.salvar_paciente(target,{'nome':'Pessoa Fictícia PG','status':'Em tratamento'},'Autor Fictício')
    humanos.salvar_acompanhamento(target,paciente,{'data':'2026-06-10','status':'Acabou tratamento'},'Autor Fictício')
    humanos.salvar_acompanhamento(target,paciente,{'data':'2026-06-01','status':'Em tratamento'},'Autor Fictício')
    assert humanos.obter_paciente(target,paciente)['status']=='Acabou tratamento'
    from app_core import kobo_conciliacao as conferencia
    registro={'_uuid':'uuid-ficticio-bri_registros','start':'2026-06-01T08:00:00','end':'2026-06-01T09:00:00',
              'Data':'2026-06-01','Hora':'08:00','Quantidade_de_carga':2.5}
    previa=conferencia.preparar(target,'BRI',[registro],ROOT/'config.json',private,1,'endemias','segredo-somente-ficticio')
    selecoes=[{'registro':r['chave'],'campo':'quantidade_carga'} for r in previa['registros']
              if any(c['campo']=='quantidade_carga' for c in r['alteracoes'])]
    assert len(selecoes)==1
    antes=db.scalar(target,"SELECT quantidade_carga FROM bri_registros WHERE kobo_uuid=?",(registro['_uuid'],))
    def falha_auditoria(*args):raise RuntimeError('Falha fictícia de auditoria')
    try:conferencia.aplicar(target,private,previa['token'],selecoes,1,'endemias','segredo-somente-ficticio',falha_auditoria)
    except RuntimeError:pass
    else:raise AssertionError('A falha deveria desfazer a alteração de ensaio')
    assert db.scalar(target,"SELECT quantidade_carga FROM bri_registros WHERE kobo_uuid=?",(registro['_uuid'],))==antes
    def auditoria(conn,tipo,changes):
        conn.execute("INSERT INTO auditoria_eventos(acao,entidade,detalhes_json,criado_em,setor) VALUES(?,?,?,?,?)",
                     ('conferencia_ficticia',tipo,json.dumps(changes),'2026-06-01T10:00:00','endemias'))
    conferencia.aplicar(target,private,previa['token'],selecoes,1,'endemias','segredo-somente-ficticio',auditoria)
    assert db.scalar(target,"SELECT quantidade_carga FROM bri_registros WHERE kobo_uuid=?",(registro['_uuid'],))==2.5
    assert db.scalar(target,"SELECT COUNT(*) FROM auditoria_eventos WHERE acao='conferencia_ficticia'")==1
    checks['conferencia_kobo_campos_e_auditoria_atomicos_pg']=True
    for operacao in ('revisar','excluir'):
        fid=formularios.salvar(target,'rg_atualizacao',payload,usuario)
        formularios.revisar(target,fid,payload,formularios.STATUS_APROVADO,usuario)
        principal=db.connect(target); concorrente=db.connect(target)
        leu_status=threading.Event(); erros=[]
        class ConexaoDeEnsaio:
            def execute(self,sql,params=()):
                cur=concorrente.execute(sql,params)
                if sql.startswith('SELECT status FROM formularios'):
                    leu_status.set()
                return cur
            def __getattr__(self,nome):return getattr(concorrente,nome)
        def executar():
            try:
                if operacao=='revisar':formularios.revisar(target,fid,{},formularios.STATUS_DEVOLVIDO,usuario)
                else:formularios.excluir(target,fid)
            except Exception as exc:erros.append(exc)
        thread=threading.Thread(target=executar,daemon=True)
        try:
            principal.execute('SELECT id_formulario FROM formularios WHERE id_formulario=? FOR UPDATE',(fid,))
            with mock.patch.object(db,'connect',return_value=ConexaoDeEnsaio()):
                thread.start()
                assert leu_status.wait(5),'Operação concorrente não chegou à leitura esperada'
                principal.execute('UPDATE formularios SET status=? WHERE id_formulario=?',(formularios.STATUS_OFICIALIZADO,fid))
                principal.commit()
                thread.join(5)
                assert not thread.is_alive(),'Operação concorrente não terminou'
            assert len(erros)==1 and isinstance(erros[0],ValueError),(operacao,erros)
            assert formularios.obter(target,fid)['status']==formularios.STATUS_OFICIALIZADO
        finally:
            principal.rollback();principal.close()
            if thread.is_alive():thread.join(5)
            concorrente.close()
    checks['formulario_oficializado_preservado_em_revisao_exclusao_concorrentes_pg']=True
    checks['correcoes_201_listas_validacao_rg_atomico_cronologia_pg']=True


def main():
    if ROOT == Path('C:/endemias'):
        raise ValueError('Execute na worktree com massa ficticia.')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', PORT))
    from scripts.validar_backup_completo_isolado import proteger
    private = Path(tempfile.mkdtemp(prefix='pg-setores-', dir=ROOT / '.venv'))
    proteger(private)
    data = private / 'pgdata'
    pwfile = private / 'senha.tmp'
    password = secrets.token_urlsafe(32)
    pwfile.write_text(password, encoding='utf-8')
    env = {**os.environ, 'PGPASSWORD':password}
    started = False
    checks = {}

    def run(name, *args):
        with (private / 'comandos.log').open('ab') as log:
            subprocess.run([str(BIN / (name + '.exe')), *map(str,args)], env=env,
                stdout=log, stderr=log, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

    try:
        run('initdb', '-D',data,'-U','postgres','--auth=scram-sha-256','--pwfile',pwfile,'--no-locale','--encoding=UTF8')
        run('pg_ctl','-D',data,'-l',private/'postgres.log','-o',f'-h 127.0.0.1 -p {PORT}','-w','start')
        started = True
        run('createdb','-h','127.0.0.1','-p',PORT,'-U','postgres','endemias_teste')
        import psycopg2
        from psycopg2 import sql
        from psycopg2.extras import execute_values
        from app_core import postgresql_migrations, postgresql_data_migration, sqlite_inventory
        connection = psycopg2.connect(host='127.0.0.1',port=PORT,user='postgres',dbname='endemias_teste',password=password)
        try:
            migrations = postgresql_migrations.discover(ROOT/'migrations/postgresql')
            with connection.cursor() as cursor:
                for migration in migrations:
                    if migration.version<'0035':cursor.execute(migration.sql)
            connection.commit()
            seed = ROOT/'.venv/seed.db'
            inventory = sqlite_inventory.build_inventory(seed)
            sqlite = sqlite3.connect(seed)
            try:
                with connection.cursor() as cursor:
                    for name in postgresql_data_migration.table_load_order(inventory):
                        info = next(t for t in inventory['tables'] if t['name']==name)
                        cursor.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',('public',name))
                        available = {r[0] for r in cursor.fetchall()}
                        columns = [c for c in sorted(info['columns'],key=lambda c:c['position']) if c['name'] in available]
                        if not columns:continue
                        names = [c['name'] for c in columns]
                        select = 'SELECT '+','.join('"'+n+'"' for n in names)+' FROM "'+name+'"'
                        rows = sqlite.execute(select).fetchall()
                        if rows:
                            statement = sql.SQL('INSERT INTO {} ({}) VALUES %s').format(sql.Identifier(name),sql.SQL(',').join(map(sql.Identifier,names)))
                            execute_values(cursor,statement,[postgresql_data_migration.convert_row(r,name,columns,{}) for r in rows])
                        for column in names:
                            cursor.execute('SELECT pg_get_serial_sequence(%s,%s)',(name,column))
                            sequence=cursor.fetchone()[0]
                            if sequence and rows:
                                cursor.execute(sql.SQL('SELECT setval(%s,COALESCE(MAX({}),1),TRUE) FROM {}').format(sql.Identifier(column),sql.Identifier(name)),(sequence,))
                connection.commit()
            finally:
                sqlite.close()
            from scripts.ativar_setores_windows import fingerprints
            legacy=fingerprints(connection)
            with connection.cursor() as cursor:
                cursor.execute('SELECT id_usuario,usuario,senha_hash FROM usuarios ORDER BY id_usuario')
                before=cursor.fetchall()
                cursor.execute(next(m.sql for m in migrations if m.version=='0035'))
                cursor.execute('SELECT id_usuario,usuario,senha_hash FROM usuarios ORDER BY id_usuario')
                assert before==cursor.fetchall()
                cursor.execute("SELECT COUNT(*) FROM usuarios WHERE setor<>'endemias'")
                assert cursor.fetchone()[0]==0
            connection.commit()
            assert fingerprints(connection,legacy)==legacy
            with connection.cursor() as cursor:
                cursor.execute("UPDATE usuarios SET nome='Pessoa Ficticia Alterada' WHERE id_usuario=1")
            assert fingerprints(connection,legacy)!=legacy
            connection.rollback()
            checks['assinaturas_detectam_alteracao_de_dados_e_ignoram_coluna_nova']=True
            with connection.cursor() as cursor:
                cursor.execute("UPDATE usuarios SET nivel='superadmin' WHERE id_usuario=1")
                cursor.execute("UPDATE usuarios SET setor='ambiental' WHERE id_usuario=4")
            connection.commit()
            checks['0035_aditiva_contas_senhas_preservadas']=True
        finally:
            connection.close()
        passfile=private/'pgpass.tmp'
        passfile.write_text(f'127.0.0.1:{PORT}:endemias_teste:postgres:{password}\n',encoding='utf-8')
        os.environ.update(ENDEMIAS_DB_BACKEND='postgresql',ENDEMIAS_PG_DATABASE='endemias_teste',
            ENDEMIAS_PG_HOST='127.0.0.1',ENDEMIAS_PG_PORT=str(PORT),ENDEMIAS_PG_USER='postgres',
            ENDEMIAS_PG_SSLMODE='disable',PGPASSFILE=str(passfile),ENDEMIAS_INSTANCE_DIR=str(private),
            ENDEMIAS_DB_PATH=str(private/'nao-utilizado.db'),ENDEMIAS_LOG_PATH=str(private/'ensaio.log'),
            ENDEMIAS_AMBIENTE='teste',ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK='1')
        import app
        from app_core import auth, db, sessoes
        target=db.DatabaseTarget('postgresql','endemias_teste')
        for sector in ('endemias','ambiental'):
            application=app.create_app({'TESTING':True,'WTF_CSRF_ENABLED':False,'SETORES_ENABLED':True,'SETOR':sector})
            client=application.test_client()
            user=db.query_one(target,'SELECT * FROM usuarios WHERE id_usuario=1')
            with application.app_context(),client.session_transaction() as session:
                session.update(uid=1,nome=user['nome'],auth_token=auth.token_sessao(user['senha_hash']),sessao_id=sessoes.criar(target,user))
            for path in ('/','/dashboard','/api/dashboard','/mapa','/api/mapa','/processar','/admin/usuarios'):
                response=client.get(path)
                assert response.status_code==200,(sector,path,response.status_code)
            if sector=='ambiental':
                assert client.get('/api/dashboard').json['registros']==3
                for fmt in ('csv','xlsx','pdf'):assert client.get('/relatorios/exportar/'+fmt).status_code==200
                for query,total in [('fonte=Esporotricose',2),('quarteirao=0001&visita=normal',2),
                                    ('especie=gato',0),('tipo_animal=escorpiao',0),('origem_estrutura=nova',3)]:
                    response=client.get('/api/ambiental/dashboard?'+query)
                    assert response.status_code==200 and response.json['registros']==total,(query,response.status_code)
                assert client.get('/relatorios?agrupamento=mes').status_code==200
                checks['ambiental_filtros_agrupamentos_postgresql']=True
            else:
                assert 'esporotricose' not in client.get('/api/dashboard').json
                query='?agente=Agente+Ficticio&d_ini=2026-06-01&d_fim=2026-06-03'
                response=client.get('/api/relatorio-agente'+query)
                assert response.status_code==200 and not response.json['esporotricose']['totais']
                assert client.get('/relatorio-agente/pdf'+query).status_code==200
                assert client.get('/api/boletim-mensal?mes=2026-06').status_code==200
                verificar_correcoes_201(target, client, checks, private)
            event=client.post('/api/agenda/eventos',json={'titulo':'Evento ficticio '+sector,'tipo':'reuniao','data_inicio':'2026-06-01T09:00'})
            assert event.status_code==201
            events=client.get('/api/agenda/eventos?start=2026-06-01&end=2026-06-03')
            assert events.status_code==200
            own='Evento ficticio '+sector
            other='Evento ficticio '+('endemias' if sector=='ambiental' else 'ambiental')
            text=events.get_data(as_text=True)
            assert own in text and other not in text
            checks[sector+'_consultas_agenda_exportacoes']=True
        print(json.dumps({'ok':True,'checks':checks,'porta_oficial_utilizada':False}))
        (ROOT/'.venv/setores-pg-resultado.json').write_text(json.dumps({'ok':True,'checks':checks},indent=2),encoding='utf-8')
    finally:
        if started:run('pg_ctl','-D',data,'-m','fast','-w','stop')
        # Remove somente o cluster/palavras de acesso criados por este ensaio.
        assert private.resolve().is_relative_to((ROOT/'.venv').resolve())
        for path in (data,pwfile,private/'pgpass.tmp'):
            if path.is_dir():shutil.rmtree(path)
            elif path.exists():path.unlink()


if __name__=='__main__':main()
