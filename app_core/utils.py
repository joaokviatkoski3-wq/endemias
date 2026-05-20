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
