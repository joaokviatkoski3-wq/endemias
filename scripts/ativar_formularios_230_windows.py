"""Instala catálogo privado e ativa a captura interna sem migração de banco."""
import ctypes
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ativar_interface_setores_windows import main


def instalar_definicoes(source=None,home=None):
    from app_core.formularios_kobo import compilar,TITULOS
    if not ctypes.windll.shell32.IsUserAnAdmin():raise PermissionError('Execute como administrador.')
    source=Path(source or ROOT/'.venv/formularios-internos/definicoes.json')
    home=Path(home or 'C:/ProgramData/EndemiasWeb')
    if json.loads((home/'config.json').read_text(encoding='utf-8')).get('version')!='2.2.1':
        raise ValueError('Origem não é 2.2.1; catálogo preservado.')
    raw=source.read_bytes();data=json.loads(raw)
    if not data.get('somente_definicoes') or data.get('respostas_consultadas') is not False or data.get('errors'):
        raise ValueError('Catálogo de definição incompleto.')
    if {f['tipo'] for f in data['forms']}!=set(TITULOS) or len(data['forms'])!=10:
        raise ValueError('São necessárias as dez definições conferidas.')
    for form in data['forms']:compilar(form)
    destination=home/'formularios-kobo.json'
    if destination.exists():
        previous=destination.read_bytes();digest=hashlib.sha256(previous).hexdigest()[:16]
        (home/('formularios-kobo-anterior-'+digest+'.json')).write_bytes(previous)
    temporary=home/'formularios-kobo-novo.tmp';temporary.write_bytes(raw)
    import win32security
    # O arquivo recém-criado recebe a mesma proteção de leitura da configuração do serviço.
    security=win32security.GetFileSecurity(str(home/'config.json'),win32security.DACL_SECURITY_INFORMATION)
    win32security.SetFileSecurity(str(temporary),win32security.DACL_SECURITY_INFORMATION,security)
    temporary.replace(destination)
    print('Dez definições privadas instaladas. Nenhuma resposta Kobo consultada ou alterada.')


if __name__=='__main__':
    try:
        instalar_definicoes()
        raise SystemExit(main(origin='2.2.1',target='2.3.0',marker='ativacao-formularios230'))
    except Exception as exc:
        print('Ativação não concluída: '+type(exc).__name__+'. Avise o Codex.');raise SystemExit(1)
