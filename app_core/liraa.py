"""Planejamento territorial e sorteio auditável do LIRAa.

Não calcula índices nem exporta .lira: faltam as inspeções e a consolidação
laboratorial específicas do levantamento.
"""

import hashlib
import json
import math
import random
import secrets
from datetime import datetime

from app_core import db as db_core
from app_core import registro_geografico as rg_core


class LiraaError(ValueError):
    pass


def _schema(conn):
    if getattr(conn, "backend", "sqlite") != "sqlite":
        return
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS liraa_ciclos (
                id_ciclo INTEGER PRIMARY KEY AUTOINCREMENT,
                ano INTEGER NOT NULL, nome TEXT NOT NULL, inicio TEXT, fim TEXT,
                observacoes TEXT NOT NULL DEFAULT '', criado_em TEXT NOT NULL,
                UNIQUE(ano, nome));
            CREATE TABLE IF NOT EXISTS liraa_estratos (
                id_estrato INTEGER PRIMARY KEY AUTOINCREMENT,
                id_ciclo INTEGER NOT NULL REFERENCES liraa_ciclos(id_ciclo) ON DELETE CASCADE,
                numero INTEGER NOT NULL, tipo TEXT NOT NULL,
                imoveis_confirmados INTEGER NOT NULL, observacoes TEXT NOT NULL DEFAULT '',
                criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL,
                UNIQUE(id_ciclo, numero));
            CREATE TABLE IF NOT EXISTS liraa_estrato_localidades (
                id_estrato INTEGER NOT NULL REFERENCES liraa_estratos(id_estrato) ON DELETE CASCADE,
                id_ciclo INTEGER NOT NULL REFERENCES liraa_ciclos(id_ciclo) ON DELETE CASCADE,
                id_localidade INTEGER NOT NULL REFERENCES localidades(id_localidade),
                PRIMARY KEY(id_estrato, id_localidade), UNIQUE(id_ciclo, id_localidade));
            CREATE TABLE IF NOT EXISTS liraa_estrato_quarteiroes (
                id_estrato INTEGER NOT NULL REFERENCES liraa_estratos(id_estrato) ON DELETE CASCADE,
                id_ciclo INTEGER NOT NULL REFERENCES liraa_ciclos(id_ciclo) ON DELETE CASCADE,
                id_localidade INTEGER NOT NULL REFERENCES localidades(id_localidade),
                quarteirao TEXT NOT NULL,
                PRIMARY KEY(id_estrato,id_localidade,quarteirao),
                UNIQUE(id_ciclo,id_localidade,quarteirao));
            CREATE TABLE IF NOT EXISTS liraa_sorteios (
                id_sorteio INTEGER PRIMARY KEY AUTOINCREMENT,
                id_estrato INTEGER NOT NULL UNIQUE REFERENCES liraa_estratos(id_estrato) ON DELETE RESTRICT,
                criado_em TEXT NOT NULL, semente TEXT NOT NULL,
                n INTEGER NOT NULL, a INTEGER NOT NULL, q INTEGER NOT NULL,
                fracao REAL NOT NULL, intervalo REAL NOT NULL, inicio_casual REAL NOT NULL,
                universo_hash TEXT NOT NULL, universo_json TEXT NOT NULL,
                selecionados_json TEXT NOT NULL);
        """)


def _texto(value, campo, limite=200):
    result = str(value or "").strip()
    if len(result) > limite:
        raise LiraaError(f"{campo} excede {limite} caracteres.")
    return result


def _inteiro(value, campo, minimo=1, maximo=None):
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        raise LiraaError(f"Informe {campo} como número inteiro.") from None
    if result < minimo or (maximo is not None and result > maximo):
        raise LiraaError(f"{campo} fora do intervalo permitido.")
    return result


def _data(value, campo):
    result = _texto(value, campo, 10)
    if result:
        try:
            datetime.strptime(result, "%Y-%m-%d")
        except ValueError:
            raise LiraaError(f"{campo} deve estar no formato AAAA-MM-DD.") from None
    return result or None


def inventario(target, base_dir=None):
    """Quarteirões da camada ativa; RG é referência, não N oficial."""
    camada = rg_core.geojson_ativo(target, base_dir)
    conn = db_core.connect(target)
    try:
        rg_core.ensure_schema(conn, base_dir)
        localidades = [db_core.serialize_row(row) for row in conn.execute(
            "SELECT id_localidade, nome FROM localidades ORDER BY nome").fetchall()]
        nomes = {int(row["id_localidade"]): row["nome"] for row in localidades}
        ids_por_nome = {rg_core._norm(row["nome"]): int(row["id_localidade"])
                        for row in localidades}
        rows = conn.execute("""SELECT id_localidade, quarteirao,
            SUM(CASE WHEN COALESCE(tipo,'') NOT IN ('PE','REF') THEN 1 ELSE 0 END) AS registros,
            SUM(CASE WHEN COALESCE(tipo,'') NOT IN ('PE','REF')
                THEN CASE WHEN tipo='R' AND COALESCE(condominio,0)>0 THEN condominio ELSE 1 END
                ELSE 0 END) AS unidades,
            SUM(CASE WHEN tipo='PE' THEN 1 ELSE 0 END) AS pe
            FROM registro_geografico_imoveis GROUP BY id_localidade, quarteirao""").fetchall()
        rg = {(int(r["id_localidade"]), rg_core._quarteirao(r["quarteirao"])): r for r in rows}
        quarteiroes = {}
        for feature in camada.get("features", []):
            props = feature.get("properties") or {}
            raw_loc = props.get("Localidade")
            try:
                id_localidade = int(raw_loc)
            except (ValueError, TypeError):
                id_localidade = ids_por_nome.get(rg_core._norm(raw_loc))
            q = rg_core._quarteirao(props.get("id_quart", props.get("id_Q")))
            if id_localidade not in nomes or not q:
                continue
            chave = (id_localidade, q)
            if chave in quarteiroes:
                continue  # Vários trechos do mesmo quarteirão são uma unidade amostral.
            row = rg.get(chave)
            quarteiroes[chave] = {
                "id_localidade": id_localidade, "localidade": nomes[id_localidade],
                "quarteirao": q, "quarteirao_exibicao": rg_core._quarteirao_display(q),
                "registros_rg": int(row["registros"] or 0) if row else 0,
                "unidades_rg": int(row["unidades"] or 0) if row else 0,
                "pe_rg": int(row["pe"] or 0) if row else 0,
                "tem_rg": row is not None,
            }
        ordem = lambda r: (r["localidade"].casefold(),
                           0 if r["quarteirao"].isdigit() else 1,
                           int(r["quarteirao"]) if r["quarteirao"].isdigit() else r["quarteirao"])
        universo = sorted(quarteiroes.values(), key=ordem)
        por_localidade = []
        for loc in localidades:
            subset = [r for r in universo if r["id_localidade"] == loc["id_localidade"]]
            por_localidade.append({**loc, "quarteiroes": len(subset),
                "com_rg": sum(r["tem_rg"] for r in subset),
                "registros_rg_sem_pe": sum(r["registros_rg"] for r in subset),
                "unidades_rg_sem_pe": sum(r["unidades_rg"] for r in subset),
                "pe_rg": sum(r["pe_rg"] for r in subset)})
        return {"localidades": por_localidade, "quarteiroes": universo,
                "fonte": (camada.get("metadata") or {}).get("fonte", "camada estática")}
    finally:
        conn.close()


def painel(target, base_dir=None):
    territorio = inventario(target, base_dir)
    conn = db_core.connect(target)
    try:
        _schema(conn)
        ciclos = [db_core.serialize_row(r) for r in conn.execute(
            "SELECT * FROM liraa_ciclos ORDER BY ano DESC, id_ciclo DESC").fetchall()]
        estratos = [db_core.serialize_row(r) for r in conn.execute(
            "SELECT * FROM liraa_estratos ORDER BY id_ciclo, numero").fetchall()]
        vinculos = conn.execute("SELECT id_estrato, id_localidade FROM liraa_estrato_localidades").fetchall()
        blocos = conn.execute("SELECT id_estrato, id_localidade, quarteirao FROM liraa_estrato_quarteiroes").fetchall()
        sorteios = {r["id_estrato"]: db_core.serialize_row(r) for r in conn.execute(
            "SELECT * FROM liraa_sorteios").fetchall()}
        for s in sorteios.values():
            s["selecionados"] = json.loads(s.pop("selecionados_json"))
            s.pop("universo_json")  # Snapshot integral fica no banco; a UI recebe só o sorteio.
        por_estrato = {}
        for r in vinculos:
            por_estrato.setdefault(r["id_estrato"], []).append(r["id_localidade"])
        blocos_por_estrato = {}
        for r in blocos:
            blocos_por_estrato.setdefault(r["id_estrato"], []).append((int(r["id_localidade"]), r["quarteirao"]))
        por_localidade = {}
        for q in territorio["quarteiroes"]:
            por_localidade.setdefault(q["id_localidade"], set()).add(q["quarteirao"])
        ativos = {(q["id_localidade"], q["quarteirao"]) for q in territorio["quarteiroes"]}
        for e in estratos:
            chaves = set(blocos_por_estrato.get(e["id_estrato"], []))
            for loc in por_estrato.get(e["id_estrato"], []):
                chaves.update((loc, q) for q in por_localidade.get(loc, set()))
            e["quarteiroes"] = [f"{loc}:{q}" for loc, q in sorted(chaves)]
            e["ausentes"] = sum(chave not in ativos for chave in chaves)
            e["localidades"] = sorted({loc for loc, _ in chaves})
            e["legado_localidades"] = bool(por_estrato.get(e["id_estrato"]))
            e["sorteio"] = sorteios.get(e["id_estrato"])
        for c in ciclos:
            c["estratos"] = [e for e in estratos if e["id_ciclo"] == c["id_ciclo"]]
            usados = {chave for e in c["estratos"] for chave in e["quarteiroes"]}
            c["quarteiroes_sem_estrato"] = len(ativos) - len(ativos & {
                (int(chave.split(":", 1)[0]), chave.split(":", 1)[1]) for chave in usados})
        return {**territorio, "ciclos": ciclos}
    finally:
        conn.close()


def criar_ciclo(target, payload):
    ano = _inteiro(payload.get("ano"), "o ano", 2000, 2100)
    nome = _texto(payload.get("nome"), "O nome do ciclo", 100)
    if not nome:
        raise LiraaError("Informe o nome do ciclo.")
    inicio, fim = _data(payload.get("inicio"), "Data inicial"), _data(payload.get("fim"), "Data final")
    if inicio and fim and fim < inicio:
        raise LiraaError("Data final anterior à inicial.")
    obs = _texto(payload.get("observacoes"), "Observações", 1000)
    conn = db_core.connect(target)
    try:
        _schema(conn)
        with conn:
            try:
                return db_core.insert_and_get_id(conn, """INSERT INTO liraa_ciclos
                    (ano,nome,inicio,fim,observacoes,criado_em) VALUES (?,?,?,?,?,?)""",
                    (ano, nome, inicio, fim, obs, datetime.now().isoformat(timespec="seconds")), "id_ciclo")
            except Exception as exc:
                if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                    raise LiraaError("Já existe um ciclo com esse nome e ano.") from exc
                raise
    finally:
        conn.close()


def atualizar_ciclo(target, id_ciclo, payload):
    ano = _inteiro(payload.get("ano"), "o ano", 2000, 2100)
    nome = _texto(payload.get("nome"), "O nome do ciclo", 100)
    if not nome:
        raise LiraaError("Informe o nome do ciclo.")
    inicio, fim = _data(payload.get("inicio"), "Data inicial"), _data(payload.get("fim"), "Data final")
    if inicio and fim and fim < inicio:
        raise LiraaError("Data final anterior à inicial.")
    obs = _texto(payload.get("observacoes"), "Observações", 1000)
    conn = db_core.connect(target)
    try:
        _schema(conn)
        if conn.execute("""SELECT 1 FROM liraa_sorteios s JOIN liraa_estratos e ON e.id_estrato=s.id_estrato
            WHERE e.id_ciclo=? LIMIT 1""", (id_ciclo,)).fetchone():
            raise LiraaError("O ciclo tem sorteio registrado e está congelado.")
        try:
            with conn:
                cursor = conn.execute("""UPDATE liraa_ciclos SET ano=?,nome=?,inicio=?,fim=?,observacoes=?
                    WHERE id_ciclo=?""", (ano, nome, inicio, fim, obs, id_ciclo))
                if cursor.rowcount != 1:
                    raise LiraaError("Ciclo não encontrado.")
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise LiraaError("Já existe um ciclo com esse nome e ano.") from exc
            raise
        return id_ciclo
    finally:
        conn.close()


def excluir_ciclo_vazio(target, id_ciclo):
    conn = db_core.connect(target)
    try:
        _schema(conn)
        if conn.execute("SELECT 1 FROM liraa_estratos WHERE id_ciclo=? LIMIT 1", (id_ciclo,)).fetchone():
            raise LiraaError("Remova primeiro os estratos não sorteados deste ciclo.")
        with conn:
            cursor = conn.execute("DELETE FROM liraa_ciclos WHERE id_ciclo=?", (id_ciclo,))
            if cursor.rowcount != 1:
                raise LiraaError("Ciclo não encontrado.")
    finally:
        conn.close()


def salvar_estrato(target, id_ciclo, payload, id_estrato=None, base_dir=None):
    id_ciclo = _inteiro(id_ciclo, "o ciclo")
    numero = _inteiro(payload.get("numero"), "o número do estrato")
    tipo = _texto(payload.get("tipo"), "O tipo do estrato", 20)
    if tipo not in {"normal", "reduzido"}:
        raise LiraaError("Escolha estrato normal ou reduzido.")
    n_imoveis = _inteiro(payload.get("imoveis_confirmados"), "o total confirmado de imóveis")
    obs = _texto(payload.get("observacoes"), "Observações", 1000)
    territorio = inventario(target, base_dir)
    ativos = {(q["id_localidade"], q["quarteirao"]) for q in territorio["quarteiroes"]}
    selecionados = payload.get("quarteiroes")
    if selecionados is not None:
        if not isinstance(selecionados, list) or not selecionados:
            raise LiraaError("Selecione ao menos um quarteirão.")
        chaves = set()
        for valor in selecionados:
            partes = str(valor).split(":", 1)
            if len(partes) != 2:
                raise LiraaError("Quarteirão inválido na seleção.")
            chaves.add((_inteiro(partes[0], "a localidade"), rg_core._quarteirao(partes[1])))
        if len(chaves) != len(selecionados):
            raise LiraaError("Não repita quarteirões no mesmo estrato.")
    else:  # Compatibilidade com formulários antigos: localidade inteira.
        localidade_ids = payload.get("localidades")
        if not isinstance(localidade_ids, list) or not localidade_ids:
            raise LiraaError("Selecione ao menos uma localidade.")
        localidades = {_inteiro(x, "a localidade") for x in localidade_ids}
        if len(localidades) != len(localidade_ids):
            raise LiraaError("Não repita localidades no mesmo estrato.")
        chaves = {chave for chave in ativos if chave[0] in localidades}
        if not chaves or {loc for loc, _ in chaves} != localidades:
            raise LiraaError("Toda localidade do estrato deve existir na camada de quarteirões.")
    if not chaves or not chaves <= ativos:
        raise LiraaError("A seleção contém quarteirão ausente da camada ativa; revise o mapa.")
    conn = db_core.connect(target)
    try:
        _schema(conn)
        if not conn.execute("SELECT 1 FROM liraa_ciclos WHERE id_ciclo=?", (id_ciclo,)).fetchone():
            raise LiraaError("Ciclo não encontrado.")
        if id_estrato is not None:
            id_estrato = _inteiro(id_estrato, "o estrato")
            atual = conn.execute("SELECT id_ciclo FROM liraa_estratos WHERE id_estrato=?", (id_estrato,)).fetchone()
            if not atual or atual["id_ciclo"] != id_ciclo:
                raise LiraaError("Estrato não encontrado neste ciclo.")
            if conn.execute("SELECT 1 FROM liraa_sorteios WHERE id_estrato=?", (id_estrato,)).fetchone():
                raise LiraaError("Estrato já sorteado: o plano foi congelado para auditoria.")
        agora = datetime.now().isoformat(timespec="seconds")
        try:
            with conn:
                if getattr(conn, "backend", "sqlite") == "postgresql":
                    conn.execute("SELECT id_ciclo FROM liraa_ciclos WHERE id_ciclo=? FOR UPDATE", (id_ciclo,)).fetchone()
                ocupados = {(int(r["id_localidade"]), r["quarteirao"]) for r in conn.execute(
                    "SELECT id_localidade,quarteirao FROM liraa_estrato_quarteiroes WHERE id_ciclo=? AND id_estrato<>?",
                    (id_ciclo, id_estrato or 0)).fetchall()}
                legados = conn.execute("""SELECT l.id_localidade FROM liraa_estrato_localidades l
                    WHERE l.id_ciclo=? AND l.id_estrato<>?""", (id_ciclo, id_estrato or 0)).fetchall()
                ocupados.update(chave for chave in ativos if chave[0] in {int(r["id_localidade"]) for r in legados})
                if ocupados & chaves:
                    raise LiraaError("Um ou mais quarteirões já pertencem a outro estrato deste ciclo.")
                if id_estrato is None:
                    id_estrato = db_core.insert_and_get_id(conn, """INSERT INTO liraa_estratos
                        (id_ciclo,numero,tipo,imoveis_confirmados,observacoes,criado_em,atualizado_em)
                        VALUES (?,?,?,?,?,?,?)""",
                        (id_ciclo, numero, tipo, n_imoveis, obs, agora, agora), "id_estrato")
                else:
                    conn.execute("""UPDATE liraa_estratos SET numero=?,tipo=?,imoveis_confirmados=?,
                        observacoes=?,atualizado_em=? WHERE id_estrato=?""",
                        (numero, tipo, n_imoveis, obs, agora, id_estrato))
                    conn.execute("DELETE FROM liraa_estrato_localidades WHERE id_estrato=?", (id_estrato,))
                    conn.execute("DELETE FROM liraa_estrato_quarteiroes WHERE id_estrato=?", (id_estrato,))
                conn.executemany("""INSERT INTO liraa_estrato_quarteiroes
                    (id_estrato,id_ciclo,id_localidade,quarteirao) VALUES (?,?,?,?)""",
                    [(id_estrato, id_ciclo, loc, q) for loc, q in sorted(chaves)])
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise LiraaError("Número do estrato ou quarteirão já usado neste ciclo.") from exc
            raise
        return id_estrato
    finally:
        conn.close()


def excluir_estrato(target, id_estrato):
    conn = db_core.connect(target)
    try:
        _schema(conn)
        if conn.execute("SELECT 1 FROM liraa_sorteios WHERE id_estrato=?", (id_estrato,)).fetchone():
            raise LiraaError("Não é possível excluir um estrato já sorteado.")
        with conn:
            cursor = conn.execute("DELETE FROM liraa_estratos WHERE id_estrato=?", (id_estrato,))
            if cursor.rowcount != 1:
                raise LiraaError("Estrato não encontrado.")
    finally:
        conn.close()


def _calcular_sorteio(n_imoveis, universo, tipo, seed):
    a = len(universo)
    if a == 0:
        raise LiraaError("Estrato sem quarteirões na camada ativa.")
    minimo, maximo = (8100, 12000) if tipo == "normal" else (2000, 8100)
    if not minimo <= n_imoveis <= maximo:
        raise LiraaError(f"Estrato {tipo}: confirme N entre {minimo:,} e {maximo:,} imóveis.".replace(",", "."))
    n = (450 * n_imoveis + (n_imoveis + 450) - 1) // (n_imoveis + 450)
    denominador = 5 if tipo == "normal" else 2
    q = min(a, (n * a * denominador + n_imoveis - 1) // n_imoveis)
    intervalo = a / q
    sorteado = random.Random(seed).random()
    inicio = max(sorteado, 1 / (2 ** 53)) * intervalo
    selecionados = []
    for i in range(q):
        indice = math.ceil(inicio + i * intervalo) - 1
        if indice < 0 or indice >= a:
            raise LiraaError("O sorteio gerou índice fora do universo; revise o plano.")
        selecionados.append({**universo[indice], "ordem_universo": indice + 1})
    if len({(r["id_localidade"], r["quarteirao"]) for r in selecionados}) != q:
        raise LiraaError("O sorteio gerou quarteirões repetidos; revise o plano.")
    return {"n": n, "a": a, "q": q, "fracao": 1 / denominador,
            "intervalo": intervalo, "inicio_casual": inicio, "selecionados": selecionados}


def sortear(target, id_estrato, base_dir=None, seed=None):
    territorio = inventario(target, base_dir)
    conn = db_core.connect(target)
    try:
        _schema(conn)
        estrato = conn.execute("SELECT * FROM liraa_estratos WHERE id_estrato=?", (id_estrato,)).fetchone()
        if not estrato:
            raise LiraaError("Estrato não encontrado.")
        if conn.execute("SELECT 1 FROM liraa_sorteios WHERE id_estrato=?", (id_estrato,)).fetchone():
            raise LiraaError("Este estrato já foi sorteado; o resultado está preservado.")
        ids = {r["id_localidade"] for r in conn.execute(
            "SELECT id_localidade FROM liraa_estrato_localidades WHERE id_estrato=?", (id_estrato,)).fetchall()}
        chaves = {(int(r["id_localidade"]), r["quarteirao"]) for r in conn.execute(
            "SELECT id_localidade,quarteirao FROM liraa_estrato_quarteiroes WHERE id_estrato=?",
            (id_estrato,)).fetchall()}
        universo = [r for r in territorio["quarteiroes"]
                    if (r["id_localidade"], r["quarteirao"]) in chaves or r["id_localidade"] in ids]
        if not universo or {r["id_localidade"] for r in universo if r["id_localidade"] in ids} != ids or \
                len(chaves - {(r["id_localidade"], r["quarteirao"]) for r in universo}):
            raise LiraaError("O estrato possui quarteirões ausentes da camada ativa; revise antes do sorteio.")
        seed = secrets.randbits(64) if seed is None else int(seed)
        calculo = _calcular_sorteio(estrato["imoveis_confirmados"], universo, estrato["tipo"], seed)
        universo_json = json.dumps(universo, ensure_ascii=False, separators=(",", ":"))
        selecionados_json = json.dumps(calculo["selecionados"], ensure_ascii=False, separators=(",", ":"))
        try:
            with conn:
                id_sorteio = db_core.insert_and_get_id(conn, """INSERT INTO liraa_sorteios
                    (id_estrato,criado_em,semente,n,a,q,fracao,intervalo,inicio_casual,
                     universo_hash,universo_json,selecionados_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (id_estrato, datetime.now().isoformat(timespec="seconds"), str(seed),
                     calculo["n"], calculo["a"], calculo["q"], calculo["fracao"],
                     calculo["intervalo"], calculo["inicio_casual"],
                     hashlib.sha256(universo_json.encode("utf-8")).hexdigest(),
                     universo_json, selecionados_json), "id_sorteio")
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise LiraaError("Este estrato já foi sorteado por outra operação.") from exc
            raise
        return {"id_sorteio": id_sorteio, **calculo}
    finally:
        conn.close()
