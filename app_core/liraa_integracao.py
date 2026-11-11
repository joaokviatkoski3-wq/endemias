"""Integração de serviços LIRAa com a operação comum, sem duplicar visitas."""

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal

from app_core import agentes, db, focos_positivos as focos
from app_core import liraa_kobo, visitas_integradas


def ensure_schema(conn):
    if not db.table_exists(conn, "focos_positivos"):
        return False
    if not db.column_exists(conn, "focos_positivos", "id_visita_liraa"):
        if getattr(conn, "backend", "sqlite") == "postgresql":
            raise liraa_kobo.LiraaKoboError("Aplique a migração 0029 antes de integrar notificações LIRAa.")
        conn.execute("ALTER TABLE focos_positivos ADD COLUMN id_visita_liraa INTEGER REFERENCES liraa_visitas(id_visita) ON DELETE CASCADE")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_focos_visita_liraa ON focos_positivos(id_visita_liraa)")
    if not db.column_exists(conn,"focos_positivos","quarteirao_liraa"):
        if getattr(conn,"backend","sqlite")=="postgresql":
            raise liraa_kobo.LiraaKoboError("Aplique a migração 0029 antes de integrar notificações LIRAa.")
        conn.execute("ALTER TABLE focos_positivos ADD COLUMN quarteirao_liraa TEXT")
    return True


def sincronizar_foco(conn, id_visita):
    if not ensure_schema(conn):
        return None
    v = conn.execute("SELECT * FROM liraa_visitas WHERE id_visita=?", (id_visita,)).fetchone()
    if not v:
        return None
    tubes = [dict(r) for r in conn.execute("""SELECT t.* FROM liraa_visita_tubitos t
        JOIN liraa_leituras l ON l.id_tubito=t.id_tubito WHERE t.id_visita=?
        AND COALESCE(l.aegypt_larvas,0)+COALESCE(l.aegypt_pupas,0)>0 ORDER BY t.ordem""", (id_visita,))]
    old = conn.execute("SELECT id_foco FROM focos_positivos WHERE id_visita_liraa=?", (id_visita,)).fetchone()
    agora = datetime.now().isoformat(timespec="microseconds")
    if not tubes:
        if old:
            conn.execute("UPDATE focos_positivos SET gera_notificacao=0,processado_em=? WHERE id_foco=?", (agora, old[0]))
        return None
    nomes = dict(visitas_integradas.catalogo_agentes())
    participantes = ", ".join(nomes.get(c, agentes.normalizar_nome(c)) for c in v["agentes_codigos"].split() if c != "no-ace")
    deposito = ", ".join(f"{t['codigo_deposito'] or t['deposito'] or 'Não informado'} (tubo {t['numero'] or 'sem número'})" for t in tubes)
    codigo = str(v["data_visita"]).replace("-", "") + str(tubes[0]["numero"] or "")
    numero_quarteirao=Decimal(v["quarteirao"])
    quarteirao_legado=int(numero_quarteirao) if numero_quarteirao==numero_quarteirao.to_integral_value() and numero_quarteirao<=9223372036854775807 else None
    values = dict(num_tubo=", ".join(t["numero"] or "" for t in tubes), codigo=codigo, tipo_trabalho="LIRAA",
        data=v["data_visita"], id_localidade=v["id_localidade"], localidade=v["localidade_informada"],
        quarteirao=quarteirao_legado,quarteirao_liraa=v["quarteirao"], logradouro=v["logradouro"], numero=v["numero"], nome_morador=v["morador"],
        tipo_imovel=v["tipo_imovel"], depositos=deposito, agentes=participantes, observacoes=v["observacoes"],
        gera_notificacao=int(focos.deve_gerar_notificacao("LIRAA", v["tipo_imovel"])), processado_em=agora)
    id_foco = old[0] if old else hashlib.md5(f"foco:liraa:v1:{id_visita}".encode()).hexdigest()
    if old:
        conn.execute("UPDATE focos_positivos SET " + ",".join(f"{k}=?" for k in values) + " WHERE id_foco=?", (*values.values(), id_foco))
    else:
        values.update(id_foco=id_foco, id_visita_liraa=id_visita, origem="kobo")
        conn.execute("INSERT INTO focos_positivos(" + ",".join(values) + ") VALUES(" + ",".join("?" for _ in values) + ")", tuple(values.values()))
    return id_foco


def apagar_focos(conn, id_visita):
    if not db.table_exists(conn, "focos_positivos") or not db.column_exists(conn, "focos_positivos", "id_visita_liraa"):
        return
    if db.table_exists(conn, "focos_historico"):
        conn.execute("DELETE FROM focos_historico WHERE id_foco IN (SELECT id_foco FROM focos_positivos WHERE id_visita_liraa=?)", (id_visita,))
    conn.execute("DELETE FROM focos_positivos WHERE id_visita_liraa=?", (id_visita,))


def ciclo_envio(conn, record):
    valor = str(liraa_kobo._campo(record, "endemias_ciclo") or "").strip()
    if valor:
        if not valor.isascii() or not valor.isdigit() or int(valor) <= 0:
            raise liraa_kobo.LiraaKoboError("Ciclo LIRAa inválido no envio.")
        return int(valor)
    # Compatibilidade antiga apenas quando o período identifica um único ciclo.
    dia = liraa_kobo._data(liraa_kobo._campo(record, "Data"))
    candidatos = conn.execute("""SELECT id_ciclo FROM liraa_ciclos WHERE ano=?
        AND inicio IS NOT NULL AND fim IS NOT NULL AND inicio<=? AND fim>=?""", (int(dia[:4]),dia,dia)).fetchall()
    if len(candidatos) != 1:
        raise liraa_kobo.LiraaKoboError("Envio LIRAa sem ciclo identificável. Confira o formulário e o período antes de importar.")
    return candidatos[0][0]


def buscar_kobo(cfg, target, inicio=None, fim=None, limite=5000, uid=None):
    """Consulta completa dos projetos configurados; não presume um ciclo ativo."""
    from app_core import kobo_api
    uids = {str(uid).strip()} if uid else {str((cfg.get("assets") or {}).get("LIRAA") or "").strip()}
    if not uid:
        conn=db.connect(target)
        try:
            if db.table_exists(conn,"liraa_ciclo_config"):
                uids.update(str(r[0] or "").strip() for r in conn.execute("SELECT kobo_uid FROM liraa_ciclo_config"))
        finally:conn.close()
    uids.discard("")
    if not uids:
        return [],None
    todos={}
    for projeto in sorted(uids):
        rows = kobo_api.fetch_complete_submissions(cfg, projeto, limit=limite, start=inicio, end=fim)
        for row in rows:
            uuid=kobo_api.record_uuid(row)
            if uuid in todos and todos[uuid] != row:
                raise kobo_api.KoboError("LIRAa: UUID com dados diferentes entre projetos. Confira antes de importar.")
            todos[uuid]=row
    return list(todos.values()),{"count":len(todos)}


def ler_arquivo(caminho):
    from openpyxl import load_workbook
    book = load_workbook(caminho, read_only=True, data_only=True)
    try:
        if "liraa_envios" not in book.sheetnames:
            return _ler_exportacao(book)
        values = iter(book["liraa_envios"].values)
        next(values)
        return [json.loads("".join(str(c or "") for c in row)) for row in values if any(row)]
    finally:
        book.close()


def _ler_exportacao(book):
    """Exportação Kobo com nomes XML ou rótulos conhecidos e aba dos tubitos."""
    from app_core import liraa_modelo
    from openpyxl import load_workbook
    modelo=load_workbook(liraa_modelo.APROVADO_XLSFORM,read_only=True)
    def linhas(sheet):
        values=iter(sheet.values)
        head=next(values,())
        return [dict(zip(head,row)) for row in values if any(v is not None for v in row)]
    try:
        survey,choices=linhas(modelo['survey']),linhas(modelo['choices'])
    finally:modelo.close()
    caminhos,selecoes={},{}
    multiplos=set()
    grupos=[]
    for field in survey:
        tipo=str(field.get('type') or '')
        if tipo.startswith('end_') or tipo.startswith('end '):
            if grupos:grupos.pop()
            continue
        if tipo in ('begin_group','begin_repeat','begin group','begin repeat'):
            grupos.append(field['name']);continue
        nome=field.get('name')
        if not nome:continue
        caminho='/'.join(grupos+[nome])
        for alias in (nome,field.get('label'),caminho):
            if alias:caminhos[str(alias).strip()]=caminho
        if tipo.startswith('select_') or tipo.startswith('select '):
            lista=tipo.split()[-1]
            selecoes[caminho]={str(r[k]):str(r['name']) for r in choices if r.get('list_name')==lista for k in ('name','label') if r.get(k) is not None}
            if tipo.startswith('select_multiple') or tipo.startswith('select multiple'):multiplos.add(caminho)
    for alias in ('Logradouro_outro','Nome do outro logradouro','Dados_visita/Logradouro_outro'):
        caminhos[alias]='Dados_visita/Logradouro_outro'
    def traduzir(row):
        record={}
        marcados={}
        for chave,value in row.items():
            if chave is None or value is None:continue
            chave=str(chave).strip()
            if '/' in chave:
                pai,opcao=chave.rsplit('/',1)
                pai=caminhos.get(pai,pai)
                opcao_acs=pai=='ACS' and re.fullmatch(r'ACS-[0-9]+',opcao)
                if pai in multiplos and (opcao in selecoes[pai] or opcao_acs):
                    if value in (1,True,'1','true','True','sim'):
                        marcados.setdefault(pai,set()).add(selecoes[pai].get(opcao,opcao))
                    continue
            caminho=caminhos.get(chave) or caminhos.get(chave.rsplit('/',1)[-1]) or chave
            if hasattr(value,'isoformat'):value=value.isoformat()
            opcoes=selecoes.get(caminho,{})
            if str(value) in opcoes:value=opcoes[str(value)]
            if caminho in multiplos:
                partes=str(value).split()
                if any(p not in opcoes and not (caminho=='ACS' and re.fullmatch(r'ACS-[0-9]+',p)) for p in partes):
                    raise liraa_kobo.LiraaKoboError("Exporte as escolhas múltiplas LIRAa com nomes XML ou em colunas separadas para preservar os participantes.")
                marcados.setdefault(caminho,set()).update(opcoes.get(p,p) for p in partes)
                continue
            if caminho=='Dados_visita/Logradouro' and str(value).casefold() in ('outro — digitar','outro - digitar'):
                value='outro'
            record[caminho]=value
        record.update({k:' '.join(sorted(v)) for k,v in marcados.items()})
        return record
    abas=[linhas(s) for s in book]
    principais=[]
    raiz=None
    for numero,rows in enumerate(abas):
        if rows and '_uuid' in rows[0] and any((caminhos.get(str(k)) or k)=='Data' for k in rows[0]):
            principais=[traduzir(r) for r in rows];raiz=numero;break
    if raiz is None:
        raise liraa_kobo.LiraaKoboError("Exportação LIRAa sem Data e UUID. Exporte o formulário completo do Kobo, incluindo a aba de tubitos, ou use a consulta Kobo do sistema.")
    uuids={str(r.get('_uuid','')).removeprefix('uuid:'):r for r in principais}
    indices={str(r.get('_index')):r for r in principais if r.get('_index') is not None}
    if len(uuids)!=len(principais) or '' in uuids:
        raise liraa_kobo.LiraaKoboError("Exportação LIRAa com UUID ausente ou repetido.")
    for numero,rows in enumerate(abas):
        if numero==raiz:continue
        for row in rows:
            tube=traduzir(row)
            if not any(str(k).endswith('/N_mero_do_tubito') or k=='N_mero_do_tubito' for k in tube):continue
            parent=str(row.get('_submission__uuid') or row.get('_submission_uuid') or '').removeprefix('uuid:')
            visita=uuids.get(parent) if parent else indices.get(str(row.get('_parent_index')))
            if visita is None:
                raise liraa_kobo.LiraaKoboError("Tubito sem vínculo seguro com a visita na exportação LIRAa.")
            visita.setdefault('group_jr1vc40',[]).append(tube)
    return principais


def importar_lote(conn, records):
    from app_core import liraa
    grupos = {}
    for record in records:
        grupos.setdefault(ciclo_envio(conn, record), []).append(record)
    visitas = tubos = 0
    for ciclo in sorted(grupos):
        liraa._bloquear_ciclo(conn, ciclo)
        items = liraa_kobo._preparar(conn, ciclo, grupos[ciclo])
        for item in items:
            if item["situacao_importacao"] != "nova":
                continue
            for code in item["agentes_codigos"].split():
                if code not in ("no-ace", "outros"):
                    nome = dict(visitas_integradas.catalogo_agentes()).get(code, agentes.normalizar_nome(code))
                    agentes.obter_ou_criar(conn, nome)
            tubos += len(item["tubitos"])
        visitas += liraa_kobo.gravar_preparados(conn, ciclo, items)
    return {"ok":True,"visitas_novas":visitas,"visitas_atualizadas":0,"coletas_novas":tubos,"resultados_novos":0}


def importar_leitura(conn, id_tubito, counts, nome, dia, uuid):
    from app_core import liraa
    if getattr(conn,"backend","sqlite") == "sqlite" and not hasattr(conn,"in_transaction"):
        conn=conn.connection
    row = conn.execute("SELECT v.id_ciclo,v.data_visita FROM liraa_visita_tubitos t JOIN liraa_visitas v ON v.id_visita=t.id_visita WHERE t.id_tubito=?", (id_tubito,)).fetchone()
    if not row:
        raise ValueError("Tubo LIRAa não encontrado.")
    liraa._bloquear_ciclo(conn, row["id_ciclo"])
    old = conn.execute("SELECT * FROM liraa_leituras WHERE id_tubito=?", (id_tubito,)).fetchone()
    if old:
        return False, (-id_tubito,old["aegypt_larvas"]+old["aegypt_pupas"])
    if not dia or dia < row["data_visita"] or dia > date.today().isoformat():
        raise ValueError("Data de leitura LIRAa ausente, futura ou anterior à coleta.")
    nome = agentes.normalizar_nome(nome)
    users = conn.execute("""SELECT DISTINCT u.id_usuario FROM usuarios u LEFT JOIN agentes a ON a.id_agente=u.id_agente
        WHERE LOWER(TRIM(u.nome))=LOWER(?) OR LOWER(TRIM(a.nome))=LOWER(?)""", (nome,nome)).fetchall()
    if len(users) != 1:
        raise ValueError("Identifique uma única conta do laboratorista para importar o resultado LIRAa: " + nome)
    if any(not isinstance(v,int) or not 0 <= v <= 1000000 for v in counts.values()):
        raise ValueError("Quantidade laboratorial LIRAa inválida.")
    campos = dict(id_tubito=id_tubito,data_leitura=dia,laboratorista=nome,id_usuario=users[0][0],
                  **counts,observacoes="",atualizado_em=datetime.now().isoformat(timespec="microseconds"),origem="kobo",kobo_uuid=uuid or None)
    conn.execute("INSERT INTO liraa_leituras("+",".join(campos)+") VALUES("+",".join("?" for _ in campos)+")", tuple(campos.values()))
    sincronizar_foco(conn, conn.execute("SELECT id_visita FROM liraa_visita_tubitos WHERE id_tubito=?", (id_tubito,)).fetchone()[0])
    return True, (-id_tubito,counts["aegypt_larvas"]+counts["aegypt_pupas"])
