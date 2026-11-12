"""Importação automática conservadora dos envios recentes do Kobo."""

from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid
import os

from app_core import db, import_history, kobo_api, postgresql_migrations
from app_core import visitas as visitas_core
import etl


TABELAS_UUID = {
    "LIRAA": "liraa_visitas",
    "PE": "visitas", "TB": "visitas", "TBO": "visitas", "PVE": "visitas",
    "LARVAS": "resultados_laboratorio", "ESPOROTRICOSE": "esporotricose_visitas",
    "BRI": "bri_registros", "AMOSTRA_ANIMAIS": "amostras_animais",
    "RECOLHIMENTO": "recolhimentos",
}


class ImportacaoAutomaticaErro(RuntimeError):
    pass


def periodo_7_dias(hoje=None):
    hoje = hoje or date.today()
    return (hoje - timedelta(days=6)).isoformat(), hoje.isoformat()


def _exigir_migracoes(target, diretorio):
    if db.is_sqlite(target):
        return
    conn = db.connect(target)
    try:
        estados = postgresql_migrations.status(conn, diretorio)
        pendentes = [item["name"] for item in estados if item["state"] != "applied"]
        if pendentes:
            raise ImportacaoAutomaticaErro("Migrações pendentes ou divergentes: " + ", ".join(pendentes))
    finally:
        conn.close()


def _uuids_existentes(target, tipo, registros):
    uuids = [kobo_api.record_uuid(item) for item in registros]
    if any(not value for value in uuids):
        raise ImportacaoAutomaticaErro(f"{tipo}: envio Kobo sem UUID; importação interrompida.")
    if len(set(uuids)) != len(uuids):
        raise ImportacaoAutomaticaErro(f"{tipo}: UUID repetido na resposta Kobo.")
    if not uuids:
        return set()
    conn = db.connect(target)
    if tipo == "LARVAS":
        from app_core import visitas_integradas
        conn=visitas_integradas.integrar(conn)
    try:
        encontrados = set()
        for inicio in range(0, len(uuids), 500):
            lote = uuids[inicio:inicio + 500]
            placeholders = ",".join("?" for _ in lote)
            encontrados.update(row[0] for row in conn.execute(
                f"SELECT DISTINCT kobo_uuid FROM {TABELAS_UUID[tipo]} "
                f"WHERE kobo_uuid IN ({placeholders})", lote,
            ).fetchall())
            if tipo == "LIRAA" and db.table_exists(conn,"liraa_visitas_excluidas"):
                encontrados.update(r[0] for r in conn.execute(f"SELECT kobo_uuid FROM liraa_visitas_excluidas WHERE kobo_uuid IN ({placeholders})", lote))
        return encontrados
    finally:
        conn.close()


def _buscar_novos(cfg, target, inicio, fim, tipos_permitidos=None):
    novos = {}
    totais = {}
    for tipo in kobo_api.ALL_TYPES:
        if tipos_permitidos is not None and tipo not in tipos_permitidos:continue
        uid = str((cfg.get("assets") or {}).get(tipo) or "").strip()
        if not uid and tipo != "LIRAA":
            continue
        if tipo == "LIRAA":
            from app_core import liraa_integracao
            registros,resposta=liraa_integracao.buscar_kobo(cfg,target,inicio,fim)
            if resposta is None:
                continue
        else:
            registros, resposta = kobo_api.fetch_submissions(cfg, uid, limit=5000, start=inicio, end=fim)
        if isinstance(resposta, dict):
            if "count" not in resposta and len(registros) >= 5000:
                raise ImportacaoAutomaticaErro(
                    f"{tipo}: limite de 5.000 atingido sem total verificável."
                )
            try:
                total = int(resposta.get("count", len(registros)))
            except (TypeError, ValueError) as exc:
                raise ImportacaoAutomaticaErro(f"{tipo}: total inválido do Kobo.") from exc
            if resposta.get("next") or total != len(registros):
                raise ImportacaoAutomaticaErro(
                    f"{tipo}: resposta incompleta ({len(registros)} de {total}); "
                    "use a importação manual em períodos menores."
                )
        elif len(registros) >= 5000:
            raise ImportacaoAutomaticaErro(f"{tipo}: limite de 5.000 atingido sem total verificável.")
        existentes = _uuids_existentes(target, tipo, registros)
        revisoes = set()
        if tipo == "LIRAA" and registros:
            from app_core import liraa_kobo
            conn = db.connect(target)
            try:
                revisoes = liraa_kobo.edicoes_kobo_para_revisao(conn, registros)
            finally:
                conn.close()
            existentes.update(revisoes)
        novos[tipo] = [item for item in registros if kobo_api.record_uuid(item) not in existentes]
        totais[tipo] = {"recebidos": len(registros), "novos": len(novos[tipo])}
        if tipo == "LIRAA":
            totais[tipo]["edicoes_para_revisao"] = len(revisoes)
    return novos, totais


def _atualizar_catalogos(cfg, target, novos):
    avisos = []
    for tipo, formulario in (("PVE", "PVE"), ("ESPOROTRICOSE", "Esporotricose"), ("LIRAA", "LIRAa")):
        if not novos.get(tipo):
            continue
        try:
            itens = kobo_api.obter_catalogo_acs_formulario(
                cfg, cfg["assets"][tipo], formulario,
            )
            visitas_core.sincronizar_catalogo_acs(target, itens)
        except Exception as exc:
            avisos.append(f"{tipo}: catálogo ACS não atualizado ({exc})")
    return avisos


def _aviso_lacuna(target, inicio, setor=None):
    conn = db.connect(target)
    try:
        row = conn.execute(
            "SELECT MAX(criado_em) FROM importacoes "
            "WHERE status IN ('auto_confirmado', 'auto_sem_novos')" + (' AND setor=?' if setor else ''),
            (setor,) if setor else (),
        ).fetchone()
        anterior = row[0] if row else None
    finally:
        conn.close()
    if anterior and datetime.fromisoformat(str(anterior)).date().isoformat() < inicio:
        return "Mais de 7 dias desde a última execução bem-sucedida; confira o intervalo anterior manualmente."
    return None


def executar(*, target, config_path, kobo_config_path, migracoes_dir,
             hoje=None, aplicar=False, setor=None):
    """Falha fechada: consulta integral, dry-run e só então grava um lote único."""
    from app_core import setores
    if setor is not None and setor not in setores.SETORES:
        raise ImportacaoAutomaticaErro('Setor invalido.')
    if str(os.environ.get('ENDEMIAS_SETORES_ENABLED','')).lower() in {'1','true','sim'} and setor is None:
        raise ImportacaoAutomaticaErro('Informe o setor da rotina automatica antes de executar na divisao.')
    options={'tipos_permitidos':setores.TIPOS_KOBO[setor]} if setor else {}
    history_options={'setor':setor} if setor else {}
    if aplicar and db.is_sqlite(target):
        raise ImportacaoAutomaticaErro("A gravação automática exige PostgreSQL.")
    inicio, fim = periodo_7_dias(hoje)
    job_id = str(uuid.uuid4())
    get_db = lambda: db.connect(target)
    if aplicar:
        import_history.registrar_importacao(get_db, job_id, [], "auto_preparando", "Kobo automático",**history_options)
    try:
        _exigir_migracoes(target, migracoes_dir)
        cfg = kobo_api.load_config(kobo_config_path)
        if not cfg.get("server_url") or not cfg.get("api_token"):
            raise ImportacaoAutomaticaErro("Kobo não configurado para a importação automática.")
        if not any(str(value or "").strip() for value in (cfg.get("assets") or {}).values()):
            raise ImportacaoAutomaticaErro("Nenhum formulário Kobo configurado.")
        novos, totais = _buscar_novos(cfg, target, inicio, fim,**options)
        quantidade = sum(item["novos"] for item in totais.values())
        relatorio = {"inicio": inicio, "fim": fim, "formularios": totais, "novos": quantidade}
        if aplicar:
            aviso = _aviso_lacuna(target, inicio,**history_options)
            if aviso:
                relatorio["avisos"] = [aviso]
        if not quantidade:
            if aplicar:
                import_history.atualizar_importacao(get_db, job_id, "auto_sem_novos", sumario=[relatorio])
            return relatorio
        with TemporaryDirectory(prefix="endemias_kobo_auto_") as diretorio:
            caminhos = kobo_api.write_etl_workbooks(novos, config_path, diretorio, prefix=job_id[:8])
            if not caminhos:
                raise ImportacaoAutomaticaErro("Há envios novos, mas nenhum arquivo foi gerado.")
            trabalho = [p for p in caminhos if Path(p).name.upper().split("_", 1)[0] != "LARVAS"]
            larvas = [p for p in caminhos if p not in trabalho]
            verificado, resumo = etl.processar_upload(
                trabalho, larvas, target, config_path, etl.Logger(), dry_run=True,**options,
            )
            if not verificado:
                raise ImportacaoAutomaticaErro("Verificação do lote falhou; banco não alterado.")
            if aplicar:
                gravado, resumo = etl.processar_upload(
                    trabalho, larvas, target, config_path, etl.Logger(),
                    dry_run=False, backup_confirmado=True,**options,
                )
                if not gravado:
                    raise ImportacaoAutomaticaErro("Gravação falhou; transação revertida.")
                avisos = _atualizar_catalogos(cfg, target, novos)
                if avisos:
                    relatorio.setdefault("avisos", []).extend(avisos)
                import_history.atualizar_importacao(
                    get_db, job_id, "auto_confirmado", dry_run_ok=True,
                    commit_ok=True, sumario=[relatorio],
                )
        return relatorio
    except Exception as exc:
        if aplicar:
            import_history.atualizar_importacao(
                get_db, job_id, "auto_erro", commit_ok=False, erro=str(exc),
            )
        raise
