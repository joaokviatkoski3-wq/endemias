import json
import os
from datetime import datetime
from pathlib import Path
from urllib import error, parse, request
import unicodedata

import pandas as pd


DEFAULT_SERVER_URL = "https://kf.kobotoolbox.org"
VISIT_TYPES = ("PE", "TB", "TBO", "PVE")
EXTRA_TYPES = ("LARVAS", "ESPOROTRICOSE", "BRI", "AMOSTRA_ANIMAIS", "RECOLHIMENTO")
ALL_TYPES = VISIT_TYPES + EXTRA_TYPES
TYPE_LABELS = {
    "PE": "Ponto Estratégico",
    "TB": "Tratamento/Bloqueio",
    "TBO": "Ovitrampas",
    "PVE": "Pesquisa Vetorial Especial",
    "LARVAS": "Resultados de laboratório",
    "ESPOROTRICOSE": "Esporotricose",
    "BRI": "Borrifamento residual",
    "AMOSTRA_ANIMAIS": "Amostra de animais",
    "RECOLHIMENTO": "Recolhimento",
}


class KoboError(RuntimeError):
    pass


def default_config():
    return {
        "server_url": DEFAULT_SERVER_URL,
        "api_token": "",
        "assets": {codigo: "" for codigo in ALL_TYPES},
        "last_sync": {},
    }


def normalize_server_url(value):
    url = (value or DEFAULT_SERVER_URL).strip().rstrip("/")
    if not url.startswith(("https://", "http://")):
        url = "https://" + url
    return url


def load_config(path):
    cfg = default_config()
    arquivo = Path(path)
    if arquivo.exists():
        try:
            raw = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        cfg.update({k: v for k, v in raw.items() if k in cfg})
        assets = dict(default_config()["assets"])
        assets.update((raw.get("assets") or {}) if isinstance(raw.get("assets"), dict) else {})
        cfg["assets"] = assets
        cfg["last_sync"] = raw.get("last_sync") if isinstance(raw.get("last_sync"), dict) else {}
    cfg["server_url"] = normalize_server_url(cfg.get("server_url"))
    return cfg


def save_config(path, data, keep_token=True):
    atual = load_config(path)
    token = (data.get("api_token") or "").strip()
    if keep_token and not token:
        token = atual.get("api_token") or ""
    cfg = {
        "server_url": normalize_server_url(data.get("server_url") or atual.get("server_url")),
        "api_token": token,
        "assets": {codigo: (data.get("assets") or {}).get(codigo, atual["assets"].get(codigo, "")).strip() for codigo in ALL_TYPES},
        "last_sync": atual.get("last_sync") or {},
    }
    arquivo = Path(path)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(arquivo, 0o600)
    except OSError:
        pass
    return public_config(cfg)


def public_config(cfg):
    assets = cfg.get("assets") or {}
    return {
        "server_url": cfg.get("server_url") or DEFAULT_SERVER_URL,
        "has_token": bool(cfg.get("api_token")),
        "assets": {codigo: assets.get(codigo, "") for codigo in ALL_TYPES},
        "last_sync": cfg.get("last_sync") or {},
        "tipos_visita": list(VISIT_TYPES),
        "tipos_extra": list(EXTRA_TYPES),
        "tipos": [{"codigo": codigo, "label": TYPE_LABELS.get(codigo, codigo)} for codigo in ALL_TYPES],
    }


def _headers(cfg):
    token = (cfg.get("api_token") or "").strip()
    if not token:
        raise KoboError("Configure o token da API do Kobo antes de conectar.")
    return {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
        "User-Agent": "Endemias/KoBo-Preview",
    }


def _url(cfg, path, params=None):
    base = normalize_server_url(cfg.get("server_url"))
    query = parse.urlencode(params or {}, doseq=True)
    return f"{base}{path}{'?' + query if query else ''}"


def _get_json(cfg, path, params=None, timeout=30):
    url = _url(cfg, path, params)
    req = request.Request(url, headers=_headers(cfg), method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            raise KoboError("Token recusado pelo Kobo. Confira o token e permissões do formulário.") from exc
        raise KoboError(f"Kobo retornou erro HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise KoboError(f"Falha de conexão com o Kobo: {exc.reason}") from exc
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise KoboError("Resposta do Kobo não veio em JSON válido.") from exc


def test_connection(cfg):
    data = _get_json(cfg, "/api/v2/assets/", {"format": "json", "limit": 1})
    return {
        "ok": True,
        "count": data.get("count"),
        "server_url": normalize_server_url(cfg.get("server_url")),
    }


def fetch_submissions(cfg, asset_uid, limit=100, start=None, end=None):
    asset_uid = (asset_uid or "").strip()
    if not asset_uid:
        raise KoboError("Informe o UID do formulário Kobo.")
    limit = max(1, min(int(limit or 100), 5000))
    params = {"format": "json", "limit": limit}
    query = {}
    if start:
        query["$and"] = query.get("$and", []) + [{"_submission_time": {"$gte": f"{start}T00:00:00"}}]
    if end:
        query["$and"] = query.get("$and", []) + [{"_submission_time": {"$lte": f"{end}T23:59:59"}}]
    if query:
        params["query"] = json.dumps(query, ensure_ascii=False)
    data = _get_json(cfg, f"/api/v2/assets/{asset_uid}/data/", params)
    results = data.get("results") if isinstance(data, dict) else None
    if results is None and isinstance(data, list):
        results = data
    if results is None:
        raise KoboError("Resposta do Kobo não contém lista de registros.")
    return results[:limit], data


def record_uuid(record):
    value = record.get("_uuid") or record.get("meta/instanceID") or record.get("instanceID") or ""
    return str(value).replace("uuid:", "").strip()


def record_date(record):
    for key in ("data", "Data", "data_visita", "Data da visita", "start", "_submission_time"):
        value = record.get(key)
        if not value:
            continue
        text = str(value)
        try:
            return datetime.fromisoformat(text[:19].replace("Z", "")).date().isoformat()
        except ValueError:
            if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
                return text[:10]
    return None


def _date_value(value):
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text[:19].replace("Z", "")).date().isoformat()
    except ValueError:
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]
    return None


def _norm(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").casefold()


def _value(record, candidates):
    wanted = {_norm(c) for c in candidates}
    for key, value in record.items():
        if _norm(key) in wanted and value not in (None, ""):
            return str(value).strip()
    for key, value in record.items():
        key_norm = _norm(key)
        if value not in (None, "") and any(c in key_norm for c in wanted):
            return str(value).strip()
    return ""


def _iter_dict_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dict_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dict_nodes(child)


def record_tubes(record, fallback_date=None):
    fallback_date = _date_value(fallback_date) or record_date(record)
    tubes = []
    seen = set()
    for node in _iter_dict_nodes(record):
        tubo = _value(node, ["Número do tubito", "Numero do tubito", "num_tubo", "tubo", "tubito"])
        if not tubo:
            continue
        data = _date_value(_value(node, ["Data da coleta", "data_coleta", "Data"])) or fallback_date
        key = (tubo.strip(), data or "")
        if key in seen:
            continue
        seen.add(key)
        tubes.append({"tubo": key[0], "data": key[1]})
    return tubes


def _collect_values(record, tokens, limit=4):
    result = []
    tokens_norm = [_norm(t) for t in tokens]
    for key, value in record.items():
        if value in (None, ""):
            continue
        key_norm = _norm(key)
        if any(token in key_norm for token in tokens_norm):
            text = str(value).strip()
            if text and text.lower() not in ("nan", "none") and text not in result:
                result.append(text)
        if len(result) >= limit:
            break
    return ", ".join(result)


def record_details(tipo, record, larvas_links=None):
    larvas_links = larvas_links or {}
    tubos = record_tubes(record)
    tubo = _value(record, ["Número do tubito", "Numero do tubito", "num_tubo", "tubo", "tubito"])
    if not tubo and tubos:
        tubo = tubos[0]["tubo"]
    data = record_date(record)
    data_coleta = _value(record, ["Data da coleta", "data_coleta"]) or (tubos[0]["data"] if tubos else "") or data
    detalhes = {
        "data": data or data_coleta or "-",
        "enviado_em": record.get("_submission_time") or "-",
        "agentes": _collect_values(record, ["agente"]),
        "localidade": _value(record, ["Localidade", "localidade", "bairro"]),
        "endereco": _value(record, ["Logradouro", "Endereco", "Endereço", "Rua"]),
        "numero": _value(record, ["Número", "Numero"]),
        "quarteirao": _value(record, ["Quarteirão", "Quarteirao"]),
        "morador": _value(record, ["Morador", "Responsável", "Responsavel"]),
        "visita": _value(record, ["Visita", "Situação da visita", "Situacao da visita"]),
        "tubo": tubo,
        "data_coleta": data_coleta,
        "laboratorio": _collect_values(record, ["laboratorista", "leitura"]),
        "resultado": _collect_values(record, ["aegypt", "albopictus", "outra especie", "outra espécie"], limit=6),
        "vinculo_visita": "",
        "tubos": tubos,
    }
    if tipo == "LARVAS" and tubo and data_coleta:
        link = larvas_links.get((tubo.strip(), data_coleta[:10]))
        if link is True:
            link = "banco"
        detalhes["vinculo_visita"] = link or "pendente"
    return detalhes


def summarize_submissions(records, existing_uuids=None, sample_size=20, tipo=None, larvas_links=None):
    existing_uuids = existing_uuids or set()
    rows = []
    novos = duplicados = sem_uuid = 0
    pendencias = 0
    for record in records:
        uuid = record_uuid(record)
        duplicado = bool(uuid and uuid in existing_uuids)
        detalhes = record_details(tipo or "", record, larvas_links=larvas_links)
        problemas = []
        if not uuid:
            sem_uuid += 1
            problemas.append("Sem identificador interno do Kobo")
        elif duplicado:
            duplicados += 1
        else:
            novos += 1
        if detalhes["data"] == "-":
            problemas.append("Sem data identificada")
        if tipo == "LARVAS":
            if not detalhes["tubo"]:
                problemas.append("Sem número do tubo")
            if not detalhes["data_coleta"] or detalhes["data_coleta"] == "-":
                problemas.append("Sem data da coleta")
            if detalhes["vinculo_visita"] == "pendente":
                problemas.append("Tubo sem visita/coleta correspondente no sistema")
        if problemas:
            pendencias += 1
        if len(rows) < sample_size:
            rows.append({
                "uuid": uuid or "-",
                "id": record.get("_id") or record.get("_xform_id_string") or "-",
                "data": detalhes["data"],
                "submission_time": record.get("_submission_time") or "-",
                "status": "sem_uuid" if not uuid else ("duplicado" if duplicado else "novo"),
                "status_label": "Precisa de atenção" if problemas else ("Já existe" if duplicado else "Pronto para importar"),
                "problemas": problemas,
                "detalhes": detalhes,
            })
    return {
        "total": len(records),
        "novos": novos,
        "duplicados": duplicados,
        "sem_uuid": sem_uuid,
        "pendencias": pendencias,
        "amostra": rows,
    }


def _flat_record(record):
    flat = {}
    for key, value in record.items():
        if isinstance(value, (dict, list)):
            continue
        flat[key] = value
    return flat


def _ensure_visit_columns(row, tipo, cfg_tipo, record):
    detalhes = record_details(tipo, record)
    data = detalhes.get("data") if detalhes.get("data") != "-" else record_date(record)
    col_data = cfg_tipo.get("col_data") or "Data"
    col_localidade = cfg_tipo.get("col_localidade") or "Localidade"
    row.setdefault("_uuid", record_uuid(record))
    row.setdefault("_id", record.get("_id"))
    row.setdefault("_submission_time", record.get("_submission_time"))
    if data:
        row.setdefault(col_data, data)
        row.setdefault("Data", data)
        if tipo == "PE":
            row.setdefault("Digite a data", data)
    row.setdefault(col_localidade, detalhes.get("localidade"))
    row.setdefault("Localidade", detalhes.get("localidade"))
    row.setdefault("localidade", detalhes.get("localidade"))
    row.setdefault("Logradouro", detalhes.get("endereco"))
    row.setdefault("Número", detalhes.get("numero"))
    row.setdefault("Quarteirão", detalhes.get("quarteirao"))
    row.setdefault("Visita", detalhes.get("visita"))
    if cfg_tipo.get("col_sequencia"):
        row.setdefault(cfg_tipo["col_sequencia"], "")
    return row


def _coleta_row(record, tubo, cfg_tipo):
    uuid = record_uuid(record)
    col_tubo = cfg_tipo.get("col_numero_tubo_coletas") or "Número do tubito"
    return {
        "_uuid": uuid,
        "submission__uuid": uuid,
        col_tubo: tubo.get("tubo"),
        cfg_tipo.get("col_codigo_deposito_coletas", "Código do depósito"): "",
        cfg_tipo.get("col_nome_deposito_coletas", "Depósito"): "",
        cfg_tipo.get("col_deposito_eliminado_coletas", "O Depósito onde foi feita a coleta foi eliminado?"): "",
    }


def _larva_row(record, cfg_larvas):
    row = _flat_record(record)
    detalhes = record_details("LARVAS", record)
    row.setdefault("_uuid", record_uuid(record))
    row.setdefault("_id", record.get("_id"))
    row.setdefault("_submission_time", record.get("_submission_time"))
    row.setdefault(cfg_larvas.get("col_numero_tubo", "Número do tubito"), detalhes.get("tubo"))
    row.setdefault(cfg_larvas.get("col_data_coleta", "Data da coleta"), detalhes.get("data_coleta"))
    for col in cfg_larvas.get("colunas_resultado", []):
        row.setdefault(col, "")
    return row


def write_etl_workbooks(registros_por_tipo, config_path, output_dir, prefix="kobo_api"):
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    tipos_cfg = cfg.get("tipos_trabalho") or {}
    cfg_larvas = cfg.get("larvas") or {}

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    arquivos = []

    for tipo in VISIT_TYPES:
        records = registros_por_tipo.get(tipo) or []
        if not records or tipo not in tipos_cfg:
            continue
        cfg_tipo = tipos_cfg[tipo]
        visitas = [_ensure_visit_columns(_flat_record(record), tipo, cfg_tipo, record) for record in records]
        coletas = []
        for record in records:
            data_visita = record_date(record)
            for tubo in record_tubes(record, fallback_date=data_visita):
                coletas.append(_coleta_row(record, tubo, cfg_tipo))
        path = out / f"{tipo}_{prefix}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(visitas).to_excel(writer, sheet_name="dados", index=False)
            pd.DataFrame(coletas).to_excel(writer, sheet_name="coletas", index=False)
        arquivos.append(str(path))

    larvas = registros_por_tipo.get("LARVAS") or []
    if larvas:
        path = out / f"LARVAS_{prefix}.xlsx"
        pd.DataFrame([_larva_row(record, cfg_larvas) for record in larvas]).to_excel(path, index=False, engine="openpyxl")
        arquivos.append(str(path))

    return arquivos
