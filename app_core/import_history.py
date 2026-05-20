import json
from datetime import datetime


STATUS_LABELS = {
    "upload": "Upload recebido",
    "dry_run_ok": "Verificado",
    "dry_run_erro": "Erro na verificacao",
    "confirmado": "Gravado",
    "erro_confirmacao": "Erro ao gravar",
    "cancelado": "Cancelado",
}

STATUS_CLASSES = {
    "upload": "azul",
    "dry_run_ok": "verde",
    "dry_run_erro": "vermelho",
    "confirmado": "verde",
    "erro_confirmacao": "vermelho",
    "cancelado": "cinza",
}


def garantir_tabela_importacoes(get_db, conn=None):
    fechar = conn is None
    conn = conn or get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS importacoes (
            id_importacao INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id        TEXT    NOT NULL UNIQUE,
            usuario       TEXT,
            arquivos_json TEXT    NOT NULL DEFAULT '[]',
            status        TEXT    NOT NULL DEFAULT 'upload',
            dry_run_ok    INTEGER,
            commit_ok     INTEGER,
            sumario_json  TEXT,
            erro          TEXT,
            criado_em     TEXT    NOT NULL,
            atualizado_em TEXT    NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_importacoes_criado ON importacoes(criado_em)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_importacoes_status ON importacoes(status)")
    conn.commit()
    if fechar:
        conn.close()


def registrar_importacao(get_db, job_id, arquivos, status="upload", usuario=""):
    agora = datetime.now().isoformat()
    conn = get_db()
    try:
        garantir_tabela_importacoes(get_db, conn)
        conn.execute("""
            INSERT OR REPLACE INTO importacoes
                (job_id, usuario, arquivos_json, status, criado_em, atualizado_em)
            VALUES (
                ?,
                COALESCE((SELECT usuario FROM importacoes WHERE job_id=?), ?),
                ?,
                ?,
                COALESCE((SELECT criado_em FROM importacoes WHERE job_id=?), ?),
                ?
            )
        """, (
            job_id, job_id, usuario,
            json.dumps(list(arquivos), ensure_ascii=False),
            status, job_id, agora, agora,
        ))
        conn.commit()
    finally:
        conn.close()


def atualizar_importacao(get_db, job_id, status, dry_run_ok=None, commit_ok=None, sumario=None, erro=None):
    agora = datetime.now().isoformat()
    sets = ["status=?", "atualizado_em=?"]
    params = [status, agora]
    if dry_run_ok is not None:
        sets.append("dry_run_ok=?")
        params.append(1 if dry_run_ok else 0)
    if commit_ok is not None:
        sets.append("commit_ok=?")
        params.append(1 if commit_ok else 0)
    if sumario is not None:
        sets.append("sumario_json=?")
        params.append(json.dumps(sumario, ensure_ascii=False))
    if erro is not None:
        sets.append("erro=?")
        params.append(str(erro)[:2000])
    params.append(job_id)
    conn = get_db()
    try:
        garantir_tabela_importacoes(get_db, conn)
        conn.execute(f"UPDATE importacoes SET {', '.join(sets)} WHERE job_id=?", params)
        conn.commit()
    finally:
        conn.close()


def listar_importacoes_recentes(get_db, limite=10):
    limite = max(1, min(int(limite or 10), 50))
    conn = get_db()
    try:
        garantir_tabela_importacoes(get_db, conn)
        rows = conn.execute("""
            SELECT job_id, usuario, arquivos_json, status, dry_run_ok, commit_ok,
                   sumario_json, erro, criado_em, atualizado_em
            FROM importacoes
            ORDER BY datetime(criado_em) DESC, id_importacao DESC
            LIMIT ?
        """, (limite,)).fetchall()
    finally:
        conn.close()

    importacoes = []
    for r in rows:
        d = dict(r)
        try:
            d["arquivos"] = json.loads(d.get("arquivos_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            d["arquivos"] = []
        d["status_label"] = STATUS_LABELS.get(d.get("status"), d.get("status") or "Sem status")
        d["status_classe"] = STATUS_CLASSES.get(d.get("status"), "cinza")
        importacoes.append(d)
    return importacoes
