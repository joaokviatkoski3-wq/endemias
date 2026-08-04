"""Consultas somente leitura para a central da integracao Conta Ovos.

A central usa o espelho local sincronizado. Ela nao chama a API remota e nao
altera filas, cadastros ou contagens durante a navegacao.
"""

from app_core import db as db_core


def _limit(value, default=100, maximum=500):
    try:
        return max(1, min(int(value or default), maximum))
    except (TypeError, ValueError):
        return default


def _integer(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("Ano e semana precisam ser numeros inteiros.")


def _prepare(conn):
    """Confere o espelho sem criar ou adaptar schema durante uma consulta."""
    missing = [
        table for table in (
            "ovitrampas_armadilhas", "ovitrampas_ocorrencias_conta_ovos"
        ) if not db_core.table_exists(conn, table)
    ]
    if missing:
        raise RuntimeError(
            "O espelho local Conta Ovos ainda nao esta preparado: " + ", ".join(missing)
        )
    return db_core.table_exists(conn, "contaovos_execucoes")


def _open(target):
    """Abre o destino ou reaproveita uma conexao de ensaio temporaria."""
    if hasattr(target, "execute"):
        return target, False
    return db_core.connect(target), True


def _where_contagens(filters):
    clauses, params = [], []
    ano = _integer(filters.get("ano"))
    semana = _integer(filters.get("semana"))
    if ano is not None:
        clauses.append("c.ano=?")
        params.append(ano)
    if semana is not None:
        clauses.append("c.semana=?")
        params.append(semana)
    if filters.get("data_inicio"):
        clauses.append("c.data>=?")
        params.append(filters["data_inicio"])
    if filters.get("data_fim"):
        clauses.append("c.data<=?")
        params.append(filters["data_fim"])
    if filters.get("positivas") == "1":
        clauses.append("COALESCE(c.ovos,0)>0")
    if filters.get("resultado"):
        clauses.append("LOWER(COALESCE(c.resultado,''))=LOWER(?)")
        params.append(filters["resultado"])
    if filters.get("busca"):
        term = f"%{str(filters['busca']).strip().lower()}%"
        clauses.append(
            "(" + " OR ".join(
                f"LOWER(COALESCE(CAST({column} AS TEXT),'')) LIKE ?"
                for column in (
                    "c.id_contagem", "c.ovitrampa_id", "a.localidade",
                    "a.quarteirao", "a.rua", "c.resultado",
                )
            ) + ")"
        )
        params.extend([term] * 6)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def resumo(target):
    conn, close = _open(target)
    try:
        tem_execucoes = _prepare(conn)
        totais = db_core.serialize_row(conn.execute(
            """SELECT
                   (SELECT COUNT(*) FROM ovitrampas_armadilhas) AS armadilhas,
                   (SELECT COUNT(*) FROM ovitrampas_armadilhas
                     WHERE COALESCE(ativo,1)=1) AS armadilhas_ativas,
                   COUNT(*) AS contagens,
                   COUNT(DISTINCT ovitrampa_id) AS ovitrampas_com_contagem,
                   COALESCE(SUM(ovos),0) AS ovos,
                   COALESCE(SUM(CASE WHEN COALESCE(ovos,0)>0 THEN 1 ELSE 0 END),0) AS positivas,
                   MAX(data) AS ultima_data,
                   MAX(importado_em) AS ultima_importacao
                 FROM ovitrampas_ocorrencias_conta_ovos"""
        ).fetchone())
        semanas = [db_core.serialize_row(row) for row in conn.execute(
            """SELECT ano, semana, COUNT(*) AS contagens,
                      COALESCE(SUM(ovos),0) AS ovos,
                      COALESCE(SUM(CASE WHEN COALESCE(ovos,0)>0 THEN 1 ELSE 0 END),0) AS positivas
                 FROM ovitrampas_ocorrencias_conta_ovos
                GROUP BY ano, semana
                ORDER BY ano DESC, semana DESC
                LIMIT 12"""
        )]
        execucoes = []
        if tem_execucoes:
            execucoes = [db_core.serialize_row(row) for row in conn.execute(
                """SELECT id_execucao, tipo, iniciado_em, finalizado_em, status,
                          itens_ok, itens_erro, resumo_sanitizado
                     FROM contaovos_execucoes
                    ORDER BY iniciado_em DESC, id_execucao DESC
                    LIMIT 5"""
            )]
    finally:
        if close:
            conn.close()
    return {"totais": totais, "semanas": semanas, "execucoes": execucoes}


def listar_contagens(target, filters=None, limit=None):
    filters = filters or {}
    conn, close = _open(target)
    try:
        _prepare(conn)
        where, params = _where_contagens(filters)
        rows = [db_core.serialize_row(row) for row in conn.execute(
            f"""SELECT c.*, a.rua, a.numero, a.complemento, a.localidade,
                       a.quarteirao, a.responsavel, a.telefone_responsavel,
                       a.ativo AS armadilha_ativa
                  FROM ovitrampas_ocorrencias_conta_ovos c
                  LEFT JOIN ovitrampas_armadilhas a ON a.ovitrampa_id=c.ovitrampa_id
                  {where}
                 ORDER BY c.data DESC NULLS LAST, c.ano DESC, c.semana DESC,
                          c.id_contagem DESC
                 LIMIT ?""",
            [*params, _limit(limit)],
        )]
        total = conn.execute(
            f"""SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos c
                  LEFT JOIN ovitrampas_armadilhas a ON a.ovitrampa_id=c.ovitrampa_id
                  {where}""",
            params,
        ).fetchone()[0]
    finally:
        if close:
            conn.close()
    return {"total": total, "registros": rows}


def listar_ovitrampas(target, filters=None, limit=None):
    filters = filters or {}
    clauses, params = [], []
    if filters.get("ativo") in ("0", "1"):
        clauses.append("COALESCE(a.ativo,1)=?")
        params.append(int(filters["ativo"]))
    if filters.get("localidade"):
        clauses.append("LOWER(COALESCE(a.localidade,''))=LOWER(?)")
        params.append(filters["localidade"])
    if filters.get("busca"):
        term = f"%{str(filters['busca']).strip().lower()}%"
        clauses.append("(" + " OR ".join(
            f"LOWER(COALESCE(CAST({column} AS TEXT),'')) LIKE ?"
            for column in ("a.ovitrampa_id", "a.rua", "a.localidade", "a.quarteirao", "a.responsavel")
        ) + ")")
        params.extend([term] * 5)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn, close = _open(target)
    try:
        _prepare(conn)
        rows = [db_core.serialize_row(row) for row in conn.execute(
            f"""SELECT a.*, COUNT(c.id_contagem) AS contagens,
                       COALESCE(SUM(c.ovos),0) AS ovos_total,
                       COALESCE(SUM(CASE WHEN COALESCE(c.ovos,0)>0 THEN 1 ELSE 0 END),0) AS positivas,
                       MAX(c.data) AS ultima_contagem
                  FROM ovitrampas_armadilhas a
                  LEFT JOIN ovitrampas_ocorrencias_conta_ovos c ON c.ovitrampa_id=a.ovitrampa_id
                  {where}
                 GROUP BY a.ovitrampa_id, a.rua, a.numero, a.complemento, a.bairro,
                          a.localizacao, a.localidade, a.responsavel, a.telefone_responsavel,
                          a.quarteirao, a.latitude, a.longitude, a.ativo, a.arquivo_origem,
                          a.atualizado_em
                 ORDER BY LOWER(CAST(a.ovitrampa_id AS TEXT))
                 LIMIT ?""",
            [*params, _limit(limit)],
        )]
        total = conn.execute(
            f"SELECT COUNT(*) FROM ovitrampas_armadilhas a {where}", params
        ).fetchone()[0]
    finally:
        if close:
            conn.close()
    return {"total": total, "registros": rows}


def detalhes_ovitrampa(target, ovitrampa_id):
    conn, close = _open(target)
    try:
        _prepare(conn)
        armadilha = conn.execute(
            "SELECT * FROM ovitrampas_armadilhas WHERE ovitrampa_id=?", (str(ovitrampa_id),)
        ).fetchone()
        contagens = [db_core.serialize_row(row) for row in conn.execute(
            """SELECT * FROM ovitrampas_ocorrencias_conta_ovos
                 WHERE ovitrampa_id=?
                 ORDER BY data DESC NULLS LAST, ano DESC, semana DESC, id_contagem DESC
                 LIMIT 100""",
            (str(ovitrampa_id),),
        )]
    finally:
        if close:
            conn.close()
    return {"armadilha": db_core.serialize_row(armadilha) if armadilha else None, "contagens": contagens}
