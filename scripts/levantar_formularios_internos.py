"""Consulta apenas definições implantadas; não acessa /data nem altera produção.

Saída privada em .venv; não versionar catálogos, nomes ou definições recebidas.
"""
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.auditar_esquemas_kobo import get_metadata, ALLOWED

OUT=ROOT/'.venv/formularios-internos/definicoes.json'


def extrair(content):
    allowed=('name','$autoname','type','label','hint','required','relevant','constraint',
             'constraint_message','calculation','default','select_from_list_name',
             'select_from_list','choice_filter','appearance')
    return {'survey':[{k:r[k] for k in allowed if k in r} for r in content.get('survey',[]) if isinstance(r,dict)],
            'choices':[r for r in content.get('choices',[]) if isinstance(r,dict)]}


def main():
    if ROOT==Path('C:/endemias'):raise ValueError('Exige worktree de desenvolvimento.')
    forms=[];errors=[]
    for sector,filename in (('endemias','kobo_config.json'),('ambiental','kobo_ambiental.json')):
        cfg=json.loads((Path('C:/endemias')/filename).read_text(encoding='utf-8'))
        base=str(cfg.get('server_url','')).rstrip('/');url=urlsplit(base)
        if url.scheme!='https' or url.hostname not in ALLOWED or url.path or url.username or url.port:
            raise ValueError('Servidor Kobo não permitido.')
        for kind,uid in cfg.get('assets',{}).items():
            if not uid:continue
            try:
                if not re.fullmatch('[A-Za-z0-9_-]+',uid):raise ValueError('Identificador inválido.')
                asset=get_metadata(base,cfg['api_token'],f'/api/v2/assets/{uid}/')
                version=asset.get('deployed_version_id')
                if not isinstance(version,str) or not re.fullmatch('[A-Za-z0-9_-]+',version):
                    raise ValueError('Formulário sem versão implantada.')
                deployed=get_metadata(base,cfg['api_token'],f'/api/v2/assets/{uid}/versions/{version}/')
                content=deployed.get('content')
                if not isinstance(content,dict):raise ValueError('Definição ausente.')
                forms.append({'sector':sector,'tipo':kind,**extrair(content)})
            except Exception as exc:
                errors.append({'sector':sector,'tipo':kind,'error_type':type(exc).__name__})
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'somente_definicoes':True,'respostas_consultadas':False,
        'forms':forms,'errors':errors},ensure_ascii=False),encoding='utf-8')
    print(f'Definicoes consultadas: {len(forms)}. Pendencias: {len(errors)}.')
    print('Nenhuma resposta consultada; nenhum banco, servico ou formulario alterado.')
    print('Relatorio privado salvo para o desenvolvimento dos formularios internos.')
    return 0 if not errors else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Consulta nao concluida: '+type(exc).__name__+'. Avise o Codex.');raise SystemExit(1)
