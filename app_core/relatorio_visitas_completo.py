"""Histórico completo de visitas de vetores e esporotricose por agente.

Somente leitura. Não usa os resumos de produção, que agregam registros e
perderiam os detalhes individuais necessários ao PDF.
"""

from datetime import date

from app_core import db as db_core
from app_core import visitas as visitas_core


class FiltroInvalido(ValueError):
    pass


def validar_filtros(agente, inicio, fim):
    agente = str(agente or "").strip()
    if not agente:
        raise FiltroInvalido("Selecione um agente.")
    try:
        data_inicial = date.fromisoformat(str(inicio or ""))
        data_final = date.fromisoformat(str(fim or ""))
    except ValueError:
        raise FiltroInvalido("Informe as duas datas no formato AAAA-MM-DD.") from None
    if data_final < data_inicial:
        raise FiltroInvalido("A data final deve ser igual ou posterior à inicial.")
    return agente, data_inicial.isoformat(), data_final.isoformat()


def _rows(conn, sql, params):
    return [db_core.serialize_row(row) for row in conn.execute(sql, params).fetchall()]


def _detalhe_vetores(conn, id_visita):
    detalhe = visitas_core.detalhar(conn, id_visita)
    # Lê as linhas completas: a API de tela seleciona apenas um subconjunto.
    secoes = []
    for tabela, titulo, ordem in (
        ("depositos_inspecionados", "Depósitos inspecionados", "id"),
        ("tratamentos", "Tratamentos", "id"),
        ("coletas", "Coletas", "id_coleta"),
        ("resultados_laboratorio", "Resultados laboratoriais", "id_resultado"),
        ("focos_positivos", "Focos positivos e notificações", "id_foco"),
    ):
        if tabela == "resultados_laboratorio":
            registros = _rows(conn, """SELECT rl.* FROM resultados_laboratorio rl
                JOIN coletas c ON c.id_coleta=rl.id_coleta
                WHERE c.id_visita=? ORDER BY rl.id_resultado""", (id_visita,))
        else:
            registros = _rows(conn, f"SELECT * FROM {tabela} WHERE id_visita=? ORDER BY {ordem}",
                              (id_visita,))
        if registros:
            secoes.append({"titulo": titulo, "registros": registros})
    return {"origem": "Vetores", "visita": detalhe["visita"], "secoes": secoes}


def _detalhe_esporotricose(conn, id_visita, catalogo_acs):
    visita = db_core.serialize_row(conn.execute(
        "SELECT * FROM esporotricose_visitas WHERE id_visita=?", (id_visita,)).fetchone())
    agentes = _rows(conn, """SELECT a.nome, COALESCE(NULLIF(a.nome_completo,''), a.nome) AS nome_completo
        FROM esporotricose_visita_agentes va JOIN agentes a ON a.id_agente=va.id_agente
        WHERE va.id_visita=? ORDER BY a.nome""", (id_visita,))
    visita["agentes"] = ", ".join(a["nome_completo"] for a in agentes)
    if db_core.table_exists(conn, "esporotricose_visita_acs"):
        codigos = [r["acs_codigo"] for r in _rows(conn,
            "SELECT acs_codigo FROM esporotricose_visita_acs WHERE id_visita=? ORDER BY acs_codigo",
            (id_visita,))]
        visita["acs"] = visitas_core.formatar_acs_codigos(", ".join(codigos), catalogo_acs)
    secoes = []
    animais = _rows(conn, "SELECT * FROM esporotricose_animais WHERE id_visita=? ORDER BY id_animal",
                    (id_visita,))
    if animais:
        secoes.append({"titulo": "Animais registrados na visita", "registros": animais})
    if db_core.table_exists(conn, "esporotricose_visita_imoveis"):
        vinculos = _rows(conn,
            "SELECT * FROM esporotricose_visita_imoveis WHERE id_visita=?", (id_visita,))
        if vinculos:
            secoes.append({"titulo": "Vínculo com imóvel acompanhado", "registros": vinculos})
    return {"origem": "Esporotricose", "visita": visita, "secoes": secoes}


def coletar(target, agente, inicio, fim):
    agente, inicio, fim = validar_filtros(agente, inicio, fim)
    conn = db_core.connect(target)
    try:
        pessoa = conn.execute("""SELECT COALESCE(NULLIF(nome_completo,''), nome) AS nome_exibicao
            FROM agentes WHERE nome=?""", (agente,)).fetchone()
        if not pessoa:
            raise FiltroInvalido("Agente não encontrado no cadastro.")
        vetores = _rows(conn, """SELECT v.id_visita, v.data, v.hora_inicio FROM visitas v
            WHERE v.data BETWEEN ? AND ? AND EXISTS (
                SELECT 1 FROM visita_agentes va JOIN agentes a ON a.id_agente=va.id_agente
                WHERE va.id_visita=v.id_visita AND a.nome=?)
            ORDER BY v.data, v.hora_inicio, v.id_visita""", (inicio, fim, agente))
        esporotricose = _rows(conn, """SELECT v.id_visita, v.data, v.hora_inicio
            FROM esporotricose_visitas v WHERE v.data BETWEEN ? AND ? AND EXISTS (
                SELECT 1 FROM esporotricose_visita_agentes va JOIN agentes a ON a.id_agente=va.id_agente
                WHERE va.id_visita=v.id_visita AND a.nome=?)
            ORDER BY v.data, v.hora_inicio, v.id_visita""", (inicio, fim, agente))
        catalogo = visitas_core.catalogo_acs(conn)
        registros = [_detalhe_vetores(conn, row["id_visita"]) for row in vetores]
        registros.extend(_detalhe_esporotricose(conn, row["id_visita"], catalogo)
                         for row in esporotricose)
        registros.sort(key=lambda item: (str(item["visita"].get("data") or ""),
                      str(item["visita"].get("hora_inicio") or ""), item["origem"],
                      str(item["visita"].get("id_visita") or "")))
        return {"agente": agente, "agente_exibicao": pessoa["nome_exibicao"],
                "inicio": inicio, "fim": fim, "visitas": registros,
                "totais": {"vetores": len(vetores), "esporotricose": len(esporotricose)}}
    finally:
        conn.close()
