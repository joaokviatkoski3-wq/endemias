"""Conferencia manual de registros existentes, com aprovacao campo a campo."""
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from datetime import date, datetime, time as time_type
from decimal import Decimal
from pathlib import Path

from app_core import bri, db, kobo_api, recolhimentos, visitas


TTL = 15 * 60
MAX_REGISTROS = 5000
COMUNS = {"data": "Data", "hora": "Hora", "localidade": "Localidade", "agentes_texto": "Agentes"}
BRI_CAMPOS = {
    **COMUNS, "destino_tratamento": "Destino do tratamento", "local_tratamento": "Local do tratamento",
    "logradouro": "Logradouro", "numero": "Número", "quarteirao": "Quarteirão",
    "numero_ovitrampa": "Número da ovitrampa", "quantidade_carga": "Carga",
    "tratou_imovel_extra": "Tratou imóvel adicional", "qual_imovel_extra": "Imóvel adicional",
    "depositos_tratados_extra": "Depósitos adicionais tratados", "quantidade_carga_extra": "Carga adicional",
}
RECOLHA_CAMPOS = {**COMUNS, "pneu": "Pneus", "louca_sanitaria": "Louças sanitárias", "tv": "Televisores",
                  "parachoque": "Para-choques", "outros": "Outros materiais"}
CONTRATOS = {"BRI": (bri, "bri_registros", "id_bri", BRI_CAMPOS),
             "RECOLHIMENTO": (recolhimentos, "recolhimentos", "id_recolhimento", RECOLHA_CAMPOS)}
PE_CAMPOS = {"destino_tratamento", "local_tratamento", "localidade", "logradouro", "numero", "quarteirao"}


class ConferenciaInvalida(ValueError):
    status = 400


class ConferenciaConflito(ConferenciaInvalida):
    status = 409


def validar_periodo(inicio, fim):
    try:
        a, b = date.fromisoformat(inicio), date.fromisoformat(fim)
    except (TypeError, ValueError):
        raise ConferenciaInvalida("Informe as datas inicial e final válidas.") from None
    if a > b or (b - a).days > 365:
        raise ConferenciaInvalida("Escolha um período em ordem cronológica de até um ano.")
    return a.isoformat(), b.isoformat()


def _scalar(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, time_type):
        return value.strftime("%H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str) and re.fullmatch(r"\d{2}:\d{2}:00(?:\.0+)?", value):
        return value[:5]
    return value


def _snapshot(row, fields):
    return {field: _scalar(row[field]) for field in fields}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _directory(root):
    path = Path(root).resolve() / "conferencias_kobo"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _signature(body, secret):
    key = secret if isinstance(secret, bytes) else str(secret).encode()
    return hmac.new(key, _json(body).encode("utf-8"), hashlib.sha256).hexdigest()


def _save(path, body, secret):
    # Escrita exclusiva: o identificador nunca e escolhido pelo navegador.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as fh:
        fh.write(_json({"body": body, "signature": _signature(body, secret)}))


def _load(root, token, uid, setor, secret):
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ConferenciaInvalida("Conferência inválida. Gere uma nova prévia.")
    path = _directory(root) / (token + ".json")
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        body = envelope["body"]
        valid = hmac.compare_digest(envelope["signature"], _signature(body, secret))
    except (OSError, ValueError, KeyError, TypeError):
        raise ConferenciaInvalida("Conferência indisponível. Gere uma nova prévia.") from None
    if not valid or body.get("uid") != uid or body.get("setor") != setor:
        raise ConferenciaInvalida("Conferência indisponível para este usuário ou setor.")
    if body.get("expira", 0) <= time.time():
        raise ConferenciaConflito("A conferência expirou. Gere uma nova prévia.")
    return path, body


def _agent_links(conn, module, ident):
    return sorted(r[0] for r in conn.execute(
        f"SELECT id_agente FROM {module.AGENTES_TABLE} WHERE {CONTRATOS['BRI' if module is bri else 'RECOLHIMENTO'][2]}=?",
        (ident,),
    ))


def preparar(target, tipo, records, config_path, root, uid, setor, secret):
    if not isinstance(tipo, str) or tipo not in CONTRATOS or setor not in (None, "endemias"):
        raise ConferenciaInvalida("Formulário indisponível para conferência nesta área.")
    if not isinstance(records, list) or len(records) > MAX_REGISTROS or any(not isinstance(r, dict) for r in records):
        raise ConferenciaInvalida("Reduza o período para conferir até 5.000 registros.")
    uuids = [kobo_api.record_uuid(r) for r in records]
    if any(not u for u in uuids) or len(set(uuids)) != len(uuids):
        raise ConferenciaInvalida("O formulário contém identificação ausente ou repetida. Nenhuma alteração foi preparada.")
    module, table, pk, fields = CONTRATOS[tipo]
    directory = _directory(root)
    # Elimina apenas previas antigas desta funcionalidade; nunca uploads gerais.
    for old in directory.glob("*.json"):
        try:
            if re.fullmatch(r"[a-f0-9]{64}\.json", old.name) and old.stat().st_mtime < time.time() - TTL * 2:
                old.unlink(missing_ok=True)
        except OSError:
            pass
    normalized = []
    if records:
        with tempfile.TemporaryDirectory(prefix="normalizar-", dir=directory) as temp:
            paths = kobo_api.write_etl_workbooks({tipo: records}, config_path, temp)
            _, normalized = module.preparar_arquivo(paths[0])
    if len(normalized) != len(records) or {r.get("kobo_uuid") for r in normalized} != set(uuids):
        raise ConferenciaInvalida("Há registros que não puderam ser normalizados. Confira o formulário antes de continuar.")
    conn = db.connect(target)
    entries = []
    matched = unchanged = 0
    try:
        for new in normalized:
            old = conn.execute(f"SELECT * FROM {table} WHERE kobo_uuid=?", (new["kobo_uuid"],)).fetchone()
            if old is None:
                continue
            matched += 1
            before = _snapshot(old, fields)
            after = {f: _scalar(new.get(f)) for f in fields}
            changes = [f for f in fields if before[f] != after[f]]
            if not changes:
                unchanged += 1
                continue
            entries.append({"chave": secrets.token_hex(12), "id": old[pk], "uuid": new["kobo_uuid"],
                "antes": before, "depois": after, "campos": changes, "agentes": _agent_links(conn, module, old[pk]),
                "pe": [_scalar(old["id_pe"]), old["codigo_pe"]] if tipo == "BRI" else None})
    finally:
        conn.close()
    token = secrets.token_hex(32)
    body = {"uid": uid, "setor": setor, "tipo": tipo, "expira": time.time() + TTL, "registros": entries}
    _save(directory / (token + ".json"), body, secret)
    return {"token": token, "expira": body["expira"], "recebidos": len(records), "encontrados": matched,
        "sem_alteracao": unchanged, "nao_importados": len(records) - matched,
        "registros": [{"chave": e["chave"], "uuid": e["uuid"], "data": e["antes"].get("data"), "hora": e["antes"].get("hora"), "localidade": e["antes"].get("localidade"),
            "referencia": ", ".join(str(v) for v in (e["antes"].get("logradouro"), e["antes"].get("numero")) if v) or e["antes"].get("agentes_texto"),
            "alteracoes": [{"campo": f, "rotulo": fields[f], "antes": e["antes"][f], "depois": e["depois"][f]} for f in e["campos"]]} for e in entries]}


def _pe_vinculo(conn, merged):
    if merged.get("destino_tratamento") != "Ponto Estratégico":
        return None, None
    linked = bri._resolver_pe_vinculo(conn, merged)
    if linked:
        point = conn.execute("SELECT id_localidade,quarteirao FROM pontos_estrategicos WHERE id_pe=?", (linked["id_pe"],)).fetchone()
        if point and point["id_localidade"] == merged.get("id_localidade") and point["quarteirao"] == merged.get("quarteirao"):
            return linked["id_pe"], linked["codigo_pe"]
    try:
        return visitas._reconciliar_pe_edicao(conn, {}, {**merged, "tipo": "PE"})
    except visitas.VisitaInvalida as exc:
        raise ConferenciaInvalida(str(exc)) from exc


def aplicar(target, root, token, selecoes, uid, setor, secret, registrar):
    path, body = _load(root, token, uid, setor, secret)
    tipo = body["tipo"]
    if tipo not in CONTRATOS or setor not in (None, "endemias"):
        raise ConferenciaInvalida("Formulário indisponível nesta área.")
    module, table, pk, fields = CONTRATOS[tipo]
    if not isinstance(selecoes, list) or not selecoes or len(selecoes) > MAX_REGISTROS * len(fields):
        raise ConferenciaInvalida("Selecione individualmente os campos que deseja alterar.")
    entries = {e["chave"]: e for e in body["registros"]}
    approved = {}
    for item in selecoes:
        if not isinstance(item, dict) or set(item) != {"registro", "campo"}:
            raise ConferenciaInvalida("Seleção de campos inválida.")
        key, field = item["registro"], item["campo"]
        if not isinstance(key, str) or not isinstance(field, str) or key not in entries or field not in fields or field not in entries[key]["campos"]:
            raise ConferenciaInvalida("Um campo selecionado não pertence a esta prévia.")
        if field in approved.setdefault(key, set()):
            raise ConferenciaInvalida("Há campos repetidos na seleção.")
        approved[key].add(field)
    conn = db.connect(target)
    changes = []
    try:
        pg = getattr(conn, "backend", "sqlite") == "postgresql"
        if not pg:
            conn.execute("BEGIN IMMEDIATE")
        # Ordem estavel tambem evita inversao de locks entre duas conferencias.
        for key in sorted(approved, key=lambda k: str(entries[k]["id"])):
            selected = approved[key]
            e = entries[key]
            old = conn.execute(f"SELECT * FROM {table} WHERE {pk}=?" + (" FOR UPDATE" if pg else ""), (e["id"],)).fetchone()
            if old is None or old["kobo_uuid"] != e["uuid"] or any(_scalar(old[f]) != e["antes"][f] for f in selected):
                raise ConferenciaConflito("Um registro mudou desde a conferência. Gere uma nova prévia; nenhuma alteração foi aplicada.")
            if "agentes_texto" in selected and _agent_links(conn, module, e["id"]) != e["agentes"]:
                raise ConferenciaConflito("A equipe mudou desde a conferência. Gere uma nova prévia.")
            if tipo == "BRI" and selected & PE_CAMPOS and [_scalar(old["id_pe"]), old["codigo_pe"]] != e["pe"]:
                raise ConferenciaConflito("O vínculo do PE mudou desde a conferência. Gere uma nova prévia.")
            merged = dict(old)
            updates = {f: e["depois"][f] for f in sorted(selected)}
            merged.update(updates)
            if "localidade" in selected:
                updates["id_localidade"] = module._obter_ou_criar_localidade(conn, merged["localidade"]) if merged["localidade"] else None
                merged.update(updates)
            if tipo == "BRI" and selected & PE_CAMPOS:
                updates["id_pe"], updates["codigo_pe"] = _pe_vinculo(conn, merged)
            if tipo == "RECOLHIMENTO" and selected & {"pneu", "louca_sanitaria", "tv", "parachoque", "outros"}:
                updates["total_materiais"] = sum(merged.get(f) or 0 for f in ("pneu", "louca_sanitaria", "tv", "parachoque", "outros"))
            conn.execute(f"UPDATE {table} SET " + ",".join(f"{f}=?" for f in updates) + f" WHERE {pk}=?", (*updates.values(), e["id"]))
            if "agentes_texto" in selected:
                conn.execute(f"DELETE FROM {module.AGENTES_TABLE} WHERE {pk}=?", (e["id"],))
                module._inserir_agentes(conn, e["id"], merged.get("agentes_texto"))
            changes.append({"id": e["id"],
                "campos": [{"campo": f, "antes": e["antes"][f], "depois": e["depois"][f]} for f in sorted(selected)],
                "derivados": [{"campo": f, "antes": _scalar(old[f]), "depois": updates[f]} for f in updates if f not in selected and _scalar(old[f]) != updates[f]],
                "agentes": {"antes": e["agentes"], "depois": _agent_links(conn, module, e["id"])} if "agentes_texto" in selected else None})
        registrar(conn, tipo, changes)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    # O optimistic check tambem impede repeticao caso o descarte do arquivo falhe.
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True, "registros": len(changes), "campos": sum(len(c["campos"]) for c in changes)}
