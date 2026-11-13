"""Espelho para a digitação no programa LIRAa e histórico de encerramentos."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json

from app_core import db, liraa, liraa_boletim, liraa_kobo, liraa_laboratorio, liraa_operacional


DEPOSITOS = liraa_operacional.DEPOSITOS
COLUNAS_ENTRADA = (
    ("programados", "Prog."), ("trabalhados", "Insp."),
    ("aegypt_tb", "TB"), ("aegypt_outros", "Outros"), ("aegypt_imoveis", "Total"),
    ("albopictus_tb", "TB"), ("albopictus_outros", "Outros"), ("albopictus_imoveis", "Total"),
    *((f"aegypt_recipientes.{codigo}", codigo) for codigo in DEPOSITOS),
    ("aegypt_total", "Total"), ("critica", "Crítica"), ("albopictus_total", "Total"),
)
GRUPOS_ENTRADA = (("Amostra", 2), ("Imóveis positivos Ae. aegypti", 3), ("Imóveis positivos Ae. albopictus", 3),
                  ("Recipientes Ae. aegypti", 8), ("Conferência", 1), ("Recipientes Ae. albopictus", 1))
COLUNAS_INDICES = (
    ("programados", "Prog."), ("trabalhados", "Insp."),
    ("aegypt_tb_pct", "Ae. aegypti TB (%)"), ("aegypt_outros_pct", "Ae. aegypti Outros (%)"),
    ("albopictus_tb_pct", "Ae. albopictus TB (%)"), ("albopictus_outros_pct", "Ae. albopictus Outros (%)"),
    ("perda", "Perda (%)"), ("aegypt_iip", "IIP aeg. (%)"), ("albopictus_iip", "IIP alb. (%)"),
    ("aegypt_ib", "IB aeg."), ("albopictus_ib", "IB alb."),
    *((f"itr.{codigo}", f"ITR {codigo} (%)") for codigo in DEPOSITOS),
)
COLUNAS_RESUMO_INDICES = (COLUNAS_INDICES[1], *COLUNAS_INDICES[7:])
AVISOS = {
    "pendentes": "Tubitos aguardando leitura",
    "tipos_invalidos": "Imóveis com tipo a conferir",
    "depositos_invalidos": "Recipientes com código a conferir",
    "coletas_inconsistentes": "Visitas com dados de coleta a conferir",
    "visitas_suspeitas": "Possíveis visitas duplicadas",
    "tubitos_repetidos": "Números de tubito repetidos",
}
CONTAGENS = ("programados", "trabalhados",
             "aegypt_tb", "aegypt_outros", "albopictus_tb", "albopictus_outros",
             "aegypt_total", "albopictus_total", "trabalhados_adicionais", "tubitos_adicionais",
             "tubitos", "leituras", *AVISOS)


def _percentual(parte, total):
    if not total:
        return None
    return float((Decimal(100 * parte) / total).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _indices(linha):
    insp = linha["trabalhados"]
    prog = linha["programados"]
    for especie in ("aegypt", "albopictus"):
        positivos = linha[f"{especie}_tb"] + linha[f"{especie}_outros"]
        linha[f"{especie}_imoveis"] = positivos
        linha[f"{especie}_iip"] = _percentual(positivos, insp)
        linha[f"{especie}_ib"] = _percentual(linha[f"{especie}_total"], insp)
        for tipo in ("tb", "outros"):
            linha[f"{especie}_{tipo}_pct"] = _percentual(linha[f"{especie}_{tipo}"], insp)
    linha["itr"] = {codigo: _percentual(qtd, linha["aegypt_total"])
                    for codigo, qtd in linha["aegypt_recipientes"].items()}
    linha["perda"] = _percentual(linha["faltam"], prog)
    linha["critica"] = "Conferir" if any(linha[campo] for campo in AVISOS) else ("OK" if insp else "—")
    return linha


def celula(linha, campo):
    grupo, _, chave = campo.partition(".")
    valor = linha[grupo][chave] if chave else linha[grupo]
    if isinstance(valor, float):
        return f"{valor:.1f}".replace(".", ",")
    return valor if valor is not None else "—"


def cabecalho_csv():
    rotulos = iter(rotulo for _, rotulo in COLUNAS_ENTRADA)
    entrada = [f"{grupo} · {next(rotulos)}" for grupo, tamanho in GRUPOS_ENTRADA for _ in range(tamanho)]
    entrada[:2] = [rotulo for _, rotulo in COLUNAS_ENTRADA[:2]]
    return ["Estrato", *entrada, *(rotulo for _, rotulo in COLUNAS_INDICES[2:])]


def _somar_contagens(linhas):
    total = {campo: sum(linha[campo] or 0 for linha in linhas) for campo in CONTAGENS}
    total["aegypt_recipientes"] = {
        codigo: sum(linha["aegypt_recipientes"][codigo] for linha in linhas)
        for codigo in DEPOSITOS
    }
    return total


def _calcular(conn, id_ciclo):
    contexto = liraa_kobo._contexto(conn, id_ciclo)
    ciclo, _, _, sorteados, _, adicionais = contexto
    grupos = {}
    grupos_locais = {}
    nomes = {r["id_localidade"]: r["nome"] for r in conn.execute("SELECT id_localidade, nome FROM localidades")}
    quadras = set()
    for row in conn.execute("""SELECT e.id_estrato, e.numero, s.n FROM liraa_estratos e
            LEFT JOIN liraa_sorteios s ON s.id_estrato=e.id_estrato
            WHERE e.id_ciclo=? ORDER BY e.numero""", (id_ciclo,)):
        ident = row["id_estrato"]
        grupo = liraa_boletim.novo_grupo(row["numero"], row["n"])
        extras = {key for key, item in adicionais.items() if item["id_estrato"] == ident}
        ativos = sorteados.get(ident, set()) | extras
        quadras.update(ativos)
        grupo.update(quarteiroes=len(ativos), quarteiroes_adicionais=len(extras))
        grupos[ident, None] = grupo
        for loc in {loc for loc, _ in ativos}:
            grupos_locais[ident, loc] = liraa_boletim.novo_grupo(row["numero"], None)

    excluidas = liraa_boletim.agregar(conn, id_ciclo, contexto, grupos_locais, "localidade")
    por_estrato = {}
    por_localidade = {}
    visitados = set()
    for (ident, loc), grupo in grupos_locais.items():
        por_estrato.setdefault(ident, []).append(grupo)
        por_localidade.setdefault(loc, []).append(grupo)
        visitados.update(grupo["_visitados"])
    linhas = []
    for (ident, _), grupo in grupos.items():
        programados = grupo["programados"]
        subgrupos = por_estrato.get(ident, [])
        grupo.update(_somar_contagens(subgrupos))
        grupo["programados"] = programados
        grupo.pop("_visitados")
        grupo["quarteiroes_sem_visita"] = grupo["quarteiroes"] - sum(len(g["_visitados"]) for g in subgrupos)
        grupo["parcial"] = bool(grupo["quarteiroes_sem_visita"] or any(grupo[campo] for campo in AVISOS))
        for especie in ("aegypt", "albopictus"):
            campo = f"positivos_adicionais_{especie}"
            grupo[campo] = sum(g[campo] for g in subgrupos)
        saldo = grupo["trabalhados"] - grupo["programados"] if grupo["programados"] is not None else 0
        grupo["faltam"] = max(0, -saldo)
        grupo["excedentes"] = max(0, saldo)
        linhas.append(_indices(grupo))
    total = _somar_contagens(linhas)
    total["faltam"] = sum(linha["faltam"] for linha in linhas)
    total["excedentes"] = sum(linha["excedentes"] for linha in linhas)
    _indices(total)
    locais = []
    for loc, subgrupos in sorted(por_localidade.items(), key=lambda item: nomes.get(item[0], "").casefold()):
        linha = _somar_contagens(subgrupos)
        linha.update(localidade=nomes.get(loc, "Localidade não identificada"), programados=None, faltam=0)
        locais.append(_indices(linha))
    faltantes = [{"localidade": nomes.get(loc, "Localidade não identificada"), "quarteirao": q}
                 for loc, q in sorted(quadras - visitados,
                                      key=lambda item: (nomes.get(item[0], ""), liraa._ordem_quarteirao(item[1])))]
    pendentes_laboratorio = conn.execute("""SELECT COUNT(*) FROM liraa_visita_tubitos t
        JOIN liraa_visitas v ON v.id_visita=t.id_visita
        LEFT JOIN liraa_leituras l ON l.id_tubito=t.id_tubito
        WHERE v.id_ciclo=? AND l.id_tubito IS NULL""", (id_ciclo,)).fetchone()[0]
    ciclo = db.serialize_row(ciclo)
    return {"ciclo": {key: ciclo[key] for key in ("id_ciclo", "ano", "nome", "inicio", "fim")},
            "estratos": linhas, "localidades": locais, "total": total, "excluidas": excluidas,
            "sem_sorteio": sum(linha["programados"] is None for linha in linhas),
            "pendentes_laboratorio": pendentes_laboratorio,
            "quarteiroes": len(quadras), "quarteiroes_pendentes": faltantes,
            "progresso": _percentual(total["programados"] - total["faltam"], total["programados"])}


def _encerramento(conn, id_ciclo):
    if not db.table_exists(conn, "liraa_encerramentos"):
        return None
    return conn.execute("""SELECT id_encerramento, encerrado_em, responsavel, observacoes, resumo_json
        FROM liraa_encerramentos WHERE id_ciclo=? AND reaberto_em IS NULL""", (id_ciclo,)).fetchone()


def resumir(target, id_ciclo):
    conn = db.connect(target)
    try:
        liraa_laboratorio.ensure_schema(conn)
        if conn.backend == "postgresql":
            conn.rollback()
            conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        else:
            conn.commit()
            conn.execute("BEGIN")
        salvo = _encerramento(conn, id_ciclo)
        if salvo:
            resumo = json.loads(salvo["resumo_json"])
            resumo["encerramento"] = {key: salvo[key] for key in ("encerrado_em", "responsavel", "observacoes")}
            return resumo
        return _calcular(conn, id_ciclo)
    finally:
        conn.close()


def encerrar(target, id_ciclo, usuario, observacoes, auditar=None):
    if usuario.get("nivel") != "superadmin":
        raise liraa.LiraaError("Somente o superadmin pode encerrar um ciclo.")
    observacoes = liraa._texto(observacoes, "Observações do encerramento", 2000)
    conn = db.connect(target)
    try:
        liraa._schema(conn)
        liraa_laboratorio.ensure_schema(conn)
        with conn:
            liraa._bloquear_ciclo(conn, id_ciclo)
            resumo = _calcular(conn, id_ciclo)
            if resumo["pendentes_laboratorio"]:
                raise liraa.LiraaError("Ainda há tubitos aguardando leitura neste ciclo.")
            if not resumo["total"]["trabalhados"] or resumo["sem_sorteio"]:
                raise liraa.LiraaError("Confira os estratos e as inspeções antes de encerrar.")
            alertas = resumo["excluidas"] or resumo["quarteiroes_pendentes"] or resumo["total"]["faltam"] or any(
                resumo["total"][campo] for campo in AVISOS
            )
            if alertas and not observacoes:
                raise liraa.LiraaError("Registre as observações sobre as pendências ou a cobertura antes de encerrar.")
            conn.execute("""INSERT INTO liraa_encerramentos
                (id_ciclo,encerrado_em,encerrado_por,responsavel,observacoes,resumo_json) VALUES (?,?,?,?,?,?)""",
                (id_ciclo, datetime.now().isoformat(timespec="seconds"), usuario["id_usuario"],
                 usuario["nome"], observacoes, json.dumps(resumo, ensure_ascii=False)))
            if auditar:
                auditar(conn, {"observacoes": observacoes, "inspecionados": resumo["total"]["trabalhados"],
                               "quarteiroes_pendentes": len(resumo["quarteiroes_pendentes"])})
    finally:
        conn.close()


def reabrir(target, id_ciclo, usuario, motivo, auditar=None):
    if usuario.get("nivel") != "superadmin":
        raise liraa.LiraaError("Somente o superadmin pode reabrir um ciclo.")
    motivo = liraa._texto(motivo, "Motivo da reabertura", 1000)
    if not motivo:
        raise liraa.LiraaError("Informe o motivo da reabertura.")
    conn = db.connect(target)
    try:
        liraa._schema(conn)
        with conn:
            if not liraa._bloquear_ciclo(conn, id_ciclo, permitir_encerrado=True):
                raise liraa.LiraaError("Este ciclo já está aberto.")
            conn.execute("""UPDATE liraa_encerramentos SET reaberto_em=?, reaberto_por=?, motivo_reabertura=?
                WHERE id_ciclo=? AND reaberto_em IS NULL""",
                (datetime.now().isoformat(timespec="seconds"), usuario["id_usuario"], motivo, id_ciclo))
            if auditar:
                auditar(conn, {"motivo": motivo})
    finally:
        conn.close()
