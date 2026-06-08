import re
import uuid
from datetime import date, datetime, timedelta

from app_core import db as db_core


MESES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)

LEGACY_INDICADORES = {
    "Vistorias de denuncias e focos suspeitos do Aedes aegypti (PVE - Pesquisa Vetorial Especial)",
    "Bloqueio de transmissao do Aedes aegypti em imoveis visitados apos casos notificados",
    "Imoveis visitados em Pontos Estrategicos (PE)",
    "Depositos inspecionados nas visitas de campo",
    "Depositos eliminados nas visitas de campo",
    "Coletas encaminhadas ao laboratorio",
    "Focos positivos identificados em laboratorio",
    "Recolhimento de materiais jogados ou acumulados (pneus, loucas, plasticos, para-choques e outros)",
    "Pneus recolhidos em atividades de vigilancia ambiental",
    "Aplicacoes de BRI (Borrifamento Residual Intradomiciliar) registradas",
    "Amostras e atendimentos relacionados a animais de interesse em saude",
    "Animais registrados em amostras, reclamacoes, capturas ou acidentes",
}


def ensure_schema(db_path):
    conn = db_core.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS boletim_mensal_itens (
                id_item     INTEGER PRIMARY KEY AUTOINCREMENT,
                ano_mes     TEXT NOT NULL,
                chave       TEXT NOT NULL,
                origem      TEXT NOT NULL DEFAULT 'manual'
                           CHECK(origem IN ('auto','manual')),
                ordem       INTEGER NOT NULL DEFAULT 0,
                indicador   TEXT NOT NULL,
                quantidade  INTEGER NOT NULL DEFAULT 0,
                unidade     TEXT,
                ativo       INTEGER NOT NULL DEFAULT 1 CHECK(ativo IN (0,1)),
                atualizado_em TEXT NOT NULL,
                UNIQUE(ano_mes, chave)
            );
            CREATE INDEX IF NOT EXISTS idx_boletim_mensal_mes
                ON boletim_mensal_itens(ano_mes, ordem);
        """)
        conn.commit()
    finally:
        conn.close()


def periodo_mes(ano_mes):
    if not re.fullmatch(r"\d{4}-\d{2}", ano_mes or ""):
        hoje = date.today()
        ano_mes = f"{hoje.year:04d}-{hoje.month:02d}"
    ano, mes = [int(part) for part in ano_mes.split("-")]
    inicio = date(ano, mes, 1)
    if mes == 12:
        fim = date(ano + 1, 1, 1) - timedelta(days=1)
    else:
        fim = date(ano, mes + 1, 1) - timedelta(days=1)
    return {
        "ano_mes": f"{ano:04d}-{mes:02d}",
        "d_ini": inicio.isoformat(),
        "d_fim": fim.isoformat(),
        "label": f"{MESES[mes - 1]} de {ano}",
    }


def _table_exists(conn, table):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone())


def _scalar(conn, sql, params=(), default=0):
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else default
    except Exception:
        return default


def _sum(conn, sql, params=()):
    return _scalar(conn, sql, params, 0)


def _linha(chave, indicador, quantidade, unidade="", ordem=0, origem="auto", ativo=None):
    quantidade = int(quantidade or 0)
    return {
        "chave": chave,
        "origem": origem,
        "ordem": ordem,
        "indicador": indicador,
        "quantidade": quantidade,
        "unidade": unidade,
        "ativo": bool(quantidade) if ativo is None else bool(ativo),
    }


def linhas_automaticas(db_path, ano_mes):
    periodo = periodo_mes(ano_mes)
    d_ini, d_fim = periodo["d_ini"], periodo["d_fim"]
    conn = db_core.connect(db_path)
    try:
        linhas = [
            _linha(
                "visitas_pve",
                "Vistorias de denúncias e focos suspeitos do Aedes aegypti (PVE - Pesquisa Vetorial Especial)",
                _scalar(conn, "SELECT COUNT(*) FROM visitas WHERE tipo='PVE' AND data BETWEEN ? AND ?", (d_ini, d_fim)),
                "visitas",
                10,
            ),
            _linha(
                "visitas_tb",
                "Bloqueio de transmissão do Aedes aegypti em imóveis visitados após casos notificados",
                _scalar(conn, "SELECT COUNT(*) FROM visitas WHERE tipo='TB' AND data BETWEEN ? AND ?", (d_ini, d_fim)),
                "visitas",
                20,
            ),
            _linha(
                "visitas_tbo",
                "Bloqueio em armadilhas ovitrampas positivas (TBO)",
                _scalar(conn, "SELECT COUNT(*) FROM visitas WHERE tipo='TBO' AND data BETWEEN ? AND ?", (d_ini, d_fim)),
                "visitas",
                30,
            ),
            _linha(
                "visitas_pe",
                "Imóveis visitados em Pontos Estratégicos (PE)",
                _scalar(conn, "SELECT COUNT(*) FROM visitas WHERE tipo='PE' AND data BETWEEN ? AND ?", (d_ini, d_fim)),
                "visitas",
                40,
            ),
            _linha(
                "depositos_inspecionados",
                "Depósitos inspecionados nas visitas de campo",
                _sum(conn, """
                    SELECT SUM(COALESCE(d.inspecionado,0))
                      FROM depositos_inspecionados d
                      JOIN visitas v ON v.id_visita=d.id_visita
                     WHERE v.data BETWEEN ? AND ?
                """, (d_ini, d_fim)),
                "depósitos",
                50,
            ),
            _linha(
                "depositos_eliminados",
                "Depósitos eliminados nas visitas de campo",
                _sum(conn, """
                    SELECT SUM(COALESCE(d.eliminado,0))
                      FROM depositos_inspecionados d
                      JOIN visitas v ON v.id_visita=d.id_visita
                     WHERE v.data BETWEEN ? AND ?
                """, (d_ini, d_fim)),
                "depósitos",
                60,
            ),
            _linha(
                "coletas_laboratorio",
                "Coletas encaminhadas ao laboratório",
                _scalar(conn, """
                    SELECT COUNT(DISTINCT c.id_coleta)
                      FROM coletas c
                      JOIN visitas v ON v.id_visita=c.id_visita
                     WHERE v.data BETWEEN ? AND ?
                """, (d_ini, d_fim)),
                "coletas",
                70,
            ),
            _linha(
                "focos_positivos",
                "Focos positivos identificados em laboratório",
                _scalar(conn, "SELECT COUNT(*) FROM focos_positivos WHERE data BETWEEN ? AND ?", (d_ini, d_fim)),
                "focos",
                80,
            ),
        ]

        if _table_exists(conn, "esporotricose_visitas"):
            linhas.append(_linha(
                "esporotricose_visitas",
                "Bloqueio de esporotricose - visitas domiciliares",
                _scalar(conn, "SELECT COUNT(*) FROM esporotricose_visitas WHERE data BETWEEN ? AND ?", (d_ini, d_fim)),
                "visitas",
                90,
            ))
        if _table_exists(conn, "esporotricose_animais"):
            linhas.append(_linha(
                "esporotricose_animais",
                "Animais cadastrados no bloqueio de esporotricose",
                _scalar(conn, """
                    SELECT COUNT(DISTINCT a.id_animal)
                      FROM esporotricose_animais a
                      JOIN esporotricose_visitas v ON v.id_visita=a.id_visita
                     WHERE v.data BETWEEN ? AND ?
                """, (d_ini, d_fim)),
                "animais",
                100,
            ))
            linhas.append(_linha(
                "esporotricose_animais_feridas",
                "Animais cadastrados com feridas sugestivas de esporotricose",
                _scalar(conn, """
                    SELECT COUNT(DISTINCT a.id_animal)
                      FROM esporotricose_animais a
                      JOIN esporotricose_visitas v ON v.id_visita=a.id_visita
                     WHERE v.data BETWEEN ? AND ? AND LOWER(COALESCE(a.feridas,''))='sim'
                """, (d_ini, d_fim)),
                "animais",
                110,
            ))
        if _table_exists(conn, "recolhimentos"):
            linhas.extend([
                _linha(
                    "recolhimentos_materiais",
                    "Recolhimento de materiais jogados ou acumulados (pneus, louças, plásticos, para-choques e outros)",
                    _sum(conn, "SELECT SUM(COALESCE(total_materiais,0)) FROM recolhimentos WHERE data BETWEEN ? AND ?", (d_ini, d_fim)),
                    "materiais",
                    120,
                ),
                _linha(
                    "recolhimentos_pneus",
                    "Pneus recolhidos em atividades de vigilância ambiental",
                    _sum(conn, "SELECT SUM(COALESCE(pneu,0)) FROM recolhimentos WHERE data BETWEEN ? AND ?", (d_ini, d_fim)),
                    "pneus",
                    130,
                ),
            ])
        if _table_exists(conn, "bri_registros"):
            linhas.append(_linha(
                "bri_registros",
                "Aplicações de BRI (Borrifamento Residual Intradomiciliar) registradas",
                _scalar(conn, "SELECT COUNT(*) FROM bri_registros WHERE data BETWEEN ? AND ?", (d_ini, d_fim)),
                "registros",
                140,
            ))
        if _table_exists(conn, "amostras_animais"):
            linhas.extend([
                _linha(
                    "amostras_animais_registros",
                    "Amostras e atendimentos relacionados a animais de interesse em saúde",
                    _scalar(conn, "SELECT COUNT(*) FROM amostras_animais WHERE data BETWEEN ? AND ?", (d_ini, d_fim)),
                    "registros",
                    150,
                ),
                _linha(
                    "amostras_animais_quantidade",
                    "Animais registrados em amostras, reclamações, capturas ou acidentes",
                    _sum(conn, "SELECT SUM(COALESCE(quantidade,0)) FROM amostras_animais WHERE data BETWEEN ? AND ?", (d_ini, d_fim)),
                    "animais",
                    160,
                ),
            ])

        return linhas
    finally:
        conn.close()


def _salvos(db_path, ano_mes):
    ensure_schema(db_path)
    conn = db_core.connect(db_path)
    try:
        rows = conn.execute("""
            SELECT chave, origem, ordem, indicador, quantidade, unidade, ativo
              FROM boletim_mensal_itens
             WHERE ano_mes=?
             ORDER BY ordem, id_item
        """, (ano_mes,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def boletim(db_path, ano_mes, usar_salvos=True):
    periodo = periodo_mes(ano_mes)
    autos = linhas_automaticas(db_path, periodo["ano_mes"])
    if not usar_salvos:
        linhas = autos
    else:
        salvos = _salvos(db_path, periodo["ano_mes"])
        por_chave = {row["chave"]: row for row in salvos}
        linhas = []
        for auto in autos:
            salvo = por_chave.pop(auto["chave"], None)
            if salvo:
                indicador_salvo = salvo["indicador"]
                if indicador_salvo in LEGACY_INDICADORES:
                    indicador_salvo = auto["indicador"]
                auto.update({
                    "origem": "auto",
                    "ordem": int(salvo["ordem"]),
                    "indicador": indicador_salvo,
                    "quantidade": int(salvo["quantidade"] or 0),
                    "unidade": salvo["unidade"] or "",
                    "ativo": bool(salvo["ativo"]),
                    "ajustado": True,
                })
            linhas.append(auto)
        for row in por_chave.values():
            if row["origem"] == "manual":
                linhas.append({
                    "chave": row["chave"],
                    "origem": "manual",
                    "ordem": int(row["ordem"]),
                    "indicador": row["indicador"],
                    "quantidade": int(row["quantidade"] or 0),
                    "unidade": row["unidade"] or "",
                    "ativo": bool(row["ativo"]),
                    "ajustado": True,
                })
        linhas.sort(key=lambda item: (int(item.get("ordem") or 0), item.get("indicador") or ""))
    total = sum(int(item.get("quantidade") or 0) for item in linhas if item.get("ativo"))
    return {
        "periodo": periodo,
        "linhas": linhas,
        "total": total,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


def salvar(db_path, ano_mes, linhas):
    periodo = periodo_mes(ano_mes)
    ensure_schema(db_path)
    agora = datetime.now().isoformat(timespec="seconds")
    conn = db_core.connect(db_path)
    try:
        conn.execute("DELETE FROM boletim_mensal_itens WHERE ano_mes=?", (periodo["ano_mes"],))
        for idx, item in enumerate(linhas or [], 1):
            indicador = (item.get("indicador") or "").strip()
            if not indicador:
                continue
            chave = (item.get("chave") or "").strip() or f"manual_{uuid.uuid4().hex}"
            origem = item.get("origem") if item.get("origem") in ("auto", "manual") else "manual"
            try:
                quantidade = int(item.get("quantidade") or 0)
            except (TypeError, ValueError):
                quantidade = 0
            conn.execute("""
                INSERT INTO boletim_mensal_itens
                    (ano_mes, chave, origem, ordem, indicador, quantidade, unidade, ativo, atualizado_em)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                periodo["ano_mes"],
                chave,
                origem,
                int(item.get("ordem") or idx * 10),
                indicador,
                quantidade,
                (item.get("unidade") or "").strip(),
                1 if item.get("ativo", True) else 0,
                agora,
            ))
        conn.commit()
    finally:
        conn.close()
    return boletim(db_path, periodo["ano_mes"], usar_salvos=True)
