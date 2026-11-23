"""Definições internas de campo, independentes das definições publicadas no Kobo."""

import json
import os

from app_core import db, setores
from app_core.formulario_campo import chave
from app_core.formulario_equipamentos import CATEGORIAS

TIPOS = ("PE", "PE_CADASTRO", "TB", "TBO", "PVE", "BRI", "RECOLHIMENTO")
DEPOSITOS = {
    "A1": "Água elevada", "A2": "Água ao nível do solo", "B": "Depósitos móveis",
    "C": "Depósitos fixos", "D1": "Pneus e materiais rodantes",
    "D2": "Lixo, entulho, sucata", "E": "Depósitos naturais",
}
DESTINO = "Onde_vai_ser_realizado_o_trata"
REFERENCIAS = {
    "pe": ("pontos_estrategicos", """SELECT CAST(id_pe AS TEXT) AS id,codigo_pe,nome,
            localidade,quarteirao,logradouro,numero FROM pontos_estrategicos WHERE situacao=1""",
           "CAST(id_pe AS TEXT)", "codigo_pe"),
    "ovitrampa": ("ovitrampas_armadilhas", """SELECT ovitrampa_id AS id,localidade,quarteirao,
                  rua AS logradouro,numero FROM ovitrampas_armadilhas WHERE ativo=1""",
                  "ovitrampa_id", "ovitrampa_id"),
    "equipamento": ("equipamentos_publicos", """SELECT uid AS id,categoria,nome,logradouro,numero,bairro
                    FROM equipamentos_publicos WHERE 1=1""", "uid", "nome"),
}


def habilitado(usuario):
    piloto = os.environ.get("ENDEMIAS_FORMULARIOS_OFFLINE_USUARIO", "").strip().casefold()
    return bool(piloto and setores.atual() != "ambiental"
                and usuario.get("nivel") in {"usuario", "operador", "admin", "superadmin"}
                and (usuario.get("nivel") == "superadmin"
                     or str(usuario.get("usuario") or "").casefold() == piloto)
                and not usuario.get("somente_laboratorio"))


def _field(name, label, kind="text", **attrs):
    return {"name": name, "label": label, "type": kind, **attrs}


def _choice_group(name, choices):
    return [{"list_name": name, "name": value, "label": label} for value, label in choices.items()]


def _source(row):
    return row.get("$autoname") or row.get("name") or ""


def _catalog(name, label, kind, **attrs):
    return _field(name, label, vsatt_catalog=kind, **attrs)


def _address(rows):
    order = {"localidade": 0, "quarteirao": 1, "logradouro": 2, "numero": 3,
             "sequencia": 4, "tipodoimvel": 5, "imovel": 5, "visita": 6, "observaes": 7}
    aliases = {"quarteiro": "quarteirao", "nmero": "numero", "sequncia": "sequencia"}
    fields, rest = [], []
    for row in rows:
        name = chave(_source(row)).rstrip("0123456789")
        key = aliases.get(name, name)
        if key not in order:
            rest.append(row)
            continue
        row = dict(row)
        if key in {"quarteirao", "logradouro", "numero"}:
            row.pop("choice_filter", None)
            row.pop("constraint", None)
            row["type"] = "text"
            row["label"] = {"quarteirao": "Quarteirão", "logradouro": "Logradouro", "numero": "Número"}[key]
            if key != "numero":
                row["vsatt_catalog"] = key
                row["hint"] = "Selecione na lista ou escolha Outros para digitar."
        fields.append((order[key], row))
    return [row for _, row in sorted(fields, key=lambda pair: pair[0])] + rest


def adaptar(definition, tipo):
    """Preserva nomes e caminhos que o importador usa, inclusive nas repetições."""
    variants = dict(definition, tipo=tipo)
    choices = list(definition["choices"])
    choices += _choice_group("vsatt_depositos", {k: f"{k} - {v}" for k, v in DEPOSITOS.items()})
    choices += _choice_group("vsatt_sim_nao", {"sim": "Sim", "nao": "Não"})
    variants["choices"] = choices
    original = [dict(row) for row in definition["survey"]]
    if tipo == "PE_CADASTRO":
        choices += _choice_group("vsatt_cadastro", {"novo": "Novo PE", "corrigir": "Corrigir PE existente"})
        team = next((row for row in original if row["type"] == "select_multiple" and "agente" in chave(_source(row))), None)
        variants["survey"] = [
            *([team] if team else []),
            _field("vsatt_cadastro", "O que precisa solicitar?", "select_one",
                   select_from_list_name="vsatt_cadastro", required=True),
            _catalog("vsatt_localidade", "Localidade", "localidade", required=True),
            _catalog("vsatt_pe", "Ponto Estratégico", "pe", required=True,
                     relevant="${vsatt_cadastro} = 'corrigir'"),
            *[_field(name, label, required=relevant) for name, label, relevant in (
                ("vsatt_nome_pe", "Nome do ponto", "${vsatt_cadastro} = 'novo'"),
                ("vsatt_tipo_pe", "Tipo de Ponto Estratégico", False),
            )],
            _catalog("vsatt_quarteirao", "Quarteirão", "quarteirao"),
            _catalog("vsatt_logradouro", "Logradouro", "logradouro"),
            _field("vsatt_numero", "Número"), _field("vsatt_responsavel", "Responsável no local"),
            _field("vsatt_telefone", "Telefone"), _field("vsatt_cnpj", "CNPJ"),
            _field("vsatt_observacoes_cadastro", "Observações sobre o cadastro", required=True),
        ]
        return variants

    def group(rows, name, transform):
        start = next((i for i, row in enumerate(rows) if _source(row) == name), None)
        if start is None:
            return rows
        stop = next(i for i in range(start + 1, len(rows)) if rows[i]["type"] == "end_group")
        return rows[:start + 1] + transform(rows[start + 1:stop]) + rows[stop:]

    def registered(rows, ref_type):
        keep = [row for row in rows if _source(row) == "Visita"]
        return [_catalog("vsatt_localidade", "Localidade", "localidade", required=True),
                _catalog("vsatt_" + ref_type, "Ponto Estratégico" if ref_type == "pe" else "Ovitrampa",
                         ref_type, required=True), *keep]

    rows = original
    if tipo == "PE":
        rows = group(rows, "group_zn1kq42", lambda fields: registered(fields, "pe"))
        start = next((i for i, row in enumerate(rows) if _source(row) == "group_zn1kq42"), None)
        if start is not None:
            end = next(i+1 for i in range(start+1,len(rows)) if rows[i]["type"]=="end_group")
            rows = rows[start:end] + rows[:start] + rows[end:]
        rows = group(rows, "group_ng6bj50", lambda _: [])
        rows = [row for i, row in enumerate(rows) if _source(row) != "group_ng6bj50"
                and (i == 0 or _source(rows[i - 1]) != "group_ng6bj50")]
        insert = next((i for i, row in enumerate(rows) if row["type"] == "begin_repeat"), len(rows))
        rows.insert(insert, _field("Observa_es", "Observações da visita"))
    if tipo in {"TB", "TBO", "PVE"}:
        def address_fields(fields):
            if tipo != "PVE":
                return _address(fields)
            geo_start = next((i for i, row in enumerate(fields) if chave(_source(row)) == "localidade"), len(fields))
            return [*fields[:geo_start],
                    _field("vsatt_e_ouve", "Essa visita se origina de uma denúncia do E-Ouve?", "select_one",
                           select_from_list_name="vsatt_sim_nao", required=True),
                    _field("vsatt_protocolo", "Protocolo da denúncia E-Ouve", required=True,
                           relevant="${vsatt_e_ouve} = 'sim'", vsatt_digits=True),
                    *_address(fields[geo_start:])]

        rows = group(rows, "Dados_visita" if tipo == "TBO" else "group_zn1kq42", address_fields)
        if tipo == "TBO":
            index = next((i for i, row in enumerate(rows) if _source(row) == "Dados_visita"), len(rows))
            rows.insert(index, _catalog("vsatt_ovitrampas", "Ovitrampas que deram origem ao bloqueio",
                                        "ovitrampas", required=True))
    if tipo == "BRI":
        options = next((row.get("select_from_list_name") for row in rows if _source(row) == DESTINO), None)
        if options:
            choices += _choice_group(options, CATEGORIAS)
        rows = group(rows, "group_zn1kq42", lambda fields: registered(fields, "pe"))
        rows = group(rows, "group_cu8sh31", lambda fields: registered(fields, "ovitrampa"))
        rows = group(rows, "group_pt6ft99", _address)
        index = next((i for i, row in enumerate(rows) if _source(row) == "group_rb5ho54"), len(rows))
        # Os nomes dos campos são únicos, pois participam das condições e do endereço oficial.
        for i, row in enumerate(rows):
            if _source(row) == "group_cu8sh31":
                rows[i + 1] = dict(rows[i + 1], name="vsatt_localidade_ovit")
        rows[index:index] = [
            _field("vsatt_equipamento_local", "Equipamento público", "begin_group",
                   relevant=" or ".join(f"${{{DESTINO}}} = '{key}'" for key in CATEGORIAS)),
            _catalog("vsatt_localidade_equip", "Localidade", "localidade", required=True),
            _catalog("vsatt_equipamento", "Equipamento público", "equipamento", required=True),
            _catalog("vsatt_quarteirao_equip", "Quarteirão", "quarteirao", required=True),
            _field("", "", "end_group"),
        ]
        for i, row in enumerate(rows):
            if _source(row) == "Foi_tratado_algum_im_vel_al_m_":
                rows[i] = dict(row, relevant=f"${{{DESTINO}}} = 'ponto_estrat_gico' or ${{{DESTINO}}} = 'ovitrampa'")
    if tipo == "RECOLHIMENTO":
        index = next((i for i, row in enumerate(rows) if chave(_source(row)) == "localidade"), None)
        if index is not None:
            rows[index + 1:index + 1] = [
                _catalog("vsatt_quarteirao", "Quarteirão", "quarteirao"),
                _catalog("vsatt_logradouro", "Logradouro", "logradouro",
                         hint="Se a rua não estiver na lista, escolha Outros e informe um endereço aproximado."),
                _field("vsatt_numero", "Número"),
            ]
    for i, row in enumerate(rows):
        if chave(_source(row)) == "cdigododepsito":
            rows[i] = dict(row, type="select_one", select_from_list_name="vsatt_depositos", required=True,
                           label="Código do depósito")
        if row["type"] == "begin_repeat" and _source(row) == "group_jr1vc40":
            rows[i] = dict(row, label="Tubitos")
    variants["survey"] = rows
    return variants


def _referencias(conn, tipo, ids=()):
    tabela, sql, coluna, ordem = REFERENCIAS[tipo]
    if not db.table_exists(conn, tabela):
        return []
    if ids:
        sql += " AND " + coluna + " IN (" + ",".join("?" for _ in ids) + ")"
    return [dict(row) for row in conn.execute(sql + " ORDER BY " + ordem, ids)]


def catalogos(target):
    from app_core import registro_geografico as rg
    conn = db.connect(target)
    try:
        local = [row[0] for row in conn.execute("SELECT nome FROM localidades ORDER BY nome")]
        areas = {chave(nome): {} for nome in local}
        queries = {
            "registro_geografico_quarteiroes": """SELECT DISTINCT l.nome,q.quarteirao,'' AS rua
                FROM registro_geografico_quarteiroes q JOIN localidades l USING(id_localidade)""",
            "registro_geografico_quarteiroes_geometrias": """SELECT DISTINCT l.nome,q.quarteirao,'' AS rua
                FROM registro_geografico_quarteiroes_geometrias q JOIN localidades l USING(id_localidade)
                JOIN registro_geografico_geojson_importacoes i USING(id_importacao) WHERE i.ativo""",
            "registro_geografico_imoveis": """SELECT DISTINCT l.nome,q.quarteirao,q.logradouro AS rua
                FROM registro_geografico_imoveis q JOIN localidades l USING(id_localidade)""",
        }
        for name, sql in queries.items():
            if not db.table_exists(conn, name):
                continue
            for nome, number, rua in conn.execute(sql):
                if number:
                    streets = areas[chave(nome)].setdefault(rg._quarteirao_display(str(number)), [])
                    if rua:
                        streets.append(rua)
        for blocks in areas.values():
            for number, streets in blocks.items():
                blocks[number] = sorted(set(streets), key=chave)
        return {"localidades": local, "areas": areas,
                **{tipo: _referencias(conn, tipo) for tipo in REFERENCIAS}}
    finally:
        conn.close()


def _val(values, name):
    return next((str(value) for path, value in values.items() if path.rsplit("/", 1)[-1] == name), "")


def enriquecer(target, tree, payload, original, publicar):
    """Apenas o servidor atribui o retrato e os vínculos usados no lançamento."""
    payload.pop("referencia_campo", None)
    if not tree.get("campo_v2"):
        return
    from app_core.formularios_kobo import validar
    values = validar(tree, payload, publicar=publicar)
    tipo = tree["tipo"]
    selection = next(((kind, _val(values, "vsatt_" + kind)) for kind in ("pe", "ovitrampa", "equipamento")
                      if _val(values, "vsatt_" + kind)), None)
    traps = _val(values, "vsatt_ovitrampas").split()
    if not selection and not traps:
        return
    if len(traps) > 100 or len(set(traps)) != len(traps):
        raise ValueError("Confira as ovitrampas de origem do bloqueio.")
    conn = db.connect(target)
    try:
        current_traps = {r["id"] for r in _referencias(conn, "ovitrampa", traps)} if traps else set()
        matches = _referencias(conn, selection[0], (selection[1],)) if selection else []
    finally:
        conn.close()
    if traps:
        previous = (original or {}).get("referencia_campo") or {}
        if not set(traps) <= (current_traps | set(previous.get("ovitrampas", []))):
            raise ValueError("Confira as ovitrampas de origem do bloqueio.")
        payload["referencia_campo"] = {"ovitrampas": traps}
    if selection:
        kind, ident = selection
        locality = _val(values, {"pe":"vsatt_localidade", "ovitrampa":"vsatt_localidade_ovit",
                                "equipamento":"vsatt_localidade_equip"}[kind])
        match = matches[0] if matches else None
        historical = (original or {}).get("referencia_campo") or {}
        if historical.get("id") == ident and historical.get("kind") == kind and historical.get("localidade") == locality:
            match = historical
        if not match or kind != "equipamento" and chave(match.get("localidade")) != chave(locality):
            raise ValueError("Confira o local selecionado para esta localidade.")
        if kind == "equipamento" and match["categoria"] != _val(values, DESTINO):
            raise ValueError("O equipamento não corresponde ao tipo de local selecionado.")
        payload["referencia_campo"] = {**match, "kind": kind, "localidade": locality}
        if kind == "equipamento":
            payload["referencia_campo"]["quarteirao"] = _val(values, "vsatt_quarteirao_equip")


def registro(tipo, data, reference):
    if not reference or "kind" not in reference:
        return
    kind = reference["kind"]
    if tipo == "PE" or tipo == "BRI" and kind == "pe":
        fields = {"localidade": "localidade", "logradouro": "logradouro", "quarteirao": "quarteirao", "numero": "numero"}
        group = "group_zn1kq42"
    elif tipo == "BRI" and kind == "ovitrampa":
        fields = {"localidade": "localidade_001_002", "logradouro": "Logradouro_002",
                  "quarteirao": "Quarteir_o_001", "numero": "N_mero_001", "id": "N_mero_da_Ovitrampa"}
        group = "group_cu8sh31"
    elif tipo == "BRI":
        fields = {"localidade": "localidade_001", "logradouro": "Logradouro_001", "quarteirao": "Quarteir_o",
                  "numero": "N_mero", "nome": "Onde_foi_realizado_o_tratamento"}
        group = "group_pt6ft99"
    else:
        return
    data.update({f"{group}/{field}": reference.get(key) or "" for key, field in fields.items()})


def persistir(conn, tipo, record, reference):
    if getattr(conn, "backend", "sqlite") == "sqlite":
        from app_core.formulario_equipamentos import ensure_sqlite
        ensure_sqlite(conn)
    uuid = record["_uuid"]
    if tipo in {"PE", "BRI"} and (reference or {}).get("kind") == "pe":
        table = "visitas" if tipo == "PE" else "bri_registros"
        conn.execute(f"UPDATE {table} SET id_pe=?,codigo_pe=? WHERE kobo_uuid=?",
                     (int(reference["id"]), reference["codigo_pe"], uuid))
    if tipo == "BRI" and (reference or {}).get("kind") == "equipamento":
        conn.execute("UPDATE bri_registros SET equipamento_uid=? WHERE kobo_uuid=?", (reference["id"], uuid))
    if tipo == "PVE":
        conn.execute("UPDATE visitas SET protocolo_e_ouve=? WHERE kobo_uuid=?",
                     (_val(record, "vsatt_protocolo") or None, uuid))
    if tipo == "TBO":
        conn.execute("UPDATE visitas SET ovitrampas_bloqueio=? WHERE kobo_uuid=?",
                     (json.dumps((reference or {}).get("ovitrampas", [])), uuid))
    if tipo == "RECOLHIMENTO":
        conn.execute("UPDATE recolhimentos SET quarteirao=?,logradouro=?,numero=? WHERE kobo_uuid=?",
                     (*(_val(record, "vsatt_" + name) or None for name in ("quarteirao", "logradouro", "numero")), uuid))
