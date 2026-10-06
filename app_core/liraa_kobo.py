"""Diário Kobo do LIRAa, separado das importações gerais de visitas."""

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app_core import db, kobo_api, normalizadores, registro_geografico


class LiraaKoboError(ValueError):
    pass


LOCALIDADES_KOBO = {
    "cachoeira": "Cachoeira", "grasiela": "Graziela", "lamenha": "Lamenha",
    "para_so": "Paraíso", "roma": "Roma", "rosana": "Rosana",
    "santa_maria": "Santa Maria", "s_o_francisco": "São Francisco",
    "s_o_jo_o_batista": "São João Batista", "s_o_ven_ncio": "São Venâncio",
    "centro": "Sede", "tamboara": "Tamboara", "tangu": "Tanguá",
    "tranqueira": "Tranqueira",
}


def ensure_schema(conn):
    if getattr(conn, "backend", "sqlite") != "sqlite":
        if not db.table_exists(conn, "liraa_visitas"):
            raise LiraaKoboError("Aplique a migração 0025 antes de importar visitas LIRAa.")
        return
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS liraa_visitas (
                id_visita INTEGER PRIMARY KEY AUTOINCREMENT,
                id_ciclo INTEGER NOT NULL REFERENCES liraa_ciclos(id_ciclo) ON DELETE RESTRICT,
                id_estrato INTEGER REFERENCES liraa_estratos(id_estrato) ON DELETE RESTRICT,
                kobo_uuid TEXT NOT NULL UNIQUE, kobo_id INTEGER,
                data_visita TEXT NOT NULL, hora_inicio TEXT, enviado_em TEXT,
                agentes_codigos TEXT NOT NULL DEFAULT '', acs_codigos TEXT NOT NULL DEFAULT '',
                id_localidade INTEGER REFERENCES localidades(id_localidade),
                localidade_informada TEXT NOT NULL, quarteirao TEXT NOT NULL,
                situacao_vinculo TEXT NOT NULL, tipo_imovel TEXT, logradouro TEXT,
                numero TEXT, sequencia TEXT, morador TEXT, observacoes TEXT,
                criado_em TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_liraa_visitas_ciclo_data
                ON liraa_visitas(id_ciclo, data_visita);
            CREATE TABLE IF NOT EXISTS liraa_visita_tubitos (
                id_tubito INTEGER PRIMARY KEY AUTOINCREMENT,
                id_visita INTEGER NOT NULL REFERENCES liraa_visitas(id_visita) ON DELETE CASCADE,
                ordem INTEGER NOT NULL, numero TEXT, codigo_deposito TEXT,
                deposito TEXT, UNIQUE(id_visita, ordem));
            CREATE TABLE IF NOT EXISTS liraa_visitas_excluidas (
                kobo_uuid TEXT PRIMARY KEY, excluida_em TEXT NOT NULL,
                id_ciclo INTEGER, motivo TEXT NOT NULL DEFAULT '');
        """)


def _campo(record, name):
    if name in record:
        return record[name]
    current = record
    for part in name.split("/"):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _texto(value, limite=500):
    text = str(value if value is not None else "").strip()
    if len(text) > limite:
        raise LiraaKoboError("Um campo do Kobo excede o limite esperado.")
    return text


def _quarteirao(value):
    text = _texto(value, 30).replace(",", ".")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        raise LiraaKoboError(f"Quarteirão inválido: {text or '(vazio)' }.") from None
    if not number.is_finite() or number <= 0:
        raise LiraaKoboError("O quarteirão precisa ser um número positivo.")
    canonical = format(number.normalize(), "f")
    return registro_geografico._quarteirao(canonical)


def _data(value):
    text = _texto(value, 40)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise LiraaKoboError("Visita Kobo sem data válida.") from None


def _localidade(value):
    raw = _texto(value, 100)
    return normalizadores.normalizar_localidade(LOCALIDADES_KOBO.get(raw.casefold(), raw))


def _tubitos(record):
    rows = _campo(record, "group_jr1vc40") or []
    if not isinstance(rows, list):
        raise LiraaKoboError("O grupo de tubitos do Kobo não é uma lista.")
    result = []
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise LiraaKoboError("Tubito do Kobo inválido.")
        result.append({"ordem": i,
                       "numero": _texto(_campo(row, "N_mero_do_tubito"), 60),
                       "codigo_deposito": _texto(_campo(row, "C_digo_do_dep_sito"), 60),
                       "deposito": _texto(_campo(row, "Dep_sito"), 200)})
    return result


def _normalizar(record):
    if not isinstance(record, dict):
        raise LiraaKoboError("Envio Kobo inválido.")
    uuid = kobo_api.record_uuid(record)
    if not uuid or len(uuid) > 100:
        raise LiraaKoboError("Envio Kobo sem UUID válido.")
    raw_loc = _campo(record, "Dados_visita/Localidade")
    loc = _localidade(raw_loc)
    if not loc:
        raise LiraaKoboError("Visita Kobo sem localidade.")
    raw_id = record.get("_id")
    try:
        kobo_id = int(raw_id) if raw_id not in (None, "") else None
    except (TypeError, ValueError):
        raise LiraaKoboError("ID do envio Kobo inválido.") from None
    return {
        "kobo_uuid": uuid, "kobo_id": kobo_id,
        "data_visita": _data(_campo(record, "Data")),
        "hora_inicio": _texto(_campo(record, "Hora_inicio"), 40),
        "enviado_em": _texto(record.get("_submission_time"), 40),
        "agentes_codigos": _texto(_campo(record, "Agentes"), 500),
        "acs_codigos": _texto(_campo(record, "ACS"), 500),
        "localidade_informada": loc,
        "quarteirao": _quarteirao(_campo(record, "Dados_visita/Quarteir_o")),
        "tipo_imovel": _texto(_campo(record, "Dados_visita/Imovel"), 100),
        "logradouro": _texto(_campo(record, "Dados_visita/Logradouro"), 300),
        "numero": _texto(_campo(record, "Dados_visita/Numero"), 60),
        "sequencia": _texto(_campo(record, "Dados_visita/Sequencia"), 100),
        "morador": _texto(_campo(record, "Dados_visita/Morador"), 300),
        "observacoes": _texto(_campo(record, "Dados_visita/Observa_es"), 2000),
        "tubitos": _tubitos(record),
    }


def _contexto(conn, id_ciclo):
    cycle = conn.execute("SELECT * FROM liraa_ciclos WHERE id_ciclo=?", (id_ciclo,)).fetchone()
    if not cycle:
        raise LiraaKoboError("Ciclo LIRAa não encontrado.")
    nomes = {normalizadores.normalizar_localidade(r["nome"]): r["id_localidade"]
             for r in conn.execute("SELECT id_localidade,nome FROM localidades")}
    estratos = {(r["id_localidade"], _quarteirao(r["quarteirao"])): r["id_estrato"]
                for r in conn.execute("""SELECT id_localidade,quarteirao,id_estrato
                    FROM liraa_estrato_quarteiroes WHERE id_ciclo=?""", (id_ciclo,))}
    sorteados = {}
    for row in conn.execute("""SELECT s.id_estrato,s.selecionados_json FROM liraa_sorteios s
        JOIN liraa_estratos e ON e.id_estrato=s.id_estrato WHERE e.id_ciclo=?""", (id_ciclo,)):
        sorteados[row["id_estrato"]] = {
            (item["id_localidade"], _quarteirao(item["quarteirao"]))
            for item in json.loads(row["selecionados_json"])}
    return cycle, nomes, estratos, sorteados


def _vincular(item, context):
    cycle, nomes, estratos, sorteados = context
    if item["localidade_informada"] == "Capivara dos Manfron":
        return None, None, "area_rural_fora_liraa"
    if int(item["data_visita"][:4]) != int(cycle["ano"]):
        return None, None, "fora_do_ano"
    if (cycle["inicio"] and item["data_visita"] < cycle["inicio"]) or (
            cycle["fim"] and item["data_visita"] > cycle["fim"]):
        return None, None, "fora_do_periodo"
    localidade_id = nomes.get(item["localidade_informada"])
    if localidade_id is None:
        return None, None, "localidade_desconhecida"
    estrato_id = estratos.get((localidade_id, item["quarteirao"]))
    if not estrato_id:
        return localidade_id, None, "fora_do_estrato"
    if estrato_id not in sorteados:
        return localidade_id, estrato_id, "estrato_sem_sorteio"
    if (localidade_id, item["quarteirao"]) not in sorteados[estrato_id]:
        return localidade_id, estrato_id, "fora_do_sorteio"
    return localidade_id, estrato_id, "sorteado"


def _preparar(conn, id_ciclo, records):
    context = _contexto(conn, id_ciclo)
    if len(records) > 5000:
        raise LiraaKoboError("Reduza o período: mais de 5.000 envios.")
    uuids = set()
    preparados = []
    for record in records:
        item = _normalizar(record)
        if item["kobo_uuid"] in uuids:
            raise LiraaKoboError("A resposta Kobo contém UUID repetido.")
        uuids.add(item["kobo_uuid"])
        item["id_localidade"], item["id_estrato"], item["situacao_vinculo"] = _vincular(item, context)
        exists = conn.execute("SELECT 1 FROM liraa_visitas WHERE kobo_uuid=?", (item["kobo_uuid"],)).fetchone()
        deleted = conn.execute("SELECT 1 FROM liraa_visitas_excluidas WHERE kobo_uuid=?", (item["kobo_uuid"],)).fetchone()
        item["situacao_importacao"] = "importada" if exists else "excluida" if deleted else "nova"
        preparados.append(item)
    return preparados


def previa(target, id_ciclo, records):
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        return _preparar(conn, id_ciclo, records)
    finally:
        conn.close()


def importar(target, id_ciclo, records, auditar=None):
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        with conn:
            items = _preparar(conn, id_ciclo, records)
            created = 0
            for item in items:
                if item["situacao_importacao"] != "nova":
                    continue
                visit_id = db.insert_and_get_id(conn, """INSERT INTO liraa_visitas
                    (id_ciclo,id_estrato,kobo_uuid,kobo_id,data_visita,hora_inicio,enviado_em,
                     agentes_codigos,acs_codigos,id_localidade,localidade_informada,quarteirao,
                     situacao_vinculo,tipo_imovel,logradouro,numero,sequencia,morador,observacoes,criado_em)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (id_ciclo, item["id_estrato"], item["kobo_uuid"], item["kobo_id"],
                     item["data_visita"], item["hora_inicio"], item["enviado_em"],
                     item["agentes_codigos"], item["acs_codigos"], item["id_localidade"],
                     item["localidade_informada"], item["quarteirao"], item["situacao_vinculo"],
                     item["tipo_imovel"], item["logradouro"], item["numero"], item["sequencia"],
                     item["morador"], item["observacoes"], datetime.now().isoformat(timespec="seconds")),
                    "id_visita")
                for tube in item["tubitos"]:
                    conn.execute("""INSERT INTO liraa_visita_tubitos
                        (id_visita,ordem,numero,codigo_deposito,deposito) VALUES (?,?,?,?,?)""",
                        (visit_id, tube["ordem"], tube["numero"], tube["codigo_deposito"], tube["deposito"]))
                created += 1
            if auditar:
                auditar(conn, {"id_ciclo": id_ciclo, "recebidos": len(items), "novos": created,
                                "ja_importados": sum(x["situacao_importacao"] == "importada" for x in items),
                                "excluidos_ignorados": sum(x["situacao_importacao"] == "excluida" for x in items)})
            return created
    finally:
        conn.close()


def listar(target, id_ciclo=None, limite=100, deslocamento=0, inicio=None, fim=None, busca=None):
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        conditions, params = [], []
        if id_ciclo:
            conditions.append("v.id_ciclo=?")
            params.append(id_ciclo)
        for bound, comparator in ((inicio, ">="), (fim, "<=")):
            if bound:
                parsed = _data(bound)
                conditions.append(f"v.data_visita{comparator}?")
                params.append(parsed)
        if busca:
            term = _texto(busca, 100)
            conditions.append("(v.logradouro LIKE ? OR v.numero LIKE ? OR v.quarteirao LIKE ? OR v.morador LIKE ?)")
            params.extend([f"%{term}%"] * 4)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        limit = max(1, min(int(limite), 500))
        offset = max(0, int(deslocamento))
        rows = conn.execute(f"""SELECT v.*,e.numero AS estrato_numero,
            (SELECT COUNT(*) FROM liraa_visita_tubitos t WHERE t.id_visita=v.id_visita) AS total_tubitos
            FROM liraa_visitas v LEFT JOIN liraa_estratos e ON e.id_estrato=v.id_estrato
            {where} ORDER BY v.data_visita DESC,v.id_visita DESC LIMIT ? OFFSET ?""",
            (*params, limit, offset)).fetchall()
        visits = [db.serialize_row(row) for row in rows]
        if visits:
            ids = [visit["id_visita"] for visit in visits]
            placeholders = ",".join("?" for _ in ids)
            by_visit = {visit_id: [] for visit_id in ids}
            for tube in conn.execute(f"""SELECT * FROM liraa_visita_tubitos
                WHERE id_visita IN ({placeholders}) ORDER BY id_visita,ordem""", ids):
                by_visit[tube["id_visita"]].append(db.serialize_row(tube))
            for visit in visits:
                visit["tubitos"] = by_visit[visit["id_visita"]]
        contexts = {}
        numbers = {}
        for visit in visits:
            cycle_id = visit["id_ciclo"]
            if cycle_id not in contexts:
                contexts[cycle_id] = _contexto(conn, cycle_id)
                numbers[cycle_id] = {r["id_estrato"]: r["numero"] for r in conn.execute(
                    "SELECT id_estrato,numero FROM liraa_estratos WHERE id_ciclo=?", (cycle_id,))}
            _, estrato_id, status = _vincular(visit, contexts[cycle_id])
            visit["id_estrato"] = estrato_id
            visit["estrato_numero"] = numbers[cycle_id].get(estrato_id)
            visit["situacao_vinculo"] = status
        return visits
    finally:
        conn.close()


def tubitos(target, id_visita):
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        return [db.serialize_row(row) for row in conn.execute(
            "SELECT * FROM liraa_visita_tubitos WHERE id_visita=? ORDER BY ordem", (id_visita,))]
    finally:
        conn.close()


def excluir(target, id_visita, motivo="", auditar=None):
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        with conn:
            row = conn.execute("SELECT id_ciclo,kobo_uuid FROM liraa_visitas WHERE id_visita=?", (id_visita,)).fetchone()
            if not row:
                raise LiraaKoboError("Visita LIRAa não encontrada.")
            tube_count = conn.execute("SELECT COUNT(*) FROM liraa_visita_tubitos WHERE id_visita=?", (id_visita,)).fetchone()[0]
            conn.execute("""INSERT INTO liraa_visitas_excluidas
                (kobo_uuid,excluida_em,id_ciclo,motivo) VALUES (?,?,?,?)""",
                (row["kobo_uuid"], datetime.now().isoformat(timespec="seconds"),
                 row["id_ciclo"], _texto(motivo, 300)))
            conn.execute("DELETE FROM liraa_visitas WHERE id_visita=?", (id_visita,))
            if auditar:
                auditar(conn, {"id_ciclo": row["id_ciclo"], "uuid": row["kobo_uuid"],
                                "tubitos_excluidos": tube_count, "motivo": _texto(motivo, 300)})
            return row["id_ciclo"]
    finally:
        conn.close()
