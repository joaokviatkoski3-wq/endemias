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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BIN = Path('C:/Program Files/PostgreSQL/18/bin')
PORT = 55444


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
            with connection.cursor() as cursor:
                cursor.execute('SELECT id_usuario,usuario,senha_hash FROM usuarios ORDER BY id_usuario')
                before=cursor.fetchall()
                cursor.execute(next(m.sql for m in migrations if m.version=='0035'))
                cursor.execute('SELECT id_usuario,usuario,senha_hash FROM usuarios ORDER BY id_usuario')
                assert before==cursor.fetchall()
                cursor.execute("SELECT COUNT(*) FROM usuarios WHERE setor<>'endemias'")
                assert cursor.fetchone()[0]==0
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
            else:
                assert 'esporotricose' not in client.get('/api/dashboard').json
                query='?agente=Agente+Ficticio&d_ini=2026-06-01&d_fim=2026-06-03'
                response=client.get('/api/relatorio-agente'+query)
                assert response.status_code==200 and not response.json['esporotricose']['totais']
                assert client.get('/relatorio-agente/pdf'+query).status_code==200
                assert client.get('/api/boletim-mensal?mes=2026-06').status_code==200
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
