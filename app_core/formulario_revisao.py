"""Fila de revisão administrativa, limitada aos formulários do setor ativo."""
from datetime import date
import json

from app_core import db, formularios as forms, formularios_kobo as kobo
from app_core import formulario_campo, formulario_piloto, setores
from app_core.formularios import versao

SITUACOES = {
    "pendentes": "Pendentes", "enviado": "Enviado",
    "em_revisao": "Em revisão", "aprovado": "Aprovado", "devolvido": "Devolvido",
    "oficializado": "Registrado", "todos": "Todos os envios",
}
POR_PAGINA = 30


def tipos(usuario):
    allowed = {kobo.KIND_PREFIX+code: title for code, title in kobo.TITULOS.items()
               if kobo.permitido(code, usuario)}
    if setores.atual() != "ambiental":
        allowed = {forms.FORMULARIOS[0]["tipo"]: forms.FORMULARIOS[0]["titulo"], **allowed}
    return allowed


def _resumo(payload, tipo, definicoes, agentes):
    if tipo == "rg_atualizacao":
        return dict(localidade=payload.get("localidade"), quadra=payload.get("quarteirao"),
                    data=payload.get("data_atualizacao"), endereco="",
                    equipe=[agentes.get(i,str(i)) for i in (payload.get("agentes_ids") or [])],
                    complemento=f'{len(payload.get("linhas") or [])} imóvel(is)')
    code = tipo[len(kobo.KIND_PREFIX):]
    key = (code, payload.get("versao"))
    if key not in definicoes:
        try:
            original = kobo.carregar("PE" if code=="PE_CADASTRO" else code)
            schema = kobo.compilar(original)
            if code in formulario_piloto.TIPOS and (code=="PE_CADASTRO" or schema["versao"]!=key[1]):
                schema = kobo.compilar(formulario_piloto.adaptar(original,code))
            definicoes[key] = {node["path"]:node for node in kobo.percorrer(schema["nodes"])}
        except (KeyError, ValueError, OSError):
            definicoes[key] = {}
    reference = payload.get("referencia_campo") or {}
    result = dict(localidade=reference.get("localidade"), quadra=reference.get("quarteirao"),
                  endereco=reference.get("logradouro"), numero=reference.get("numero"),
                  data=None, equipe=[], complemento=reference.get("nome"))
    for path, value in (payload.get("values") or {}).items():
        if not value:
            continue
        node=definicoes[key].get(path,{})
        name=formulario_campo.chave(path.rsplit("/",1)[-1])
        options={c["value"]:c["label"] for c in node.get("options",[])}
        if formulario_campo.equipe(node):
            picks=[str(value)] if node["kind"]=="select_one" else str(value).split()
            result["equipe"].extend(options.get(v,v) for v in picks)
        elif ((name in {"data","digiteadata","datavisita","datadavisita","datadacoleta"})
              or node.get("kind")=="date") and not result["data"]:
            result["data"]=str(value)[:10]
        elif name.startswith(("localidade","vsattlocalidade")) and not result["localidade"]:
            result["localidade"]=options.get(str(value),value)
        elif name.startswith(("quarteir","vsattquarteirao")) and not result["quadra"]:
            result["quadra"]=value
        elif name.startswith(("logradouro","vsattlogradouro")) and not result["endereco"]:
            result["endereco"]=options.get(str(value),value)
        elif name in {"numero","nmero","vsattnumero"} and not result["numero"]:
            result["numero"]=value
    result["equipe"]=list(dict.fromkeys(result["equipe"]))
    if result["endereco"] and result["numero"]:
        result["endereco"]=f'{result["endereco"]}, {result["numero"]}'
    return result


def listar(target, usuario, args):
    catalogo=tipos(usuario)
    filtros={k:str(args.get(k,"")).strip()[:150] for k in ("tipo","agente","autor","localidade","busca","inicio","fim")}
    filtros["status"]=args.get("status","pendentes")
    if filtros["status"] not in SITUACOES:
        filtros["status"]="pendentes"
    for k in ("inicio","fim"):
        if filtros[k]:
            filtros[k]=date.fromisoformat(filtros[k]).isoformat()
    pagina=max(args.get("pagina",1,type=int),1)
    tipos_sql=[filtros["tipo"]] if filtros["tipo"] in catalogo else list(catalogo)
    itens, definicoes = [], {}
    if not tipos_sql:
        return itens, filtros, 0, pagina
    conn=db.connect(target)
    try:
        if not db.table_exists(conn,"formularios"):
            return itens,filtros,0,pagina
        agentes={r[0]: r[1] for r in conn.execute("SELECT id_agente,nome FROM agentes")}
        where=["tipo_formulario IN ("+",".join("?" for _ in tipos_sql)+")","status<>'rascunho'"]
        params=list(tipos_sql)
        if filtros["status"]=="pendentes":
            where.append("""(status IN ('enviado','em_revisao') OR
                            (status='aprovado' AND tipo_formulario<>'kobo_PE_CADASTRO'))""")
        elif filtros["status"]!="todos":
            where.append("status=?")
            params.append(filtros["status"])
        rows=conn.execute("SELECT id_formulario,tipo_formulario,status,agente_nome,enviado_em,payload_json"
            " FROM formularios WHERE "+" AND ".join(where)+" ORDER BY id_formulario DESC",params)
        total=0
        for row in rows:
            resumo=_resumo(json.loads(row["payload_json"]),row["tipo_formulario"],definicoes,agentes)
            dia=resumo.get("data") or (row["enviado_em"] or "")[:10]
            if ((filtros["inicio"] and dia<filtros["inicio"]) or
                (filtros["fim"] and dia>filtros["fim"])):
                continue
            id_form=row["id_formulario"]
            titulo=catalogo[row["tipo_formulario"]]
            checks={"agente": " ".join(resumo["equipe"]), "autor": row["agente_nome"],
                    "localidade": resumo["localidade"]}
            checks["busca"]=" ".join(str(part or "") for part in (*checks.values(),id_form,titulo,
                resumo["quadra"],resumo["endereco"],resumo["complemento"]))
            if any(formulario_campo.chave(filtros[k]) not in formulario_campo.chave(value)
                   for k,value in checks.items() if filtros[k]):
                continue
            total+=1
            if (pagina-1)*POR_PAGINA<total<=pagina*POR_PAGINA:
                itens.append({**resumo, "tipo":row["tipo_formulario"],"id":id_form,"titulo":titulo,
                              "status":row["status"],"autor":row["agente_nome"],"data":dia,
                              "etag":versao(row)})
        return itens,filtros,total,pagina
    finally:
        conn.close()
