"""Janela 1.79 -> 1.80: dependencias locais verificadas, copias antigas e sessao."""
import argparse
import ctypes
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ativar_recuperacao_senha_windows import Release, apply, config_atualizada, git, HOME
from scripts.endurecer_web_windows import Windows, READ, EXECUTE

RELEASE=Release('1.79.0','1.80.0','0034_sessoes_revogaveis.sql','ativacao180',snapshot_completo=True)
LEGADOS=('pre_agent_text_restore_20260710_083840.db','pre_reparo_kobo_api_20260707_150011.db')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def conferir_wheels(directory, manifest):
    actual={p.name:digest(p) for p in directory.iterdir() if p.is_file()}
    if actual!=manifest or not actual or any(not name.endswith('.whl') for name in actual):
        raise ValueError('Pacotes locais diferem dos hashes conferidos.')


def proteger_legados(config, state):
    root=Path('D:/BackupsEndemias')
    if root.resolve()!=root or root.lstat().st_file_attributes & 0x400:
        raise ValueError('Diretorio de backups inesperado ou redirecionado.')
    files=[root/name for name in LEGADOS]
    if any(not p.is_file() or p.lstat().st_file_attributes & 0x400 for p in files):
        raise ValueError('Inventario das copias antigas mudou; revisar antes de alterar permissoes.')
    before={p.name:digest(p) for p in files}
    win=Windows()
    win.web=win.sec.ConvertStringSidToSid(config['sid'])
    for p in [root,*files]:
        win.remember(p)
    (state/'permissoes-anteriores.json').write_text(json.dumps(win.journal,indent=2),encoding='utf-8')
    win.protect(root,remember=False)
    # Apenas atravessar/ler o diretorio raiz; nao herdar leitura para os arquivos.
    sd=win.sec.GetNamedSecurityInfo(str(root),win.sec.SE_FILE_OBJECT,win.sec.DACL_SECURITY_INFORMATION)
    acl=sd.GetSecurityDescriptorDacl()
    acl.AddAccessAllowedAceEx(win.sec.ACL_REVISION_DS,0,READ|EXECUTE,win.web)
    win.sec.SetNamedSecurityInfo(str(root),win.sec.SE_FILE_OBJECT,
        win.sec.DACL_SECURITY_INFORMATION|win.sec.PROTECTED_DACL_SECURITY_INFORMATION,None,None,acl,None)
    for p in files:
        win.protect(p,remember=False)
    after={p.name:digest(p) for p in files}
    if before!=after:
        raise RuntimeError('Conteudo de copia antiga mudou; nao excluir nem restaurar automaticamente.')
    broad={'S-1-1-0','S-1-5-11','S-1-5-32-545'}
    for p in [root,*files]:
        sd=win.sec.GetNamedSecurityInfo(str(p),win.sec.SE_FILE_OBJECT,win.sec.DACL_SECURITY_INFORMATION)
        acl=sd.GetSecurityDescriptorDacl()
        if any(win.sec.ConvertSidToStringSid(acl.GetAce(i)[2]) in broad for i in range(acl.GetAceCount())):
            raise RuntimeError('Grupo amplo ainda presente nas permissoes.')
    return {'arquivos':before,'conteudo_preservado':True,'grupos_amplos_removidos':True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--aplicar',action='store_true',required=True)
    parser.add_argument('--release',required=True)
    parser.add_argument('--expected-current',required=True)
    args=parser.parse_args()
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print('Execute como administrador do Windows. Nenhuma alteracao realizada.')
        return 1
    report={'status':'preparando'}
    output=HOME/'seguranca180-preparacao.json'
    try:
        if git('rev-parse','HEAD')!=args.expected_current or git('status','--porcelain'):
            raise ValueError('Instalacao oficial mudou.')
        candidate=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        dirty=subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True).strip()
        if candidate!=args.release or dirty:
            raise ValueError('Pacote mudou depois da validacao.')
        config=json.loads((HOME/'config.json').read_text(encoding='utf-8'))
        config_atualizada(config,RELEASE)
        if config['env'].get('ENDEMIAS_PG_DATABASE')!='endemias':
            raise ValueError('Banco oficial inesperado.')
        wheels=ROOT/'.venv/wheels-seguranca'
        manifest=json.loads((ROOT/'scripts/wheels_seguranca_manifest.json').read_text(encoding='utf-8'))
        conferir_wheels(wheels,manifest)
        runtime=HOME/'python/Scripts/python.exe'
        with (HOME/'instalacao-py7zr180.log').open('w',encoding='utf-8') as log:
            subprocess.run([str(runtime),'-I','-m','pip','--isolated','install','--no-index','--find-links',str(wheels),
                            '--require-hashes','-r',str(ROOT/'scripts/requirements_seguranca.lock')],stdout=log,stderr=log,check=True)
            subprocess.run([str(runtime),'-I','-m','pip','--isolated','check'],stdout=log,stderr=log,check=True)
        report['pacotes_locais_verificados']=True
        state=HOME/('seguranca180-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
        state.mkdir()
        Windows().protect(state,remember=False,operator=False)
        report['copias_antigas']=proteger_legados(config,state)
        report['status']='preparado'
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        return apply(args,RELEASE)
    except Exception as error:
        report.update(status='falhou',error_type=type(error).__name__,trace=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)])
        print('Atualizacao nao concluida. Confira os relatorios locais com o Codex.')
        return 1
    finally:
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':
    raise SystemExit(main())
