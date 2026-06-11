import csv
import hashlib
import os
from datetime import datetime
from pathlib import Path

from app_core import db as db_core


TABLE = "ovitrampas_leituras"
ARMADILHAS_TABLE = "ovitrampas_armadilhas"
CAL_GRUPOS_TABLE = "ovitrampas_calendario_grupos"
CAL_EVENTOS_TABLE = "ovitrampas_calendario_eventos"
CAL_AGENTES_TABLE = "ovitrampas_calendario_agentes"

MOVIMENTOS = {
    "instalacao": "Instalação",
    "troca": "Troca",
    "retirada": "Retirada",
    "feriado": "Feriado",
}

GRUPOS_PADRAO = (
    ("Tanguá / Paraíso", "Tanguá, Paraíso", "#facc15"),
    ("Sede / São Francisco / Graziela / Tamboara / Rosana", "Sede, São Francisco, Graziela, Tamboara, Rosana", "#22c55e"),
    ("Tranqueira / São João Batista", "Tranqueira, São João Batista", "#3b82f6"),
    ("Cachoeira / São Venâncio / Roma", "Cachoeira, São Venâncio, Roma", "#f97316"),
    ("Lamenha / Santa Maria", "Lamenha, Santa Maria", "#a855f7"),
)


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ovitrampas_armadilhas (
            ovitrampa_id    TEXT PRIMARY KEY,
            rua             TEXT,
            numero          TEXT,
            complemento     TEXT,
            bairro          TEXT,
            localizacao     TEXT,
            localidade      TEXT,
            responsavel     TEXT,
            quarteirao      TEXT,
            latitude        REAL,
            longitude       REAL,
            arquivo_origem  TEXT,
            atualizado_em   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ovitrampas_leituras (
            id_leitura          TEXT PRIMARY KEY,
            ovitrampa_id        TEXT NOT NULL,
            estado              TEXT,
            municipio           TEXT,
            distrito            TEXT,
            rua                 TEXT,
            numero              TEXT,
            complemento         TEXT,
            localizacao         TEXT,
            latitude            REAL,
            longitude           REAL,
            ano                 INTEGER NOT NULL,
            semana              INTEGER NOT NULL,
            data_envio_contagem TEXT,
            ovos                INTEGER DEFAULT 0,
            quem_enviou         TEXT,
            observacao          TEXT,
            lat_lng             TEXT,
            quarteirao          TEXT,
            data_instalacao     DATE,
            data_coleta         DATE,
            id_laboratorista    INTEGER REFERENCES agentes(id_agente),
            data_leitura        DATE,
            arquivo_origem      TEXT,
            importado_em        TEXT NOT NULL,
            UNIQUE(ovitrampa_id, ano, semana, data_instalacao, data_coleta, data_envio_contagem)
        );

        CREATE INDEX IF NOT EXISTS idx_ovitrampas_armadilhas_localidade ON ovitrampas_armadilhas(localidade);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_armadilhas_quarteirao ON ovitrampas_armadilhas(quarteirao);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_ano_semana ON ovitrampas_leituras(ano, semana);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_id ON ovitrampas_leituras(ovitrampa_id);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_distrito ON ovitrampas_leituras(distrito);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_coleta ON ovitrampas_leituras(data_coleta);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_ovos ON ovitrampas_leituras(ovos);

        CREATE TABLE IF NOT EXISTS ovitrampas_calendario_grupos (
            id_grupo      INTEGER PRIMARY KEY AUTOINCREMENT,
            nome          TEXT NOT NULL,
            localidades   TEXT,
            cor           TEXT NOT NULL DEFAULT '#0f766e',
            ativo         INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
            criado_em     TEXT NOT NULL,
            atualizado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS ovitrampas_calendario_eventos (
            id_evento     INTEGER PRIMARY KEY AUTOINCREMENT,
            data          DATE NOT NULL UNIQUE,
            movimento     TEXT NOT NULL CHECK(movimento IN ('instalacao','troca','retirada','feriado')),
            titulo        TEXT,
            id_grupo      INTEGER REFERENCES ovitrampas_calendario_grupos(id_grupo),
            ciclo         TEXT,
            observacoes   TEXT,
            criado_por    TEXT,
            criado_em     TEXT NOT NULL,
            atualizado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS ovitrampas_calendario_agentes (
            id_evento INTEGER NOT NULL REFERENCES ovitrampas_calendario_eventos(id_evento) ON DELETE CASCADE,
            id_agente INTEGER NOT NULL REFERENCES agentes(id_agente),
            PRIMARY KEY (id_evento, id_agente)
        );

        CREATE INDEX IF NOT EXISTS idx_ovitrampas_cal_eventos_data ON ovitrampas_calendario_eventos(data);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_cal_eventos_grupo ON ovitrampas_calendario_eventos(id_grupo);
        CREATE INDEX IF NOT EXISTS idx_ovitrampas_cal_agentes_agente ON ovitrampas_calendario_agentes(id_agente);
        """
    )
    _ensure_columns(conn, TABLE, {
        "id_laboratorista": "INTEGER REFERENCES agentes(id_agente)",
        "data_leitura": "DATE",
    })
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ovitrampas_laboratorista ON ovitrampas_leituras(id_laboratorista)")
    _migrar_calendario_schema(conn)
    _semear_grupos_padrao(conn)


def _ensure_columns(conn, table, columns):
    existentes = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for column, definition in columns.items():
        if column not in existentes:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _semear_grupos_padrao(conn):
    total = conn.execute(f"SELECT COUNT(*) FROM {CAL_GRUPOS_TABLE}").fetchone()[0]
    if total:
        return
    agora = datetime.now().isoformat(timespec="seconds")
    for nome, localidades, cor in GRUPOS_PADRAO:
        conn.execute(
            f"""INSERT INTO {CAL_GRUPOS_TABLE}
                (nome, localidades, cor, ativo, criado_em, atualizado_em)
                VALUES (?, ?, ?, 1, ?, ?)""",
            (nome, localidades, cor, agora, agora),
        )


def _migrar_calendario_schema(conn):
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (CAL_EVENTOS_TABLE,),
    ).fetchone()
    if not sql:
        return
    table_sql = sql[0] or ""
    precisa = "feriado" not in table_sql or "id_grupo      INTEGER NOT NULL" in table_sql or "titulo" not in table_sql
    if not precisa:
        return
    conn.executescript(f"""
        ALTER TABLE {CAL_EVENTOS_TABLE} RENAME TO {CAL_EVENTOS_TABLE}_old;
        CREATE TABLE {CAL_EVENTOS_TABLE} (
            id_evento     INTEGER PRIMARY KEY AUTOINCREMENT,
            data          DATE NOT NULL UNIQUE,
            movimento     TEXT NOT NULL CHECK(movimento IN ('instalacao','troca','retirada','feriado')),
            titulo        TEXT,
            id_grupo      INTEGER REFERENCES {CAL_GRUPOS_TABLE}(id_grupo),
            ciclo         TEXT,
            observacoes   TEXT,
            criado_por    TEXT,
            criado_em     TEXT NOT NULL,
            atualizado_em TEXT
        );
        INSERT INTO {CAL_EVENTOS_TABLE}
            (id_evento, data, movimento, titulo, id_grupo, ciclo, observacoes, criado_por, criado_em, atualizado_em)
        SELECT
            id_evento, data, movimento, NULL, id_grupo, ciclo, observacoes, criado_por, criado_em, atualizado_em
        FROM {CAL_EVENTOS_TABLE}_old;
        DROP TABLE {CAL_EVENTOS_TABLE}_old;
    """)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_ovitrampas_cal_eventos_data ON {CAL_EVENTOS_TABLE}(data)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_ovitrampas_cal_eventos_grupo ON {CAL_EVENTOS_TABLE}(id_grupo)")


def importar_pasta(db_path, pasta, logger=None):
    paths = sorted(Path(pasta).glob("*.csv"), key=lambda p: p.name)
    total = {"arquivos": 0, "linhas": 0, "inseridos": 0, "duplicados": 0, "erros": []}
    for path in paths:
        result = importar_csv(db_path, path)
        total["arquivos"] += 1
        total["linhas"] += result["linhas"]
        total["inseridos"] += result["inseridos"]
        total["duplicados"] += result["duplicados"]
        total["erros"].extend(result["erros"])
        if logger:
            logger(f"{path.name}: {result['inseridos']} novo(s), {result['duplicados']} duplicado(s)")
    return total


def importar_csv(db_path, path):
    result = {"arquivo": os.path.basename(path), "linhas": 0, "inseridos": 0, "duplicados": 0, "erros": []}
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        agora = datetime.now().isoformat(timespec="seconds")
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for idx, row in enumerate(reader, start=2):
                if not any((v or "").strip() for v in row.values()):
                    continue
                result["linhas"] += 1
                try:
                    registro = _registro(row, result["arquivo"], agora)
                    inserted = _insert(conn, registro)
                    if inserted:
                        result["inseridos"] += 1
                    else:
                        result["duplicados"] += 1
                except Exception as exc:
                    result["erros"].append(f"Linha {idx}: {exc}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return result


def importar_armadilhas_csv(db_path, path):
    result = {"arquivo": os.path.basename(path), "linhas": 0, "inseridos": 0, "atualizados": 0, "sem_alteracao": 0, "erros": []}
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        agora = datetime.now().isoformat(timespec="seconds")
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for idx, row in enumerate(reader, start=2):
                if not any((v or "").strip() for v in row.values()):
                    continue
                result["linhas"] += 1
                try:
                    registro = _registro_armadilha(row, result["arquivo"], agora)
                    status = _upsert_armadilha(conn, registro)
                    result[status] += 1
                except Exception as exc:
                    result["erros"].append(f"Linha {idx}: {exc}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return result


def resumo(db_path, filtros=None):
    filtros = filtros or {}
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        where, params = _where(filtros)
        totais = dict(conn.execute(
            f"""SELECT COUNT(*) AS leituras,
                       COUNT(DISTINCT ovitrampa_id) AS ovitrampas,
                       COALESCE(SUM(ovos),0) AS ovos,
                       COALESCE(AVG(ovos),0) AS media_ovos,
                       SUM(CASE WHEN ovos > 0 THEN 1 ELSE 0 END) AS positivas,
                       MAX(ano) AS ultimo_ano,
                       MAX(CASE WHEN ano=(SELECT MAX(ano) FROM ovitrampas_leituras) THEN semana ELSE NULL END) AS ultima_semana
                  FROM ovitrampas_leituras l {where}""",
            params,
        ).fetchone())
        por_distrito = [dict(row) for row in conn.execute(
            f"""SELECT COALESCE(l.distrito,'-') AS distrito, COUNT(*) AS leituras,
                       COUNT(DISTINCT l.ovitrampa_id) AS ovitrampas, COALESCE(SUM(l.ovos),0) AS ovos
                  FROM ovitrampas_leituras l {where}
                 GROUP BY COALESCE(l.distrito,'-')
                 ORDER BY ovos DESC, leituras DESC, distrito
                 LIMIT 12""",
            params,
        )]
        por_semana = [dict(row) for row in conn.execute(
            f"""SELECT l.ano, l.semana, COUNT(*) AS leituras, COALESCE(SUM(l.ovos),0) AS ovos,
                       SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END) AS positivas
                  FROM ovitrampas_leituras l {where}
                 GROUP BY l.ano, l.semana
                 ORDER BY l.ano DESC, l.semana DESC
                 LIMIT 16""",
            params,
        )]
    finally:
        conn.close()
    return {"totais": totais, "por_distrito": por_distrito, "por_semana": por_semana}


def listar(db_path, filtros=None, limite=500):
    filtros = filtros or {}
    limite = max(1, min(int(limite or 500), 2000))
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        where, params = _where(filtros, busca=True)
        rows = [dict(row) for row in conn.execute(
            f"""SELECT l.*, a.nome AS laboratorista
                  FROM ovitrampas_leituras l
                  LEFT JOIN agentes a ON a.id_agente=l.id_laboratorista
                  {where}
                 ORDER BY ano DESC, semana DESC, ovitrampa_id COLLATE NOCASE
                 LIMIT ?""",
            [*params, limite],
        )]
        total = conn.execute(f"SELECT COUNT(*) FROM ovitrampas_leituras l {where}", params).fetchone()[0]
    finally:
        conn.close()
    return {"total": total, "registros": rows}


def listar_armadilhas(db_path, filtros=None, limite=500):
    filtros = filtros or {}
    limite = max(1, min(int(limite or 500), 2000))
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        where, params = _where_armadilhas(filtros)
        rows = [dict(row) for row in conn.execute(
            f"""SELECT a.*,
                       COUNT(l.id_leitura) AS leituras,
                       COALESCE(SUM(l.ovos),0) AS ovos_total,
                       SUM(CASE WHEN l.ovos > 0 THEN 1 ELSE 0 END) AS positivas,
                       MAX(l.data_coleta) AS ultima_coleta,
                       MAX(l.ano) AS ultimo_ano
                  FROM ovitrampas_armadilhas a
                  LEFT JOIN ovitrampas_leituras l ON l.ovitrampa_id=a.ovitrampa_id
                  {where}
                 GROUP BY a.ovitrampa_id
                 ORDER BY CAST(a.ovitrampa_id AS INTEGER), a.ovitrampa_id COLLATE NOCASE
                 LIMIT ?""",
            [*params, limite],
        )]
        total = conn.execute(f"SELECT COUNT(*) FROM ovitrampas_armadilhas a {where}", params).fetchone()[0]
    finally:
        conn.close()
    return {"total": total, "registros": rows}


def historico_armadilha(db_path, ovitrampa_id):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        armadilha = conn.execute(
            f"SELECT * FROM {ARMADILHAS_TABLE} WHERE ovitrampa_id=?",
            (str(ovitrampa_id),),
        ).fetchone()
        leituras = [dict(row) for row in conn.execute(
            """SELECT l.*, a.nome AS laboratorista
                 FROM ovitrampas_leituras l
                 LEFT JOIN agentes a ON a.id_agente=l.id_laboratorista
                WHERE l.ovitrampa_id=?
                ORDER BY l.ano DESC, l.semana DESC, l.data_coleta DESC""",
            (str(ovitrampa_id),),
        )]
    finally:
        conn.close()
    return {"armadilha": dict(armadilha) if armadilha else None, "leituras": leituras}


def atualizar_leitura(db_path, id_leitura, dados):
    id_laboratorista = _int(dados.get("id_laboratorista"))
    data_leitura = _date(dados.get("data_leitura"))
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        if id_laboratorista:
            agente = conn.execute("SELECT id_agente FROM agentes WHERE id_agente=? AND ativo=1", (id_laboratorista,)).fetchone()
            if not agente:
                raise ValueError("Laboratorista nao encontrado.")
        cur = conn.execute(
            f"""UPDATE {TABLE}
                   SET id_laboratorista=?, data_leitura=?
                 WHERE id_leitura=?""",
            (id_laboratorista, data_leitura, id_leitura),
        )
        if cur.rowcount == 0:
            raise ValueError("Leitura nao encontrada.")
        conn.commit()
        row = conn.execute(
            """SELECT l.*, a.nome AS laboratorista
                 FROM ovitrampas_leituras l
                 LEFT JOIN agentes a ON a.id_agente=l.id_laboratorista
                WHERE l.id_leitura=?""",
            (id_leitura,),
        ).fetchone()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def agentes(db_path):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        return [dict(row) for row in conn.execute(
            "SELECT id_agente, nome FROM agentes WHERE ativo=1 ORDER BY nome COLLATE NOCASE"
        )]
    finally:
        conn.close()


def calendario_dados(db_path, ano):
    ano = _int(ano) or datetime.now().year
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        grupos = [_grupo_dict(row) for row in conn.execute(
            f"SELECT * FROM {CAL_GRUPOS_TABLE} ORDER BY ativo DESC, nome COLLATE NOCASE"
        )]
        eventos = [_cal_evento_dict(row) for row in conn.execute(
            f"""SELECT e.*, g.nome AS grupo_nome, g.localidades AS grupo_localidades, g.cor AS grupo_cor,
                       GROUP_CONCAT(a.id_agente || ':' || a.nome, '|') AS agentes_raw
                  FROM {CAL_EVENTOS_TABLE} e
                  LEFT JOIN {CAL_GRUPOS_TABLE} g ON g.id_grupo=e.id_grupo
                  LEFT JOIN {CAL_AGENTES_TABLE} ea ON ea.id_evento=e.id_evento
                  LEFT JOIN agentes a ON a.id_agente=ea.id_agente
                 WHERE substr(e.data, 1, 4)=?
                 GROUP BY e.id_evento
                 ORDER BY e.data""",
            (str(ano),),
        )]
    finally:
        conn.close()
    return {"ano": ano, "grupos": grupos, "eventos": eventos, "movimentos": MOVIMENTOS}


def salvar_grupo(db_path, dados, id_grupo=None):
    nome = _text(dados.get("nome"))
    if not nome:
        raise ValueError("Informe o nome do grupo.")
    payload = {
        "nome": nome,
        "localidades": _text(dados.get("localidades")),
        "cor": _cor(dados.get("cor")) or "#0f766e",
        "ativo": 1 if dados.get("ativo", True) in (True, 1, "1", "true", "on") else 0,
    }
    agora = datetime.now().isoformat(timespec="seconds")
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        if id_grupo:
            existe = conn.execute(f"SELECT 1 FROM {CAL_GRUPOS_TABLE} WHERE id_grupo=?", (id_grupo,)).fetchone()
            if not existe:
                raise ValueError("Grupo nao encontrado.")
            conn.execute(
                f"""UPDATE {CAL_GRUPOS_TABLE}
                       SET nome=?, localidades=?, cor=?, ativo=?, atualizado_em=?
                     WHERE id_grupo=?""",
                (payload["nome"], payload["localidades"], payload["cor"], payload["ativo"], agora, id_grupo),
            )
        else:
            cur = conn.execute(
                f"""INSERT INTO {CAL_GRUPOS_TABLE}
                    (nome, localidades, cor, ativo, criado_em, atualizado_em)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (payload["nome"], payload["localidades"], payload["cor"], payload["ativo"], agora, agora),
            )
            id_grupo = cur.lastrowid
        conn.commit()
        row = conn.execute(f"SELECT * FROM {CAL_GRUPOS_TABLE} WHERE id_grupo=?", (id_grupo,)).fetchone()
        return _grupo_dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def excluir_grupo(db_path, id_grupo):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        usado = conn.execute(f"SELECT COUNT(*) FROM {CAL_EVENTOS_TABLE} WHERE id_grupo=?", (id_grupo,)).fetchone()[0]
        if usado:
            raise ValueError("Grupo possui eventos vinculados. Desative ou edite os eventos antes de excluir.")
        cur = conn.execute(f"DELETE FROM {CAL_GRUPOS_TABLE} WHERE id_grupo=?", (id_grupo,))
        if cur.rowcount == 0:
            raise ValueError("Grupo nao encontrado.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def salvar_evento_calendario(db_path, dados, usuario_nome="sistema", id_evento=None):
    payload = _cal_evento_payload(dados)
    agora = datetime.now().isoformat(timespec="seconds")
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        if payload["movimento"] != "feriado":
            grupo = conn.execute(
                f"SELECT id_grupo FROM {CAL_GRUPOS_TABLE} WHERE id_grupo=? AND ativo=1",
                (payload["id_grupo"],),
            ).fetchone()
            if not grupo:
                raise ValueError("Selecione um grupo ativo.")
        if id_evento:
            existe = conn.execute(f"SELECT 1 FROM {CAL_EVENTOS_TABLE} WHERE id_evento=?", (id_evento,)).fetchone()
            if not existe:
                raise ValueError("Evento nao encontrado.")
            conn.execute(
                f"""UPDATE {CAL_EVENTOS_TABLE}
                       SET data=?, movimento=?, titulo=?, id_grupo=?, ciclo=?, observacoes=?, atualizado_em=?
                     WHERE id_evento=?""",
                (
                    payload["data"], payload["movimento"], payload["titulo"], payload["id_grupo"], payload["ciclo"],
                    payload["observacoes"], agora, id_evento,
                ),
            )
        else:
            cur = conn.execute(
                f"""INSERT INTO {CAL_EVENTOS_TABLE}
                    (data, movimento, titulo, id_grupo, ciclo, observacoes, criado_por, criado_em, atualizado_em)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload["data"], payload["movimento"], payload["titulo"], payload["id_grupo"], payload["ciclo"],
                    payload["observacoes"], usuario_nome, agora, agora,
                ),
            )
            id_evento = cur.lastrowid
        _salvar_cal_agentes(conn, id_evento, payload["agentes"])
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if isinstance(exc, Exception) and "UNIQUE" in str(exc).upper():
            raise ValueError("Ja existe um movimento de ovitrampa nessa data.") from exc
        raise
    finally:
        conn.close()
    return calendario_evento(db_path, id_evento)


def calendario_evento(db_path, id_evento):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            f"""SELECT e.*, g.nome AS grupo_nome, g.localidades AS grupo_localidades, g.cor AS grupo_cor,
                       GROUP_CONCAT(a.id_agente || ':' || a.nome, '|') AS agentes_raw
                  FROM {CAL_EVENTOS_TABLE} e
                  LEFT JOIN {CAL_GRUPOS_TABLE} g ON g.id_grupo=e.id_grupo
                  LEFT JOIN {CAL_AGENTES_TABLE} ea ON ea.id_evento=e.id_evento
                  LEFT JOIN agentes a ON a.id_agente=ea.id_agente
                 WHERE e.id_evento=?
                 GROUP BY e.id_evento""",
            (id_evento,),
        ).fetchone()
        if not row:
            raise ValueError("Evento nao encontrado.")
        return _cal_evento_dict(row)
    finally:
        conn.close()


def excluir_evento_calendario(db_path, id_evento):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        conn.execute(f"DELETE FROM {CAL_AGENTES_TABLE} WHERE id_evento=?", (id_evento,))
        cur = conn.execute(f"DELETE FROM {CAL_EVENTOS_TABLE} WHERE id_evento=?", (id_evento,))
        if cur.rowcount == 0:
            raise ValueError("Evento nao encontrado.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def eventos_agenda(db_path, inicio, fim):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            f"""SELECT e.*, g.nome AS grupo_nome, g.localidades AS grupo_localidades, g.cor AS grupo_cor,
                       GROUP_CONCAT(a.nome, ', ') AS agentes
                  FROM {CAL_EVENTOS_TABLE} e
                  JOIN {CAL_GRUPOS_TABLE} g ON g.id_grupo=e.id_grupo
                  LEFT JOIN {CAL_AGENTES_TABLE} ea ON ea.id_evento=e.id_evento
                  LEFT JOIN agentes a ON a.id_agente=ea.id_agente
                 WHERE e.data BETWEEN ? AND ?
                   AND e.movimento <> 'feriado'
                 GROUP BY e.id_evento
                 ORDER BY e.data""",
            (str(inicio)[:10], str(fim)[:10]),
        ).fetchall()
    finally:
        conn.close()
    eventos = []
    for row in rows:
        movimento_label = MOVIMENTOS.get(row["movimento"], row["movimento"])
        titulo = f"{movimento_label} de ovitrampas - {row['grupo_nome']}"
        detalhes = []
        if row["ciclo"]:
            detalhes.append(f"Ciclo: {row['ciclo']}")
        if row["grupo_localidades"]:
            detalhes.append(f"Localidades: {row['grupo_localidades']}")
        if row["observacoes"]:
            detalhes.append(f"Observações: {row['observacoes']}")
        eventos.append({
            "data": row["data"],
            "titulo": titulo,
            "resumo": " | ".join(detalhes),
            "localidades": row["grupo_localidades"] or row["grupo_nome"],
            "agentes": row["agentes"] or "-",
            "cor": row["grupo_cor"] or "#0f766e",
            "id_evento": row["id_evento"],
            "movimento": row["movimento"],
        })
    return eventos


def distritos(db_path):
    conn = db_core.connect(db_path)
    try:
        ensure_schema(conn)
        return [row[0] for row in conn.execute(
            """SELECT nome FROM (
                   SELECT DISTINCT distrito AS nome FROM ovitrampas_leituras WHERE distrito IS NOT NULL AND TRIM(distrito)<>''
                   UNION
                   SELECT DISTINCT localidade AS nome FROM ovitrampas_armadilhas WHERE localidade IS NOT NULL AND TRIM(localidade)<>''
               )
               ORDER BY nome"""
        )]
    finally:
        conn.close()


def _registro(row, arquivo, agora):
    ovitrampa_id = _text(row.get("Ovitrampa ID"))
    ano = _int(row.get("Ano"))
    semana = _int(row.get("Semana"))
    data_instalacao = _date(row.get("Data da instalação"))
    data_coleta = _date(row.get("Data de coleta"))
    data_envio = _datetime(row.get("Data do envio da contagem"))
    if not ovitrampa_id:
        raise ValueError("sem Ovitrampa ID")
    if not ano or not semana:
        raise ValueError("sem ano/semana")
    chave = "|".join([ovitrampa_id, str(ano), str(semana), data_instalacao or "", data_coleta or "", data_envio or ""])
    return {
        "id_leitura": hashlib.md5(chave.encode("utf-8")).hexdigest(),
        "ovitrampa_id": ovitrampa_id,
        "estado": _text(row.get("Estado")),
        "municipio": _text(row.get("Município")),
        "distrito": _title_distrito(row.get("Distrito")),
        "rua": _text(row.get("Rua")),
        "numero": _text(row.get("Número")),
        "complemento": _text(row.get("Complemento")),
        "localizacao": _text(row.get("Localização")),
        "latitude": _real(row.get("Latitude")),
        "longitude": _real(row.get("Longitude")),
        "ano": ano,
        "semana": semana,
        "data_envio_contagem": data_envio,
        "ovos": _int(row.get("Ovos")) or 0,
        "quem_enviou": _text(row.get("Quem enviou")),
        "observacao": _text(row.get("Observação")),
        "lat_lng": _text(row.get("Lat_lng")),
        "quarteirao": _text(row.get("Quarteirão")),
        "data_instalacao": data_instalacao,
        "data_coleta": data_coleta,
        "arquivo_origem": arquivo,
        "importado_em": agora,
    }


def _registro_armadilha(row, arquivo, agora):
    ovitrampa_id = _text(row.get("ID"))
    if not ovitrampa_id:
        raise ValueError("sem ID da armadilha")
    return {
        "ovitrampa_id": ovitrampa_id,
        "rua": _text(row.get("Rua")),
        "numero": _text(row.get("Número do logradouro") or row.get("NÃºmero do logradouro")),
        "complemento": _text(row.get("Complemento")),
        "bairro": _text(row.get("Bairro")),
        "localizacao": _text(row.get("Localização da ovitrampa") or row.get("LocalizaÃ§Ã£o da ovitrampa")),
        "localidade": _title_distrito(row.get("Setor/Distrito da ovitrampa")),
        "responsavel": _text(row.get("Responsável") or row.get("ResponsÃ¡vel")),
        "quarteirao": _text(row.get("Quarteirão") or row.get("QuarteirÃ£o")),
        "latitude": _real(row.get("Latitude")),
        "longitude": _real(row.get("Longitude")),
        "arquivo_origem": arquivo,
        "atualizado_em": agora,
    }


def _grupo_dict(row):
    item = dict(row)
    item["ativo"] = bool(item.get("ativo"))
    return item


def _cal_evento_dict(row):
    item = dict(row)
    item["movimento_label"] = MOVIMENTOS.get(item.get("movimento"), item.get("movimento") or "")
    if item.get("movimento") == "feriado":
        item["grupo_nome"] = item.get("titulo") or "Feriado"
        item["grupo_localidades"] = ""
        item["grupo_cor"] = "#94a3b8"
    raw = item.pop("agentes_raw", "") or ""
    item["agentes"] = [
        {"id_agente": int(x.split(":", 1)[0]), "nome": x.split(":", 1)[1]}
        for x in raw.split("|")
        if ":" in x
    ]
    item["agentes_nomes"] = ", ".join(a["nome"] for a in item["agentes"])
    return item


def _cal_evento_payload(dados):
    data = _date(dados.get("data"))
    if not data:
        raise ValueError("Informe a data do movimento.")
    movimento = _text(dados.get("movimento"))
    if movimento not in MOVIMENTOS:
        raise ValueError("Movimento invalido.")
    id_grupo = _int(dados.get("id_grupo"))
    if movimento != "feriado" and not id_grupo:
        raise ValueError("Selecione o grupo.")
    titulo = _text(dados.get("titulo"))
    if movimento == "feriado" and not titulo:
        raise ValueError("Informe o título do feriado.")
    return {
        "data": data,
        "movimento": movimento,
        "titulo": titulo if movimento == "feriado" else None,
        "id_grupo": id_grupo if movimento != "feriado" else None,
        "ciclo": _text(dados.get("ciclo")),
        "observacoes": _text(dados.get("observacoes")),
        "agentes": _parse_ids(dados.get("agentes")),
    }


def _salvar_cal_agentes(conn, id_evento, agentes):
    conn.execute(f"DELETE FROM {CAL_AGENTES_TABLE} WHERE id_evento=?", (id_evento,))
    for id_agente in agentes:
        conn.execute(
            f"INSERT OR IGNORE INTO {CAL_AGENTES_TABLE} (id_evento, id_agente) VALUES (?, ?)",
            (id_evento, id_agente),
        )


def _parse_ids(values):
    ids = []
    for value in values or []:
        numero = _int(value)
        if numero and numero not in ids:
            ids.append(numero)
    return ids


def _cor(value):
    text = _text(value)
    if not text:
        return None
    if len(text) == 7 and text.startswith("#") and all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
        return text
    return None


def _insert(conn, registro):
    cols = list(registro.keys())
    placeholders = ",".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT OR IGNORE INTO {TABLE} ({','.join(cols)}) VALUES ({placeholders})",
        [registro[col] for col in cols],
    )
    return cur.rowcount > 0


def _upsert_armadilha(conn, registro):
    atual = conn.execute(
        f"SELECT * FROM {ARMADILHAS_TABLE} WHERE ovitrampa_id=?",
        (registro["ovitrampa_id"],),
    ).fetchone()
    cols = list(registro.keys())
    if not atual:
        placeholders = ",".join("?" for _ in cols)
        conn.execute(
            f"INSERT INTO {ARMADILHAS_TABLE} ({','.join(cols)}) VALUES ({placeholders})",
            [registro[col] for col in cols],
        )
        return "inseridos"

    mudou = any((atual[col] != registro[col]) for col in cols if col not in ("arquivo_origem", "atualizado_em"))
    if not mudou:
        return "sem_alteracao"
    sets = ",".join(f"{col}=?" for col in cols if col != "ovitrampa_id")
    conn.execute(
        f"UPDATE {ARMADILHAS_TABLE} SET {sets} WHERE ovitrampa_id=?",
        [registro[col] for col in cols if col != "ovitrampa_id"] + [registro["ovitrampa_id"]],
    )
    return "atualizados"


def _where(filtros, busca=False):
    clauses = []
    params = []
    if filtros.get("ano"):
        clauses.append("l.ano=?")
        params.append(_int(filtros.get("ano")))
    if filtros.get("semana"):
        clauses.append("l.semana=?")
        params.append(_int(filtros.get("semana")))
    if filtros.get("distrito"):
        clauses.append("l.distrito=?")
        params.append(filtros["distrito"])
    if filtros.get("positivas") == "1":
        clauses.append("l.ovos > 0")
    if busca and filtros.get("busca"):
        term = f"%{filtros['busca'].strip()}%"
        clauses.append("(l.ovitrampa_id LIKE ? OR l.rua LIKE ? OR l.complemento LIKE ? OR l.localizacao LIKE ? OR l.quarteirao LIKE ?)")
        params.extend([term] * 5)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _where_armadilhas(filtros):
    clauses = []
    params = []
    if filtros.get("distrito"):
        clauses.append("a.localidade=?")
        params.append(filtros["distrito"])
    if filtros.get("busca"):
        term = f"%{filtros['busca'].strip()}%"
        clauses.append("(a.ovitrampa_id LIKE ? OR a.rua LIKE ? OR a.complemento LIKE ? OR a.localizacao LIKE ? OR a.quarteirao LIKE ? OR a.responsavel LIKE ?)")
        params.extend([term] * 6)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in ("nan", "none") else None


def _int(value):
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text.replace(".", "").replace(",", ".")))
    except ValueError:
        return None


def _real(value):
    text = _text(value)
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _date(value):
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        return None


def _datetime(value):
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:19]).isoformat(sep=" ")
    except ValueError:
        return text


def _title_distrito(value):
    text = _text(value)
    return text.title() if text and text.isupper() else text
