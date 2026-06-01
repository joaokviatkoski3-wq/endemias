import sqlite3
from collections import defaultdict

from app_core import utils


EDITABLE_FIELDS = {
    "nome": "TEXT",
    "matricula": "TEXT",
    "cargo": "TEXT",
    "ativo": "INTEGER",
    "data_inicio": "TEXT",
    "data_saida": "TEXT",
    "observacoes": "TEXT",
}


def ensure_schema(conn_or_path):
    close = False
    if isinstance(conn_or_path, (str, bytes)):
        conn = sqlite3.connect(conn_or_path)
        conn.row_factory = sqlite3.Row
        close = True
    else:
        conn = conn_or_path
    try:
        cols = {
            row["name"] if isinstance(row, sqlite3.Row) else row[1]
            for row in conn.execute("PRAGMA table_info(agentes)").fetchall()
        }
        if not cols:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agentes (
                    id_agente INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    matricula TEXT,
                    cargo TEXT,
                    ativo INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
                    data_inicio TEXT,
                    data_saida TEXT,
                    observacoes TEXT
                )
            """)
            conn.commit()
            return
        if "matricula" not in cols:
            conn.execute("ALTER TABLE agentes ADD COLUMN matricula TEXT")
        if "cargo" not in cols:
            conn.execute("ALTER TABLE agentes ADD COLUMN cargo TEXT")
        if "ativo" not in cols:
            conn.execute("ALTER TABLE agentes ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1))")
        if "data_inicio" not in cols:
            conn.execute("ALTER TABLE agentes ADD COLUMN data_inicio TEXT")
        if "data_saida" not in cols:
            conn.execute("ALTER TABLE agentes ADD COLUMN data_saida TEXT")
        if "observacoes" not in cols:
            conn.execute("ALTER TABLE agentes ADD COLUMN observacoes TEXT")
        conn.commit()
    finally:
        if close:
            conn.close()


def listar(db_path, filtros=None):
    filtros = filtros or {}
    ensure_schema(db_path)
    where = []
    params = []
    status = filtros.get("status", "ativos")
    if status == "ativos":
        where.append("ativo=1")
    elif status == "inativos":
        where.append("ativo=0")
    busca = (filtros.get("busca") or "").strip()
    if busca:
        where.append("(nome LIKE ? OR COALESCE(matricula,'') LIKE ?)")
        params.extend([f"%{busca}%", f"%{busca}%"])
    sql = "SELECT * FROM agentes"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ativo DESC, nome"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def obter(db_path, id_agente):
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM agentes WHERE id_agente=?", (id_agente,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def criar(db_path, dados):
    ensure_schema(db_path)
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ValueError("Informe o nome do agente.")
    ativo = 1 if str(dados.get("ativo", "1")) == "1" else 0
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO agentes(nome, matricula, cargo, ativo, data_inicio, data_saida, observacoes)
               VALUES (?,?,?,?,?,?,?)""",
            (
                nome,
                _clean(dados.get("matricula")),
                _clean(dados.get("cargo")),
                ativo,
                _clean(dados.get("data_inicio")),
                _clean(dados.get("data_saida")),
                _clean(dados.get("observacoes")),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def atualizar_campo(db_path, id_agente, campo, valor):
    ensure_schema(db_path)
    if campo not in EDITABLE_FIELDS:
        raise ValueError("Campo invalido.")
    if campo == "nome" and not (valor or "").strip():
        raise ValueError("O nome nao pode ficar vazio.")
    if campo == "ativo":
        valor = 1 if str(valor) == "1" else 0
    else:
        valor = _clean(valor)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        anterior = conn.execute("SELECT * FROM agentes WHERE id_agente=?", (id_agente,)).fetchone()
        if not anterior:
            raise ValueError("Agente nao encontrado.")
        conn.execute(f"UPDATE agentes SET {campo}=? WHERE id_agente=?", (valor, id_agente))
        conn.commit()
        return dict(anterior), valor
    finally:
        conn.close()


def historico(db_path, id_agente, d_ini=None, d_fim=None):
    ensure_schema(db_path)
    d_ini = d_ini or utils.data_n_dias(30)
    d_fim = d_fim or utils.hoje()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        agente = conn.execute("SELECT * FROM agentes WHERE id_agente=?", (id_agente,)).fetchone()
        if not agente:
            return None
        eventos = []
        eventos.extend(_hist_vetores(conn, id_agente, d_ini, d_fim))
        eventos.extend(_hist_esporotricose(conn, id_agente, d_ini, d_fim))
        eventos.extend(_hist_recolhimentos(conn, id_agente, d_ini, d_fim))
        eventos.extend(_hist_amostras(conn, id_agente, d_ini, d_fim))
        eventos.extend(_hist_bri(conn, id_agente, d_ini, d_fim))
    finally:
        conn.close()

    eventos.sort(key=lambda item: (item["data"], item["origem"], item.get("localidade") or ""))
    por_dia = defaultdict(lambda: {"data": "", "total": 0, "por_origem": defaultdict(int), "eventos": []})
    por_origem = defaultdict(int)
    for evento in eventos:
        dia = por_dia[evento["data"]]
        dia["data"] = evento["data"]
        dia["total"] += 1
        dia["por_origem"][evento["origem"]] += 1
        dia["eventos"].append(evento)
        por_origem[evento["origem"]] += 1
    dias = []
    for dia in sorted(por_dia.values(), key=lambda item: item["data"]):
        dia["por_origem"] = dict(dia["por_origem"])
        dias.append(dia)
    return {
        "agente": dict(agente),
        "d_ini": d_ini,
        "d_fim": d_fim,
        "total": len(eventos),
        "dias_trabalhados": len(dias),
        "por_origem": dict(sorted(por_origem.items())),
        "dias": dias,
    }


def _clean(value):
    text = "" if value is None else str(value).strip()
    return text or None


def _table_exists(conn, table):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone())


def _hist_vetores(conn, id_agente, d_ini, d_fim):
    if not _table_exists(conn, "visitas"):
        return []
    rows = conn.execute(
        """
        SELECT v.data, v.tipo, COALESCE(l.nome, v.localidade) AS localidade,
               v.quarteirao, v.logradouro, v.numero, v.visita
          FROM visitas v
          JOIN visita_agentes va ON va.id_visita=v.id_visita
          LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
         WHERE va.id_agente=? AND v.data BETWEEN ? AND ?
         ORDER BY v.data, v.tipo, localidade
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    return [
        {
            "data": row["data"],
            "origem": "Vetores",
            "tipo": row["tipo"],
            "localidade": row["localidade"],
            "detalhe": _join_detail(row["visita"], f"Q {row['quarteirao']}" if row["quarteirao"] else None, row["logradouro"], row["numero"]),
        }
        for row in rows
    ]


def _hist_esporotricose(conn, id_agente, d_ini, d_fim):
    if not (_table_exists(conn, "esporotricose_visitas") and _table_exists(conn, "esporotricose_visita_agentes")):
        return []
    rows = conn.execute(
        """
        SELECT e.data, COALESCE(l.nome, e.localidade) AS localidade,
               e.quarteirao, e.logradouro, e.numero, e.visita,
               COUNT(DISTINCT an.id_animal) AS animais
          FROM esporotricose_visitas e
          JOIN esporotricose_visita_agentes va ON va.id_visita=e.id_visita
          LEFT JOIN localidades l ON l.id_localidade=e.id_localidade
          LEFT JOIN esporotricose_animais an ON an.id_visita=e.id_visita
         WHERE va.id_agente=? AND e.data BETWEEN ? AND ?
         GROUP BY e.id_visita
         ORDER BY e.data, localidade
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    return [
        {
            "data": row["data"],
            "origem": "Esporotricose",
            "tipo": "Esporotricose",
            "localidade": row["localidade"],
            "detalhe": _join_detail(row["visita"], f"{row['animais'] or 0} animais", f"Q {row['quarteirao']}" if row["quarteirao"] else None, row["logradouro"], row["numero"]),
        }
        for row in rows
    ]


def _hist_recolhimentos(conn, id_agente, d_ini, d_fim):
    if not (_table_exists(conn, "recolhimentos") and _table_exists(conn, "recolhimento_agentes")):
        return []
    rows = conn.execute(
        """
        SELECT r.data, r.localidade, r.total_materiais, r.pneu
          FROM recolhimentos r
          JOIN recolhimento_agentes ra ON ra.id_recolhimento=r.id_recolhimento
         WHERE ra.id_agente=? AND r.data BETWEEN ? AND ?
         ORDER BY r.data, r.localidade
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    return [
        {
            "data": row["data"],
            "origem": "Recolhimentos",
            "tipo": "Recolhimento",
            "localidade": row["localidade"],
            "detalhe": f"{row['total_materiais'] or 0} materiais, {row['pneu'] or 0} pneus",
        }
        for row in rows
    ]


def _hist_amostras(conn, id_agente, d_ini, d_fim):
    if not (_table_exists(conn, "amostras_animais") and _table_exists(conn, "amostra_animais_agentes")):
        return []
    rows = conn.execute(
        """
        SELECT a.data, a.localidade, a.motivo_visita, a.tipo_animal,
               a.quantidade, a.houve_acidente, a.houve_captura
          FROM amostras_animais a
          JOIN amostra_animais_agentes aa ON aa.id_amostra=a.id_amostra
         WHERE aa.id_agente=? AND a.data BETWEEN ? AND ?
         ORDER BY a.data, a.localidade
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    return [
        {
            "data": row["data"],
            "origem": "Amostras animais",
            "tipo": row["tipo_animal"] or "Amostra",
            "localidade": row["localidade"],
            "detalhe": _join_detail(row["motivo_visita"], f"{row['quantidade'] or 0} animais", f"acidente: {row['houve_acidente']}" if row["houve_acidente"] else None, f"captura: {row['houve_captura']}" if row["houve_captura"] else None),
        }
        for row in rows
    ]


def _hist_bri(conn, id_agente, d_ini, d_fim):
    if not (_table_exists(conn, "bri_registros") and _table_exists(conn, "bri_agentes")):
        return []
    rows = conn.execute(
        """
        SELECT b.data, b.localidade, b.destino_tratamento, b.local_tratamento,
               b.quarteirao, b.logradouro, b.numero,
               COALESCE(b.quantidade_carga,0) + COALESCE(b.quantidade_carga_extra,0) AS carga
          FROM bri_registros b
          JOIN bri_agentes ba ON ba.id_bri=b.id_bri
         WHERE ba.id_agente=? AND b.data BETWEEN ? AND ?
         ORDER BY b.data, b.localidade
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    return [
        {
            "data": row["data"],
            "origem": "BRI",
            "tipo": row["destino_tratamento"] or "BRI",
            "localidade": row["localidade"],
            "detalhe": _join_detail(row["local_tratamento"], f"{row['carga'] or 0:g} carga", f"Q {row['quarteirao']}" if row["quarteirao"] else None, row["logradouro"], row["numero"]),
        }
        for row in rows
    ]


def _join_detail(*parts):
    return " | ".join(str(part) for part in parts if part not in (None, ""))
