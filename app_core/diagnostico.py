import re
import unicodedata
from datetime import datetime
from pathlib import Path


CORE_TABLES = (
    "usuarios",
    "localidades",
    "agentes",
    "visitas",
    "visita_agentes",
    "depositos_inspecionados",
    "tratamentos",
    "coletas",
    "resultados_laboratorio",
    "focos_positivos",
    "agenda_eventos",
    "importacoes",
)


def gerar(conn, db_path=None, backup_dir=None):
    itens = []
    tabelas = _tables(conn)

    _check_integridade(conn, itens)
    _check_tabelas(tabelas, itens)
    _check_foreign_keys(conn, itens)
    _check_vinculos_principais(conn, tabelas, itens)
    _check_dados_operacionais(conn, tabelas, itens)
    _check_duplicidades_textuais(conn, tabelas, itens)
    _check_backups(backup_dir, itens)

    resumo = _resumo(itens, db_path, tabelas)
    return {"resumo": resumo, "itens": itens}


def _check_integridade(conn, itens):
    try:
        valor = conn.execute("PRAGMA integrity_check").fetchone()[0]
    except Exception as exc:
        _add(itens, "erro", "Banco", "Falha ao verificar integridade do banco.", detalhe=str(exc))
        return
    if valor == "ok":
        _add(itens, "ok", "Banco", "Integridade SQLite confirmada.", valor="ok")
    else:
        _add(itens, "erro", "Banco", "Integridade SQLite retornou problema.", valor=valor)


def _check_tabelas(tabelas, itens):
    ausentes = [nome for nome in CORE_TABLES if nome not in tabelas]
    if ausentes:
        _add(
            itens,
            "erro",
            "Estrutura",
            "Tabelas essenciais ausentes.",
            valor=len(ausentes),
            detalhe=", ".join(ausentes),
        )
    else:
        _add(itens, "ok", "Estrutura", "Tabelas essenciais encontradas.", valor=len(CORE_TABLES))


def _check_foreign_keys(conn, itens):
    try:
        rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    except Exception as exc:
        _add(itens, "aviso", "Vinculos", "Nao foi possivel executar foreign_key_check.", detalhe=str(exc))
        return
    if not rows:
        _add(itens, "ok", "Vinculos", "Nenhuma quebra de chave estrangeira detectada.")
        return
    exemplos = []
    for row in rows[:8]:
        valores = tuple(row)
        exemplos.append(f"{valores[0]} rowid {valores[1]} -> {valores[2]}")
    _add(
        itens,
        "erro",
        "Vinculos",
        "Ha registros apontando para dados inexistentes.",
        valor=len(rows),
        detalhe="; ".join(exemplos),
    )


def _check_vinculos_principais(conn, tabelas, itens):
    checks = (
        (
            {"visita_agentes", "visitas"},
            "Visitas",
            "Agentes vinculados a visitas inexistentes.",
            """SELECT COUNT(*) FROM visita_agentes va
               LEFT JOIN visitas v ON v.id_visita=va.id_visita
              WHERE v.id_visita IS NULL""",
            "erro",
        ),
        (
            {"coletas", "visitas"},
            "Laboratorio",
            "Coletas sem visita correspondente.",
            """SELECT COUNT(*) FROM coletas c
               LEFT JOIN visitas v ON v.id_visita=c.id_visita
              WHERE v.id_visita IS NULL""",
            "erro",
        ),
        (
            {"resultados_laboratorio", "coletas"},
            "Laboratorio",
            "Resultados de laboratorio sem coleta correspondente.",
            """SELECT COUNT(*) FROM resultados_laboratorio rl
               LEFT JOIN coletas c ON c.id_coleta=rl.id_coleta
              WHERE c.id_coleta IS NULL""",
            "erro",
        ),
        (
            {"esporotricose_animais", "esporotricose_visitas"},
            "Esporotricose",
            "Animais de esporotricose sem visita correspondente.",
            """SELECT COUNT(*) FROM esporotricose_animais a
               LEFT JOIN esporotricose_visitas v ON v.id_visita=a.id_visita
              WHERE v.id_visita IS NULL""",
            "erro",
        ),
        (
            {"ovitrampas_ocorrencias_conta_ovos", "ovitrampas_armadilhas"},
            "Ovitrampas",
            "Ocorrencias importadas sem cadastro mestre da armadilha.",
            """SELECT COUNT(DISTINCT o.ovitrampa_id)
                 FROM ovitrampas_ocorrencias_conta_ovos o
                 LEFT JOIN ovitrampas_armadilhas a ON a.ovitrampa_id=o.ovitrampa_id
                WHERE a.ovitrampa_id IS NULL""",
            "aviso",
        ),
    )
    for required, categoria, titulo, sql, nivel in checks:
        if not required.issubset(tabelas):
            continue
        total = _scalar(conn, sql)
        if total:
            _add(itens, nivel, categoria, titulo, valor=total)


def _check_dados_operacionais(conn, tabelas, itens):
    if {"visitas", "visita_agentes"}.issubset(tabelas):
        total = _scalar(
            conn,
            """SELECT COUNT(*) FROM visitas v
                WHERE NOT EXISTS (
                      SELECT 1 FROM visita_agentes va WHERE va.id_visita=v.id_visita
                )""",
        )
        if total:
            _add(itens, "aviso", "Visitas", "Visitas sem agente vinculado.", valor=total)

    if "visitas" in tabelas:
        total = _scalar(
            conn,
            """SELECT COUNT(*) FROM visitas
                WHERE TRIM(COALESCE(localidade,''))='' AND id_localidade IS NULL""",
        )
        if total:
            _add(itens, "aviso", "Visitas", "Visitas sem localidade.", valor=total)

        pendentes = _scalar(
            conn,
            "SELECT COUNT(*) FROM visitas WHERE tipo='TBO' AND COALESCE(CONTAOVOS_STATUS,0)=0",
        ) if _has_column(conn, "visitas", "CONTAOVOS_STATUS") else 0
        if pendentes:
            _add(itens, "aviso", "Conta Ovos", "Leituras TBO pendentes de Conta Ovos.", valor=pendentes)

    if {"coletas", "resultados_laboratorio"}.issubset(tabelas):
        total = _scalar(
            conn,
            """SELECT COUNT(*) FROM coletas c
               LEFT JOIN resultados_laboratorio rl ON rl.id_coleta=c.id_coleta
              WHERE rl.id_coleta IS NULL""",
        )
        if total:
            _add(
                itens,
                "info",
                "Laboratorio",
                "Coletas ainda sem resultado de laboratorio.",
                valor=total,
                detalhe="Pode ser normal quando as larvas ainda nao foram lidas.",
            )

    if "resultados_laboratorio" in tabelas:
        total = _scalar(
            conn,
            """SELECT COUNT(*) FROM resultados_laboratorio
                WHERE TRIM(COALESCE(laboratorista,''))='' OR TRIM(COALESCE(data_leitura,''))=''""",
        )
        if total:
            _add(itens, "aviso", "Laboratorio", "Resultados sem laboratorista ou data de leitura.", valor=total)

    if "tratamentos" in tabelas:
        total = _scalar(
            conn,
            """SELECT COUNT(*) FROM tratamentos
                WHERE COALESCE(qtd_depositos_tratados,0)>0
                  AND (quantidade_carga IS NULL OR quantidade_carga=0)""",
        ) if _has_column(conn, "tratamentos", "qtd_depositos_tratados") else 0
        if total:
            _add(itens, "aviso", "SisPNCD", "Tratamentos com deposito tratado, mas sem carga.", valor=total)

    if "depositos_inspecionados" in tabelas:
        total = _scalar(
            conn,
            """SELECT COUNT(*) FROM depositos_inspecionados
                WHERE COALESCE(tratado,0)>0
                  AND (qtd_carga IS NULL OR qtd_carga=0)""",
        ) if _has_column(conn, "depositos_inspecionados", "qtd_carga") else 0
        if total:
            _add(itens, "aviso", "SisPNCD", "Depositos tratados sem carga informada.", valor=total)

    if "focos_positivos" in tabelas:
        pendentes = _scalar(
            conn,
            "SELECT COUNT(*) FROM focos_positivos WHERE status_notificacao='pendente' AND gera_notificacao=1",
        )
        atrasados = _scalar(
            conn,
            """SELECT COUNT(*) FROM focos_positivos
                WHERE status_notificacao='pendente'
                  AND gera_notificacao=1
                  AND date(COALESCE(processado_em, data)) <= date('now', '-7 days')""",
        )
        if atrasados:
            _add(itens, "aviso", "Notificacoes", "Notificacoes pendentes ha 7 dias ou mais.", valor=atrasados)
        elif pendentes:
            _add(itens, "info", "Notificacoes", "Notificacoes pendentes.", valor=pendentes)

    if "ovitrampas_leituras" in tabelas:
        sem_laboratorista = _scalar(
            conn,
            "SELECT COUNT(*) FROM ovitrampas_leituras WHERE id_laboratorista IS NULL",
        )
        if sem_laboratorista:
            _add(itens, "info", "Ovitrampas", "Leituras sem laboratorista.", valor=sem_laboratorista)
        sem_data = _scalar(
            conn,
            "SELECT COUNT(*) FROM ovitrampas_leituras WHERE TRIM(COALESCE(data_leitura,''))=''",
        )
        if sem_data:
            _add(itens, "info", "Ovitrampas", "Leituras sem data de leitura.", valor=sem_data)

    if {"ovitrampas_ocorrencias_conta_ovos", "ovitrampas_leituras"}.issubset(tabelas):
        ocorrencias = _scalar(
            conn,
            "SELECT COUNT(*) FROM ovitrampas_ocorrencias_conta_ovos WHERE ocorrencia_codigo BETWEEN 1 AND 9",
        )
        leituras = _scalar(conn, "SELECT COUNT(*) FROM ovitrampas_leituras")
        if ocorrencias and not leituras:
            _add(
                itens,
                "aviso",
                "Ovitrampas",
                "Historico de ocorrencias existe, mas nao ha leituras semanais importadas.",
                valor=ocorrencias,
            )


def _check_duplicidades_textuais(conn, tabelas, itens):
    for tabela, coluna, categoria, titulo in (
        ("localidades", "nome", "Padronizacao", "Localidades possivelmente duplicadas por acento/caixa."),
        ("agentes", "nome", "Padronizacao", "Agentes possivelmente duplicados por acento/caixa."),
    ):
        if tabela not in tabelas or not _has_column(conn, tabela, coluna):
            continue
        grupos = {}
        for row in conn.execute(f"SELECT {coluna} AS nome FROM {tabela} WHERE TRIM(COALESCE({coluna},''))<>''"):
            nome = row["nome"]
            grupos.setdefault(_norm(nome), set()).add(nome)
        suspeitos = [sorted(valores) for valores in grupos.values() if len(valores) > 1]
        if suspeitos:
            detalhe = "; ".join(", ".join(item) for item in suspeitos[:6])
            _add(itens, "aviso", categoria, titulo, valor=len(suspeitos), detalhe=detalhe)


def _check_backups(backup_dir, itens):
    if not backup_dir:
        return
    pasta = Path(backup_dir)
    if not pasta.exists():
        _add(itens, "aviso", "Backups", "Pasta de backups ainda nao existe.", detalhe=str(pasta))
        return
    backups = sorted(pasta.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        _add(itens, "aviso", "Backups", "Nenhum backup encontrado.", detalhe=str(pasta))
        return
    ultimo = backups[0]
    modificado = datetime.fromtimestamp(ultimo.stat().st_mtime)
    dias = (datetime.now() - modificado).days
    if dias > 7:
        _add(
            itens,
            "aviso",
            "Backups",
            "Backup mais recente tem mais de 7 dias.",
            valor=f"{dias} dias",
            detalhe=ultimo.name,
        )
    else:
        _add(itens, "ok", "Backups", "Backup recente encontrado.", valor=ultimo.name)


def _resumo(itens, db_path, tabelas):
    contagens = {
        "erro": sum(1 for item in itens if item["nivel"] == "erro"),
        "aviso": sum(1 for item in itens if item["nivel"] == "aviso"),
        "info": sum(1 for item in itens if item["nivel"] == "info"),
        "ok": sum(1 for item in itens if item["nivel"] == "ok"),
    }
    if contagens["erro"]:
        status = "critico"
        status_label = "Precisa de atencao"
    elif contagens["aviso"]:
        status = "atencao"
        status_label = "Com avisos"
    else:
        status = "ok"
        status_label = "Estavel"
    return {
        "status": status,
        "status_label": status_label,
        "contagens": contagens,
        "total_itens": len(itens),
        "tabelas": len(tabelas),
        "banco": str(db_path) if db_path else "",
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }


def _add(itens, nivel, categoria, titulo, valor=None, detalhe=""):
    itens.append({
        "nivel": nivel,
        "categoria": categoria,
        "titulo": titulo,
        "valor": valor,
        "detalhe": detalhe,
    })


def _tables(conn):
    return {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _has_column(conn, table, column):
    try:
        return column in {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    except Exception:
        return False


def _scalar(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "", text.lower())
    return text
