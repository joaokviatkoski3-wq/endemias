import hashlib
import re
from datetime import datetime

import pandas as pd


VISITAS_TABLE = "esporotricose_visitas"
ANIMAIS_TABLE = "esporotricose_animais"
VISITA_AGENTES_TABLE = "esporotricose_visita_agentes"
NORMAL_IMPORT_MARKER = "esporotricose_kobo_v2"
LEGACY_IMPORT_MARKER = "esporotricose_historico_legado"
MOTIVO_ATENCAO_SQL = """CASE
    WHEN LOWER(COALESCE(a.feridas,'')) = 'sim' THEN 'Ferida informada'
    WHEN a.feridas IS NULL OR LOWER(COALESCE(a.feridas,'')) = 'desconhecido' THEN 'Feridas sem confirma\u00e7\u00e3o'
    WHEN a.vacinado IS NULL OR LOWER(COALESCE(a.vacinado,'')) = 'desconhecido' THEN 'Vacina sem confirma\u00e7\u00e3o'
    WHEN a.castrado IS NULL OR LOWER(COALESCE(a.castrado,'')) = 'desconhecido' THEN 'Castra\u00e7\u00e3o sem confirma\u00e7\u00e3o'
    WHEN a.ambiente IS NULL OR TRIM(COALESCE(a.ambiente,'')) = '' THEN 'Ambiente n\u00e3o informado'
    ELSE ''
END"""

AGENTE_COMPOSTO = {
    "ana beatriz": "Ana Beatriz",
}

LOCALIDADES_PADRAO = {
    "sao venancio": "Sao Venancio",
    "são venâncio": "São Venâncio",
    "sao venâncio": "São Venâncio",
    "são venancio": "São Venâncio",
    "tangua": "Tanguá",
    "tanguá": "Tanguá",
}


class ValidationError(Exception):
    pass


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS esporotricose_visitas (
            id_visita       TEXT PRIMARY KEY,
            kobo_uuid       TEXT NOT NULL UNIQUE,
            kobo_id         INTEGER,
            data            DATE NOT NULL,
            hora_inicio     TIME,
            hora_fim        TIME,
            inicio_registro TEXT,
            fim_registro    TEXT,
            agentes_texto   TEXT,
            localidade      TEXT,
            id_localidade   INTEGER REFERENCES localidades(id_localidade),
            quarteirao      INTEGER,
            tipo_imovel     TEXT,
            logradouro      TEXT,
            numero          TEXT,
            morador         TEXT,
            visita          TEXT,
            telefone        TEXT,
            observacoes     TEXT,
            deseja_cadastrar_animal TEXT,
            origem_estrutura TEXT NOT NULL DEFAULT 'nova',
            arquivo_origem  TEXT,
            submission_time TEXT,
            processado_em   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS esporotricose_visita_agentes (
            id_visita TEXT NOT NULL REFERENCES esporotricose_visitas(id_visita) ON DELETE CASCADE,
            id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
            PRIMARY KEY (id_visita, id_agente)
        );

        CREATE TABLE IF NOT EXISTS esporotricose_animais (
            id_animal       TEXT PRIMARY KEY,
            id_visita       TEXT NOT NULL REFERENCES esporotricose_visitas(id_visita) ON DELETE CASCADE,
            kobo_uuid       TEXT,
            especie         TEXT,
            outro_animal    TEXT,
            nome            TEXT,
            raca            TEXT,
            sexo            TEXT,
            ambiente        TEXT,
            vacinado        TEXT,
            castrado        TEXT,
            feridas         TEXT,
            regiao_ferida   TEXT,
            atendimento_veterinario TEXT,
            data_atendimento DATE,
            evolucao_caso   TEXT,
            arquivo_origem  TEXT,
            processado_em   TEXT NOT NULL,
            UNIQUE(id_visita, kobo_uuid)
        );

        CREATE INDEX IF NOT EXISTS idx_esporo_visitas_data ON esporotricose_visitas(data);
        CREATE INDEX IF NOT EXISTS idx_esporo_visitas_localidade ON esporotricose_visitas(id_localidade);
        CREATE INDEX IF NOT EXISTS idx_esporo_visitas_quarteirao ON esporotricose_visitas(quarteirao);
        CREATE INDEX IF NOT EXISTS idx_esporo_visitas_kobo_uuid ON esporotricose_visitas(kobo_uuid);
        CREATE INDEX IF NOT EXISTS idx_esporo_animais_visita ON esporotricose_animais(id_visita);
        CREATE INDEX IF NOT EXISTS idx_esporo_animais_especie ON esporotricose_animais(especie);
        """
    )


def is_new_format(path):
    df = pd.read_excel(path, sheet_name=0, nrows=1, engine="openpyxl")
    columns = set(df.columns)
    required = {
        "start",
        "end",
        "Dados do morador/Hora Inicio",
        "Hora Final",
        "Dados do morador/Agentes",
        "meta/rootUuid",
    }
    return required.issubset(columns)


def processar_arquivo(path, conn, logger, agora_iso, dry_run=False, aceitar_legado=False):
    estrutura = "nova" if is_new_format(path) else "legada"
    if estrutura != "nova" and not aceitar_legado:
        raise ValidationError("Planilha de esporotricose em formato legado. Use a importacao historica unica.")

    visitas, animais = parse_workbook(path, estrutura)
    logger.log(f"  Estrutura: {estrutura} | Visitas: {len(visitas)} | Animais: {len(animais)}")

    inseridas = animais_inseridos = vinculos = duplicadas = 0
    for visita in visitas:
        visita["arquivo_origem"] = _basename(path)
        visita["origem_estrutura"] = estrutura
        nova = _inserir_visita(conn, visita, agora_iso)
        if nova:
            inseridas += 1
        else:
            duplicadas += 1
        vinculos += _inserir_agentes(conn, visita["id_visita"], visita.get("agentes_texto"))

    for animal in animais:
        animal["arquivo_origem"] = _basename(path)
        if _inserir_animal(conn, animal, agora_iso):
            animais_inseridos += 1

    logger.log(
        f"  Visitas novas: {inseridas} | Duplicadas: {duplicadas} | "
        f"Animais novos: {animais_inseridos} | Vinculos agentes: {vinculos}",
        "ok",
    )
    return {
        "ok": True,
        "tipo": "ESPOROTRICOSE",
        "visitas_novas": inseridas,
        "animais_novos": animais_inseridos,
        "coletas_novas": animais_inseridos,
        "resultados_novos": 0,
        "duplicadas": duplicadas,
    }


def parse_workbook(path, estrutura=None):
    xls = pd.ExcelFile(path, engine="openpyxl")
    main = pd.read_excel(path, sheet_name=xls.sheet_names[0], engine="openpyxl").dropna(how="all")
    animals_df = pd.read_excel(path, sheet_name=xls.sheet_names[1], engine="openpyxl").dropna(how="all")
    estrutura = estrutura or ("nova" if is_new_format(path) else "legada")

    visitas = []
    uuid_to_id = {}
    index_to_id = {}
    for _, row in main.iterrows():
        uuid = _uuid(row.get("_uuid"))
        if not uuid:
            continue
        data = _date(row.get("Dados do morador/Data"))
        if not data:
            continue
        id_visita = _hash("esporotricose:visita", uuid)
        visita = {
            "id_visita": id_visita,
            "kobo_uuid": uuid,
            "kobo_id": _int(row.get("_id")),
            "data": data,
            "hora_inicio": _time(row.get("Dados do morador/Hora Inicio" if estrutura == "nova" else "Dados do morador/Hora")),
            "hora_fim": _time(row.get("Hora Final")) if estrutura == "nova" else None,
            "inicio_registro": _datetime(row.get("start")) if estrutura == "nova" else None,
            "fim_registro": _datetime(row.get("end")) if estrutura == "nova" else None,
            "agentes_texto": _text(row.get("Dados do morador/Agentes" if estrutura == "nova" else "Dados do morador/Nome do(s) agente(s)")),
            "localidade": _localidade(row.get("Dados do morador/Localidade")),
            "quarteirao": _int(row.get("Dados do morador/Quarteirão")),
            "tipo_imovel": _text(row.get("Dados do morador/Tipo do imóvel")),
            "logradouro": _text(row.get("Dados do morador/Logradouro")),
            "numero": _text(row.get("Dados do morador/Número")),
            "morador": _text(row.get("Dados do morador/Morador")),
            "visita": _text(row.get("Dados do morador/Visita:")),
            "telefone": _text(row.get("Dados do morador/Telefone")),
            "observacoes": _text(row.get("Dados do morador/Observações")),
            "deseja_cadastrar_animal": _text(row.get("Deseja cadastrar um animal?")),
            "submission_time": _datetime(row.get("_submission_time")),
        }
        visitas.append(visita)
        uuid_to_id[uuid] = id_visita
        idx = _text(row.get("_index"))
        if idx:
            index_to_id[idx] = id_visita

    animais = []
    for _, row in animals_df.iterrows():
        sub_uuid = _uuid(row.get("_submission__uuid"))
        parent_idx = _text(row.get("_parent_index"))
        id_visita = uuid_to_id.get(sub_uuid) or index_to_id.get(parent_idx)
        if not id_visita:
            continue
        animal_uuid = f"{sub_uuid or parent_idx}:{_text(row.get('_index')) or len(animais)}"
        animais.append({
            "id_animal": _hash("esporotricose:animal", animal_uuid),
            "id_visita": id_visita,
            "kobo_uuid": animal_uuid,
            "especie": _text(row.get("Dados do animal/Escolha o animal a ser cadastrado:")),
            "outro_animal": _text(row.get("Dados do animal/Qual animal?")),
            "nome": _text(row.get("Dados do animal/Nome do animal:")),
            "raca": _text(row.get("Dados do animal/Raça:")),
            "sexo": _text(row.get("Dados do animal/Sexo:")),
            "ambiente": _text(row.get("Dados do animal/Classificação quanto ao ambiente em que o animal vive:")),
            "vacinado": _text(row.get("Dados do animal/Vacinado?")),
            "castrado": _text(row.get("Dados do animal/Castrado?")),
            "feridas": _text(row.get("Dados do animal/Apresenta feridas pelo corpo?")),
            "regiao_ferida": _text(row.get("Dados do animal/Região:")),
            "atendimento_veterinario": _text(row.get("Dados do animal/Já passou por atendimento veterinário?")),
            "data_atendimento": _date(row.get("Dados do animal/Data do atendimento:")),
            "evolucao_caso": _text(row.get("Dados do animal/Evolução do caso:")),
        })
    return visitas, animais


def importar_historico(paths, db_path, logger, dry_run=False):
    conn = __import__("sqlite3").connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    ensure_schema(conn)
    agora_iso = datetime.now().isoformat(timespec="seconds")
    total = {"visitas": 0, "animais": 0}
    try:
        conn.execute("BEGIN")
        for path in paths:
            result = processar_arquivo(path, conn, logger, agora_iso, dry_run=dry_run, aceitar_legado=True)
            total["visitas"] += result.get("visitas_novas", 0)
            total["animais"] += result.get("animais_novos", 0)
        if dry_run:
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return total


def resumo(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros)
    try:
        totais = dict(conn.execute(
            f"""SELECT
                COUNT(*) AS visitas,
                COUNT(DISTINCT data) AS dias,
                COUNT(DISTINCT localidade) AS localidades,
                SUM(CASE WHEN LOWER(COALESCE(visita,''))='normal' THEN 1 ELSE 0 END) AS normais,
                SUM(CASE WHEN LOWER(COALESCE(visita,''))='fechado' THEN 1 ELSE 0 END) AS fechadas,
                SUM(CASE WHEN LOWER(COALESCE(visita,''))='recusa' THEN 1 ELSE 0 END) AS recusas,
                SUM(CASE WHEN LOWER(COALESCE(visita,''))='recuperado' THEN 1 ELSE 0 END) AS recuperadas
              FROM esporotricose_visitas v {where}""",
            params,
        ).fetchone())
        animais = dict(conn.execute(
            f"""SELECT
                COUNT(a.id_animal) AS total,
                SUM(CASE WHEN LOWER(COALESCE(a.especie,'')) LIKE 'c%' THEN 1 ELSE 0 END) AS caes,
                SUM(CASE WHEN LOWER(COALESCE(a.especie,'')) LIKE 'gato%' THEN 1 ELSE 0 END) AS gatos,
                SUM(CASE WHEN LOWER(COALESCE(a.feridas,''))='sim' THEN 1 ELSE 0 END) AS com_feridas
              FROM esporotricose_visitas v
              LEFT JOIN esporotricose_animais a ON a.id_visita=v.id_visita
              {where}""",
            params,
        ).fetchone())
        por_localidade = [dict(r) for r in conn.execute(
            f"""SELECT COALESCE(v.localidade,'-') AS localidade, COUNT(*) AS total
                FROM esporotricose_visitas v {where}
                GROUP BY COALESCE(v.localidade,'-') ORDER BY total DESC, localidade LIMIT 12""",
            params,
        )]
        recentes = [dict(r) for r in conn.execute(
            f"""SELECT v.id_visita, v.data, v.localidade, v.quarteirao, v.logradouro, v.numero,
                       v.morador, v.telefone, v.visita, COUNT(a.id_animal) AS animais
                FROM esporotricose_visitas v
                LEFT JOIN esporotricose_animais a ON a.id_visita=v.id_visita
                {where}
                GROUP BY v.id_visita
                ORDER BY v.data DESC, v.hora_inicio DESC
                LIMIT 100""",
            params,
        )]
    finally:
        conn.close()
    return {
        "totais": {k: (v or 0) for k, v in totais.items()},
        "animais": {k: (v or 0) for k, v in animais.items()},
        "por_localidade": por_localidade,
        "recentes": recentes,
    }


def listar_visitas(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where_visitas(filtros)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM esporotricose_visitas v {where}",
            params,
        ).fetchone()[0]
        registros = [dict(r) for r in conn.execute(
            f"""SELECT
                    v.id_visita, v.data, v.hora_inicio, v.localidade, v.quarteirao,
                    v.logradouro, v.numero, v.morador, v.telefone, v.visita,
                    v.tipo_imovel, v.observacoes, COUNT(a.id_animal) AS animais,
                    COALESCE(GROUP_CONCAT(DISTINCT ag.nome), '') AS agentes
                FROM esporotricose_visitas v
                LEFT JOIN esporotricose_animais a ON a.id_visita = v.id_visita
                LEFT JOIN esporotricose_visita_agentes va ON va.id_visita = v.id_visita
                LEFT JOIN agentes ag ON ag.id_agente = va.id_agente
                {where}
                GROUP BY v.id_visita
                ORDER BY v.data DESC, v.hora_inicio DESC, v.localidade, v.quarteirao
                LIMIT 500""",
            params,
        )]
    finally:
        conn.close()
    return {"total": total or 0, "registros": registros}


def listar_animais(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where_animais(filtros)
    try:
        total = conn.execute(
            f"""SELECT COUNT(*)
                FROM esporotricose_animais a
                JOIN esporotricose_visitas v ON v.id_visita = a.id_visita
                {where}""",
            params,
        ).fetchone()[0]
        registros = [dict(r) for r in conn.execute(
            f"""SELECT
                    a.id_animal, a.especie, a.outro_animal, a.nome, a.raca, a.sexo,
                    a.ambiente, a.vacinado, a.castrado, a.feridas, a.regiao_ferida,
                    a.atendimento_veterinario, a.data_atendimento, a.evolucao_caso,
                    {MOTIVO_ATENCAO_SQL} AS motivo_atencao,
                    v.data, v.localidade, v.quarteirao, v.logradouro, v.numero,
                    v.morador, v.telefone, v.visita
                FROM esporotricose_animais a
                JOIN esporotricose_visitas v ON v.id_visita = a.id_visita
                {where}
                ORDER BY
                    CASE WHEN LOWER(COALESCE(a.feridas,'')) = 'sim' THEN 0 ELSE 1 END,
                    v.data DESC,
                    v.localidade,
                    a.especie,
                    a.nome
                LIMIT 500""",
            params,
        )]
    finally:
        conn.close()
    return {"total": total or 0, "registros": registros}


def resumo_localidades(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros)
    try:
        registros = [dict(r) for r in conn.execute(
            f"""SELECT
                    COALESCE(v.localidade, '-') AS localidade,
                    COUNT(DISTINCT v.id_visita) AS visitas,
                    COUNT(a.id_animal) AS animais,
                    SUM(CASE WHEN LOWER(COALESCE(a.especie,'')) LIKE 'c%' THEN 1 ELSE 0 END) AS caes,
                    SUM(CASE WHEN LOWER(COALESCE(a.especie,'')) LIKE 'gato%' THEN 1 ELSE 0 END) AS gatos,
                    SUM(CASE WHEN LOWER(COALESCE(a.feridas,'')) = 'sim' THEN 1 ELSE 0 END) AS com_feridas,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,'')) = 'fechado' THEN v.id_visita END) AS fechadas,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(v.visita,'')) = 'recusa' THEN v.id_visita END) AS recusas
                FROM esporotricose_visitas v
                LEFT JOIN esporotricose_animais a ON a.id_visita = v.id_visita
                {where}
                GROUP BY COALESCE(v.localidade, '-')
                ORDER BY visitas DESC, localidade""",
            params,
        )]
    finally:
        conn.close()
    return {"registros": [{k: (v or 0) if k != "localidade" else v for k, v in row.items()} for row in registros]}


def dashboard(db_path, filtros=None):
    filtros = filtros or {}
    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    ensure_schema(conn)
    where, params = _where(filtros)
    try:
        evolucao = _rows(conn, f"""
            SELECT substr(v.data, 1, 7) AS mes, COUNT(*) AS visitas
            FROM esporotricose_visitas v {where}
            GROUP BY substr(v.data, 1, 7)
            ORDER BY mes
        """, params)
        status = _rows(conn, f"""
            SELECT COALESCE(NULLIF(v.visita, ''), 'Sem informação') AS nome, COUNT(*) AS total
            FROM esporotricose_visitas v {where}
            GROUP BY COALESCE(NULLIF(v.visita, ''), 'Sem informação')
            ORDER BY total DESC, nome
        """, params)
        especies = _rows(conn, f"""
            SELECT COALESCE(NULLIF(a.especie, ''), 'Sem informação') AS nome, COUNT(*) AS total
            FROM esporotricose_visitas v
            JOIN esporotricose_animais a ON a.id_visita = v.id_visita
            {where}
            GROUP BY COALESCE(NULLIF(a.especie, ''), 'Sem informação')
            ORDER BY total DESC, nome
        """, params)
        ambiente = _rows(conn, f"""
            SELECT COALESCE(NULLIF(a.ambiente, ''), 'Sem informação') AS nome, COUNT(*) AS total
            FROM esporotricose_visitas v
            JOIN esporotricose_animais a ON a.id_visita = v.id_visita
            {where}
            GROUP BY COALESCE(NULLIF(a.ambiente, ''), 'Sem informação')
            ORDER BY total DESC, nome
        """, params)
        localidades = _rows(conn, f"""
            SELECT COALESCE(v.localidade, '-') AS nome, COUNT(DISTINCT v.id_visita) AS visitas, COUNT(a.id_animal) AS animais
            FROM esporotricose_visitas v
            LEFT JOIN esporotricose_animais a ON a.id_visita = v.id_visita
            {where}
            GROUP BY COALESCE(v.localidade, '-')
            ORDER BY visitas DESC, nome
            LIMIT 12
        """, params)
        saude = _rows(conn, f"""
            SELECT 'Feridas' AS grupo,
                   SUM(CASE WHEN LOWER(COALESCE(a.feridas,'')) = 'sim' THEN 1 ELSE 0 END) AS sim,
                   SUM(CASE WHEN LOWER(COALESCE(a.feridas,'')) = 'não' THEN 1 ELSE 0 END) AS nao,
                   SUM(CASE WHEN a.feridas IS NULL OR LOWER(COALESCE(a.feridas,'')) = 'desconhecido' THEN 1 ELSE 0 END) AS desconhecido
            FROM esporotricose_visitas v JOIN esporotricose_animais a ON a.id_visita = v.id_visita {where}
            UNION ALL
            SELECT 'Vacinados' AS grupo,
                   SUM(CASE WHEN LOWER(COALESCE(a.vacinado,'')) = 'sim' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN LOWER(COALESCE(a.vacinado,'')) = 'não' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN a.vacinado IS NULL OR LOWER(COALESCE(a.vacinado,'')) = 'desconhecido' THEN 1 ELSE 0 END)
            FROM esporotricose_visitas v JOIN esporotricose_animais a ON a.id_visita = v.id_visita {where}
            UNION ALL
            SELECT 'Castrados' AS grupo,
                   SUM(CASE WHEN LOWER(COALESCE(a.castrado,'')) = 'sim' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN LOWER(COALESCE(a.castrado,'')) = 'não' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN a.castrado IS NULL OR LOWER(COALESCE(a.castrado,'')) = 'desconhecido' THEN 1 ELSE 0 END)
            FROM esporotricose_visitas v JOIN esporotricose_animais a ON a.id_visita = v.id_visita {where}
        """, params * 3)
    finally:
        conn.close()
    return {
        "evolucao": evolucao,
        "status": status,
        "especies": especies,
        "ambiente": ambiente,
        "localidades": localidades,
        "saude": saude,
    }


def _rows(conn, sql, params):
    return [{k: (v or 0) if k not in {"nome", "mes", "grupo"} else v for k, v in dict(r).items()} for r in conn.execute(sql, params)]


def _where(filtros):
    clauses = ["1=1"]
    params = []
    if filtros.get("d_ini"):
        clauses.append("v.data >= ?")
        params.append(filtros["d_ini"])
    if filtros.get("d_fim"):
        clauses.append("v.data <= ?")
        params.append(filtros["d_fim"])
    localidade = filtros.get("localidade")
    if localidade:
        if isinstance(localidade, (list, tuple)):
            valores = [v for v in localidade if v]
            if valores:
                clauses.append(f"v.localidade IN ({','.join('?' * len(valores))})")
                params.extend(valores)
        else:
            clauses.append("v.localidade = ?")
            params.append(localidade)
    if filtros.get("visita"):
        clauses.append("v.visita = ?")
        params.append(filtros["visita"])
    agente = filtros.get("agente")
    if agente:
        if isinstance(agente, (list, tuple)):
            valores = [v for v in agente if v]
            if valores:
                clauses.append(
                    f"""EXISTS (
                        SELECT 1 FROM esporotricose_visita_agentes va
                        JOIN agentes ag ON ag.id_agente = va.id_agente
                        WHERE va.id_visita = v.id_visita AND ag.nome IN ({','.join('?' * len(valores))})
                    )"""
                )
                params.extend(valores)
        else:
            clauses.append(
                """EXISTS (
                    SELECT 1 FROM esporotricose_visita_agentes va
                    JOIN agentes ag ON ag.id_agente = va.id_agente
                    WHERE va.id_visita = v.id_visita AND ag.nome = ?
                )"""
            )
            params.append(agente)
    return "WHERE " + " AND ".join(clauses), params


def _where_visitas(filtros):
    where, params = _where(filtros)
    clauses = [where[6:]]
    busca = _text(filtros.get("busca"))
    if busca:
        like = f"%{busca.lower()}%"
        clauses.append(
            """(
                LOWER(COALESCE(v.localidade,'')) LIKE ?
                OR LOWER(COALESCE(v.logradouro,'')) LIKE ?
                OR LOWER(COALESCE(v.numero,'')) LIKE ?
                OR LOWER(COALESCE(v.morador,'')) LIKE ?
                OR LOWER(COALESCE(v.telefone,'')) LIKE ?
                OR LOWER(COALESCE(v.data,'')) LIKE ?
                OR LOWER(COALESCE(v.quarteirao,'')) LIKE ?
                OR LOWER(COALESCE(v.visita,'')) LIKE ?
            )"""
        )
        params.extend([like] * 8)
    return "WHERE " + " AND ".join(clauses), params


def _where_animais(filtros):
    where, params = _where(filtros)
    clauses = [where[6:]]
    busca = _text(filtros.get("busca"))
    if busca:
        like = f"%{busca.lower()}%"
        clauses.append(
            """(
                LOWER(COALESCE(v.localidade,'')) LIKE ?
                OR LOWER(COALESCE(v.logradouro,'')) LIKE ?
                OR LOWER(COALESCE(v.numero,'')) LIKE ?
                OR LOWER(COALESCE(v.morador,'')) LIKE ?
                OR LOWER(COALESCE(v.telefone,'')) LIKE ?
                OR LOWER(COALESCE(v.data,'')) LIKE ?
                OR LOWER(COALESCE(a.nome,'')) LIKE ?
                OR LOWER(COALESCE(a.raca,'')) LIKE ?
                OR LOWER(COALESCE(a.especie,'')) LIKE ?
            )"""
        )
        params.extend([like] * 9)
    if filtros.get("especie"):
        clauses.append("a.especie = ?")
        params.append(filtros["especie"])
    if filtros.get("feridas"):
        clauses.append("a.feridas = ?")
        params.append(filtros["feridas"])
    if filtros.get("vacinado"):
        clauses.append("a.vacinado = ?")
        params.append(filtros["vacinado"])
    if filtros.get("castrado"):
        clauses.append("a.castrado = ?")
        params.append(filtros["castrado"])
    if filtros.get("ambiente"):
        clauses.append("a.ambiente = ?")
        params.append(filtros["ambiente"])
    if filtros.get("motivo_atencao"):
        clauses.append(f"({MOTIVO_ATENCAO_SQL}) = ?")
        params.append(filtros["motivo_atencao"])
    if filtros.get("prioritarios"):
        clauses.append(f"({MOTIVO_ATENCAO_SQL}) <> ''")
    return "WHERE " + " AND ".join(clauses), params


def _inserir_visita(conn, visita, agora_iso):
    cur = conn.cursor()
    id_localidade = _obter_ou_criar_localidade(cur, visita.get("localidade"))
    cur.execute(
        """INSERT OR IGNORE INTO esporotricose_visitas (
            id_visita, kobo_uuid, kobo_id, data, hora_inicio, hora_fim, inicio_registro,
            fim_registro, agentes_texto, localidade, id_localidade, quarteirao, tipo_imovel,
            logradouro, numero, morador, visita, telefone, observacoes, deseja_cadastrar_animal,
            origem_estrutura, arquivo_origem, submission_time, processado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            visita["id_visita"], visita["kobo_uuid"], visita.get("kobo_id"), visita["data"],
            visita.get("hora_inicio"), visita.get("hora_fim"), visita.get("inicio_registro"),
            visita.get("fim_registro"), visita.get("agentes_texto"), visita.get("localidade"),
            id_localidade, visita.get("quarteirao"), visita.get("tipo_imovel"), visita.get("logradouro"),
            visita.get("numero"), visita.get("morador"), visita.get("visita"), visita.get("telefone"),
            visita.get("observacoes"), visita.get("deseja_cadastrar_animal"), visita.get("origem_estrutura"),
            visita.get("arquivo_origem"), visita.get("submission_time"), agora_iso,
        ),
    )
    return cur.rowcount > 0


def _inserir_agentes(conn, id_visita, agentes_texto):
    nomes = _split_agentes(conn, agentes_texto)
    count = 0
    cur = conn.cursor()
    for nome in nomes:
        id_agente = _obter_ou_criar_agente(cur, nome)
        cur.execute(
            "INSERT OR IGNORE INTO esporotricose_visita_agentes(id_visita, id_agente) VALUES (?,?)",
            (id_visita, id_agente),
        )
        count += cur.rowcount
    return count


def _inserir_animal(conn, animal, agora_iso):
    cur = conn.cursor()
    cur.execute(
        """INSERT OR IGNORE INTO esporotricose_animais (
            id_animal, id_visita, kobo_uuid, especie, outro_animal, nome, raca, sexo,
            ambiente, vacinado, castrado, feridas, regiao_ferida, atendimento_veterinario,
            data_atendimento, evolucao_caso, arquivo_origem, processado_em
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            animal["id_animal"], animal["id_visita"], animal.get("kobo_uuid"),
            animal.get("especie"), animal.get("outro_animal"), animal.get("nome"),
            animal.get("raca"), animal.get("sexo"), animal.get("ambiente"), animal.get("vacinado"),
            animal.get("castrado"), animal.get("feridas"), animal.get("regiao_ferida"),
            animal.get("atendimento_veterinario"), animal.get("data_atendimento"),
            animal.get("evolucao_caso"), animal.get("arquivo_origem"), agora_iso,
        ),
    )
    return cur.rowcount > 0


def _obter_ou_criar_localidade(cur, nome):
    if not nome:
        return None
    cur.execute("SELECT id_localidade FROM localidades WHERE nome=?", (nome,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO localidades(nome, cod_localidade) VALUES (?,NULL)", (nome,))
    return cur.lastrowid


def _obter_ou_criar_agente(cur, nome):
    cur.execute("SELECT id_agente FROM agentes WHERE nome=?", (nome,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO agentes(nome) VALUES (?)", (nome,))
    return cur.lastrowid


def _split_agentes(conn, texto):
    texto = _text(texto)
    if not texto:
        return []
    cur = conn.cursor()
    conhecidos = [r[0] for r in cur.execute("SELECT nome FROM agentes ORDER BY LENGTH(nome) DESC, nome")]
    restantes = texto
    nomes = []
    for nome in conhecidos:
        padrao = re.compile(rf"(^|\s){re.escape(nome)}(?=\s|$)", re.I)
        if padrao.search(restantes):
            nomes.append(nome)
            restantes = padrao.sub(" ", restantes).strip()
    for original, normalizado in AGENTE_COMPOSTO.items():
        if re.search(rf"(^|\s){re.escape(original)}(?=\s|$)", restantes, re.I) and normalizado not in nomes:
            nomes.append(normalizado)
            restantes = re.sub(rf"(^|\s){re.escape(original)}(?=\s|$)", " ", restantes, flags=re.I).strip()
    for parte in re.split(r"[,;/]|\s{2,}", restantes):
        parte = parte.strip()
        if parte and parte not in nomes:
            nomes.append(parte)
    return nomes


def _localidade(valor):
    texto = _text(valor)
    if not texto:
        return None
    return LOCALIDADES_PADRAO.get(texto.lower(), texto)


def _text(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    texto = str(valor).strip()
    if texto.lower() in {"nan", "nat", "none"}:
        return None
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]
    return texto or None


def _int(valor):
    texto = _text(valor)
    if not texto:
        return None
    try:
        return int(float(texto.replace(",", ".")))
    except Exception:
        return None


def _date(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    try:
        return pd.to_datetime(valor).date().isoformat()
    except Exception:
        return None


def _time(valor):
    texto = _text(valor)
    if not texto:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", texto)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    try:
        parsed = pd.to_datetime(texto, errors="coerce")
        return None if pd.isna(parsed) else parsed.strftime("%H:%M")
    except Exception:
        return None


def _datetime(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    try:
        return pd.to_datetime(valor).isoformat()
    except Exception:
        return None


def _uuid(valor):
    texto = _text(valor)
    if texto and texto.startswith("uuid:"):
        return texto[5:]
    return texto


def _hash(prefix, value):
    return hashlib.md5(f"{prefix}:{value}".encode("utf-8")).hexdigest()


def _basename(path):
    return str(path).replace("\\", "/").split("/")[-1]
