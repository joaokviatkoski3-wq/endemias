"""Plano de campo, mapa e configurações do ciclo LIRAa."""

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from app_core import db, liraa, registro_geografico as rg, visitas


BASE_XLSFORM = Path(__file__).parent / "data" / "liraa_kobo_base.xlsx"
DEPOSITOS = {
    "A1": "Caixa de água ligada à rede (depósitos elevados)",
    "A2": "Depósitos ao nível do solo (barril, tina, tambor, tanque, poço)",
    "B": "Depósitos móveis (vasos, frascos, pratos, bebedouros etc.)",
    "C": "Depósitos fixos (tanques, calhas, lajes etc.)",
    "D1": "Pneus e outros materiais rodantes",
    "D2": "Lixo, recipientes plásticos, garrafas, latas e sucatas",
    "E": "Depósitos naturais",
}


def require_config(conn):
    liraa._schema(conn)
    if not db.table_exists(conn, "liraa_ciclo_config"):
        raise liraa.LiraaError("Aplique a migração 0026 para configurar o formulário do ciclo.")


def catalogo_acs(target):
    """Códigos do formulário de referência com rótulos do catálogo municipal."""
    from openpyxl import load_workbook
    workbook = load_workbook(BASE_XLSFORM, read_only=True)
    try:
        survey = list(workbook["survey"].values)
        headers = list(survey[0])
        fields = [dict(zip(headers, row)) for row in survey[1:]]
        field = next(row for row in fields if row.get("name") == "ACS")
        list_name = field["type"].split()[1]
        choices = list(workbook["choices"].values)
        rows = [dict(zip(choices[0], row)) for row in choices[1:]]
    finally:
        workbook.close()
    conn = db.connect(target)
    try:
        catalog = visitas.catalogo_acs(conn)
    finally:
        conn.close()
    return sorted([{"codigo": str(row["name"]),
                    "nome": catalog.get(str(row["name"]).casefold(), str(row["label"]))}
                   for row in rows if row.get("list_name") == list_name and row.get("name") != "no-acs"],
                  key=lambda row: row["nome"].casefold())


def configuracao(target, id_ciclo):
    conn = db.connect(target)
    try:
        require_config(conn)
        if not conn.execute("SELECT 1 FROM liraa_ciclos WHERE id_ciclo=?", (id_ciclo,)).fetchone():
            raise liraa.LiraaError("Ciclo não encontrado.")
        row = conn.execute("SELECT * FROM liraa_ciclo_config WHERE id_ciclo=?", (id_ciclo,)).fetchone()
        result = db.serialize_row(row) if row else {"acs_json": "[]", "acs_definidos": 0, "kobo_uid": ""}
        result["acs"] = json.loads(result.pop("acs_json"))
        return result
    finally:
        conn.close()


def salvar_configuracao(target, id_ciclo, codigos, uid, auditar=None):
    acs = {row["codigo"]: row for row in catalogo_acs(target)}
    if not isinstance(codigos, list) or len(codigos) != len(set(codigos)) or not set(codigos) <= set(acs):
        raise liraa.LiraaError("Selecione ACS válidos da lista do formulário.")
    uid = str(uid or "").strip()
    if uid and (len(uid) > 100 or not uid.isalnum()):
        raise liraa.LiraaError("UID Kobo inválido.")
    selected = [acs[code] for code in sorted(codigos)]
    conn = db.connect(target)
    try:
        require_config(conn)
        with conn:
            lock = " FOR UPDATE" if getattr(conn, "backend", "sqlite") == "postgresql" else ""
            if not conn.execute("SELECT id_ciclo FROM liraa_ciclos WHERE id_ciclo=?" + lock, (id_ciclo,)).fetchone():
                raise liraa.LiraaError("Ciclo não encontrado.")
            conn.execute("""INSERT INTO liraa_ciclo_config (id_ciclo,acs_json,acs_definidos,kobo_uid,atualizado_em)
                VALUES (?,?,1,?,?) ON CONFLICT(id_ciclo) DO UPDATE SET acs_json=excluded.acs_json,
                acs_definidos=1,kobo_uid=excluded.kobo_uid,atualizado_em=excluded.atualizado_em""",
                (id_ciclo, json.dumps(selected, ensure_ascii=False), uid, datetime.now().isoformat(timespec="seconds")))
            if auditar:
                auditar(conn, {"id_ciclo": id_ciclo, "acs": selected, "kobo_uid": uid})
    finally:
        conn.close()


def plano_hash_conn(conn, id_ciclo):
    snapshots = [dict(db.serialize_row(row)) for row in conn.execute("""SELECT s.id_sorteio,
        s.id_estrato,s.universo_hash,s.selecionados_json FROM liraa_sorteios s
        JOIN liraa_estratos e ON e.id_estrato=s.id_estrato WHERE e.id_ciclo=? ORDER BY e.numero""", (id_ciclo,))]
    return hashlib.sha256(json.dumps(snapshots, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def plano(target, id_ciclo, base_dir=None, id_estrato=None, id_localidade=None):
    """Seleção congelada do sorteio, enriquecida pelo RG/camada ativos."""
    data = liraa.painel(target, base_dir)
    ciclo = next((c for c in data["ciclos"] if str(c["id_ciclo"]) == str(id_ciclo)), None)
    if not ciclo:
        raise liraa.LiraaError("Ciclo não encontrado.")
    if id_estrato and not any(str(e["id_estrato"]) == str(id_estrato) for e in ciclo["estratos"]):
        raise liraa.LiraaError("Estrato não encontrado neste ciclo.")
    ativos = {(q["id_localidade"], q["quarteirao"]): q for q in data["quarteiroes"]}
    rows = []
    for estrato in ciclo["estratos"]:
        if not estrato["sorteio"] or (id_estrato and str(estrato["id_estrato"]) != str(id_estrato)):
            continue
        for saved in estrato["sorteio"]["selecionados"]:
            if id_localidade and str(saved["id_localidade"]) != str(id_localidade):
                continue
            atual = ativos.get((saved["id_localidade"], saved["quarteirao"]))
            row = {**saved, **(atual or {}), "id_estrato": estrato["id_estrato"],
                   "estrato": estrato["numero"], "tipo_estrato": estrato["tipo"],
                   "fracao": estrato["sorteio"]["fracao"], "geometria_ausente": atual is None}
            row["unidades_rg"] = atual["unidades_rg"] if atual and atual["tem_rg"] else None
            row["meta_rg"] = math.ceil(row["unidades_rg"] / (5 if estrato["tipo"] == "normal" else 2)) if row["unidades_rg"] is not None else None
            rows.append(row)
    rows.sort(key=lambda q: (q["estrato"], q["localidade"].casefold(), liraa._ordem_quarteirao(q["quarteirao"])))
    grupos = []
    for key in dict.fromkeys((r["id_estrato"], r["id_localidade"]) for r in rows):
        subset = [r for r in rows if (r["id_estrato"], r["id_localidade"]) == key]
        grupos.append({"id_estrato": key[0], "id_localidade": key[1], "estrato": subset[0]["estrato"],
                       "localidade": subset[0]["localidade"], "quarteiroes": len(subset),
                       "fracao": subset[0]["fracao"], "sem_rg": sum(r["unidades_rg"] is None for r in subset),
                       "unidades_rg": sum(r["unidades_rg"] or 0 for r in subset),
                       "meta_rg": sum(r["meta_rg"] or 0 for r in subset)})
    conn = db.connect(target)
    try:
        hash_plano = plano_hash_conn(conn, ciclo["id_ciclo"])
    finally:
        conn.close()
    return {"ciclo": ciclo, "quarteiroes": rows, "grupos": grupos, "plano_hash": hash_plano,
            "sem_sorteio": sum(not e["sorteio"] for e in ciclo["estratos"]),
            "sem_rg": sum(r["unidades_rg"] is None for r in rows),
            "geometrias_ausentes": sum(r["geometria_ausente"] for r in rows)}


def historico_sorteios(target, id_estrato):
    conn = db.connect(target)
    try:
        liraa._schema(conn)
        if not db.table_exists(conn, "liraa_sorteios_historico"):
            return []
        result = []
        for row in conn.execute("SELECT * FROM liraa_sorteios_historico WHERE id_estrato=? ORDER BY id_historico DESC", (id_estrato,)):
            item = db.serialize_row(row)
            snapshot = json.loads(item.pop("snapshot_json"))
            item["sorteio"] = snapshot
            item["selecionados"] = json.loads(snapshot["selecionados_json"])
            result.append(item)
        return result
    finally:
        conn.close()


def geojson(target, id_ciclo, base_dir=None, id_estrato=None, id_localidade=None):
    data = plano(target, id_ciclo, base_dir, id_estrato, id_localidade)
    if data["geometrias_ausentes"]:
        raise liraa.LiraaError("Há quarteirões sorteados sem geometria na camada ativa. Atualize a camada antes de exportar.")
    camada = rg.geojson_ativo(target, base_dir)
    conn = db.connect(target)
    try:
        locais = {rg._norm(row["nome"]): row["id_localidade"] for row in conn.execute("SELECT id_localidade,nome FROM localidades")}
    finally:
        conn.close()
    selecionados = {(r["id_localidade"], r["quarteirao"]): r for r in data["quarteiroes"]}
    features = []
    for feature in camada.get("features", []):
        props = feature.get("properties") or {}
        raw = props.get("Localidade")
        try:
            loc = int(raw)
        except (ValueError, TypeError):
            loc = locais.get(rg._norm(raw))
        q = rg._quarteirao(props.get("id_quart", props.get("id_Q")))
        row = selecionados.get((loc, q))
        if not row:
            continue
        features.append({"type": "Feature", "geometry": feature["geometry"], "properties": {
            "ciclo": data["ciclo"]["nome"], "ano": data["ciclo"]["ano"],
            "estrato": row["estrato"], "Localidade": row["localidade"], "id_localidade": loc,
            "id_Q": q, "quarteirao": row["quarteirao_exibicao"], "fracao": row["fracao"],
            "imoveis_rg": row["unidades_rg"], "meta_rg": row["meta_rg"], "id_estrato": row["id_estrato"]}})
    return {"type": "FeatureCollection", "features": features}


def kml(target, id_ciclo, base_dir=None, id_estrato=None, id_localidade=None):
    data = geojson(target, id_ciclo, base_dir, id_estrato, id_localidade)
    if not data["features"]:
        raise liraa.LiraaError("Nenhum quarteirão sorteado neste filtro.")
    root = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(root, "Document")
    ET.SubElement(document, "name").text = "LIRAa - quarteirões sorteados"
    colors = ["2563eb", "dc2626", "16a34a", "9333ea", "ea580c", "0891b2", "be123c", "65a30d"]
    folders, placemarks = {}, {}
    for feature in data["features"]:
        p = feature["properties"]
        key = (p["estrato"], p["Localidade"])
        if key not in folders:
            folders[key] = ET.SubElement(document, "Folder")
            ET.SubElement(folders[key], "name").text = f"Estrato {key[0]} - {key[1]}"
        qkey = (*key, p["id_Q"])
        if qkey not in placemarks:
            pm = ET.SubElement(folders[key], "Placemark")
            ET.SubElement(pm, "name").text = f"Q. {p['quarteirao']} - {p['Localidade']}"
            ET.SubElement(pm, "description").text = f"Estrato {p['estrato']} | Imóveis RG: {p['imoveis_rg'] if p['imoveis_rg'] is not None else 'não disponível'} | Meta RG {p['fracao']:.0%}: {p['meta_rg'] if p['meta_rg'] is not None else 'não disponível'}"
            color = colors[(int(p["estrato"]) - 1) % len(colors)]
            abgr = color[4:6] + color[2:4] + color[:2]
            style = ET.SubElement(pm, "Style")
            line = ET.SubElement(style, "LineStyle")
            ET.SubElement(line, "color").text = "ff" + abgr
            ET.SubElement(line, "width").text = "2"
            poly = ET.SubElement(style, "PolyStyle")
            ET.SubElement(poly, "color").text = "99" + abgr
            attrs = ET.SubElement(pm, "ExtendedData")
            for name, value in p.items():
                attr = ET.SubElement(attrs, "Data", name=name)
                ET.SubElement(attr, "value").text = str(value) if value is not None else "Não disponível"
            placemarks[qkey] = ET.SubElement(pm, "MultiGeometry")
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for rings in polygons:
            polygon = ET.SubElement(placemarks[qkey], "Polygon")
            for index, ring in enumerate(rings):
                boundary = ET.SubElement(polygon, "outerBoundaryIs" if index == 0 else "innerBoundaryIs")
                line = ET.SubElement(boundary, "LinearRing")
                ET.SubElement(line, "coordinates").text = " ".join(f"{point[0]},{point[1]},0" for point in ring)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
