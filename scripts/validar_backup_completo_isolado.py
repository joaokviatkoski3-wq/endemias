"""Restaura backup real em pasta privada/PG temporario; nunca toca o banco oficial."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import traceback
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BIN=Path('C:/Program Files/PostgreSQL/18/bin')
PORT=55443
DATABASE='endemias_teste'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def proteger(path):
    import win32api,win32con,win32security as sec
    user=sec.GetTokenInformation(sec.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY),sec.TokenUser)[0]
    acl=sec.ACL()
    for sid in (user,sec.ConvertStringSidToSid('S-1-5-18'),sec.ConvertStringSidToSid('S-1-5-32-544')):
        acl.AddAccessAllowedAceEx(sec.ACL_REVISION_DS,3,0x1F01FF,sid)
    sec.SetNamedSecurityInfo(str(path),sec.SE_FILE_OBJECT,
        sec.DACL_SECURITY_INFORMATION|sec.PROTECTED_DACL_SECURITY_INFORMATION,None,None,acl,None)


def extrair_seguro(archive,destination):
    infos=archive.infolist()
    for info in infos:
        name=info.filename
        target=(destination/name).resolve()
        if ('\\' in name or ':' in name or not target.is_relative_to(destination.resolve())
                or stat.S_ISLNK(info.external_attr>>16)):
            raise ValueError('Caminho de arquivo fora do destino privado.')
    required={'manifesto_backup.json','configuracao/secret.key','configuracao/kobo_config.json'}
    if not required.issubset(set(archive.namelist())):
        raise ValueError('Backup sem componentes obrigatorios.')
    if archive.testzip() is not None:
        raise ValueError('CRC do backup completo invalido.')
    archive.extractall(destination)
    # Confere bytes de todos os arquivos, sem carregar chaves/configuracoes.
    for info in infos:
        if info.is_dir():continue
        with archive.open(info) as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=digest(destination/info.filename):
                raise ValueError('Arquivo extraido diferente do original.')
    return len([i for i in infos if not i.is_dir()])


def main():
    if ROOT==Path('C:/endemias'):
        raise ValueError('Executar apenas na worktree de manutencao.')
    # Requer porta livre; nunca encerra outra instancia ou usa 5432.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',PORT))
    activation=json.loads(Path('C:/ProgramData/EndemiasWeb/ativacao180-resultado.json').read_text(encoding='utf-8'))
    if activation.get('status')!='aplicado':raise ValueError('Ativacao ainda nao confirmada.')
    source=Path(activation['backup_completo']['arquivo'])
    permitted=Path('D:/BackupsEndemias/backups_web/completos').resolve()
    if not source.resolve().is_relative_to(permitted) or source.suffix!='.zip':
        raise ValueError('Origem inesperada.')
    private=Path(tempfile.mkdtemp(prefix='restauracao180-',dir=ROOT/'.venv'))
    proteger(private)  # Antes de extrair qualquer dado real.
    output=private/'resultado.json'
    summary=ROOT/'.venv/restauracao180-resultado.json'
    data=private/'pgdata'
    files=private/'arquivos'
    files.mkdir()
    report={'ok':False,'producao_alterada':False,'pasta_privada':True,'stage':'conferindo_backup'}
    password=secrets.token_urlsafe(32)
    pwfile=private/'senha-inicial.tmp'
    passfile=private/'pgpass.tmp'
    pwfile.write_text(password+'\n',encoding='utf-8')
    passfile.write_text(f'127.0.0.1:{PORT}:*:postgres:{password}\n',encoding='utf-8')
    env={k:v for k,v in os.environ.items() if not k.upper().startswith('PG')}
    env.update(PGPASSFILE=str(passfile),PGCONNECT_TIMEOUT='10',PGSSLMODE='disable',PGAPPNAME='endemias_restore_isolado')
    started=False
    success=False
    def save(stage):
        report['stage']=stage
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        summary.write_text(json.dumps(report,indent=2),encoding='utf-8')
    def run(program,*args):
        with (private/'comandos.log').open('ab') as log:
            subprocess.run([str(BIN/(program+'.exe')),*map(str,args)],env=env,stdout=log,stderr=log,
                           check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        if digest(source)!=activation['backup_completo']['sha256']:
            raise ValueError('Hash do ZIP diferente do registrado na ativacao.')
        with zipfile.ZipFile(source) as archive:
            manifest=json.loads(archive.read('manifesto_backup.json'))
            if manifest.get('tipo')!='backup_completo_endemias' or manifest.get('backend_banco')!='postgresql':
                raise ValueError('Formato de backup inesperado.')
            save('extraindo_em_pasta_privada')
            report['arquivos_conferidos']=extrair_seguro(archive,files)
        dumps=list((files/'banco').glob('*.dump'))
        if len(dumps)!=1:raise ValueError('Quantidade inesperada de dumps.')
        dump=dumps[0]
        expected=next(i['sha256'] for i in manifest['incluidos'] if i.get('destino_zip')=='banco/'+dump.name)
        if digest(dump)!=expected:raise ValueError('Hash do dump invalido.')
        save('iniciando_postgresql_privado_scram')
        run('initdb','-D',data,'-U','postgres','--auth=scram-sha-256','--pwfile',pwfile,'--no-locale','--encoding=UTF8')
        run('pg_ctl','-D',data,'-l',private/'postgresql.log','-o',f'-h 127.0.0.1 -p {PORT}','-w','start')
        started=True
        run('createdb','-h','127.0.0.1','-p',PORT,'-U','postgres',DATABASE)
        save('restaurando_banco_descartavel')
        run('pg_restore','-h','127.0.0.1','-p',PORT,'-U','postgres','-d',DATABASE,
            '--no-owner','--no-privileges','--no-tablespaces','--single-transaction','--exit-on-error',dump)
        import psycopg2
        from psycopg2 import sql
        connection=psycopg2.connect(host='127.0.0.1',port=PORT,user='postgres',dbname=DATABASE,password=password,sslmode='disable')
        connection.set_session(readonly=True)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SHOW data_directory')
                if Path(cursor.fetchone()[0]).resolve()!=data.resolve():raise ValueError('Servidor fora da pasta privada.')
                cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
                tables=[r[0] for r in cursor.fetchall()]
                counts={}
                for name in tables:
                    cursor.execute(sql.SQL('SELECT COUNT(*) FROM public.{}').format(sql.Identifier(name)))
                    counts[name]=cursor.fetchone()[0]
                (private/'contagens.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
                cursor.execute('SELECT COUNT(*) FROM pg_index WHERE NOT indisvalid')
                report['indices_invalidos']=cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM usuarios WHERE nivel='superadmin' AND ativo=1")
                report['superadmin_unico']=cursor.fetchone()[0]==1
                report['tabelas_restauradas']=len(tables)
                report['dump_restaurado']=True
                report['arquivos_e_configuracoes_conferidos']=True
        finally:
            connection.close()
        if report['indices_invalidos'] or not report['superadmin_unico']:raise ValueError('Conferencia estrutural incompleta.')
        success=True
    except Exception as error:
        report.update(error_type=type(error).__name__,trace=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)])
    finally:
        if started or (data/'postmaster.pid').is_file():
            try:
                run('pg_ctl','-D',data,'-m','fast','-w','stop')
                report['instancia_encerrada']=True
            except Exception:
                report['instancia_encerrada']=False
                success=False
        if success:
            # Apenas copias temporarias criadas aqui; valida todos os destinos.
            for item in (data,files):
                resolved=item.resolve()
                if resolved.parent!=private.resolve() or resolved.name not in {'pgdata','arquivos'}:
                    raise ValueError('Limpeza recusada fora da pasta privada.')
                shutil.rmtree(resolved)
            report['copias_temporarias_removidas']=True
        pwfile.unlink(missing_ok=True);passfile.unlink(missing_ok=True)
        report['ok']=success
        save('concluido' if success else 'falhou')
    print(json.dumps(report))
    return 0 if success else 1


if __name__=='__main__':
    raise SystemExit(main())
