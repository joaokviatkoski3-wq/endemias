"""Resultados oficiais de laboratório para os integrantes da equipe de coleta."""

from contextlib import closing
from datetime import date, timedelta

from app_core import visitas_integradas


ESPECIES = ("aegypt", "albopictus", "outra")
ESTAGIOS = ("larvas", "pupas", "exuvias", "adulto")
CONTAGENS = tuple(f"{especie}_{estagio}" for especie in ESPECIES for estagio in ESTAGIOS)


def _consulta(conn, usuario, agente, resultado=None, *, desde_push=None):
    if conn.backend == "sqlite":
        conn.execute("""CREATE TABLE IF NOT EXISTS avisos_campo_lidos (
            id_usuario INTEGER NOT NULL REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
            id_agente INTEGER NOT NULL REFERENCES agentes(id_agente) ON DELETE CASCADE,
            id_resultado INTEGER NOT NULL, versao TEXT NOT NULL,
            PRIMARY KEY (id_usuario, id_agente, id_resultado))""")
    data = "CAST(r.data_leitura AS TEXT)"
    versao = f"COALESCE(NULLIF(r.atualizado_em,''), NULLIF(r.criado_em,''), {data})"
    campos = ", ".join(f"COALESCE(r.{c},0) AS {c}" for c in CONTAGENS)
    filtro = "AND r.id_resultado=?" if resultado is not None else ""
    args = [usuario, agente, agente, (date.today() - timedelta(days=30)).isoformat()]
    if resultado is not None:
        args.append(resultado)
    if desde_push is not None:
        filtro += f""" AND {versao}>=? AND (l.versao IS NULL OR l.versao<>{versao})
            AND NOT EXISTS (SELECT 1 FROM campo_push_entregas e
                WHERE e.id_usuario=? AND e.id_agente=? AND e.id_resultado=r.id_resultado AND e.versao={versao})"""
        args.extend((desde_push, usuario, agente))
    return conn.execute(f"""
        WITH pessoais AS (
            SELECT r.id_resultado, r.num_tubo, CAST(r.data_coleta AS TEXT) AS data_coleta,
                   {data} AS data_leitura, v.tipo AS trabalho, v.localidade,
                   {versao} AS versao, {campos},
                   CASE WHEN l.versao={versao} THEN 0 ELSE 1 END AS novo
              FROM resultados_laboratorio r
              JOIN coletas c ON c.id_coleta=r.id_coleta
              JOIN visitas v ON v.id_visita=c.id_visita
              LEFT JOIN avisos_campo_lidos l
                ON l.id_usuario=? AND l.id_agente=? AND l.id_resultado=r.id_resultado
             WHERE EXISTS (SELECT 1 FROM visita_agentes a WHERE a.id_visita=v.id_visita AND a.id_agente=?)
               AND {data} IS NOT NULL AND {data}<>''
               AND SUBSTR({versao},1,10)>=? {filtro}
        )
        SELECT *, SUM(novo) OVER () AS nao_lidos
          FROM pessoais ORDER BY novo DESC, versao DESC, id_resultado DESC LIMIT 40
    """, args)


def pendentes_push(conn, usuario, agente, desde):
    return [(row["id_resultado"], row["versao"]) for row in
            _consulta(conn, usuario, agente, desde_push=desde)]


def listar(target, usuario, agente):
    with closing(visitas_integradas.connect(target)) as conn:
        rows = [dict(row) for row in _consulta(conn, usuario, agente)]
    total = rows[0]["nao_lidos"] if rows else 0
    for row in rows:
        del row["nao_lidos"]
    return {"itens": rows, "nao_lidos": total}


def ler(target, usuario, agente, resultado, versao):
    with closing(visitas_integradas.connect(target)) as conn, conn:
        row = _consulta(conn, usuario, agente, resultado).fetchone()
        if not row or row["versao"] != versao:
            return False
        conn.execute("""
            INSERT INTO avisos_campo_lidos (id_usuario,id_agente,id_resultado,versao)
            VALUES (?,?,?,?) ON CONFLICT (id_usuario,id_agente,id_resultado)
            DO UPDATE SET versao=excluded.versao
            WHERE avisos_campo_lidos.versao<=excluded.versao
        """, (usuario, agente, resultado, versao))
    return True
