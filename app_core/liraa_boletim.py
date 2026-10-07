"""Resumo por estrato ou localidade, sem transformar pendências em negativos."""

from app_core import db, liraa, liraa_kobo, liraa_laboratorio as lab, liraa_operacional as op


def resumir(target, id_ciclo, base_dir=None, agrupar="estrato", id_estrato=None, id_localidade=None):
    if agrupar not in ("estrato", "localidade"):
        raise liraa.LiraaError("Agrupamento inválido.")
    plano = op.plano(target, id_ciclo, base_dir, id_estrato, id_localidade)
    grupos = {}
    for q in plano["quarteiroes"]:
        key = (q["id_estrato"], q["id_localidade"] if agrupar == "localidade" else None)
        if key not in grupos:
            grupos[key] = {"estrato": q["estrato"], "localidade": q["localidade"] if agrupar == "localidade" else "Todas as localidades do estrato",
                "quarteiroes": 0, "programados": next(e['sorteio']['n'] for e in plano['ciclo']['estratos'] if e['id_estrato']==q['id_estrato']),
                "referencia_rg": 0, "sem_rg": 0, "trabalhados": 0,
                "pendentes": 0, "tubitos": 0, "leituras": 0, "tipos_invalidos": 0,
                "depositos_invalidos": 0, "aegypt_tb": set(), "aegypt_outros": set(),
                "albopictus_tb": set(), "albopictus_outros": set(),
                "aegypt_recipientes": {code: 0 for code in op.DEPOSITOS},
                "aegypt_total": 0, "albopictus_total": 0}
        g = grupos[key]
        g["quarteiroes"] += 1
        g["sem_rg"] += q["meta_rg"] is None
        g["referencia_rg"] += q["meta_rg"] or 0
    conn = db.connect(target)
    try:
        lab.ensure_schema(conn)
        context = liraa_kobo._contexto(conn, id_ciclo)
        readings = {r["id_tubito"]: db.serialize_row(r) for r in conn.execute("""SELECT l.* FROM liraa_leituras l
            JOIN liraa_visita_tubitos t ON t.id_tubito=l.id_tubito JOIN liraa_visitas v ON v.id_visita=t.id_visita WHERE v.id_ciclo=?""", (id_ciclo,))}
        tubes = {}
        for r in conn.execute("""SELECT t.* FROM liraa_visita_tubitos t JOIN liraa_visitas v ON v.id_visita=t.id_visita WHERE v.id_ciclo=?""", (id_ciclo,)):
            tubes.setdefault(r["id_visita"], []).append(db.serialize_row(r))
        excluded = 0
        for row in conn.execute("SELECT * FROM liraa_visitas WHERE id_ciclo=? ORDER BY id_visita", (id_ciclo,)):
            v = db.serialize_row(row)
            loc, estrato, status = liraa_kobo._vincular(v, context)
            if status != "sorteado":
                excluded += 1
                continue
            key = (estrato, loc if agrupar == "localidade" else None)
            if key not in grupos or (id_localidade and str(loc) != str(id_localidade)):
                continue
            g = grupos[key]
            g["trabalhados"] += 1
            tipo = "tb" if v["tipo_imovel"] == "terreno_baldio" else "outros" if v["tipo_imovel"] == "rco" else None
            if tipo is None:
                g["tipos_invalidos"] += 1
            for tube in tubes.get(v["id_visita"], []):
                g["tubitos"] += 1
                reading = readings.get(tube["id_tubito"])
                if reading is None:
                    g["pendentes"] += 1
                    continue
                g["leituras"] += 1
                for specie in ("aegypt", "albopictus"):
                    if reading[f"{specie}_larvas"] + reading[f"{specie}_pupas"] <= 0:
                        continue
                    g[f"{specie}_total"] += 1
                    if tipo:
                        g[f"{specie}_{tipo}"].add(v["id_visita"])
                    if specie == "aegypt":
                        code = str(tube["codigo_deposito"] or "").strip().upper()
                        if code in op.DEPOSITOS:
                            g["aegypt_recipientes"][code] += 1
                        else:
                            g["depositos_invalidos"] += 1
        for g in grupos.values():
            for field in ("aegypt_tb", "aegypt_outros", "albopictus_tb", "albopictus_outros"):
                g[field] = len(g[field])
            g["parcial"] = bool(g["pendentes"] or g["tipos_invalidos"] or g["depositos_invalidos"])
        return {"ciclo": plano["ciclo"], "grupos": list(grupos.values()), "excluidas": excluded, "agrupar": agrupar,
                "sem_sorteio": plano["sem_sorteio"]}
    finally:
        conn.close()
