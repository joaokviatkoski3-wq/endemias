"""Lê somente a estrutura dos formulários configurados, nunca as respostas.

Executado após promoção 2.0.0 no console administrativo. Não grava config,
last_sync, banco, arquivo importado ou dados no Kobo. Relatório local exclui
token, UID, URL privada, respostas e listas de pessoas/localidades.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib import request,error,parse

ROOT=Path(__file__).resolve().parents[1]
OFFICIAL=Path('C:/endemias')
REPORT=ROOT/'.venv/auditoria-geral/kobo-esquemas.json'
ALLOWED={'kf.kobotoolbox.org','eu.kobotoolbox.org'}


def label(value):
    if isinstance(value,str):return value[:400]
    if isinstance(value,list):return next((label(v) for v in value if label(v)),'')
    if isinstance(value,dict):return next((label(v) for v in value.values() if label(v)),'')
    return ''


def norm(value):
    return unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()


def schema(content,kind):
    fields=[];groups=[];allowed_lists=set()
    for row in content.get('survey') or []:
        if not isinstance(row,dict):continue
        type_=str(row.get('type') or '')
        name=str(row.get('$autoname') or row.get('name') or '')
        if type_ in {'end_group','end_repeat'}:
            if groups:groups.pop()
            continue
        text=label(row.get('label'))
        entry={'name':name,'type':type_,'label':text,'group':'/'.join(groups)}
        fields.append(entry)
        if type_ in {'begin_group','begin_repeat'}:groups.append(name)
        # Apenas escolhas operacionais do BRI, excluindo cadastros nominais.
        combined=norm(name+' '+text)
        if (kind=='BRI' and re.search(r'tratamento|imovel|deposito',combined)
                and not re.search(r'agente|localidade|nome|endereco|logradouro|morador|paciente|responsavel',combined)):
            list_name=row.get('select_from_list_name') or row.get('select_from_list')
            if not list_name and type_.startswith('select_') and ' ' in type_:list_name=type_.split(' ',1)[1]
            if list_name:allowed_lists.add(str(list_name))
    choices=[{'list':str(r.get('list_name','')),'value':str(r.get('name','')),'label':label(r.get('label'))}
             for r in content.get('choices') or [] if isinstance(r,dict) and str(r.get('list_name','')) in allowed_lists]
    return {'fields':fields,'operational_choices':choices,'personal_choices_exported':False}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def get_metadata(base,token,path):
    if not re.fullmatch(r'/api/v2/assets/[A-Za-z0-9_-]+/(?:versions/[A-Za-z0-9_-]+/)?',path):
        raise ValueError('Apenas metadados de assets/versões são permitidos.')
    req=request.Request(base+path+'?format=json',headers={
        'Authorization':'Token '+token,'Accept':'application/json','User-Agent':'VSATT-schema-audit/2.0.0'})
    with request.build_opener(NoRedirect).open(req,timeout=15) as response:
        body=response.read(10*1024*1024+1)
    if len(body)>10*1024*1024:raise ValueError('Estrutura excede o limite de leitura.')
    return json.loads(body)


def collect_one(item,fetch=get_metadata):
    sector,kind,uid,base,token=item
    result={'sector':sector,'type':kind,'asset_hash':hashlib.sha256(uid.encode()).hexdigest()[:12]}
    try:
        if not re.fullmatch('[A-Za-z0-9_-]+',uid):raise ValueError('UID inválido.')
        asset=fetch(base,token,f'/api/v2/assets/{uid}/')
        content=asset.get('content') or {};source='asset.content (pode conter rascunho)'
        version=asset.get('deployed_version_id')
        if isinstance(version,str) and re.fullmatch('[A-Za-z0-9_-]+',version):
            try:
                deployed=fetch(base,token,f'/api/v2/assets/{uid}/versions/{version}/')
                if isinstance(deployed.get('content'),dict):content=deployed['content'];source='versão implantada'
            except Exception:pass
        result.update(status='ok',definition_source=source,**schema(content,kind))
    except Exception as exc:
        result.update(status='indisponivel',error_type=type(exc).__name__)
        if isinstance(exc,error.HTTPError):result['http_status']=exc.code
    return result


def main():
    if ROOT==OFFICIAL:raise ValueError('Execute a cópia de auditoria, não a produção.')
    items=[];errors=[]
    for sector,name in [('endemias','kobo_config.json'),('ambiental','kobo_ambiental.json')]:
        try:
            cfg=json.loads((OFFICIAL/name).read_text(encoding='utf-8'))
            base=str(cfg.get('server_url','')).rstrip('/');parts=parse.urlsplit(base)
            if parts.scheme!='https' or parts.hostname not in ALLOWED or parts.path or parts.username or parts.port:
                raise ValueError('Servidor fora da lista conferida.')
            token=str(cfg.get('api_token') or '')
            if not token:raise ValueError('Token ausente.')
            for kind,uid in (cfg.get('assets') or {}).items():
                if isinstance(uid,str) and uid:items.append((sector,kind,uid,base,token))
        except Exception as exc:errors.append({'sector':sector,'error_type':type(exc).__name__})
    with ThreadPoolExecutor(max_workers=3) as pool:forms=list(pool.map(collect_one,items))
    report={'only_schema':True,'responses_read':False,'production_written':False,
            'forms':forms,'errors':errors,'status':'ok' if not errors and all(f['status']=='ok' for f in forms) else 'parcial'}
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Estruturas Kobo consultadas; nenhuma resposta lida ou alterada. Relatório local salvo.',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Coleta de estrutura indisponível: '+type(exc).__name__+'. Sem alteração no sistema.')
        raise SystemExit(0)
