"""Apuração operacional a partir das visitas e leituras registradas no ciclo."""

from collections import Counter, defaultdict
from datetime import date, datetime, time

from app_core import db, liraa, liraa_kobo


TURNOS = {
    "dia": "Dia inteiro",
    "manha": "Manhã",
    "tarde": "Tarde",
    "noite": "Noite",
    "sem_horario": "Sem horário",
}
DIAS = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)
TIPOS = {
    "rco": "Residência / comércio / outros",
    "residencia": "Residência",
    "comercio": "Comércio",
    "outros": "Outros",
    "terreno_baldio": "Terreno baldio",
    "sem_tipo": "Tipo a conferir",
}


def _turno(valor):
    texto = str(valor or "").strip()
    if len(texto) > 1 and texto[1] == ":":
        texto = "0" + texto
    try:
        hora = time.fromisoformat(texto).hour
    except ValueError:
        return "sem_horario"
    if hora < 12:
        return "manha"
    return "tarde" if hora < 18 else "noite"


def resumir(target, id_ciclo, dia, turno="dia"):
    if turno not in TURNOS:
        raise liraa.LiraaError("Selecione um turno válido.")
    dia = date.fromisoformat(str(dia))
    conn = db.connect(target)
    try:
        if conn.backend == "postgresql":
            conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        else:
            conn.execute("BEGIN")
        contexto = liraa_kobo._contexto(conn, id_ciclo)
        ciclo, localidades, _, sorteados, _, adicionais = contexto
        estratos = {
            row["id_estrato"]: {
                "numero": row["numero"], "meta": row["meta"],
                "sorteadas": 0, "adicionais": 0,
            }
            for row in conn.execute("""
                SELECT e.id_estrato, e.numero, s.n AS meta
                FROM liraa_estratos e LEFT JOIN liraa_sorteios s ON s.id_estrato=e.id_estrato
                WHERE e.id_ciclo=? ORDER BY e.numero
            """, (id_ciclo,))
        }
        tubos = defaultdict(list)
        if db.table_exists(conn, "liraa_visita_tubitos"):
            tem_leituras = db.table_exists(conn, "liraa_leituras")
            leitura = "l.id_tubito" if tem_leituras else "NULL"
            join = "LEFT JOIN liraa_leituras l ON l.id_tubito=t.id_tubito" if tem_leituras else ""
            for row in conn.execute(f"""
                SELECT t.id_visita, t.numero, {leitura} AS leitura
                FROM liraa_visita_tubitos t
                JOIN liraa_visitas v ON v.id_visita=t.id_visita
                {join}
                WHERE v.id_ciclo=?
            """, (id_ciclo,)):
                tubos[row["id_visita"]].append(db.serialize_row(row))

        recorte, acumulado = Counter(), Counter()
        tipos_recorte, tipos_ciclo = Counter(), Counter()
        turnos_dia = Counter()
        visitados = set()
        visitas = conn.execute("""
            SELECT id_visita, data_visita, hora_inicio, localidade_informada, quarteirao,
                   tipo_imovel, form_ciclo, plano_hash, tratamento_json
            FROM liraa_visitas WHERE id_ciclo=?
        """, (id_ciclo,)) if db.table_exists(conn, "liraa_visitas") else ()
        for row in visitas:
            visita = db.serialize_row(row)
            loc, estrato, vinculo = liraa_kobo._vincular(visita, contexto)
            no_plano = vinculo in {"sorteado", "adicional"}
            if no_plano:
                visitados.add((loc, visita["quarteirao"]))
                campo = "sorteadas" if vinculo == "sorteado" else "adicionais"
                estratos[estrato][campo] += 1

            amostras = tubos[visita["id_visita"]]
            pendentes = sum(tubo["leitura"] is None for tubo in amostras)
            tipo = visita["tipo_imovel"]
            tipo = tipo if tipo in TIPOS else "sem_tipo"
            contagem = {
                "visitas": 1, "no_plano": int(no_plano), "fora_plano": int(not no_plano),
                "visitas_com_coleta": int(bool(amostras)), "tubitos": len(amostras),
                "leituras": len(amostras) - pendentes, "pendentes": pendentes,
                "coletas_a_conferir": int(bool(liraa_kobo.avisos_coleta(visita, amostras))),
            }
            acumulado.update(contagem)
            tipos_ciclo[tipo] += 1
            if str(visita["data_visita"]) == dia.isoformat():
                turno_visita = _turno(visita["hora_inicio"])
                turnos_dia[turno_visita] += 1
                if turno == "dia" or turno_visita == turno:
                    recorte.update(contagem)
                    tipos_recorte[tipo] += 1

        metas = [e for e in estratos.values() if e["meta"] is not None]
        for estrato in metas:
            estrato["faltam"] = max(0, estrato["meta"] - estrato["sorteadas"])
        meta = sum(e["meta"] for e in metas)
        faltam = sum(e["faltam"] for e in metas)
        plano = set().union(*sorteados.values(), adicionais.keys())
        nomes = {ident: nome for nome, ident in localidades.items()}
        quarteiroes_pendentes = sorted(
            (
                {"localidade": nomes.get(loc, "Localidade não identificada"),
                 "quarteirao": quadra, "adicional": (loc, quadra) in adicionais}
                for loc, quadra in plano - visitados
            ),
            key=lambda item: (item["localidade"], liraa._ordem_quarteirao(item["quarteirao"])),
        )
        inicio = date.fromisoformat(str(ciclo["inicio"])) if ciclo["inicio"] else None
        fim = date.fromisoformat(str(ciclo["fim"])) if ciclo["fim"] else None
        dia_do_ciclo = (dia - inicio).days + 1 if inicio and dia >= inicio and (fim is None or dia <= fim) else None
        return {
            "ciclo": ciclo["nome"], "dia": dia.strftime("%d/%m/%Y"),
            "dia_do_ciclo": dia_do_ciclo, "dia_semana": DIAS[dia.weekday()],
            "turno": TURNOS[turno], "atualizado": datetime.now().strftime("%H:%M:%S"),
            "recorte": recorte, "acumulado": acumulado, "estratos": list(estratos.values()),
            "meta": meta, "faltam": faltam, "sem_sorteio": len(estratos) - len(metas),
            "sorteadas": sum(e["sorteadas"] for e in estratos.values()),
            "adicionais": sum(e["adicionais"] for e in estratos.values()),
            "percentual": round(100 * (meta - faltam) / meta, 1) if meta else 0,
            "total_quarteiroes": len(plano), "quarteiroes_visitados": len(plano & visitados),
            "quarteiroes_pendentes": quarteiroes_pendentes,
            "turnos_dia": [(TURNOS[chave], turnos_dia[chave]) for chave in TURNOS if chave != "dia"],
            "tipos": [(rotulo, tipos_recorte[chave], tipos_ciclo[chave])
                      for chave, rotulo in TIPOS.items() if tipos_ciclo[chave]],
        }
    finally:
        conn.close()
