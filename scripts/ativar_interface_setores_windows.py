"""Atualiza rc.1 para rc.2 sem migração, alterações de contas, Kobo ou rede.

Janela única: para antes de integrar templates; prova a identidade limitada;
retorna código/configuração em falha, sem restaurar banco ou apagar dados.
"""
import argparse
import copy
import ctypes
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from scripts.ativar_acesso_externo_windows import connect,git,http_login
from scripts.endurecer_web_windows import Windows,backup_before_change
from scripts.ativar_setores_windows import (digest,database_fingerprints,operational_files,
                                          scheduled_import,await_probe,origin_portal)

OFFICIAL=Path('C:/endemias')
HOME=Path('C:/ProgramData/EndemiasWeb')
ORIGIN='2.0.0-rc.1'
TARGET='2.0.0-rc.2'
MARKER='ativacao-interface200rc2'


def proposed_config(original,origin=ORIGIN,target=TARGET):
    if (original.get('version')!=origin or original.get('root')!=str(OFFICIAL)
            or original.get('server')!='waitress' or original.get('probe_only')):
        raise ValueError('Origem diferente da instalação conferida.')
    expected={'ENDEMIAS_DB_BACKEND':'postgresql','ENDEMIAS_PG_DATABASE':'endemias',
              'ENDEMIAS_PG_HOST':'127.0.0.1','ENDEMIAS_PG_PORT':'5432',
              'ENDEMIAS_SETORES_ENABLED':'1','ENDEMIAS_DOMINIO_BASE':'vsatt.com.br',
              'ENDEMIAS_ALLOWED_HOSTS':'endemias.vsatt.com.br','ENDEMIAS_LOCAL_PORT':'5000',
              'ENDEMIAS_AMBIENTAL_LOCAL_PORT':'5004','ENDEMIAS_TUNNEL_PORT':'5001'}
    if any(original['env'].get(k)!=v for k,v in expected.items()):
        raise ValueError('Entradas/ambiente mudaram; preservar e revisar.')
    proposed=copy.deepcopy(original);proposed['version']=target
    return proposed


def wait_closed(timeout=35):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        free=True
        for port in (5000,5001,5004):
            with socket.socket() as listener:
                listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
                try:listener.bind(('0.0.0.0',port))
                except OSError:free=False
        if free:return True
        time.sleep(.5)
    return False


def apply(args,origin=ORIGIN,target=TARGET,marker=MARKER):
    from app_core import postgresql_migrations,backup_completo,db
    if not ctypes.windll.shell32.IsUserAnAdmin():raise PermissionError('Execute como administrador do Windows.')
    if not all(re.fullmatch('[0-9a-f]{40}',v) for v in (args.release,args.expected_current)):
        raise ValueError('Commits completos obrigatórios.')
    if SOURCE==OFFICIAL or git('rev-parse','HEAD')!=args.expected_current or git('branch','--show-current')!='master' or git('status','--porcelain'):
        raise ValueError('Produção mudou; pacote não será integrado.')
    candidate=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True).strip()
    if candidate!=args.release or dirty:raise ValueError('Candidata mudou após validação.')
    git('merge-base','--is-ancestor',args.expected_current,args.release)
    if (SOURCE/'app_core/version.py').read_text(encoding='utf-8').splitlines()[0]!=f'APP_VERSION = "{target}"':
        raise ValueError('Versão candidata inesperada.')
    original=json.loads((HOME/'config.json').read_text(encoding='utf-8'));proposed=proposed_config(original,origin,target)
    connection=connect(original,readonly=True)
    try:
        status=postgresql_migrations.status(connection,SOURCE/'migrations/postgresql')
        if not status or any(r['state']!='applied' for r in status):
            raise ValueError('Este pacote não aplica migrações; esquema precisa estar atualizado.')
    finally:connection.close()
    win=Windows();win.web=win.sec.ConvertStringSidToSid(original['sid'])
    task=win.folder.GetTask('Endemias - Servidor')
    sid=win.sec.ConvertSidToStringSid(win.sec.LookupAccountName(None,task.Definition.Principal.UserId)[0])
    if sid!=original['sid'] or task.Definition.Principal.RunLevel!=0 or task.State!=4:
        raise ValueError('Tarefa/identidade limitada mudou.')
    auto=scheduled_import(win.folder);auto_enabled=bool(auto.Enabled) if auto else False
    state=HOME/(marker+'-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    state.mkdir();win.protect(state,remember=False,operator=False)
    shutil.copyfile(HOME/'config.json',state/'config-anterior.json')
    immutable={str(p):digest(p) for p in [OFFICIAL/n for n in ('secret.key','config.json','endemias.db','kobo_config.json','kobo_ambiental.json')]}
    native=HOME/'servico_web_windows.py';immutable[str(native)]=digest(native)
    report={'status':'preparando','state':str(state),'old_head':args.expected_current,'release':args.release,
            'version':target,'migrations_applied':[],'database_restored_or_deleted':False}
    output=HOME/(marker+'-resultado.json')
    stopped=integrated=False
    def save(stage):
        report['stage']=stage;output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        if auto_enabled:
            auto.Enabled=False
            if auto.State==4:raise RuntimeError('Importação iniciou durante a pausa; aguarde e revise.')
        save('backup_postgresql');report['backup']=backup_before_change(original,state)
        save('parando_aplicacao');task.Stop(0);stopped=True
        if not wait_closed():raise RuntimeError('Uma entrada continua ativa; não integrar templates.')
        before=database_fingerprints(original);files_before=operational_files(original)
        (state/'assinaturas-antes.json').write_text(json.dumps(before),encoding='utf-8')
        env=original['env'];save('backup_completo')
        info=backup_completo.criar_backup_completo(destino_dir=env['ENDEMIAS_BACKUP_COMPLETO_DIR'],raiz=OFFICIAL,manter=None,
            anexos_dir=env.get('ENDEMIAS_ANEXOS_DIR'),kobo_config_path=str(OFFICIAL/'kobo_config.json'),
            secret_key_path=str(OFFICIAL/'secret.key'),db_target=db.DatabaseTarget('postgresql','endemias'),postgresql_env=env)
        archive=Path(info['arquivo'])
        report['backup_completo']={'arquivo':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive)}
        save('integrando_codigo');git('merge','--ff-only',args.release);integrated=True
        report['tables_compared']=len(before)
        if before!=database_fingerprints(original,before) or files_before!=operational_files(original):
            raise RuntimeError('Dados/arquivos divergiram; não restaurar automaticamente.')
        save('ensaio_identidade_limitada');await_probe(task,proposed,report)
        if any(digest(p)!=checksum for p,checksum in immutable.items()):raise RuntimeError('Arquivo protegido mudou.')
        proposed['probe_only']=False
        (HOME/'config.json').write_text(json.dumps(proposed,indent=2),encoding='utf-8')
        save('iniciando_aplicacao');task.Run('')
        for address,port,host in [('127.0.0.1',5000,None),(env['ENDEMIAS_LOCAL_BIND'],5000,None),
              ('127.0.0.1',5004,None),(env['ENDEMIAS_LOCAL_BIND'],5004,None),
              ('127.0.0.1',5001,'endemias.vsatt.com.br'),('127.0.0.1',5001,'ambiental.vsatt.com.br')]:
            if not http_login(address,port,host,expected_version=target):raise RuntimeError('Uma entrada não confirmou a candidata.')
        if not origin_portal():raise RuntimeError('Portal não respondeu corretamente.')
        if auto_enabled:auto.Enabled=True
        report.update(status='aplicado',task_identity_preserved=True,existing_environment_preserved=proposed['env']==original['env'],
            previous_data_preserved=True,operational_files_preserved=True,kobo_configs_preserved=True,
            cloudflare_changed=False,firewall_changed=False,all_entries_ok=True,kobo_automation_enabled_restored=True)
        save('concluido');return 0
    except Exception as error:
        report.update(status='falhou',error_type=type(error).__name__,trace=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)])
        save('retorno')
        if stopped:
            if task.State==4:task.Stop(0)
            if not wait_closed():raise RuntimeError('Retorno aguarda liberação das três entradas.')
            shutil.copyfile(state/'config-anterior.json',HOME/'config.json')
        if integrated:
            if git('status','--porcelain') or git('rev-parse','HEAD')!=args.release:
                raise RuntimeError('Código mudou; retorno exige revisão sem sobrescrever.')
            git('restore','--source='+args.expected_current,'--staged','--worktree','.')
            git('commit','-m',f'rollback: retorna interface {origin} preservando dados e setores')
        if stopped:
            task.Run('');report['rollback_login_ok']=http_login('127.0.0.1',5000,expected_version=origin)
        if auto_enabled and (not stopped or report.get('rollback_login_ok')):auto.Enabled=True
        save('retornado');return 1


def main(origin=ORIGIN,target=TARGET,marker=MARKER):
    parser=argparse.ArgumentParser(description=f'Atualiza {origin} para {target}, sem migração de banco.')
    parser.add_argument('--aplicar',action='store_true',required=True)
    parser.add_argument('--release',required=True);parser.add_argument('--expected-current',required=True)
    args=parser.parse_args()
    try:return apply(args,origin,target,marker)
    except Exception as error:
        result={'status':'falhou','error_type':type(error).__name__,
                'trace':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)]}
        try:(HOME/(marker+'-falha.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
        except OSError:pass
        print('Atualização não concluída. Confira o relatório local com o Codex.');return 1


if __name__=='__main__':raise SystemExit(main())
