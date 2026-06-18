import sqlite3
from collections import defaultdict
import re
import unicodedata

from app_core import utils


AGENTE_ALIASES = {
    "ana beatriz": "Ana Beatriz",
    "ana_beatriz": "Ana Beatriz",
    "cecon": "Ceccon",
    "ceccon": "Ceccon",
    "fernado": "Fernando",
    "marcio": "Márcio",
    "m arcio": "Márcio",
    "m_arcio": "Márcio",
    "m rcio": "Márcio",
    "m_rcio": "Márcio",
}

EDITABLE_FIELDS = {
    "nome": "TEXT",
    "nome_completo": "TEXT",
    "matricula": "TEXT",
    "cargo": "TEXT",
    "ativo": "INTEGER",
    "data_inicio": "TEXT",
    "data_saida": "TEXT",
    "observacoes": "TEXT",
}


def chave_nome(nome):
    texto = unicodedata.normalize("NFKD", str(nome or ""))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9_]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_nome(nome):
    texto = str(nome or "").strip()
    if not texto:
        return ""
    chave = chave_nome(texto)
    return AGENTE_ALIASES.get(chave) or AGENTE_ALIASES.get(chave.replace(" ", "_")) or texto


def obter_ou_criar(conn_or_cur, nome):
    nome = normalizar_nome(nome)
    if not nome:
        return None
    cur = conn_or_cur.execute("SELECT id_agente FROM agentes WHERE nome=?", (nome,))
    row = cur.fetchone()
    if row:
        return row["id_agente"] if isinstance(row, sqlite3.Row) else row[0]
    try:
        cols = {row[1] for row in conn_or_cur.execute("PRAGMA table_info(agentes)").fetchall()}
    except Exception:
        cols = set()
    if "nome_completo" in cols:
        cur = conn_or_cur.execute("INSERT INTO agentes(nome, nome_completo) VALUES (?, ?)", (nome, nome))
    else:
        cur = conn_or_cur.execute("INSERT INTO agentes(nome) VALUES (?)", (nome,))
    return cur.lastrowid


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
                    nome_completo TEXT,
                    matricula TEXT,
                    cargo TEXT,
                    ativo INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
                    data_inicio TEXT,
                    data_saida TEXT,
                    observacoes TEXT
                )
            """)
            conn.execute("UPDATE agentes SET nome_completo=nome WHERE nome_completo IS NULL OR TRIM(nome_completo)=''")
            conn.commit()
            return
        if "nome_completo" not in cols:
            conn.execute("ALTER TABLE agentes ADD COLUMN nome_completo TEXT")
            conn.execute("UPDATE agentes SET nome_completo=nome WHERE nome_completo IS NULL OR TRIM(nome_completo)=''")
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
        conn.execute("UPDATE agentes SET nome_completo=nome WHERE nome_completo IS NULL OR TRIM(nome_completo)=''")
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
        where.append("(nome LIKE ? OR COALESCE(nome_completo,'') LIKE ? OR COALESCE(matricula,'') LIKE ?)")
        params.extend([f"%{busca}%", f"%{busca}%", f"%{busca}%"])
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
    nome = (dados.get("nome") or dados.get("nome_completo") or "").strip()
    if not nome:
        raise ValueError("Informe o nome do agente.")
    nome_completo = (dados.get("nome_completo") or nome).strip()
    ativo = 1 if str(dados.get("ativo", "1")) == "1" else 0
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO agentes(nome, nome_completo, matricula, cargo, ativo, data_inicio, data_saida, observacoes)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                nome,
                nome_completo,
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
    if campo in {"nome", "nome_completo"} and not (valor or "").strip():
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
        eventos.extend(_hist_ovitrampas(conn, id_agente, d_ini, d_fim))
        eventos.extend(_hist_laboratorio_larvas(conn, id_agente, d_ini, d_fim))
        eventos.extend(_hist_ovitrampas_leituras(conn, id_agente, d_ini, d_fim))
        eventos.extend(_hist_acoes_setor(conn, id_agente, d_ini, d_fim))
        eventos.extend(_hist_registro_geografico(conn, id_agente, d_ini, d_fim))
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


def _hist_ovitrampas(conn, id_agente, d_ini, d_fim):
    tabelas = (
        "ovitrampas_calendario_eventos",
        "ovitrampas_calendario_agentes",
        "ovitrampas_calendario_grupos",
    )
    if not all(_table_exists(conn, tabela) for tabela in tabelas):
        return []
    rows = conn.execute(
        """
        SELECT e.data, e.movimento, e.ciclo, e.observacoes,
               g.nome AS grupo, g.localidades
          FROM ovitrampas_calendario_eventos e
          JOIN ovitrampas_calendario_agentes ea ON ea.id_evento=e.id_evento
          LEFT JOIN ovitrampas_calendario_grupos g ON g.id_grupo=e.id_grupo
         WHERE ea.id_agente=?
           AND e.data BETWEEN ? AND ?
           AND e.movimento<>'feriado'
         ORDER BY e.data, e.id_evento
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    labels = {
        "instalacao": "Instalação",
        "troca": "Troca",
        "retirada": "Retirada",
    }
    return [
        {
            "data": row["data"],
            "origem": "Ovitrampas",
            "tipo": labels.get(row["movimento"], row["movimento"] or "Ovitrampa"),
            "localidade": row["grupo"] or row["localidades"],
            "detalhe": _join_detail(row["ciclo"], row["localidades"], row["observacoes"]),
        }
        for row in rows
    ]


def _hist_acoes_setor(conn, id_agente, d_ini, d_fim):
    if not (_table_exists(conn, "acoes_setor") and _table_exists(conn, "acoes_setor_agentes")):
        return []
    rows = conn.execute(
        """
        SELECT a.data, a.tipo, a.hora_inicio, a.hora_fim, a.localidade,
               a.endereco, a.local, a.publico_aproximado, a.tema, a.contexto
          FROM acoes_setor a
          JOIN acoes_setor_agentes aa ON aa.id_acao=a.id_acao
         WHERE aa.id_agente=? AND a.data BETWEEN ? AND ?
         ORDER BY a.data, COALESCE(a.hora_inicio,''), a.localidade
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    labels = {
        "educativa": "Ação educativa",
        "limpeza": "Ação de limpeza",
    }
    return [
        {
            "data": row["data"],
            "origem": "Ações do Setor",
            "tipo": labels.get(row["tipo"], row["tipo"] or "Acao"),
            "localidade": row["localidade"],
            "detalhe": _join_detail(
                _intervalo_hora(row["hora_inicio"], row["hora_fim"]),
                row["local"],
                row["endereco"],
                row["tema"],
                f"{row['publico_aproximado']} público" if row["publico_aproximado"] is not None else None,
                row["contexto"],
            ),
        }
        for row in rows
    ]


def _hist_laboratorio_larvas(conn, id_agente, d_ini, d_fim):
    if not (_table_exists(conn, "resultados_laboratorio") and _table_exists(conn, "agentes")):
        return []
    rows = conn.execute(
        """
        SELECT COALESCE(rl.data_leitura, rl.data_coleta) AS data,
               COUNT(DISTINCT rl.id_resultado) AS leituras,
               COUNT(DISTINCT rl.num_tubo) AS tubos,
               SUM(CASE WHEN COALESCE(rl.aegypt_larvas,0) + COALESCE(rl.aegypt_pupas,0)
                           + COALESCE(rl.aegypt_exuvias,0) + COALESCE(rl.aegypt_adulto,0)
                           + COALESCE(rl.albopictus_larvas,0) + COALESCE(rl.albopictus_pupas,0)
                           + COALESCE(rl.albopictus_exuvias,0) + COALESCE(rl.albopictus_adulto,0)
                           + COALESCE(rl.outra_larvas,0) + COALESCE(rl.outra_pupas,0)
                           + COALESCE(rl.outra_exuvias,0) + COALESCE(rl.outra_adulto,0) > 0
                        THEN 1 ELSE 0 END) AS positivas
          FROM resultados_laboratorio rl
          JOIN agentes ag ON lower(trim(ag.nome)) = lower(trim(rl.laboratorista))
         WHERE ag.id_agente=?
           AND COALESCE(rl.data_leitura, rl.data_coleta) BETWEEN ? AND ?
         GROUP BY COALESCE(rl.data_leitura, rl.data_coleta)
         ORDER BY data
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    return [
        {
            "data": row["data"],
            "origem": "Laboratório",
            "tipo": "Leitura de larvas",
            "localidade": "",
            "detalhe": _join_detail(
                f"{row['leituras'] or 0} leituras",
                f"{row['tubos'] or 0} tubos",
                f"{row['positivas'] or 0} positivas",
            ),
        }
        for row in rows
    ]


def _hist_ovitrampas_leituras(conn, id_agente, d_ini, d_fim):
    if not _table_exists(conn, "ovitrampas_leituras"):
        return []
    rows = conn.execute(
        """
        SELECT COALESCE(data_leitura, data_coleta, data_envio_contagem) AS data,
               distrito AS localidade,
               COUNT(DISTINCT id_leitura) AS leituras,
               SUM(COALESCE(ovos,0)) AS ovos,
               SUM(CASE WHEN COALESCE(ovos,0)>0 THEN 1 ELSE 0 END) AS positivas
          FROM ovitrampas_leituras
         WHERE id_laboratorista=?
           AND COALESCE(data_leitura, data_coleta, data_envio_contagem) BETWEEN ? AND ?
         GROUP BY COALESCE(data_leitura, data_coleta, data_envio_contagem), distrito
         ORDER BY data, distrito
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    return [
        {
            "data": row["data"],
            "origem": "Laboratório ovitrampas",
            "tipo": "Leitura de ovos",
            "localidade": row["localidade"],
            "detalhe": _join_detail(
                f"{row['leituras'] or 0} leituras",
                f"{row['positivas'] or 0} positivas",
                f"{row['ovos'] or 0} ovos",
            ),
        }
        for row in rows
    ]


def _hist_registro_geografico(conn, id_agente, d_ini, d_fim):
    tabelas = ("registro_geografico_imoveis", "registro_geografico_imovel_agentes")
    if not all(_table_exists(conn, tabela) for tabela in tabelas):
        return []
    rows = conn.execute(
        """
        SELECT i.data_atualizacao AS data,
               i.localidade,
               i.quarteirao,
               COUNT(DISTINCT i.id_imovel) AS imoveis,
               COUNT(DISTINCT NULLIF(TRIM(i.logradouro),'')) AS logradouros
          FROM registro_geografico_imoveis i
          JOIN registro_geografico_imovel_agentes ia ON ia.id_imovel=i.id_imovel
         WHERE ia.id_agente=?
           AND i.data_atualizacao BETWEEN ? AND ?
         GROUP BY i.data_atualizacao, i.localidade, i.quarteirao
         ORDER BY i.data_atualizacao, i.localidade, CAST(i.quarteirao AS INTEGER), i.quarteirao
        """,
        (id_agente, d_ini, d_fim),
    ).fetchall()
    return [
        {
            "data": row["data"],
            "origem": "Registro Geográfico",
            "tipo": "Atualização de RG",
            "localidade": row["localidade"],
            "detalhe": _join_detail(
                f"Q {int(float(row['quarteirao']))}" if str(row["quarteirao"] or "").replace(".", "", 1).isdigit() else f"Q {row['quarteirao']}",
                f"{row['imoveis'] or 0} imóveis",
                f"{row['logradouros'] or 0} logradouros",
            ),
        }
        for row in rows
    ]


def _intervalo_hora(inicio, fim):
    if inicio and fim:
        return f"{inicio}-{fim}"
    return inicio or fim


def _join_detail(*parts):
    return " | ".join(str(part) for part in parts if part not in (None, ""))
