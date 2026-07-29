import os
import uuid

from app_core import agentes as agentes_core
from app_core import db as db_core
from app_core import normalizadores
from app_core import recolhimentos as db_helpers
from app_core import utils as utils_core


def lab_aegypti_total_sql(alias="rl"):
    return f"""
        COALESCE({alias}.aegypt_larvas, 0) + COALESCE({alias}.aegypt_pupas, 0) +
        COALESCE({alias}.aegypt_exuvias, 0) + COALESCE({alias}.aegypt_adulto, 0)
    """


LAB_AEGYPTI_TOTAL_SQL = lab_aegypti_total_sql()


ORDER_SQL = {
    "data_desc": (
        "v.data DESC, CASE WHEN v.hora_inicio IS NULL THEN 1 ELSE 0 END, "
        "v.hora_inicio DESC, v.id_visita DESC"
    ),
    "data_asc": (
        "v.data ASC, CASE WHEN v.hora_inicio IS NULL THEN 1 ELSE 0 END, "
        "v.hora_inicio ASC, v.id_visita ASC"
    ),
    "localidade_asc": "LOWER(COALESCE(l.nome, v.localidade, '')), v.data DESC",
    "tipo_asc": "LOWER(COALESCE(v.tipo, '')), v.data DESC",
    "endereco_asc": "LOWER(COALESCE(v.logradouro, '')), COALESCE(v.numero, ''), v.data DESC",
}


class VisitaNaoEncontrada(ValueError):
    pass


class VisitaInvalida(ValueError):
    pass


class ColetaComResultado(ValueError):
    pass


def _values(args, key):
    if hasattr(args, "getlist"):
        values = args.getlist(key)
    else:
        raw = args.get(key, [])
        values = raw if isinstance(raw, list) else [raw]
    return [str(value).strip() for value in values if str(value or "").strip()]


def build_where(args):
    where, params = utils_core.build_visit_where(args, localidade_fallback=True)

    busca = str(args.get("busca") or "").strip()
    if busca:
        term = f"%{busca}%"
        where += """
            AND (
                LOWER(COALESCE(v.id_visita, '')) LIKE LOWER(?) OR
                LOWER(COALESCE(v.logradouro, '')) LIKE LOWER(?) OR
                LOWER(COALESCE(v.numero, '')) LIKE LOWER(?) OR
                LOWER(COALESCE(CAST(v.quarteirao AS TEXT), '')) LIKE LOWER(?) OR
                LOWER(COALESCE(v.morador, '')) LIKE LOWER(?) OR
                LOWER(COALESCE(v.observacoes, '')) LIKE LOWER(?) OR
                EXISTS (
                    SELECT 1 FROM visita_agentes vab
                    JOIN agentes ab ON ab.id_agente=vab.id_agente
                    WHERE vab.id_visita=v.id_visita
                      AND LOWER(ab.nome) LIKE LOWER(?)
                ) OR
                EXISTS (
                    SELECT 1 FROM coletas cb
                    WHERE cb.id_visita=v.id_visita
                      AND (LOWER(COALESCE(cb.num_tubo, '')) LIKE LOWER(?)
                           OR LOWER(COALESCE(cb.tipo_deposito, '')) LIKE LOWER(?))
                ) OR
                EXISTS (
                    SELECT 1 FROM tratamentos tb
                    WHERE tb.id_visita=v.id_visita
                      AND LOWER(COALESCE(tb.tipo, '')) LIKE LOWER(?)
                )
            )
        """
        params.extend([term] * 10)

    resultados = _values(args, "resultado")
    if resultados:
        where += f" AND COALESCE(v.visita, '') IN ({','.join('?' * len(resultados))})"
        params.extend(resultados)

    imoveis = _values(args, "imovel")
    if imoveis:
        where += f" AND COALESCE(v.tipo_imovel, '') IN ({','.join('?' * len(imoveis))})"
        params.extend(imoveis)

    depositos = _values(args, "deposito")
    if depositos:
        where += f"""
            AND EXISTS (
                SELECT 1 FROM depositos_inspecionados df
                WHERE df.id_visita=v.id_visita
                  AND COALESCE(df.tipo_deposito, '') IN ({','.join('?' * len(depositos))})
            )
        """
        params.extend(depositos)

    tratamentos = _values(args, "tratamento")
    if tratamentos:
        where += f"""
            AND (
                EXISTS (
                    SELECT 1 FROM tratamentos tf
                    WHERE tf.id_visita=v.id_visita
                      AND COALESCE(tf.tipo, '') IN ({','.join('?' * len(tratamentos))})
                ) OR
                EXISTS (
                    SELECT 1 FROM depositos_inspecionados dtf
                    WHERE dtf.id_visita=v.id_visita
                      AND COALESCE(dtf.tipo_tratamento, '') IN ({','.join('?' * len(tratamentos))})
                )
            )
        """
        params.extend(tratamentos)
        params.extend(tratamentos)

    coleta = str(args.get("coleta") or "").strip()
    if coleta == "com":
        where += " AND EXISTS(SELECT 1 FROM coletas cf WHERE cf.id_visita=v.id_visita)"
    elif coleta == "sem":
        where += " AND NOT EXISTS(SELECT 1 FROM coletas cf WHERE cf.id_visita=v.id_visita)"

    tratado = str(args.get("tratado") or "").strip()
    tratamento_exists = """
        EXISTS(
            SELECT 1 FROM tratamentos ttf
            WHERE ttf.id_visita=v.id_visita
              AND (COALESCE(ttf.qtd_depositos_tratados, 0) > 0 OR
                   COALESCE(ttf.quantidade_carga, 0) > 0 OR
                   TRIM(COALESCE(ttf.tipo, '')) <> '')
        ) OR EXISTS(
            SELECT 1 FROM depositos_inspecionados dttf
            WHERE dttf.id_visita=v.id_visita
              AND (COALESCE(dttf.tratado, 0) > 0 OR
                   COALESCE(dttf.qtd_carga, 0) > 0 OR
                   TRIM(COALESCE(dttf.tipo_tratamento, '')) <> '')
        )
    """
    if tratado == "com":
        where += f" AND ({tratamento_exists})"
    elif tratado == "sem":
        where += f" AND NOT ({tratamento_exists})"

    laboratorio = str(args.get("laboratorio") or "").strip()
    if laboratorio == "positivo":
        where += f"""
            AND EXISTS(
                SELECT 1 FROM coletas clf
                JOIN resultados_laboratorio rlf ON rlf.id_coleta=clf.id_coleta
                WHERE clf.id_visita=v.id_visita AND ({lab_aegypti_total_sql('rlf')}) > 0
            )
        """
    elif laboratorio == "negativo":
        where += f"""
            AND EXISTS(
                SELECT 1 FROM coletas clf
                JOIN resultados_laboratorio rlf ON rlf.id_coleta=clf.id_coleta
                WHERE clf.id_visita=v.id_visita
            )
            AND NOT EXISTS(
                SELECT 1 FROM coletas clf
                JOIN resultados_laboratorio rlf ON rlf.id_coleta=clf.id_coleta
                WHERE clf.id_visita=v.id_visita AND ({lab_aegypti_total_sql('rlf')}) > 0
            )
        """
    elif laboratorio == "pendente":
        where += """
            AND EXISTS(
                SELECT 1 FROM coletas clf
                LEFT JOIN resultados_laboratorio rlf ON rlf.id_coleta=clf.id_coleta
                WHERE clf.id_visita=v.id_visita AND rlf.id_resultado IS NULL
            )
        """
    elif laboratorio == "sem_coleta":
        where += " AND NOT EXISTS(SELECT 1 FROM coletas clf WHERE clf.id_visita=v.id_visita)"

    return where, params


def order_sql(value):
    return ORDER_SQL.get(str(value or "").strip(), ORDER_SQL["data_desc"])


def filter_options(target):
    conn, close = _open_connection(target)

    def distinct(sql):
        values = [
            row[0]
            for row in conn.execute(sql).fetchall()
            if row[0] not in (None, "")
        ]
        return sorted(values, key=lambda value: str(value).casefold())

    try:
        treatments = distinct(
            """
            SELECT tipo FROM (
                SELECT DISTINCT TRIM(tipo) AS tipo FROM tratamentos
                UNION
                SELECT DISTINCT TRIM(tipo_tratamento) AS tipo FROM depositos_inspecionados
            ) opcoes WHERE tipo IS NOT NULL AND tipo <> ''
            """
        )
        return {
            "tipos": distinct(
                "SELECT DISTINCT tipo FROM visitas WHERE tipo IS NOT NULL"
            ),
            "localidades": distinct(
                """SELECT DISTINCT COALESCE(l.nome, v.localidade) AS nome
                     FROM visitas v
                     LEFT JOIN localidades l
                       ON l.id_localidade=v.id_localidade
                    WHERE COALESCE(l.nome, v.localidade) IS NOT NULL"""
            ),
            "agentes": distinct(
                """SELECT DISTINCT a.nome
                     FROM agentes a
                     JOIN visita_agentes va ON va.id_agente=a.id_agente"""
            ),
            "resultados": distinct(
                "SELECT DISTINCT visita FROM visitas WHERE visita IS NOT NULL"
            ),
            "imoveis": distinct(
                """SELECT DISTINCT tipo_imovel
                     FROM visitas
                    WHERE tipo_imovel IS NOT NULL"""
            ),
            "depositos": distinct(
                """SELECT DISTINCT tipo_deposito
                     FROM depositos_inspecionados
                    WHERE tipo_deposito IS NOT NULL"""
            ),
            "tratamentos": treatments,
        }
    finally:
        if close:
            conn.close()


def listar(target, args, pagina=1, por_pagina=30):
    where, params = build_where(args)
    ordem = order_sql(args.get("ordem"))
    base = f"""FROM visitas v
               LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
               {where}"""
    conn, close = _open_connection(target)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) {base}",
            params,
        ).fetchone()[0]
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        pagina = min(max(1, pagina), total_paginas)
        agentes_agg = db_helpers._agentes_aggregate(conn, "nomes.nome")
        tubos_agg = db_helpers._agentes_aggregate(conn, "tubos.num_tubo")
        rows = conn.execute(
            f"""
            SELECT v.id_visita, v.data, v.tipo,
                   COALESCE(l.nome, v.localidade) AS localidade,
                   v.quarteirao, v.logradouro, v.numero, v.visita,
                   v.tipo_imovel, v.ciclo, v.sequencia, v.morador,
                   v.hora_inicio, v.hora_fim, v.lado, v.agua_sanepar,
                   v.observacoes,
                   (
                       SELECT {agentes_agg}
                         FROM (
                               SELECT DISTINCT ag.nome
                                 FROM visita_agentes vag
                                 JOIN agentes ag
                                   ON ag.id_agente=vag.id_agente
                                WHERE vag.id_visita=v.id_visita
                         ) nomes
                   ) AS agentes,
                   COALESCE((
                       SELECT SUM(di.inspecionado)
                         FROM depositos_inspecionados di
                        WHERE di.id_visita=v.id_visita
                   ), 0) AS depositos_inspecionados,
                   COALESCE((
                       SELECT SUM(di.eliminado)
                         FROM depositos_inspecionados di
                        WHERE di.id_visita=v.id_visita
                   ), 0) AS depositos_eliminados,
                   COALESCE((
                       SELECT SUM(di.tratado)
                         FROM depositos_inspecionados di
                        WHERE di.id_visita=v.id_visita
                   ), 0) +
                   COALESCE((
                       SELECT SUM(t.qtd_depositos_tratados)
                         FROM tratamentos t
                        WHERE t.id_visita=v.id_visita
                   ), 0) AS depositos_tratados,
                   COALESCE((
                       SELECT COUNT(*)
                         FROM tratamentos t
                        WHERE t.id_visita=v.id_visita
                   ), 0) AS tratamentos_total,
                   COALESCE((
                       SELECT COUNT(*)
                         FROM coletas c
                        WHERE c.id_visita=v.id_visita
                   ), 0) AS coletas_total,
                   (
                       SELECT {tubos_agg}
                         FROM (
                               SELECT DISTINCT c.num_tubo
                                 FROM coletas c
                                WHERE c.id_visita=v.id_visita
                                  AND TRIM(COALESCE(c.num_tubo, '')) <> ''
                         ) tubos
                   ) AS tubos,
                   CASE
                     WHEN EXISTS(
                       SELECT 1
                         FROM coletas c
                         JOIN resultados_laboratorio rl
                           ON rl.id_coleta=c.id_coleta
                        WHERE c.id_visita=v.id_visita
                          AND ({LAB_AEGYPTI_TOTAL_SQL}) > 0
                     ) THEN 'positivo'
                     WHEN EXISTS(
                       SELECT 1
                         FROM coletas c
                         LEFT JOIN resultados_laboratorio rl
                           ON rl.id_coleta=c.id_coleta
                        WHERE c.id_visita=v.id_visita
                          AND rl.id_resultado IS NULL
                     ) THEN 'pendente'
                     WHEN EXISTS(
                       SELECT 1
                         FROM coletas c
                         JOIN resultados_laboratorio rl
                           ON rl.id_coleta=c.id_coleta
                        WHERE c.id_visita=v.id_visita
                     ) THEN 'negativo'
                     ELSE 'sem_coleta'
                   END AS laboratorio_status
            {base}
            ORDER BY {ordem}
            LIMIT ? OFFSET ?
            """,
            params + [por_pagina, (pagina - 1) * por_pagina],
        ).fetchall()

        resumo = conn.execute(
            f"""
            WITH filtradas AS (
                SELECT v.id_visita {base}
            )
            SELECT
                COUNT(*) AS visitas,
                COALESCE(SUM(
                    CASE
                      WHEN LOWER(COALESCE(v.visita, ''))
                           IN ('normal','recuperado')
                      THEN 1 ELSE 0
                    END
                ), 0) AS acessados,
                COALESCE(SUM((
                    SELECT SUM(di.inspecionado)
                      FROM depositos_inspecionados di
                     WHERE di.id_visita=v.id_visita
                )), 0) AS depositos_inspecionados,
                COALESCE(SUM((
                    SELECT SUM(di.eliminado)
                      FROM depositos_inspecionados di
                     WHERE di.id_visita=v.id_visita
                )), 0) AS depositos_eliminados,
                COALESCE(SUM((
                    SELECT COUNT(*)
                      FROM coletas c
                     WHERE c.id_visita=v.id_visita
                )), 0) AS coletas,
                COALESCE(SUM(
                    CASE WHEN EXISTS(
                        SELECT 1
                          FROM coletas c
                          JOIN resultados_laboratorio rl
                            ON rl.id_coleta=c.id_coleta
                         WHERE c.id_visita=v.id_visita
                           AND ({LAB_AEGYPTI_TOTAL_SQL}) > 0
                    ) THEN 1 ELSE 0 END
                ), 0) AS positivas
              FROM filtradas f
              JOIN visitas v ON v.id_visita=f.id_visita
            """,
            params,
        ).fetchone()
        return {
            "total": total,
            "total_paginas": total_paginas,
            "pagina": pagina,
            "resumo": dict(resumo) if resumo else {},
            "registros": [
                db_helpers._serializar_linha(row) for row in rows
            ],
        }
    finally:
        if close:
            conn.close()


def detalhar(target, id_visita):
    conn, close = _open_connection(target)
    try:
        agentes_agg = db_helpers._agentes_aggregate(conn, "nomes.nome")
        visita = conn.execute(
            f"""
            SELECT v.*, COALESCE(l.nome, v.localidade) AS localidade_nome,
                   (
                       SELECT {agentes_agg}
                         FROM (
                               SELECT DISTINCT a.nome
                                 FROM visita_agentes va
                                 JOIN agentes a
                                   ON a.id_agente=va.id_agente
                                WHERE va.id_visita=v.id_visita
                         ) nomes
                   ) AS agentes
              FROM visitas v
              LEFT JOIN localidades l
                ON l.id_localidade=v.id_localidade
             WHERE v.id_visita=?
            """,
            (id_visita,),
        ).fetchone()
        if not visita:
            raise VisitaNaoEncontrada("Visita não encontrada.")

        depositos = conn.execute(
            """SELECT id, tipo_deposito, inspecionado, eliminado, tratado,
                      tipo_tratamento, qtd_carga
                 FROM depositos_inspecionados
                WHERE id_visita=?
                ORDER BY id""",
            (id_visita,),
        ).fetchall()
        tratamentos = conn.execute(
            """SELECT id, tipo, quantidade_carga, qtd_depositos_tratados
                 FROM tratamentos
                WHERE id_visita=?
                ORDER BY id""",
            (id_visita,),
        ).fetchall()
        coletas = conn.execute(
            """SELECT c.id_coleta, c.num_tubo, c.codigo_deposito,
                      c.tipo_deposito, c.deposito_eliminado,
                      rl.id_resultado, rl.data_coleta, rl.data_leitura,
                      rl.laboratorista, rl.aegypt_larvas,
                      rl.aegypt_pupas, rl.aegypt_exuvias,
                      rl.aegypt_adulto, rl.albopictus_larvas,
                      rl.albopictus_pupas, rl.albopictus_exuvias,
                      rl.albopictus_adulto, rl.outra_larvas,
                      rl.outra_pupas, rl.outra_exuvias, rl.outra_adulto
                 FROM coletas c
                 LEFT JOIN resultados_laboratorio rl
                   ON rl.id_coleta=c.id_coleta
                WHERE c.id_visita=?
                ORDER BY c.num_tubo, c.id_coleta""",
            (id_visita,),
        ).fetchall()
        focos = conn.execute(
            """SELECT id_foco, codigo, num_tubo, gera_notificacao,
                      status_notificacao, data_entrega, observacoes
                 FROM focos_positivos
                WHERE id_visita=?
                ORDER BY id_foco""",
            (id_visita,),
        ).fetchall()
        return {
            "visita": db_helpers._serializar_linha(visita),
            "depositos": [
                db_helpers._serializar_linha(row) for row in depositos
            ],
            "tratamentos": [
                db_helpers._serializar_linha(row) for row in tratamentos
            ],
            "coletas": [
                db_helpers._serializar_linha(row) for row in coletas
            ],
            "focos": [
                db_helpers._serializar_linha(row) for row in focos
            ],
        }
    finally:
        if close:
            conn.close()


def editar(target, id_visita, dados):
    conn, close = _open_connection(target)
    try:
        atual = conn.execute(
            "SELECT * FROM visitas WHERE id_visita=?",
            (id_visita,),
        ).fetchone()
        if not atual:
            raise VisitaNaoEncontrada("Visita não encontrada.")
        atual_dict = db_helpers._serializar_linha(atual)

        localidade_bruta = dados.get(
            "localidade", atual_dict.get("localidade")
        )
        localidade = normalizadores.normalizar_localidade(localidade_bruta)
        payload = {
            "tipo": _limpar_texto(
                dados.get("tipo", atual_dict.get("tipo"))
            ),
            "data": _limpar_texto(
                dados.get("data", atual_dict.get("data"))
            ),
            "hora_inicio": _limpar_texto(
                dados.get("hora_inicio", atual_dict.get("hora_inicio"))
            ),
            "hora_fim": _limpar_texto(
                dados.get("hora_fim", atual_dict.get("hora_fim"))
            ),
            "ciclo": _limpar_int(
                dados.get("ciclo", atual_dict.get("ciclo"))
            ),
            "localidade": localidade,
            "id_localidade": None,
            "logradouro": _limpar_texto(
                dados.get("logradouro", atual_dict.get("logradouro"))
            ),
            "numero": _limpar_texto(
                dados.get("numero", atual_dict.get("numero"))
            ),
            "quarteirao": _limpar_int(
                dados.get("quarteirao", atual_dict.get("quarteirao"))
            ),
            "sequencia": _limpar_texto(
                dados.get("sequencia", atual_dict.get("sequencia"))
            ),
            "morador": _limpar_texto(
                dados.get("morador", atual_dict.get("morador"))
            ),
            "tipo_imovel": _limpar_texto(
                dados.get("tipo_imovel", atual_dict.get("tipo_imovel"))
            ),
            "visita": _limpar_texto(
                dados.get("visita", atual_dict.get("visita"))
            ),
            "lado": _limpar_texto(
                dados.get("lado", atual_dict.get("lado"))
            ),
            "agua_sanepar": _limpar_flag(
                dados.get(
                    "agua_sanepar", atual_dict.get("agua_sanepar")
                )
            ),
            "observacoes": _limpar_texto(
                dados.get("observacoes", atual_dict.get("observacoes"))
            ),
        }
        if not payload["data"]:
            raise VisitaInvalida("Informe a data da visita.")
        if localidade:
            payload["id_localidade"] = _obter_ou_criar_localidade(
                conn, localidade
            )

        conn.execute(
            """UPDATE visitas SET
                   tipo=?, data=?, hora_inicio=?, hora_fim=?, ciclo=?,
                   localidade=?, id_localidade=?, logradouro=?, numero=?,
                   quarteirao=?, sequencia=?, morador=?, tipo_imovel=?,
                   visita=?, lado=?, agua_sanepar=?, observacoes=?
                 WHERE id_visita=?""",
            (
                payload["tipo"],
                payload["data"],
                payload["hora_inicio"],
                payload["hora_fim"],
                payload["ciclo"],
                payload["localidade"],
                payload["id_localidade"],
                payload["logradouro"],
                payload["numero"],
                payload["quarteirao"],
                payload["sequencia"],
                payload["morador"],
                payload["tipo_imovel"],
                payload["visita"],
                payload["lado"],
                payload["agua_sanepar"],
                payload["observacoes"],
                id_visita,
            ),
        )

        agentes_atuais = conn.execute(
            """SELECT a.nome
                 FROM visita_agentes va
                 JOIN agentes a ON a.id_agente=va.id_agente
                WHERE va.id_visita=?
                ORDER BY a.nome""",
            (id_visita,),
        ).fetchall()
        agentes_padrao = ", ".join(row["nome"] for row in agentes_atuais)
        nomes_agentes = _split_agentes_edicao(
            dados.get("agentes", agentes_padrao)
        )
        conn.execute(
            "DELETE FROM visita_agentes WHERE id_visita=?",
            (id_visita,),
        )
        for nome in nomes_agentes:
            id_agente = agentes_core.obter_ou_criar(conn, nome)
            if id_agente:
                conn.execute(
                    """INSERT INTO visita_agentes(id_visita, id_agente)
                       VALUES (?,?)
                       ON CONFLICT DO NOTHING""",
                    (id_visita, id_agente),
                )

        if "depositos" in dados:
            conn.execute(
                "DELETE FROM depositos_inspecionados WHERE id_visita=?",
                (id_visita,),
            )
            for deposito in dados.get("depositos") or []:
                tipo_deposito = _limpar_texto(
                    deposito.get("tipo_deposito")
                )
                if not tipo_deposito:
                    continue
                conn.execute(
                    """INSERT INTO depositos_inspecionados
                       (id_visita, tipo_deposito, inspecionado, eliminado,
                        tratado, tipo_tratamento, qtd_carga)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        id_visita,
                        tipo_deposito,
                        _limpar_int(deposito.get("inspecionado")) or 0,
                        _limpar_int(deposito.get("eliminado")) or 0,
                        _limpar_int(deposito.get("tratado")) or 0,
                        _limpar_texto(
                            deposito.get("tipo_tratamento")
                        ),
                        _limpar_numero(deposito.get("qtd_carga")) or 0,
                    ),
                )

        if "tratamentos" in dados:
            conn.execute(
                "DELETE FROM tratamentos WHERE id_visita=?",
                (id_visita,),
            )
            for tratamento in dados.get("tratamentos") or []:
                tipo_tratamento = _limpar_texto(tratamento.get("tipo"))
                carga = (
                    _limpar_numero(tratamento.get("quantidade_carga"))
                    or 0
                )
                quantidade = (
                    _limpar_int(
                        tratamento.get("qtd_depositos_tratados")
                    )
                    or 0
                )
                if not tipo_tratamento and not carga and not quantidade:
                    continue
                conn.execute(
                    """INSERT INTO tratamentos
                       (id_visita, tipo, quantidade_carga,
                        qtd_depositos_tratados)
                       VALUES (?,?,?,?)""",
                    (id_visita, tipo_tratamento, carga, quantidade),
                )

        if "coletas" in dados:
            existentes = {
                row["id_coleta"]: dict(row)
                for row in conn.execute(
                    "SELECT * FROM coletas WHERE id_visita=?",
                    (id_visita,),
                )
            }
            mantidas = set()
            for coleta in dados.get("coletas") or []:
                coleta_id = _limpar_texto(coleta.get("id_coleta"))
                valores = (
                    _limpar_texto(coleta.get("num_tubo")),
                    _limpar_texto(coleta.get("codigo_deposito")),
                    _limpar_texto(coleta.get("tipo_deposito")),
                    _limpar_flag(coleta.get("deposito_eliminado")) or 0,
                )
                if coleta_id in existentes:
                    conn.execute(
                        """UPDATE coletas
                              SET num_tubo=?, codigo_deposito=?,
                                  tipo_deposito=?, deposito_eliminado=?
                            WHERE id_coleta=? AND id_visita=?""",
                        valores + (coleta_id, id_visita),
                    )
                    conn.execute(
                        """UPDATE resultados_laboratorio
                              SET num_tubo=?
                            WHERE id_coleta=?""",
                        (valores[0], coleta_id),
                    )
                    conn.execute(
                        "UPDATE focos_positivos SET num_tubo=? WHERE id_coleta=?",
                        (valores[0], coleta_id),
                    )
                    mantidas.add(coleta_id)
                else:
                    coleta_id = f"manual-{uuid.uuid4().hex}"
                    conn.execute(
                        """INSERT INTO coletas
                           (id_coleta, id_visita, num_tubo,
                            codigo_deposito, tipo_deposito,
                            deposito_eliminado)
                           VALUES (?,?,?,?,?,?)""",
                        (coleta_id, id_visita) + valores,
                    )
                    mantidas.add(coleta_id)

            removidas = set(existentes) - mantidas
            for coleta_id in removidas:
                possui_resultado = conn.execute(
                    """SELECT 1
                         FROM resultados_laboratorio
                        WHERE id_coleta=?
                        LIMIT 1""",
                    (coleta_id,),
                ).fetchone()
                if possui_resultado:
                    raise ColetaComResultado(
                        "Uma coleta com resultado laboratorial não pode "
                        "ser removida nesta página."
                    )
                conn.execute(
                    "DELETE FROM focos_positivos WHERE id_coleta=?",
                    (coleta_id,),
                )
                conn.execute(
                    """DELETE FROM coletas
                        WHERE id_coleta=? AND id_visita=?""",
                    (coleta_id, id_visita),
                )

        conn.execute(
            """UPDATE focos_positivos
                  SET tipo_trabalho=?, data=?, id_localidade=?,
                      localidade=?, quarteirao=?, logradouro=?, numero=?,
                      nome_morador=?, tipo_imovel=?, agentes=?
                WHERE id_visita=?""",
            (
                payload["tipo"],
                payload["data"],
                payload["id_localidade"],
                payload["localidade"],
                payload["quarteirao"],
                payload["logradouro"],
                payload["numero"],
                payload["morador"],
                payload["tipo_imovel"],
                ", ".join(nomes_agentes),
                id_visita,
            ),
        )
        conn.commit()
        return {
            "antes": atual_dict,
            "depois": payload,
            "agentes": nomes_agentes,
            "depositos": (
                len(dados.get("depositos") or [])
                if "depositos" in dados
                else None
            ),
            "tratamentos": (
                len(dados.get("tratamentos") or [])
                if "tratamentos" in dados
                else None
            ),
            "coletas": (
                len(dados.get("coletas") or [])
                if "coletas" in dados
                else None
            ),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        if close:
            conn.close()


def _obter_ou_criar_localidade(conn, nome):
    row = conn.execute(
        "SELECT id_localidade FROM localidades WHERE nome=?",
        (nome,),
    ).fetchone()
    if row:
        return row[0]
    return db_helpers._insert_id(
        conn,
        "INSERT INTO localidades(nome, cod_localidade) VALUES (?,NULL)",
        (nome,),
        "id_localidade",
    )


def _open_connection(target):
    if hasattr(target, "execute"):
        return target, False
    if isinstance(target, (str, bytes, os.PathLike, db_core.DatabaseTarget)):
        return db_core.connect(target), True
    raise TypeError("Destino ou conexao de banco invalido.")


def _limpar_texto(valor):
    texto = str(valor or "").strip()
    return texto or None


def _limpar_int(valor):
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return int(float(texto.replace(",", ".")))
    except ValueError:
        return None


def _limpar_numero(valor):
    texto = str(valor or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _limpar_bool(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    return str(valor).strip().lower() in {
        "1",
        "sim",
        "true",
        "yes",
        "on",
    }


def _limpar_flag(valor):
    resultado = _limpar_bool(valor)
    return None if resultado is None else int(resultado)


def _split_agentes_edicao(valor):
    texto = str(valor or "").replace("\n", ",").replace(";", ",")
    nomes = []
    for parte in texto.split(","):
        nome = agentes_core.normalizar_nome(parte)
        if nome and nome not in nomes:
            nomes.append(nome)
    return nomes
