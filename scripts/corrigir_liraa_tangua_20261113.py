"""Aplica ao ciclo 4 somente a correção do quarteirão das visitas conferidas."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_core import db, kobo_api, liraa, liraa_integracao, liraa_kobo, liraa_sequencias
from scripts.ativar_acesso_externo_windows import connect


CICLO = 4
LOCALIDADE = "Tanguá"
ORIGEM = "0028"
DESTINO = "0001"
DIA = "2026-11-10"
ENVIOS = {
    911738696: {1343}, 911749753: {1360}, 911757573: {1409, 1410},
    911758017: {1413}, 911758178: {1414}, 911758766: {1416},
}
HOME = Path("C:/ProgramData/EndemiasWeb")
MARKER = "ativacao-liraa-cobertura277"


def aplicar(conn, records, esperados=ENVIOS, ciclo=CICLO, localidade=LOCALIDADE,
            origem=ORIGEM, destino=DESTINO, dia=DIA):
    """Valida o lote inteiro e corrige em uma transação, mantendo as chaves."""
    with conn:
        liraa_kobo.bloquear_importacao(conn)
        liraa._bloquear_ciclo(conn, ciclo)
        context = liraa_kobo._contexto(conn, ciclo)
        achados = {}
        for record in records:
            ident = kobo_api.record_id(record)
            if ident not in esperados:
                continue
            if ident in achados:
                raise ValueError(f"Envio Kobo {ident} apareceu mais de uma vez.")
            item = liraa_kobo._normalizar(record)
            if (
                item["localidade_informada"] != localidade or item["quarteirao"] != destino
                or item["data_visita"] != dia or item["form_ciclo"] != str(ciclo)
                or liraa_kobo._vincular(item, context)[2] not in {"sorteado", "adicional"}
            ):
                raise ValueError(f"Envio Kobo {ident} mudou desde a conferência.")
            achados[ident] = (record, item)
        if achados.keys() != esperados.keys():
            raise ValueError("A consulta não localizou todos os envios de Tanguá.")

        alteradas = []
        em = datetime.now().isoformat(timespec="seconds")
        for ident, ids in esperados.items():
            record, item = achados[ident]
            visitas = [db.serialize_row(row) for row in conn.execute(
                "SELECT * FROM liraa_visitas WHERE kobo_id=? ORDER BY id_visita", (ident,),
            )]
            if {v["id_visita"] for v in visitas} != ids:
                raise ValueError(f"Os vínculos do envio {ident} mudaram desde a conferência.")
            sequencias, _ = liraa_sequencias.separar(item["sequencia"])
            if {v["sequencia"] or "" for v in visitas} != set(sequencias) or len(visitas) != len(sequencias):
                raise ValueError(f"As sequências do envio {ident} mudaram desde a conferência.")
            linhagem = liraa_kobo._uuids_anteriores(record, item["kobo_uuid"]) | {item["kobo_uuid"]}
            for v in visitas:
                meta = json.loads(v["tratamento_json"] or "{}")
                raiz = (meta.get(liraa_sequencias.META) or {}).get("uuid_origem") or v["kobo_uuid"]
                if (
                    v["id_ciclo"] != ciclo or v["localidade_informada"] != localidade
                    or v["data_visita"] != dia or v["quarteirao"] not in {origem, destino}
                    or raiz not in linhagem
                ):
                    raise ValueError(f"A visita {v['id_visita']} não corresponde à conferência.")
                if v["quarteirao"] == destino:
                    continue
                nova = {**v, "quarteirao": destino}
                loc, estrato, vinculo = liraa_kobo._vincular(nova, context)
                if vinculo not in {"sorteado", "adicional"}:
                    raise ValueError(f"A visita {v['id_visita']} não se vincula ao destino.")
                conn.execute("""UPDATE liraa_visitas
                    SET quarteirao=?,id_localidade=?,id_estrato=?,situacao_vinculo=?
                    WHERE id_visita=?""", (destino, loc, estrato, vinculo, v["id_visita"]))
                liraa_integracao.sincronizar_foco(conn, v["id_visita"])
                alteradas.append(v["id_visita"])
                detalhes = {"id_ciclo": ciclo, "id_kobo": ident, "localidade": localidade,
                            "quarteirao_anterior": origem, "quarteirao_atual": destino,
                            "motivo": "Correção de quarteirão confirmada no Kobo e autorizada pelo operador"}
                conn.execute("""INSERT INTO auditoria_eventos
                    (acao,entidade,entidade_id,usuario_nome,detalhes_json,criado_em,setor)
                    VALUES('liraa_visita_corrigida','liraa_visita',?,'Operação VSATT',?,?,'endemias')""",
                    (str(v["id_visita"]), json.dumps(detalhes, ensure_ascii=False), em))
        return {"status": "aplicado", "ciclo": ciclo, "visitas_corrigidas": alteradas,
                "visitas_conferidas": sorted(set().union(*esperados.values())), "em": em}


def executar():
    activation = json.loads((HOME / (MARKER + "-resultado.json")).read_text(encoding="utf-8"))
    if activation.get("status") != "aplicado" or activation.get("version") != "2.7.7" or not activation.get("backup"):
        raise ValueError("A ativação e o backup precisam estar concluídos.")
    config = json.loads((HOME / "config.json").read_text(encoding="utf-8"))
    if config.get("version") != "2.7.7" or config["env"].get("ENDEMIAS_PG_DATABASE") != "endemias":
        raise ValueError("Instalação diferente da conferida.")

    cfg_path = config["env"].get("ENDEMIAS_KOBO_CONFIG_PATH") or str(Path(config["root"]) / "kobo_config.json")
    cfg = kobo_api.load_config(cfg_path)
    raw = connect(config, readonly=True)
    try:
        conn = db.PostgreSQLConnection(raw)
        row = conn.execute("SELECT kobo_uid FROM liraa_ciclo_config WHERE id_ciclo=?", (CICLO,)).fetchone()
        uid = (row[0] if row else "") or cfg["assets"].get("LIRAA")
    finally:
        raw.close()
    if not uid:
        raise ValueError("O formulário LIRAa do ciclo não está configurado.")
    records = kobo_api.fetch_complete_submissions(cfg, uid, start="2026-11-09", end="2026-11-14")

    raw = connect(config)
    try:
        conn = db.PostgreSQLConnection(raw)
        result = aplicar(conn, records)
        from app_core import liraa_acompanhamento
        from app_core import liraa_operacional
        target = db.DatabaseTarget("postgresql", config["env"]["ENDEMIAS_PG_DATABASE"])
        painel = liraa_acompanhamento.resumir(target, CICLO, datetime.now().date().isoformat())
        plano = liraa_operacional.plano(target, CICLO, Path(config["root"]))
        solicitados = liraa_operacional.retirados_conn(conn, CICLO, plano["plano_hash"])
        ativos = {(q["id_localidade"], q["quarteirao"]) for q in plano["quarteiroes"]}
        pendentes = {(q["localidade"], q["quarteirao"]) for q in painel["quarteiroes_pendentes"]}
        result.update(
            retirados_fora_do_plano=not bool(solicitados & ativos),
            tangua_0001_coberto=(LOCALIDADE, DESTINO) not in pendentes,
            quarteiroes_no_plano=painel["total_quarteiroes"],
            quarteiroes_pendentes=len(pendentes),
            meta=painel["meta"],
            percentual=painel["percentual"],
        )
    finally:
        raw.close()
    (HOME / (MARKER + "-tangua.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Tanguá: {len(result['visitas_conferidas'])} visitas conferidas, {len(result['visitas_corrigidas'])} corrigidas.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", required=True)
    parser.parse_args()
    try:
        executar()
    except Exception as error:
        print(f"Correção de Tanguá interrompida ({type(error).__name__}). Confira o resultado com o Codex.")
        raise SystemExit(1)

