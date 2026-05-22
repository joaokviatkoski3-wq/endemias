from datetime import date, datetime, timedelta


def hoje():
    return date.today().isoformat()


def data_n_dias(n=30):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def data_ano():
    return f"{date.today().year}-01-01"


def safe_int(value, default=0):
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def bounded_int(value, default, minimo=None, maximo=None):
    result = safe_int(value, default)
    if minimo is not None:
        result = max(minimo, result)
    if maximo is not None:
        result = min(maximo, result)
    return result


def _getlist(params_dict, key):
    if hasattr(params_dict, "getlist"):
        return params_dict.getlist(key)
    value = params_dict.get(key, [])
    return value if isinstance(value, list) else [value]


def build_visit_where(params_dict, alias_v="v", alias_l="l"):
    where, params = "WHERE 1=1", []
    d_ini = params_dict.get("d_ini") or data_n_dias(365)
    d_fim = params_dict.get("d_fim") or hoje()
    where += f" AND {alias_v}.data BETWEEN ? AND ?"
    params += [d_ini, d_fim]

    tipos = _getlist(params_dict, "tipo")
    locs = _getlist(params_dict, "localidade")
    ags = _getlist(params_dict, "agente")

    if tipos:
        where += f" AND {alias_v}.tipo IN ({','.join('?' * len(tipos))})"
        params += tipos
    if locs:
        where += f" AND {alias_l}.nome IN ({','.join('?' * len(locs))})"
        params += locs
    if ags:
        cond = " OR ".join([
            f"EXISTS(SELECT 1 FROM visita_agentes va2 JOIN agentes a2 ON a2.id_agente=va2.id_agente "
            f"WHERE va2.id_visita={alias_v}.id_visita AND a2.nome=?)"
            for _ in ags
        ])
        where += f" AND ({cond})"
        params += ags

    return where, params


def ler_modelo(modelo_path):
    secoes, secao_atual, linhas = {}, None, []
    try:
        with open(modelo_path, encoding="utf-8") as f:
            for linha in f:
                linha = linha.rstrip("\n")
                if linha.startswith("#") or not linha.strip():
                    continue
                if linha.startswith("[") and linha.endswith("]"):
                    if secao_atual:
                        secoes[secao_atual] = "\n".join(linhas).strip()
                    secao_atual, linhas = linha[1:-1], []
                else:
                    linhas.append(linha)
        if secao_atual:
            secoes[secao_atual] = "\n".join(linhas).strip()
    except FileNotFoundError:
        pass
    return secoes
