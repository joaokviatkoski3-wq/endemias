"""Leituras exclusivas do LIRAa, sem gerar notificações ou lançamentos gerais."""

from datetime import date, datetime
from app_core import db, liraa, liraa_kobo, laboratorio_lancamentos, liraa_operacional as op

CAMPOS = tuple(f"{specie}_{forma}" for specie in ("aegypt", "albopictus", "outra") for forma in ("larvas", "pupas"))


def painel(target, args):
    """Contexto compartilhado pela aba do laboratório e pela consulta direta.

    Não cria schema na abertura do laboratório de rotina.
    """
    result = dict(rows=[], ciclos=[], erro=None, total_pendentes=0, pagina=1,
                  proxima=False, ciclo=str(args.get("ciclo") or ""),
                  pendentes=str(args.get("pendentes", "1")), campos=CAMPOS,
                  depositos=op.DEPOSITOS, hoje=date.today().isoformat())
    conn = db.connect(target)
    try:
        if not all(db.table_exists(conn, table) for table in
                   ("liraa_ciclos", "liraa_visitas", "liraa_visita_tubitos", "liraa_leituras")):
            result["erro"] = "Aplique a migração 0026 para habilitar as leituras LIRAA."
            return result
        result["ciclos"] = [db.serialize_row(row) for row in conn.execute(
            "SELECT * FROM liraa_ciclos ORDER BY ano DESC,id_ciclo DESC")]
        result["total_pendentes"] = conn.execute("""SELECT COUNT(*) FROM liraa_visita_tubitos t
            LEFT JOIN liraa_leituras l ON l.id_tubito=t.id_tubito WHERE l.id_tubito IS NULL""").fetchone()[0]
    finally:
        conn.close()
    try:
        result["pagina"] = max(1, int(args.get("pagina", "1")))
        ciclo = int(result["ciclo"]) if result["ciclo"] else None
        rows = listar(target, ciclo, result["pendentes"] != "0", (result["pagina"]-1)*100)
        result.update(rows=rows[:100], proxima=len(rows)>100)
    except (ValueError, liraa.LiraaError) as exc:
        result["erro"] = str(exc)
    return result


def ensure_schema(conn):
    liraa_kobo.ensure_schema(conn)
    if getattr(conn, "backend", "sqlite") == "sqlite":
        with conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS liraa_leituras (
                id_tubito INTEGER PRIMARY KEY REFERENCES liraa_visita_tubitos(id_tubito) ON DELETE CASCADE,
                data_leitura TEXT NOT NULL,laboratorista TEXT NOT NULL,id_usuario INTEGER NOT NULL,
                aegypt_larvas INTEGER NOT NULL DEFAULT 0 CHECK(aegypt_larvas>=0),
                aegypt_pupas INTEGER NOT NULL DEFAULT 0 CHECK(aegypt_pupas>=0),
                albopictus_larvas INTEGER NOT NULL DEFAULT 0 CHECK(albopictus_larvas>=0),
                albopictus_pupas INTEGER NOT NULL DEFAULT 0 CHECK(albopictus_pupas>=0),
                outra_larvas INTEGER NOT NULL DEFAULT 0 CHECK(outra_larvas>=0),
                outra_pupas INTEGER NOT NULL DEFAULT 0 CHECK(outra_pupas>=0),
                observacoes TEXT NOT NULL DEFAULT '',atualizado_em TEXT NOT NULL)""")
    if not db.table_exists(conn, "liraa_leituras"):
        raise liraa.LiraaError("Aplique a migração 0026 para as leituras e boletins LIRAa.")


def listar(target, ciclo=None, pendentes=False, offset=0):
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        conditions, params = [], []
        if ciclo:
            conditions.append("v.id_ciclo=?")
            params.append(ciclo)
        if pendentes:
            conditions.append("l.id_tubito IS NULL")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return [db.serialize_row(r) for r in conn.execute("""SELECT t.*,v.id_ciclo,v.data_visita,
            v.localidade_informada,v.quarteirao,v.logradouro,v.numero AS numero_imovel,
            l.id_tubito AS leitura_id,l.data_leitura,l.laboratorista,l.id_usuario,l.observacoes,l.atualizado_em,
            l.aegypt_larvas,l.aegypt_pupas,l.albopictus_larvas,l.albopictus_pupas,l.outra_larvas,l.outra_pupas
            FROM liraa_visita_tubitos t JOIN liraa_visitas v ON v.id_visita=t.id_visita
            LEFT JOIN liraa_leituras l ON l.id_tubito=t.id_tubito""" + where +
            " ORDER BY v.data_visita,t.id_tubito LIMIT 101 OFFSET ?", (*params, max(0, int(offset))))]
    finally:
        conn.close()


def salvar(target, id_tubito, payload, usuario, auditar=None):
    if not laboratorio_lancamentos.pode_lancar(usuario):
        raise liraa.LiraaError("Sem permissão para lançar resultados laboratoriais.")
    counts = {}
    for field in CAMPOS:
        raw = str(payload.get(field, "")).strip()
        if not raw.isascii() or not raw.isdigit() or not 0 <= int(raw) <= 1000000:
            raise liraa.LiraaError("Preencha todas as quantidades com inteiros entre 0 e 1.000.000; zero indica ausência.")
        counts[field] = int(raw)
    try:
        reading_date = date.fromisoformat(payload.get("data_leitura", ""))
    except (ValueError, TypeError):
        raise liraa.LiraaError("Data de leitura inválida.") from None
    if reading_date > date.today():
        raise liraa.LiraaError("A leitura não pode ter data futura.")
    obs = str(payload.get("observacoes") or "").strip()
    if len(obs) > 2000:
        raise liraa.LiraaError("Observações: máximo de 2.000 caracteres.")
    code = str(payload.get("codigo_deposito") or "").strip().upper()
    if code and (usuario.get("nivel") != "admin" or code not in op.DEPOSITOS):
        raise liraa.LiraaError("Somente administrador pode corrigir a classificação para A1/A2/B/C/D1/D2/E.")
    conn = db.connect(target)
    try:
        ensure_schema(conn)
        if getattr(conn, "backend", "sqlite") == "sqlite":
            conn.execute("BEGIN IMMEDIATE")
        with conn:
            lock = " FOR UPDATE" if getattr(conn, "backend", "sqlite") == "postgresql" else ""
            tube = conn.execute("SELECT * FROM liraa_visita_tubitos WHERE id_tubito=?" + lock, (id_tubito,)).fetchone()
            if not tube:
                raise liraa.LiraaError("Tubito não encontrado.")
            visit = conn.execute("SELECT data_visita FROM liraa_visitas WHERE id_visita=?", (tube["id_visita"],)).fetchone()
            if reading_date.isoformat() < visit["data_visita"]:
                raise liraa.LiraaError("A leitura não pode preceder a coleta.")
            old = conn.execute("SELECT * FROM liraa_leituras WHERE id_tubito=?", (id_tubito,)).fetchone()
            if old and usuario.get("nivel") != "admin":
                raise liraa.LiraaError("Somente administrador pode corrigir uma leitura já salva.")
            if old and str(payload.get("versao", "")) != old["atualizado_em"]:
                raise liraa.LiraaError("Esta leitura foi alterada. Atualize a página antes de corrigir.")
            fields = ["id_tubito", "data_leitura", "laboratorista", "id_usuario", *CAMPOS, "observacoes", "atualizado_em"]
            updated = datetime.now().isoformat(timespec="microseconds")
            values = [id_tubito, reading_date.isoformat(), usuario["nome"], usuario["id_usuario"], *counts.values(), obs, updated]
            conn.execute(f"INSERT INTO liraa_leituras ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)}) "
                         "ON CONFLICT(id_tubito) DO UPDATE SET " + ','.join(f"{f}=excluded.{f}" for f in fields[1:]), values)
            if code:
                conn.execute("UPDATE liraa_visita_tubitos SET codigo_deposito=? WHERE id_tubito=?", (code,id_tubito))
            if auditar:
                auditar(conn, {"id_tubito": id_tubito, "anterior": db.serialize_row(old) if old else None,
                                "quantidades": counts, "data_leitura": reading_date.isoformat(),
                                "deposito_anterior": tube['codigo_deposito'], "deposito_atual": code or tube['codigo_deposito']})
    finally:
        conn.close()
