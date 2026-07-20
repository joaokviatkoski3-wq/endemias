from app_core import utils as utils_core


def lab_aegypti_total_sql(alias="rl"):
    return f"""
        COALESCE({alias}.aegypt_larvas, 0) + COALESCE({alias}.aegypt_pupas, 0) +
        COALESCE({alias}.aegypt_exuvias, 0) + COALESCE({alias}.aegypt_adulto, 0)
    """


LAB_AEGYPTI_TOTAL_SQL = lab_aegypti_total_sql()


ORDER_SQL = {
    "data_desc": "v.data DESC, COALESCE(v.hora_inicio, '') DESC, v.id_visita DESC",
    "data_asc": "v.data ASC, COALESCE(v.hora_inicio, '') ASC, v.id_visita ASC",
    "localidade_asc": "COALESCE(l.nome, v.localidade, '') COLLATE NOCASE, v.data DESC",
    "tipo_asc": "COALESCE(v.tipo, '') COLLATE NOCASE, v.data DESC",
    "endereco_asc": "COALESCE(v.logradouro, '') COLLATE NOCASE, COALESCE(v.numero, ''), v.data DESC",
}


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
                COALESCE(v.id_visita, '') LIKE ? OR
                COALESCE(v.logradouro, '') LIKE ? OR
                COALESCE(v.numero, '') LIKE ? OR
                CAST(COALESCE(v.quarteirao, '') AS TEXT) LIKE ? OR
                COALESCE(v.morador, '') LIKE ? OR
                COALESCE(v.observacoes, '') LIKE ? OR
                EXISTS (
                    SELECT 1 FROM visita_agentes vab
                    JOIN agentes ab ON ab.id_agente=vab.id_agente
                    WHERE vab.id_visita=v.id_visita AND ab.nome LIKE ?
                ) OR
                EXISTS (
                    SELECT 1 FROM coletas cb
                    WHERE cb.id_visita=v.id_visita
                      AND (COALESCE(cb.num_tubo, '') LIKE ? OR COALESCE(cb.tipo_deposito, '') LIKE ?)
                ) OR
                EXISTS (
                    SELECT 1 FROM tratamentos tb
                    WHERE tb.id_visita=v.id_visita AND COALESCE(tb.tipo, '') LIKE ?
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


def filter_options(conn):
    def distinct(sql):
        return [row[0] for row in conn.execute(sql).fetchall() if row[0] not in (None, "")]

    treatments = distinct(
        """
        SELECT tipo FROM (
            SELECT DISTINCT TRIM(tipo) AS tipo FROM tratamentos
            UNION
            SELECT DISTINCT TRIM(tipo_tratamento) AS tipo FROM depositos_inspecionados
        ) WHERE tipo IS NOT NULL AND tipo <> '' ORDER BY tipo COLLATE NOCASE
        """
    )
    return {
        "tipos": distinct("SELECT DISTINCT tipo FROM visitas WHERE tipo IS NOT NULL ORDER BY tipo"),
        "localidades": distinct(
            """SELECT DISTINCT COALESCE(l.nome, v.localidade) AS nome
                 FROM visitas v LEFT JOIN localidades l ON l.id_localidade=v.id_localidade
                WHERE COALESCE(l.nome, v.localidade) IS NOT NULL ORDER BY nome COLLATE NOCASE"""
        ),
        "agentes": distinct(
            """SELECT DISTINCT a.nome FROM agentes a JOIN visita_agentes va ON va.id_agente=a.id_agente
                ORDER BY a.nome COLLATE NOCASE"""
        ),
        "resultados": distinct(
            "SELECT DISTINCT visita FROM visitas WHERE visita IS NOT NULL ORDER BY visita COLLATE NOCASE"
        ),
        "imoveis": distinct(
            "SELECT DISTINCT tipo_imovel FROM visitas WHERE tipo_imovel IS NOT NULL ORDER BY tipo_imovel COLLATE NOCASE"
        ),
        "depositos": distinct(
            """SELECT DISTINCT tipo_deposito FROM depositos_inspecionados
                WHERE tipo_deposito IS NOT NULL ORDER BY tipo_deposito COLLATE NOCASE"""
        ),
        "tratamentos": treatments,
    }
