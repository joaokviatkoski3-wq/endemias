"""Consultas somente leitura da sub-area Ovitrampas dentro do Conta Ovos.

Diferente de `contaovos_consultas.py` (visao geral, que mistura CSV legado e
API), este modulo filtra explicitamente por proveniencia API onde o pedido de
arquitetura exige (contagens e monitoramento) e usa o espelho remoto proprio
(`contaovos_registro_ovitrampas`) para cadastro e mapa. Responsavel, telefone
e demais complementos ficam sempre marcados como locais, nunca como remotos.
"""

from app_core import contaovos_sync
from app_core import db as db_core
from app_core import ovitrampas


API_SOURCE = contaovos_sync.SOURCE_LABEL
COORDINATE_TOLERANCE = 0.0005  # ~50 m; alerta informativo, nao bloqueante.


class EspelhoContaOvosIndisponivel(RuntimeError):
    """O schema local necessario para consulta ainda nao esta disponivel."""


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


def _is_postgresql(conn):
    return getattr(conn, "backend", "sqlite") == "postgresql"


def _round_one(expression):
    return f"ROUND(CAST(({expression}) AS NUMERIC), 1)"


def _open(target):
    if hasattr(target, "execute"):
        return target, False
    return db_core.connect(target), True


def _require_tables(conn, tables):
    missing = [table for table in tables if not db_core.table_exists(conn, table)]
    if missing:
        raise EspelhoContaOvosIndisponivel(
            "O espelho local necessario ainda nao esta preparado: "
            + ", ".join(missing)
        )


def _where_contagens_api(filters):
    """Mesmos filtros da central geral, sempre restritos a proveniencia API."""
    clauses, params = ["c.arquivo_origem=?"], [API_SOURCE]
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
    if filters.get("ovitrampa_id"):
        clauses.append("c.ovitrampa_id=?")
        params.append(str(filters["ovitrampa_id"]))
    if filters.get("busca"):
        term = f"%{str(filters['busca']).strip().lower()}%"
        clauses.append(
            "(" + " OR ".join(
                f"LOWER(COALESCE(CAST({column} AS TEXT),'')) LIKE ?"
                for column in ("c.id_contagem", "c.ovitrampa_id", "a.localidade", "a.rua")
            ) + ")"
        )
        params.extend([term] * 4)
    return "WHERE " + " AND ".join(clauses), params


def resumo_ovitrampas(target):
    """Contagem de apoio para o cabecalho da sub-area Ovitrampas."""
    conn, close = _open(target)
    try:
        _require_tables(conn, ("ovitrampas_ocorrencias_conta_ovos", "ovitrampas_armadilhas"))
        tem_registro = db_core.table_exists(conn, "contaovos_registro_ovitrampas")
        tem_execucoes = db_core.table_exists(conn, "contaovos_execucoes")
        totais = db_core.serialize_row(conn.execute(
            """SELECT COUNT(*) AS contagens_api,
                      COUNT(DISTINCT ovitrampa_id) AS ovitrampas_com_contagem_api,
                      COALESCE(SUM(ovos),0) AS ovos_api,
                      MAX(data) AS ultima_data_api
                 FROM ovitrampas_ocorrencias_conta_ovos
                WHERE arquivo_origem=?""",
            (API_SOURCE,),
        ).fetchone())
        totais["cadastro_remoto"] = (
            conn.execute(f"SELECT COUNT(*) FROM contaovos_registro_ovitrampas").fetchone()[0]
            if tem_registro else 0
        )
        execucoes = []
        if tem_execucoes:
            execucoes = [db_core.serialize_row(row) for row in conn.execute(
                """SELECT tipo, iniciado_em, finalizado_em, status, itens_ok, itens_erro
                     FROM contaovos_execucoes
                    WHERE tipo IN ('sincronizacao_contagens', 'sincronizacao_registro_ovitrampas')
                    ORDER BY iniciado_em DESC, id_execucao DESC
                    LIMIT 10"""
            )]
        return {"totais": totais, "execucoes_recentes": execucoes, "registro_disponivel": tem_registro}
    finally:
        if close:
            conn.close()


def listar_contagens_api(target, filters=None, limit=None):
    """Contagens restritas a proveniencia API, com filtros de periodo/busca."""
    filters = filters or {}
    conn, close = _open(target)
    try:
        _require_tables(conn, ("ovitrampas_ocorrencias_conta_ovos", "ovitrampas_armadilhas"))
        where, params = _where_contagens_api(filters)
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
        return {"total": total, "registros": rows, "fonte": API_SOURCE}
    finally:
        if close:
            conn.close()


def monitoramento_api(target, filters=None):
    """Ranking e localidades criticas calculados somente sobre contagens API."""
    filters = filters or {}
    conn, close = _open(target)
    try:
        _require_tables(conn, ("ovitrampas_ocorrencias_conta_ovos", "ovitrampas_armadilhas"))
        where, params = _where_contagens_api(filters)
        positividade = _round_one(
            "100.0 * SUM(CASE WHEN COALESCE(c.ovos,0)>0 THEN 1 ELSE 0 END) / COUNT(*)"
        )
        join_base = f"""
            FROM ovitrampas_ocorrencias_conta_ovos c
            LEFT JOIN ovitrampas_armadilhas a ON a.ovitrampa_id=c.ovitrampa_id
            {where}
        """
        totais = db_core.serialize_row(conn.execute(
            f"""SELECT COUNT(*) AS contagens,
                       COUNT(DISTINCT c.ovitrampa_id) AS ovitrampas,
                       SUM(CASE WHEN COALESCE(c.ovos,0)>0 THEN 1 ELSE 0 END) AS positivas,
                       COUNT(DISTINCT CASE WHEN COALESCE(c.ovos,0)>0 THEN c.ovitrampa_id END) AS ovitrampas_positivas,
                       COALESCE(SUM(c.ovos),0) AS ovos
                  {join_base}""",
            params,
        ).fetchone())

        ranking = [db_core.serialize_row(row) for row in conn.execute(
            f"""SELECT c.ovitrampa_id,
                       COALESCE(a.localidade, '-') AS localidade,
                       COALESCE(a.rua, '-') AS rua,
                       COUNT(*) AS contagens,
                       SUM(CASE WHEN COALESCE(c.ovos,0)>0 THEN 1 ELSE 0 END) AS positivas,
                       COALESCE(SUM(c.ovos),0) AS ovos,
                       {positividade} AS positividade
                  {join_base}
                 GROUP BY c.ovitrampa_id, COALESCE(a.localidade, '-'), COALESCE(a.rua, '-')
                HAVING SUM(CASE WHEN COALESCE(c.ovos,0)>0 THEN 1 ELSE 0 END) > 0
                 ORDER BY positivas DESC, ovos DESC, positividade DESC, c.ovitrampa_id
                 LIMIT 80""",
            params,
        )]

        localidades = [db_core.serialize_row(row) for row in conn.execute(
            f"""SELECT COALESCE(a.localidade, '-') AS localidade,
                       COUNT(DISTINCT c.ovitrampa_id) AS ovitrampas,
                       SUM(CASE WHEN COALESCE(c.ovos,0)>0 THEN 1 ELSE 0 END) AS positivas,
                       COALESCE(SUM(c.ovos),0) AS ovos
                  {join_base}
                 GROUP BY COALESCE(a.localidade, '-')
                 ORDER BY ovos DESC, positivas DESC, localidade
                 LIMIT 40""",
            params,
        )]
        return {"totais": totais, "ranking": ranking, "localidades": localidades, "fonte": API_SOURCE}
    finally:
        if close:
            conn.close()


def _armadilhas_por_chave(conn):
    """Indice local {chave_comparacao: linha} para reconciliar com o remoto."""
    rows = conn.execute(
        "SELECT ovitrampa_id, localidade, quarteirao, rua, numero, responsavel, "
        "telefone_responsavel, ativo, latitude, longitude FROM ovitrampas_armadilhas"
    ).fetchall()
    index = {}
    for row in rows:
        row = db_core.serialize_row(row)
        chave = ovitrampas.chave_comparacao_ovitrampa_id(row["ovitrampa_id"])
        if chave:
            index[chave] = row
    return index


def listar_cadastro_remoto(target, filters=None, limit=None):
    """Cadastro vindo apenas do espelho remoto, com complementos locais anexados
    e claramente identificados como locais."""
    filters = filters or {}
    conn, close = _open(target)
    try:
        _require_tables(conn, ("contaovos_registro_ovitrampas", "ovitrampas_armadilhas"))
        clauses, params = [], []
        if filters.get("busca"):
            term = f"%{str(filters['busca']).strip().lower()}%"
            clauses.append(
                "LOWER(CAST(r.ovitrampa_id_remoto AS TEXT)) LIKE ? "
                "OR LOWER(COALESCE(r.municipio,'')) LIKE ?"
            )
            params.extend([term, term])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = [db_core.serialize_row(row) for row in conn.execute(
            f"""SELECT r.* FROM contaovos_registro_ovitrampas r {where}
                 ORDER BY LOWER(CAST(r.ovitrampa_id_remoto AS TEXT))
                 LIMIT ?""",
            [*params, _limit(limit)],
        )]
        total = conn.execute(
            f"SELECT COUNT(*) FROM contaovos_registro_ovitrampas r {where}", params
        ).fetchone()[0]

        armadilhas = _armadilhas_por_chave(conn)
        for row in rows:
            chave = ovitrampas.chave_comparacao_ovitrampa_id(row["ovitrampa_id_remoto"])
            local = armadilhas.get(chave)
            row["complemento_local"] = (
                {
                    "ovitrampa_id_local": local["ovitrampa_id"],
                    "localidade": local["localidade"],
                    "quarteirao": local["quarteirao"],
                    "rua": local["rua"],
                    "numero": local["numero"],
                    "responsavel": local["responsavel"],
                    "telefone_responsavel": local["telefone_responsavel"],
                    "ativo": local["ativo"],
                }
                if local else None
            )
        return {"total": total, "registros": rows, "fonte": "Cadastro publico Conta Ovos"}
    finally:
        if close:
            conn.close()


def detalhes_cadastro_remoto(target, ovitrampa_id_remoto):
    conn, close = _open(target)
    try:
        _require_tables(conn, ("contaovos_registro_ovitrampas", "ovitrampas_armadilhas"))
        row = conn.execute(
            "SELECT * FROM contaovos_registro_ovitrampas WHERE ovitrampa_id_remoto=?",
            (str(ovitrampa_id_remoto),),
        ).fetchone()
        if not row:
            return None
        remoto = db_core.serialize_row(row)
        chave = ovitrampas.chave_comparacao_ovitrampa_id(remoto["ovitrampa_id_remoto"])
        local = None
        if chave:
            armadilha = conn.execute(
                "SELECT * FROM ovitrampas_armadilhas"
            ).fetchall()
            for candidate in armadilha:
                candidate = db_core.serialize_row(candidate)
                if ovitrampas.chave_comparacao_ovitrampa_id(candidate["ovitrampa_id"]) == chave:
                    local = candidate
                    break
        return {"remoto": remoto, "complemento_local": local}
    finally:
        if close:
            conn.close()


def mapa_pontos(target):
    """Coordenadas remotas com quarteirao/localidade LOCAIS anexados apenas
    para leitura; a API nunca altera nem recalcula o territorio local."""
    conn, close = _open(target)
    try:
        _require_tables(conn, ("contaovos_registro_ovitrampas", "ovitrampas_armadilhas"))
        rows = [db_core.serialize_row(row) for row in conn.execute(
            """SELECT ovitrampa_id_remoto, latitude, longitude, sincronizado_em
                 FROM contaovos_registro_ovitrampas
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL"""
        )]
        armadilhas = _armadilhas_por_chave(conn)
        pontos = []
        for row in rows:
            chave = ovitrampas.chave_comparacao_ovitrampa_id(row["ovitrampa_id_remoto"])
            local = armadilhas.get(chave)
            pontos.append({
                "ovitrampa_id_remoto": row["ovitrampa_id_remoto"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "sincronizado_em": row["sincronizado_em"],
                "localidade_local": local["localidade"] if local else None,
                "quarteirao_local": local["quarteirao"] if local else None,
                "responsavel_local": local["responsavel"] if local else None,
                "cadastro_local_encontrado": local is not None,
            })
        return {"pontos": pontos}
    finally:
        if close:
            conn.close()


def sincronizacao_status(target):
    """Ultima execucao de cada fluxo de sincronizacao GET, somente leitura."""
    conn, close = _open(target)
    try:
        if not db_core.table_exists(conn, "contaovos_execucoes"):
            return {"fluxos": []}
        rows = [db_core.serialize_row(row) for row in conn.execute(
            """SELECT tipo, iniciado_em, finalizado_em, status, itens_ok, itens_erro, id_execucao
                 FROM contaovos_execucoes
                ORDER BY tipo, iniciado_em DESC, id_execucao DESC"""
        )]
        ultimos = {}
        for row in rows:
            ultimos.setdefault(row["tipo"], row)
        for row in ultimos.values():
            row.pop("id_execucao", None)
        return {"fluxos": sorted(ultimos.values(), key=lambda r: r["tipo"])}
    finally:
        if close:
            conn.close()


def divergencias(target):
    """Comparacoes informativas entre espelho remoto e cadastro local.

    Nunca resolve, exclui ou sobrescreve nada; apenas lista o que um humano
    pode querer conferir manualmente.
    """
    conn, close = _open(target)
    try:
        _require_tables(conn, ("ovitrampas_armadilhas",))
        tem_registro = db_core.table_exists(conn, "contaovos_registro_ovitrampas")
        sem_cadastro_local = []
        coordenadas_divergentes = []
        if tem_registro:
            remotos = [db_core.serialize_row(row) for row in conn.execute(
                "SELECT ovitrampa_id_remoto, latitude, longitude FROM contaovos_registro_ovitrampas"
            )]
            armadilhas = _armadilhas_por_chave(conn)
            for remoto in remotos:
                chave = ovitrampas.chave_comparacao_ovitrampa_id(remoto["ovitrampa_id_remoto"])
                local = armadilhas.get(chave)
                if not local:
                    sem_cadastro_local.append(remoto["ovitrampa_id_remoto"])
                    continue
                if (
                    remoto["latitude"] is not None and remoto["longitude"] is not None
                    and local["latitude"] is not None and local["longitude"] is not None
                ):
                    delta = (
                        abs(float(remoto["latitude"]) - float(local["latitude"]))
                        + abs(float(remoto["longitude"]) - float(local["longitude"]))
                    )
                    if delta > COORDINATE_TOLERANCE:
                        coordenadas_divergentes.append({
                            "ovitrampa_id_remoto": remoto["ovitrampa_id_remoto"],
                            "ovitrampa_id_local": local["ovitrampa_id"],
                            "latitude_remota": remoto["latitude"],
                            "longitude_remota": remoto["longitude"],
                            "latitude_local": local["latitude"],
                            "longitude_local": local["longitude"],
                        })

        contagens_sem_registro = []
        if tem_registro and db_core.table_exists(conn, "ovitrampas_ocorrencias_conta_ovos"):
            registro_chaves = {
                ovitrampas.chave_comparacao_ovitrampa_id(row[0])
                for row in conn.execute(
                    "SELECT ovitrampa_id_remoto FROM contaovos_registro_ovitrampas"
                ).fetchall()
            }
            contagens_ids = conn.execute(
                "SELECT DISTINCT ovitrampa_id FROM ovitrampas_ocorrencias_conta_ovos WHERE arquivo_origem=?",
                (API_SOURCE,),
            ).fetchall()
            for (ovitrampa_id,) in contagens_ids:
                if ovitrampas.chave_comparacao_ovitrampa_id(ovitrampa_id) not in registro_chaves:
                    contagens_sem_registro.append(ovitrampa_id)

        return {
            "registro_disponivel": tem_registro,
            "sem_cadastro_local": sorted(sem_cadastro_local),
            "coordenadas_divergentes": coordenadas_divergentes,
            "contagens_sem_registro_cadastro": sorted(contagens_sem_registro),
        }
    finally:
        if close:
            conn.close()
