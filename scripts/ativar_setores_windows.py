"""Implanta a candidata por uma janela unica; nao restaura nem reduz o banco.

Requer administrador Windows. Preserva tarefa/identidade/credenciais, faz
backup, confere as colunas anteriores e retorna codigo/configuracao em falha.
Nao altera Cloudflare, senhas, niveis ou lotacao de contas existentes.
"""
import argparse
import copy
import ctypes
from datetime import datetime
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from scripts.ativar_acesso_externo_windows import connect, git, http_login
from scripts.endurecer_web_windows import Windows, backup_before_change, wait_closed, descendants
from scripts.endurecer_web_windows import split_windows

OFFICIAL = Path('C:/endemias')
HOME = Path('C:/ProgramData/EndemiasWeb')
TARGET = '2.0.0-rc.1'
MARKER = 'ativacao-setores200rc1'
RULE = 'Endemias - Ambiental LAN (VSATT 2)'
MIGRATION = '0035_setores.sql'
AUTO_TASK = 'Endemias - Importacao Kobo 1230'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def proposed_config(original):
    if (original.get('version')!='1.80.0' or original.get('server')!='waitress'
            or original.get('probe_only') or original.get('root')!=str(OFFICIAL)
            or original['env'].get('ENDEMIAS_DB_BACKEND')!='postgresql'
            or original['env'].get('ENDEMIAS_PG_DATABASE')!='endemias'
            or original['env'].get('ENDEMIAS_PG_HOST')!='127.0.0.1'
            or original['env'].get('ENDEMIAS_PG_PORT')!='5432'):
        raise ValueError('Instalacao diferente da origem conferida.')
    env=original['env']
    if (env.get('ENDEMIAS_ALLOWED_HOSTS')!='endemias.vsatt.com.br'
            or env.get('ENDEMIAS_LOCAL_PORT')!='5000' or env.get('ENDEMIAS_TUNNEL_PORT')!='5001'
            or env.get('ENDEMIAS_SETORES_ENABLED') not in (None,'0')):
        raise ValueError('Entradas oficiais mudaram; nao sobrescrever.')
    address=ipaddress.ip_address(env['ENDEMIAS_LOCAL_BIND'])
    if address.version!=4 or not address.is_private or address.is_unspecified or address.is_loopback:
        raise ValueError('IP local privado nao corresponde ao servidor.')
    kobo=Path(env.get('ENDEMIAS_KOBO_CONFIG_PATH',str(OFFICIAL/'kobo_config.json')))
    if kobo!=OFFICIAL/'kobo_config.json':
        raise ValueError('Caminho Kobo oficial mudou; revisar.')
    result=copy.deepcopy(original)
    result['version']=TARGET
    result['env'].update(ENDEMIAS_SETORES_ENABLED='1',ENDEMIAS_DOMINIO_BASE='vsatt.com.br',
                         ENDEMIAS_AMBIENTAL_LOCAL_PORT='5004')
    result['read_files']=list(dict.fromkeys([*result['read_files'],str(kobo.with_name('kobo_ambiental.json'))]))
    return result


def fingerprints(connection, previous=None):
    """Projeta somente colunas anteriores: ADD COLUMN nao mascara perda de dados."""
    from psycopg2 import sql
    with connection.cursor() as cursor:
        if previous is None:
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'endemias_schema_migrations' ORDER BY tablename")
            tables=[r[0] for r in cursor.fetchall()]
        else:
            tables=list(previous)
        result={}
        for table in tables:
            if previous is None:
                cursor.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',('public',table))
                columns=[r[0] for r in cursor.fetchall()]
            else:
                columns=previous[table]['columns']
            statement=sql.SQL('SELECT row_to_json(t)::text FROM (SELECT {} FROM public.{}) t ORDER BY row_to_json(t)::text').format(
                sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table))
            cursor.execute(statement)
            checksum=hashlib.sha256();count=0
            for row in cursor:
                checksum.update(row[0].encode('utf-8'));checksum.update(b'\n');count+=1
            result[table]={'columns':columns,'count':count,'sha256':checksum.hexdigest()}
    return result


def database_fingerprints(config, previous=None):
    connection=connect(config,readonly=True)
    try:return fingerprints(connection,previous)
    finally:connection.close()


def operational_files(config):
    roots=[Path(config['env'].get('ENDEMIAS_ANEXOS_DIR',str(OFFICIAL/'anexos'))),
           OFFICIAL/'notificacoes_geradas',OFFICIAL/'saida']
    result={}
    for root in roots:
        if not root.exists():continue
        if root.lstat().st_file_attributes & 0x400:
            raise ValueError('Diretorio operacional redirecionado; revisar.')
        for path in descendants(root):
            if path.lstat().st_file_attributes & 0x400:
                raise ValueError('Arquivo operacional redirecionado; revisar.')
            if path.is_file():result[str(path)]=digest(path)
    return result


def divided_kobo(raw):
    from app_core.setores import dividir_kobo,TIPOS_KOBO
    if (not isinstance(raw,dict) or not isinstance(raw.get('assets'),dict)
            or not isinstance(raw.get('api_token'),str) or not isinstance(raw.get('server_url'),str)
            or set(raw['assets'])-set().union(*TIPOS_KOBO.values())
            or any(not isinstance(v,str) for v in raw['assets'].values())):
        raise ValueError('Configuracao Kobo nao corresponde ao catalogo; revisar sem sobrescrever.')
    return dividir_kobo(raw)


def rule_values(bind):
    return {'Name':RULE,'Description':'Vigilancia Ambiental local; origem restrita a sub-rede local.',
        'Direction':1,'Action':1,'Protocol':6,'LocalPorts':'5004','LocalAddresses':bind,
        'RemoteAddresses':'LocalSubnet','Profiles':3,'EdgeTraversal':False,'Enabled':True}


def firewall_policy():
    import win32com.client
    return win32com.client.Dispatch('HNetCfg.FwPolicy2')


def add_firewall(bind):
    import win32com.client
    policy=firewall_policy()
    if any(r.Name==RULE for r in policy.Rules):
        raise ValueError('Regra Ambiental ja existe; nao sobrescrever.')
    rule=win32com.client.Dispatch('HNetCfg.FWRule')
    for key,value in rule_values(bind).items():setattr(rule,key,value)
    policy.Rules.Add(rule)


def remove_own_firewall(bind):
    policy=firewall_policy()
    rules=[r for r in policy.Rules if r.Name==RULE]
    if not rules:return
    if len(rules)!=1 or any(getattr(rules[0],k)!=v for k,v in rule_values(bind).items()):
        raise ValueError('Regra mudou depois da criacao; preservar para revisao.')
    policy.Rules.Remove(RULE)


def origin_portal():
    client=http.client.HTTPConnection('127.0.0.1',5001,timeout=5)
    try:
        client.request('GET','/',headers={'Host':'vsatt.com.br','CF-Connecting-IP':'203.0.113.21','X-Forwarded-Proto':'https'})
        response=client.getresponse();body=response.read()
        return (response.status==200 and b'https://endemias.vsatt.com.br' in body
                and b'https://ambiental.vsatt.com.br' in body and not response.getheader('Set-Cookie'))
    finally:client.close()


def scheduled_import(folder):
    try:
        task=folder.GetTask(AUTO_TASK)
    except Exception as error:
        codes=[getattr(error,'hresult',None)]
        info=getattr(error,'excepinfo',None)
        if info:codes.append(info[-1])
        if -2147024894 in codes:return None
        raise
    if task.State==4:
        raise RuntimeError('A importacao Kobo esta em andamento; aguarde o termino antes da atualizacao.')
    actions=task.Definition.Actions
    if actions.Count!=1:
        raise ValueError('A tarefa Kobo mudou; revisar sem sobrescrever a configuracao.')
    action=actions.Item(1)
    tokens=split_windows(action.Arguments)
    lowered=[t.lower() for t in tokens]
    if '-file' not in lowered:
        raise ValueError('Executor Kobo nao corresponde ao arquivo protegido.')
    position=lowered.index('-file')+1
    if (position>=len(tokens) or Path(tokens[position])!=OFFICIAL/'scripts/executar_importacao_kobo_automatica.ps1'
            or Path(action.Path).name.lower()!='powershell.exe'):
        raise ValueError('Executor Kobo aponta para outra instalacao; preservar e revisar.')
    return task


def await_probe(task, proposed, report):
    probe_path=HOME/'runtime/probe.json'
    probe_path.unlink(missing_ok=True)
    proposed['probe_only']=True
    (HOME/'config.json').write_text(json.dumps(proposed,indent=2),encoding='utf-8')
    task.Run('')
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        if probe_path.is_file():
            try:result=json.loads(probe_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:time.sleep(.2);continue
            report['probe']=result
            if not result.get('ok') or not all(result.get('checks',{}).values()):
                raise RuntimeError('Ensaio da conta limitada falhou.')
            break
        time.sleep(1)
    else:raise TimeoutError('Ensaio da conta limitada nao concluiu.')
    while task.State==4 and time.monotonic()<deadline:time.sleep(.5)
    if task.State==4:raise TimeoutError('Processo de ensaio nao encerrou.')


def apply(args):
    from app_core import postgresql_migrations,backup_completo,db
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError('Execute como administrador do Windows.')
    if not all(re.fullmatch('[0-9a-f]{40}',v) for v in (args.release,args.expected_current)):
        raise ValueError('Commits completos obrigatorios.')
    if SOURCE==OFFICIAL or git('rev-parse','HEAD')!=args.expected_current or git('branch','--show-current')!='master' or git('status','--porcelain'):
        raise ValueError('Instalacao mudou; nao integrar pacote desatualizado.')
    candidate=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True).strip()
    if candidate!=args.release or dirty:raise ValueError('Pacote mudou depois da validacao.')
    git('merge-base','--is-ancestor',args.expected_current,args.release)
    if (SOURCE/'app_core/version.py').read_text(encoding='utf-8').splitlines()[0]!=f'APP_VERSION = "{TARGET}"':
        raise ValueError('Versao da candidata diferente da conferida.')
    original=json.loads((HOME/'config.json').read_text(encoding='utf-8'))
    proposed=proposed_config(original)
    kobo=OFFICIAL/'kobo_config.json';ambiental=kobo.with_name('kobo_ambiental.json')
    if ambiental.exists():raise ValueError('Configuracao Ambiental ja existe; preservar e revisar.')
    raw=json.loads(kobo.read_text(encoding='utf-8'))
    divided=divided_kobo(raw)
    if any(r.Name==RULE for r in firewall_policy().Rules):raise ValueError('Regra Ambiental ja existe.')
    connection=connect(original,readonly=True)
    try:
        status=postgresql_migrations.status(connection,SOURCE/'migrations/postgresql')
        if [r['name'] for r in status if r['state']=='pending']!=[MIGRATION] or any(r['state']=='checksum_mismatch' for r in status):
            raise ValueError('Migracoes diferentes da unica prevista.')
    finally:connection.close()
    win=Windows();win.web=win.sec.ConvertStringSidToSid(original['sid'])
    task=win.folder.GetTask('Endemias - Servidor')
    sid=win.sec.ConvertSidToStringSid(win.sec.LookupAccountName(None,task.Definition.Principal.UserId)[0])
    if sid!=original['sid'] or task.Definition.Principal.RunLevel!=0 or task.State!=4:
        raise ValueError('Tarefa/identidade limitada nao corresponde ao estado esperado.')
    auto_task=scheduled_import(win.folder)
    auto_enabled=bool(auto_task.Enabled) if auto_task else False
    state=HOME/(MARKER+'-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    state.mkdir();win.protect(state,remember=False,operator=False)
    native=HOME/'servico_web_windows.py'
    shutil.copyfile(HOME/'config.json',state/'config-anterior.json')
    shutil.copyfile(native,state/'bootstrap-anterior.py')
    shutil.copyfile(kobo,state/'kobo-anterior.json')
    report={'status':'preparando','state':str(state),'old_head':args.expected_current,'release':args.release,'version':TARGET}
    output=HOME/(MARKER+'-resultado.json')
    def save(stage):
        report['stage']=stage
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    immutable={str(p):digest(p) for p in [OFFICIAL/'secret.key',OFFICIAL/'config.json',OFFICIAL/'endemias.db']}
    stopped=integrated=firewall_created=False
    report['kobo_automation_found']=auto_task is not None
    try:
        if auto_enabled:
            auto_task.Enabled=False
            report['kobo_automation_paused']=True
            if auto_task.State==4:raise RuntimeError('A importacao iniciou durante a pausa; aguarde e revise.')
        save('backup_postgresql')
        report['backup']=backup_before_change(original,state)
        save('parando_aplicacao')
        task.Stop(0);stopped=True
        if not wait_closed():raise RuntimeError('Aplicacao nao encerrou; nao iniciar outra instancia.')
        before=database_fingerprints(original)
        files_before=operational_files(original)
        (state/'assinaturas-antes.json').write_text(json.dumps(before),encoding='utf-8')
        save('backup_completo')
        env=original['env']
        info=backup_completo.criar_backup_completo(destino_dir=env['ENDEMIAS_BACKUP_COMPLETO_DIR'],raiz=OFFICIAL,manter=None,
            anexos_dir=env.get('ENDEMIAS_ANEXOS_DIR'),kobo_config_path=str(kobo),secret_key_path=str(OFFICIAL/'secret.key'),
            db_target=db.DatabaseTarget('postgresql','endemias'),postgresql_env=env)
        archive=Path(info['arquivo'])
        report['backup_completo']={'arquivo':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive)}
        save('integrando_codigo')
        git('merge','--ff-only',args.release);integrated=True
        save('migracao0035')
        connection=connect(original)
        try:
            applied=postgresql_migrations.apply_pending(connection,OFFICIAL/'migrations/postgresql')
            report['migrations_applied']=applied
            if applied!=[MIGRATION]:raise RuntimeError('Migracao diferente da prevista.')
        finally:connection.close()
        after=database_fingerprints(original,before)
        report['tables_compared']=len(before)
        report['previous_columns_preserved']=before==after
        report['operational_files_preserved']=files_before==operational_files(original)
        if not report['previous_columns_preserved'] or not report['operational_files_preserved']:
            raise RuntimeError('Dados anteriores divergiram; preservar sem restaurar dump.')
        save('configurando_setores')
        for path,sector in [(kobo,'endemias'),(ambiental,'ambiental')]:
            path.write_text(json.dumps(divided[sector],ensure_ascii=False,indent=2),encoding='utf-8')
        win.protect(ambiental,policy='write_file',remember=False,operator=False)
        if json.loads(kobo.read_text(encoding='utf-8'))!=divided['endemias'] or json.loads(ambiental.read_text(encoding='utf-8'))!=divided['ambiental']:
            raise RuntimeError('Configuracao Kobo nao corresponde a divisao preparada.')
        native.write_bytes((OFFICIAL/'scripts/servico_web_windows.py').read_bytes())
        if any(digest(path)!=checksum for path,checksum in immutable.items()):
            raise RuntimeError('Arquivo imutavel mudou.')
        save('ensaio_conta_limitada')
        await_probe(task,proposed,report)
        save('entrada_ambiental_local')
        add_firewall(env['ENDEMIAS_LOCAL_BIND']);firewall_created=True
        proposed['probe_only']=False
        (HOME/'config.json').write_text(json.dumps(proposed,indent=2),encoding='utf-8')
        save('iniciando_aplicacao')
        task.Run('')
        for address,port,host in [('127.0.0.1',5000,None),(env['ENDEMIAS_LOCAL_BIND'],5000,None),
             ('127.0.0.1',5004,None),(env['ENDEMIAS_LOCAL_BIND'],5004,None),
             ('127.0.0.1',5001,'endemias.vsatt.com.br'),('127.0.0.1',5001,'ambiental.vsatt.com.br')]:
            if not http_login(address,port,host,expected_version=TARGET):raise RuntimeError('Uma entrada nao confirmou a candidata.')
        if not origin_portal():raise RuntimeError('Portal nao confirmou os dois links.')
        if not all(digest(p)==v for p,v in immutable.items()):
            raise RuntimeError('Arquivo imutavel divergiu ao concluir a ativacao.')
        if auto_enabled:auto_task.Enabled=True
        report.update(status='aplicado',task_identity_preserved=True,users_levels_passwords_unchanged=True,
            all_existing_users_endemias=True,kobo_separated=True,accounts_sector_assignments=0,
            local_endemias_200=True,local_ambiental_200=True,origin_three_hosts_ok=True,
            immutable_files_preserved=all(digest(p)==v for p,v in immutable.items()),
            cloudflare_changed=False,database_restored_or_deleted=False,
            kobo_automation_schedule_identity_preserved=True,kobo_automation_enabled_restored=True)
        save('concluido')
        return 0
    except Exception as error:
        report.update(status='falhou',error_type=type(error).__name__,trace=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)])
        save('retorno')
        if stopped:
            if task.State==4:task.Stop(0)
            if not wait_closed():raise RuntimeError('Retorno aguarda parada; preservar estado.')
            for path,label in [(kobo,'kobo-endemias-pos-falha.json'),(ambiental,'kobo-ambiental-pos-falha.json')]:
                if path.exists():shutil.copyfile(path,state/label)
            shutil.copyfile(state/'config-anterior.json',HOME/'config.json')
            shutil.copyfile(state/'bootstrap-anterior.py',native)
            shutil.copyfile(state/'kobo-anterior.json',kobo)
            # A nova configuracao fica privada no snapshot; nao descartar uma edicao eventual.
            if ambiental.exists():
                win.protect(ambiental,remember=False,operator=False)
                ambiental.unlink()
        if firewall_created:remove_own_firewall(original['env']['ENDEMIAS_LOCAL_BIND'])
        if integrated:
            if git('status','--porcelain') or git('rev-parse','HEAD')!=args.release:
                raise RuntimeError('Codigo mudou; retorno exige revisao sem sobrescrever.')
            git('restore','--source='+args.expected_current,'--staged','--worktree','.')
            git('commit','-m','rollback: retorna 1.80 preservando esquema aditivo e dados novos')
        if stopped:
            task.Run('')
            report['rollback_login_ok']=http_login('127.0.0.1',5000,expected_version='1.80.0')
        if auto_enabled and (not stopped or report.get('rollback_login_ok')):
            auto_task.Enabled=True
            report['kobo_automation_enabled_restored']=True
        report['database_restored_or_deleted']=False
        save('retornado')
        return 1
    finally:output.write_text(json.dumps(report,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aplicar',action='store_true',required=True)
    parser.add_argument('--release',required=True)
    parser.add_argument('--expected-current',required=True)
    args=parser.parse_args()
    try:return apply(args)
    except Exception as error:
        # Sem argumentos completos, mensagens SQL ou conteudos de configuracoes.
        result={'status':'falhou','error_type':type(error).__name__,'trace':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)]}
        try:(HOME/(MARKER+'-falha.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
        except OSError:pass
        print('Atualizacao nao concluida. Confira o relatorio local com o Codex.')
        return 1


if __name__=='__main__':raise SystemExit(main())
