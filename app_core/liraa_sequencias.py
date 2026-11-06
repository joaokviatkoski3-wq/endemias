"""Expansão de unidades de um envio LIRAa, sem replicar produção ou laboratório."""
import hashlib
import json
import re
import unicodedata

META='_sequencias_v1'


def separar(value):
    from app_core.liraa_kobo import LiraaKoboError
    raw=unicodedata.normalize('NFKC',str('' if value is None else value)).strip()
    if len(raw)>2000:raise LiraaKoboError('Sequência LIRAa excede 2.000 caracteres.')
    if not raw:return [''],[]
    text=re.sub('[‐‑‒–—−]','-',raw)
    if text.upper() in {'N/A','S/N','SEM SEQUÊNCIA','SEM SEQUENCIA','NÃO SE APLICA'}:return [text.upper()],[]
    if text=='-':return [''],[]
    # A-1 ou B/02 isolados são identificadores compostos, não duas unidades.
    if re.fullmatch(r'[A-Za-z]+\s*[-/]\s*\d+',text):
        return [re.sub(r'\s+','',text).upper()],[]
    text=re.sub(r'(?<=\w)\s+[eE]\s+(?=\w)',',',text)
    if re.search(r'\b\d+\s+[aA]\s+\d+\b',text):raise LiraaKoboError('Intervalo ambíguo: informe cada sequência separadamente.')
    parts=[]
    for chunk in re.split(r'[,;|\\\r\n\t]+',text):
        for piece in re.split(r'\s+-\s+',chunk.strip()):
            piece=piece.strip()
            if not piece:continue
            if re.fullmatch(r'[A-Za-z]+\s*[-/]\s*\d+',piece):
                parts.append(re.sub(r'\s+','',piece).upper());continue
            if re.fullmatch(r'[A-Za-z]+[-/]\d+(?:[-/][A-Za-z]+[-/]\d+)+',piece):
                raise LiraaKoboError('Sequência ambígua: use vírgulas entre identificadores compostos, como A-1, A-2.')
            parts.extend(p.strip().upper() for p in re.split(r'[/\-]+',piece) if p.strip())
    if len(parts)==1:
        words=parts[0].split()
        if len(words)>1 and all(re.fullmatch(r'(?:[A-Z]*\d+[A-Z]*|[A-Z])',w) for w in words):parts=words
    if not parts:raise LiraaKoboError('Informe ao menos uma sequência válida.')
    if len(parts)>50:raise LiraaKoboError('Máximo de 50 sequências por envio. Nenhuma visita deste lote foi gravada.')
    if any(len(p)>100 for p in parts):raise LiraaKoboError('Identificador de sequência muito longo.')
    unique=list(dict.fromkeys(parts))
    warnings=['Sequências repetidas no envio foram consideradas uma única vez.'] if len(unique)!=len(parts) else []
    return unique,warnings


def filho_uuid(root,sequence):
    return 'liraa-seq:'+hashlib.sha256(json.dumps([root,sequence],ensure_ascii=False).encode()).hexdigest()


def avisos(item):
    meta=json.loads(item.get('tratamento_json') or '{}').get(META,{})
    return meta.get('avisos',[])


def expandir(conn,item):
    """Mantém o UUID original na primeira unidade e um identificador estável nas demais."""
    from app_core.liraa_kobo import LiraaKoboError
    root=item['kobo_uuid'];parts,warnings=separar(item['sequencia'])
    candidates=[root]+[filho_uuid(root,p) for p in parts]
    placeholders=','.join('?' for _ in candidates)
    old=conn.execute('SELECT kobo_uuid,tratamento_json FROM liraa_visitas WHERE kobo_uuid IN ('+placeholders+')',candidates).fetchall()
    deleted={r[0] for r in conn.execute('SELECT kobo_uuid FROM liraa_visitas_excluidas WHERE kobo_uuid IN ('+placeholders+')',candidates)}
    previous=next((json.loads(r['tratamento_json']).get(META) for r in old if json.loads(r['tratamento_json']).get(META)),None)
    # Um registro antigo pode ter correções/leituras. Não o reinterpretar por reimportação.
    if not previous and (old or root in deleted):
        if len(parts)>1:
            item['_aviso_legado']='Envio antigo não expandido: revisar os dados históricos antes de reimportar suas sequências.'
        return [item]
    if not previous and not old and deleted and root not in deleted:
        raise LiraaKoboError('Há unidades excluídas sem o histórico completo do grupo. Confira as exclusões antes de reimportar.')
    if previous and previous.get('uuid_origem')!=root:raise LiraaKoboError('Identificador de sequência conflita com outro envio.')
    first=parts[0]
    if previous:
        if set(previous['unidades'])!=set(parts):
            raise LiraaKoboError('As sequências de um envio já importado mudaram. Confira o lançamento antes de reimportar.')
        first=previous['primeira']
        parts=[first]+[p for p in parts if p!=first]
    if len(parts)>1 and item['tubitos']:
        warnings.append('Tubitos mantidos na primeira sequência ('+first+'); conferir a atribuição das coletas entre os imóveis.')
    result=[]
    for i,part in enumerate(parts):
        child=dict(item);child['sequencia']=part
        child['kobo_uuid']=root if i==0 else filho_uuid(root,part)
        treatment=json.loads(item['tratamento_json'])
        if i:
            child['tubitos']=[]
            treatment={'_campo':{k:v for k,v in treatment.get('_campo',{}).items() if k!='houve_coleta'}}
        treatment[META]={'uuid_origem':root,'original':item['sequencia'],'unidades':parts,'primeira':first,'avisos':warnings}
        child['tratamento_json']=json.dumps(treatment,ensure_ascii=False)
        result.append(child)
    return result
