from collections import defaultdict


def resolver_coletas(conn, chaves):
    """Resolve resultados laboratoriais para coletas sem arriscar vinculos ambiguos."""
    chaves = {
        (str(tubo or "").strip(), str(data or "").strip()[:10])
        for tubo, data in (chaves or [])
        if str(tubo or "").strip() and str(data or "").strip()
    }
    if not chaves:
        return {}

    tubos = sorted({tubo for tubo, _ in chaves})
    placeholders = ",".join("?" for _ in tubos)
    rows = conn.execute(
        f"""SELECT c.id_coleta, c.id_visita, TRIM(COALESCE(c.num_tubo,'')) AS num_tubo,
                   c.tipo_deposito, v.tipo, v.data, v.localidade, v.quarteirao,
                   v.logradouro, v.numero, v.morador, v.tipo_imovel, v.observacoes
              FROM coletas c
              JOIN visitas v ON v.id_visita = c.id_visita
             WHERE TRIM(COALESCE(c.num_tubo,'')) IN ({placeholders})""",
        tubos,
    ).fetchall()

    por_tubo = defaultdict(list)
    for row in rows:
        item = dict(row)
        por_tubo[item["num_tubo"]].append(item)

    resolvidas = {}
    for chave in chaves:
        tubo, data = chave
        exatas = [row for row in por_tubo[tubo] if str(row.get("data") or "")[:10] == data]
        if len(exatas) == 1:
            resolvidas[chave] = {**exatas[0], "estrategia": "data_exata"}

    pendentes_por_data = defaultdict(set)
    for tubo, data in chaves - set(resolvidas):
        pendentes_por_data[data].add(tubo)

    # Resultados do mesmo dia de laboratorio costumam pertencer ao mesmo lote.
    # Um conjunto de dois ou mais tubos identifica a visita mesmo quando a data
    # informada no formulario de campo diverge da data informada no laboratorio.
    for data, tubos_lote in pendentes_por_data.items():
        visitas = defaultdict(set)
        for tubo in tubos_lote:
            for row in por_tubo[tubo]:
                visitas[row["id_visita"]].add(tubo)
        if not visitas:
            continue
        melhor = max(len(tubos) for tubos in visitas.values())
        candidatas = [id_visita for id_visita, tubos in visitas.items() if len(tubos) == melhor]
        if melhor < 2 or len(candidatas) != 1:
            continue
        id_visita = candidatas[0]
        for tubo in tubos_lote:
            chave = (tubo, data)
            if chave in resolvidas:
                continue
            candidatas_tubo = [row for row in por_tubo[tubo] if row["id_visita"] == id_visita]
            if len(candidatas_tubo) == 1:
                resolvidas[chave] = {**candidatas_tubo[0], "estrategia": "lote_de_tubos"}

    # Se um numero de tubo existe uma unica vez em todo o banco, a associacao
    # continua inequivoca mesmo que a data tenha sido digitada incorretamente.
    for chave in chaves - set(resolvidas):
        tubo, _ = chave
        if len(por_tubo[tubo]) == 1:
            resolvidas[chave] = {**por_tubo[tubo][0], "estrategia": "tubo_unico"}

    return resolvidas
