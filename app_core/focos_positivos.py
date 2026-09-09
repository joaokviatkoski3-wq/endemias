"""Regra unica para focos laboratoriais e notificacoes.

Um foco representa todos os resultados positivos de Aedes aegypti de uma
visita. A notificacao e uma consequencia do foco, nao do resultado isolado:
PE nunca gera notificacao e TB/TBO/PVE em terreno baldio tambem nao.
"""

import hashlib
import re
import unicodedata


AEGYPT_FIELDS = (
    "aegypt_larvas",
    "aegypt_pupas",
    "aegypt_exuvias",
    "aegypt_adulto",
)

TIPOS_COM_NOTIFICACAO = {"TB", "TBO", "PVE"}


def _text(value):
    text = str(value or "").strip()
    return text if text and text.lower() not in {"nan", "none", "nat"} else ""


def _key(value):
    text = unicodedata.normalize("NFKD", _text(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().replace("_", " ").split())


def eh_terreno_baldio(tipo_imovel):
    """Aceita tanto o codigo historico TB quanto o rotulo Terreno Baldio."""
    key = _key(tipo_imovel)
    return key == "tb" or ("terreno" in key and "baldio" in key)


def deve_gerar_notificacao(tipo_trabalho, tipo_imovel):
    """Aplica a regra operacional vigente para documentos de notificacao."""
    return (
        _text(tipo_trabalho).upper() in TIPOS_COM_NOTIFICACAO
        and not eh_terreno_baldio(tipo_imovel)
    )


def _numero_tubo(item):
    digits = re.sub(r"\D", "", _text(item.get("num_tubo")))
    return int(digits) if digits else 0


def _agentes_sql(conn):
    if getattr(conn, "backend", "sqlite") == "postgresql":
        return "string_agg(CAST(a.nome AS TEXT), ', ' ORDER BY a.nome)"
    return "GROUP_CONCAT(a.nome, ', ')"


def _visita(conn, id_visita):
    agentes = _agentes_sql(conn)
    row = conn.execute(
        f"""SELECT v.id_visita, v.tipo, v.data, v.id_localidade, v.localidade,
                   v.quarteirao, v.logradouro, v.numero, v.morador,
                   v.tipo_imovel, v.observacoes,
                   (SELECT {agentes}
                      FROM visita_agentes va
                      JOIN agentes a ON a.id_agente=va.id_agente
                     WHERE va.id_visita=v.id_visita) AS agentes
              FROM visitas v
             WHERE v.id_visita=?""",
        (id_visita,),
    ).fetchone()
    return dict(row) if row else None


def _positivos(conn, id_visita):
    total = " + ".join(f"COALESCE(rl.{field},0)" for field in AEGYPT_FIELDS)
    rows = conn.execute(
        f"""SELECT rl.id_resultado, c.id_coleta, c.num_tubo, c.tipo_deposito
              FROM coletas c
              JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
             WHERE c.id_visita=? AND ({total})>0""",
        (id_visita,),
    ).fetchall()
    return sorted((dict(row) for row in rows), key=_numero_tubo)


def _codigo(data, positivos):
    data = _text(data).replace("-", "")
    tubo = re.sub(r"\D", "", _text(positivos[0].get("num_tubo"))) if positivos else ""
    return data + tubo if data and tubo else None


def sincronizar_foco_visita(conn, id_visita, agora_iso):
    """Recalcula o foco de uma visita sem apagar seu historico manual.

    Quando nao resta Aedes aegypti positivo, ou quando a regra operacional nao
    permite notificacao, o foco e mantido para analise, mas e retirado da fila
    de notificacoes por ``gera_notificacao=0``.
    """
    visita = _visita(conn, id_visita)
    if not visita:
        raise ValueError("Visita nao encontrada para sincronizar foco positivo.")

    id_foco = hashlib.md5(("foco:v3:" + str(id_visita)).encode()).hexdigest()
    positivos = _positivos(conn, id_visita)
    gera_notificacao = bool(
        positivos and deve_gerar_notificacao(visita["tipo"], visita["tipo_imovel"])
    )
    existente = conn.execute(
        "SELECT id_foco FROM focos_positivos WHERE id_foco=?", (id_foco,)
    ).fetchone()
    # Bases anteriores podem conter um foco com identificador legado para a
    # mesma visita. Reutiliza-o em vez de criar uma segunda notificacao e
    # preserva tanto o status quanto o historico manual daquele foco.
    if not existente:
        existente = conn.execute(
            "SELECT id_foco FROM focos_positivos WHERE id_visita=? "
            "ORDER BY processado_em DESC, id_foco LIMIT 1",
            (id_visita,),
        ).fetchone()
        if existente:
            id_foco = existente[0]

    if not positivos:
        if existente:
            conn.execute(
                "UPDATE focos_positivos SET gera_notificacao=0, processado_em=? WHERE id_foco=?",
                (agora_iso, id_foco),
            )
        return {
            "id_foco": id_foco,
            "tem_positivo_aegypti": False,
            "gera_notificacao": False,
            "atualizado": bool(existente),
        }

    tubos = ", ".join(item["num_tubo"] for item in positivos if item.get("num_tubo"))
    depositos = []
    for item in positivos:
        deposito, tubo = _text(item.get("tipo_deposito")), _text(item.get("num_tubo"))
        if deposito and tubo:
            depositos.append(f"{deposito} (tubo {tubo})")
        elif deposito:
            depositos.append(deposito)
        elif tubo:
            depositos.append(f"tubo {tubo}")
    primeiro = positivos[0]
    valores = (
        primeiro["id_coleta"], primeiro["id_resultado"], tubos,
        _codigo(visita["data"], positivos), visita["tipo"], visita["data"],
        visita["id_localidade"], visita["localidade"], visita["quarteirao"],
        visita["logradouro"], visita["numero"], visita["morador"],
        visita["tipo_imovel"], ", ".join(depositos) or None,
        visita["agentes"], visita["observacoes"], int(gera_notificacao), agora_iso,
    )
    if existente:
        conn.execute(
            """UPDATE focos_positivos SET
                   id_coleta=?, id_resultado=?, num_tubo=?, codigo=?,
                   tipo_trabalho=?, data=?, id_localidade=?, localidade=?,
                   quarteirao=?, logradouro=?, numero=?, nome_morador=?,
                   tipo_imovel=?, depositos=?, agentes=?, observacoes=?,
                   gera_notificacao=?, processado_em=?
                 WHERE id_foco=?""",
            valores + (id_foco,),
        )
    else:
        conn.execute(
            """INSERT INTO focos_positivos (
                   id_foco, id_visita, id_coleta, id_resultado, num_tubo, codigo,
                   origem, tipo_trabalho, data, id_localidade, localidade,
                   quarteirao, logradouro, numero, complemento, nome_morador,
                   tipo_imovel, depositos, agentes, observacoes,
                   gera_notificacao, processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (id_foco, id_visita) + valores[:4] + ("kobo",) + valores[4:11]
            + (None,) + valores[11:],
        )
    return {
        "id_foco": id_foco,
        "tem_positivo_aegypti": True,
        "gera_notificacao": gera_notificacao,
        "atualizado": bool(existente),
    }


def listar_divergencias(conn):
    """Lista visitas positivas cuja presenca na fila diverge da regra vigente."""
    total = " + ".join(f"COALESCE(rl.{field},0)" for field in AEGYPT_FIELDS)
    rows = conn.execute(
        f"""SELECT DISTINCT v.id_visita, v.tipo, v.data, v.localidade,
                   v.logradouro, v.numero, v.morador, v.tipo_imovel,
                   f.id_foco, f.gera_notificacao, f.status_notificacao
              FROM visitas v
              JOIN coletas c ON c.id_visita=v.id_visita
              JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
              LEFT JOIN focos_positivos f ON f.id_visita=v.id_visita
             WHERE ({total})>0
             ORDER BY v.data, v.id_visita"""
    ).fetchall()
    divergencias = []
    for row in rows:
        item = dict(row)
        esperado = deve_gerar_notificacao(item["tipo"], item["tipo_imovel"])
        atual = bool(item.get("gera_notificacao"))
        if esperado and not item.get("id_foco"):
            motivo = "positivo_sem_foco"
        elif esperado and not atual:
            motivo = "notificacao_desativada"
        elif not esperado and item.get("id_foco") and atual:
            motivo = "notificacao_indevida"
        else:
            continue
        item["gera_notificacao_esperado"] = esperado
        item["motivo"] = motivo
        divergencias.append(item)
    return divergencias
