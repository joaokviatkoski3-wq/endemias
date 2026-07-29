"""Homologa a pagina e o fluxo laboratorial de Ovitrampas no PostgreSQL."""

import argparse
import csv
import logging
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import ovitrampas  # noqa: E402
from app_core import ovitrampas_laboratorio  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "ovitrampas_armadilhas",
    "ovitrampas_armadilhas_historico",
    "ovitrampas_leituras",
    "ovitrampas_ocorrencias_conta_ovos",
    "ovitrampas_diarios",
    "ovitrampas_diario_armadilhas",
    "ovitrampas_calendario_grupos",
    "ovitrampas_calendario_eventos",
    "ovitrampas_calendario_agentes",
    "ovitrampas_laboratorio_lotes",
    "ovitrampas_laboratorio_itens",
)


class _SharedConnection:
    def __init__(self, conn):
        self._conn = conn
        self.backend = conn.backend

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Testa a pagina de Ovitrampas sem alterar as tabelas publicas."
        )
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio para qualquer banco diferente de endemias_teste.",
    )
    return parser


def _public_counts(conn):
    tables = [
        row[0]
        for row in conn.execute(
            """SELECT table_name
                 FROM information_schema.tables
                WHERE table_schema='public'
                  AND table_type='BASE TABLE'
                ORDER BY table_name"""
        ).fetchall()
    ]
    return {
        table: conn.execute(
            f"SELECT COUNT(*) FROM public.{table}"
        ).fetchone()[0]
        for table in tables
    }


def _temporary_schema(conn):
    for table in TEMP_TABLES:
        conn.execute(
            f"""CREATE TEMPORARY TABLE {table}
                (LIKE public.{table} INCLUDING ALL)
                ON COMMIT PRESERVE ROWS"""
        )
    conn.commit()


def _write_csv(path, rows):
    fields = [
        "ID",
        "Rua",
        "Numero do logradouro",
        "Complemento",
        "Bairro",
        "Localizacao da ovitrampa",
        "Setor/Distrito da ovitrampa",
        "Responsavel",
        "Quarteirao",
        "Latitude",
        "Longitude",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def _reading(ovitrampa_id, week, eggs, collected):
    reading_id = f"pg-{ovitrampa_id}-{week}"
    return {
        "id_leitura": reading_id,
        "ovitrampa_id": ovitrampa_id,
        "estado": "Parana",
        "municipio": "Almirante Tamandare",
        "distrito": "Tamboara",
        "rua": "Rua Teste",
        "numero": "10",
        "complemento": "Temporario",
        "localizacao": "Fundos",
        "latitude": -25.1,
        "longitude": -49.2,
        "ano": 2026,
        "semana": week,
        "data_envio_contagem": f"{collected}T17:00:00",
        "ovos": eggs,
        "quem_enviou": "Teste",
        "observacao": None,
        "lat_lng": "-25.1,-49.2",
        "quarteirao": "0012",
        "data_instalacao": "2026-07-20",
        "data_coleta": collected,
        "ocorrencia_codigo": None,
        "arquivo_origem": "temporario.csv",
        "importado_em": "2026-07-29T10:00:00",
    }


def _test_temporary_data(target):
    conn = db_core.connect(target)
    original_connect = db_core.connect
    try:
        before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        with tempfile.TemporaryDirectory() as tmpdir:
            cadastro = Path(tmpdir) / "cadastro.csv"
            _write_csv(
                cadastro,
                [
                    {
                        "ID": "901",
                        "Rua": "Rua Teste",
                        "Numero do logradouro": "10",
                        "Complemento": "UBS Temporaria",
                        "Bairro": "Centro",
                        "Localizacao da ovitrampa": "Fundos",
                        "Setor/Distrito da ovitrampa": "Tamboara",
                        "Responsavel": "Maria",
                        "Quarteirao": "12",
                        "Latitude": "-25.1",
                        "Longitude": "-49.2",
                    },
                    {
                        "ID": "902-A",
                        "Rua": "Rua Teste",
                        "Numero do logradouro": "20",
                        "Complemento": "Escola Temporaria",
                        "Bairro": "Centro",
                        "Localizacao da ovitrampa": "Entrada",
                        "Setor/Distrito da ovitrampa": "Tamboara",
                        "Responsavel": "Jose",
                        "Quarteirao": "13",
                        "Latitude": "-25.2",
                        "Longitude": "-49.3",
                    },
                ],
            )
            result = ovitrampas.importar_armadilhas_csv(
                target, cadastro, motivo="Homologacao PostgreSQL", usuario="Teste"
            )
            if result["inseridos"] != 2:
                raise RuntimeError("O cadastro temporario nao inseriu duas armadilhas.")

            _write_csv(
                cadastro,
                [
                    {
                        "ID": "901",
                        "Rua": "Rua Teste Atualizada",
                        "Numero do logradouro": "10",
                        "Complemento": "UBS Temporaria",
                        "Bairro": "Centro",
                        "Localizacao da ovitrampa": "Fundos",
                        "Setor/Distrito da ovitrampa": "Tamboara",
                        "Responsavel": "Maria",
                        "Quarteirao": "12",
                        "Latitude": "-25.1",
                        "Longitude": "-49.2",
                    }
                ],
            )
            result = ovitrampas.importar_armadilhas_csv(
                target, cadastro, motivo="Revisao PostgreSQL", usuario="Teste"
            )
            if result["atualizados"] != 1:
                raise RuntimeError("A atualizacao da armadilha temporaria falhou.")

        armadilhas = ovitrampas.listar_armadilhas(
            target, {"busca": "RUA TESTE"}, 10
        )
        if armadilhas["total"] != 2:
            raise RuntimeError("A busca de armadilhas sem diferenca de caixa falhou.")
        if armadilhas["registros"][1]["ovitrampa_id"] != "902-A":
            raise RuntimeError("A ordenacao de IDs alfanumericos divergiu.")

        historico = ovitrampas.historico_armadilha(target, "901")
        if not any(item["campo"] == "rua" for item in historico["alteracoes"]):
            raise RuntimeError("O historico da armadilha nao registrou a alteracao.")

        primeira_leitura = _reading("901", 29, 18, "2026-07-24")
        segunda_leitura = _reading("902-A", 29, 0, "2026-07-24")
        if not ovitrampas._insert(conn, primeira_leitura):
            raise RuntimeError("A leitura temporaria nao foi inserida.")
        if ovitrampas._insert(conn, primeira_leitura):
            raise RuntimeError("A leitura duplicada nao foi ignorada.")
        ovitrampas._insert(conn, segunda_leitura)
        ovitrampas._upsert_ocorrencia(
            conn,
            {
                "id_contagem": "pg-ocorrencia-1",
                "ovitrampa_id": "902-A",
                "ano": 2026,
                "semana": 29,
                "data": "2026-07-24",
                "data_envio_contagem": "2026-07-25T10:00:00",
                "ovos": 0,
                "resultado": "Negativa",
                "codigo_conta_ovos": 6,
                "observacao_conta_ovos": "Armadilha seca",
                "ocorrencia_codigo": 5,
                "latitude": -25.2,
                "longitude": -49.3,
                "lat_lng": "-25.2,-49.3",
                "arquivo_origem": "ocorrencias.csv",
                "importado_em": "2026-07-29T10:00:00",
            },
        )
        conn.commit()

        resumo = ovitrampas.resumo(target, {"ano": "2026", "semana": "29"})
        if resumo["totais"]["leituras"] != 2 or resumo["totais"]["ovos"] != 18:
            raise RuntimeError("O resumo temporario das leituras divergiu.")
        monitoramento = ovitrampas.monitoramento(
            target, {"ano": "2026", "semana_ini": "29", "semana_fim": "29"}
        )
        if monitoramento["totais"]["ocorrencias"] != 1:
            raise RuntimeError("O monitoramento nao retornou a ocorrencia.")

        agente = conn.execute(
            "SELECT id_agente FROM public.agentes WHERE ativo=1 ORDER BY id_agente LIMIT 1"
        ).fetchone()
        if agente:
            ovitrampas.atualizar_leitura(
                target,
                primeira_leitura["id_leitura"],
                {
                    "id_laboratorista": agente[0],
                    "data_leitura": "2026-07-29",
                },
            )
            lote_atualizado = ovitrampas.atualizar_leituras_lote(
                target,
                {"ano": "2026", "semana": "29"},
                {
                    "id_laboratorista": agente[0],
                    "data_leitura": "2026-07-29",
                    "somente_vazios": True,
                },
            )
            if lote_atualizado["atualizados"] != 1:
                raise RuntimeError("A atualizacao em lote das leituras falhou.")

        diario = ovitrampas.salvar_diario(
            target, {"nome": "Diario temporario", "ativo": True}
        )
        id_diario = diario["id_diario"]
        ovitrampas.vincular_armadilha_diario(
            target, {"id_diario": id_diario, "ovitrampa_id": "901"}
        )
        ovitrampas.vincular_armadilha_diario(
            target, {"id_diario": id_diario, "ovitrampa_id": "902-A"}
        )
        detalhe = ovitrampas.reordenar_armadilhas_diario(
            target, id_diario, ["902-A", "901"]
        )
        if [item["ovitrampa_id"] for item in detalhe["registros"]] != [
            "902-A",
            "901",
        ]:
            raise RuntimeError("A nova ordem do diario nao foi persistida.")

        grupo = ovitrampas.salvar_grupo(
            target,
            {
                "nome": "Grupo temporario",
                "localidades": "Tamboara",
                "cor": "#2563eb",
                "ativo": True,
            },
        )
        agentes = [agente[0]] if agente else []
        evento = ovitrampas.salvar_evento_calendario(
            target,
            {
                "data": "2099-01-10",
                "movimento": "troca",
                "id_grupo": grupo["id_grupo"],
                "ciclo": "Temporario",
                "agentes": agentes,
            },
            usuario_nome="Teste",
        )
        if evento["data"] != "2099-01-10":
            raise RuntimeError("A data do evento temporario divergiu.")
        if agentes and len(evento["agentes"]) != 1:
            raise RuntimeError("O agente do calendario nao foi vinculado.")

        agenda = ovitrampas.eventos_agenda(
            target, "2099-01-01", "2099-01-31"
        )
        if len(agenda) != 1 or agenda[0]["movimento"] != "troca":
            raise RuntimeError("O evento nao apareceu na integracao da Agenda.")

        evento_leitura = ovitrampas.salvar_evento_calendario(
            target,
            {
                "data": "2026-07-29",
                "movimento": "retirada",
                "id_grupo": grupo["id_grupo"],
                "ciclo": "Homologacao",
                "agentes": agentes,
            },
            usuario_nome="Teste",
        )
        criados = ovitrampas_laboratorio.gerar_lotes_pendentes(
            target, hoje="2026-07-29"
        )
        if criados != 1:
            raise RuntimeError("O lote laboratorial temporario nao foi gerado.")
        pendentes = ovitrampas_laboratorio.listar_para_laboratorista(
            target, hoje="2026-07-29"
        )
        if pendentes["total"] != 1:
            raise RuntimeError("O lote nao apareceu para o laboratorista.")
        lote = ovitrampas_laboratorio.obter_lote(
            target, pendentes["registros"][0]["id_lote"]
        )
        leituras = [
            {
                "id_item": item["id_item"],
                "ovos": 7 if item["ovitrampa_id"] == "901" else 0,
                "ocorrencia": 5 if item["ovitrampa_id"] == "902-A" else None,
            }
            for item in lote["itens"]
        ]
        usuario = {"id_usuario": None, "nome": "Laboratorista Teste"}
        ovitrampas_laboratorio.salvar_rascunho(
            target, lote["id_lote"], leituras, usuario
        )
        concluido = ovitrampas_laboratorio.concluir_lote(
            target, lote["id_lote"], leituras, usuario
        )
        if concluido["ovos"] != 7 or concluido["status"] != "concluido":
            raise RuntimeError("A conclusao do lote laboratorial divergiu.")
        administracao = ovitrampas_laboratorio.listar_para_administracao(
            target, status="pendente", hoje="2026-07-29"
        )
        if administracao["total"] != 1:
            raise RuntimeError("O lote concluido nao apareceu para administracao.")
        enviado = ovitrampas_laboratorio.marcar_enviado_conta_ovos(
            target, lote["id_lote"], {"id_usuario": None, "nome": "Teste"}
        )
        if enviado["status"] != "enviado_conta_ovos":
            raise RuntimeError("O envio ao Conta Ovos nao foi persistido.")

        ovitrampas.excluir_evento_calendario(target, evento["id_evento"])
        ovitrampas.excluir_evento_calendario(target, evento_leitura["id_evento"])
        ovitrampas.excluir_grupo(target, grupo["id_grupo"])
        ovitrampas.remover_armadilha_diario(target, id_diario, "901")

        after = _public_counts(conn)
        if before != after:
            raise RuntimeError("Uma tabela publica foi alterada.")
        return len(before)
    finally:
        db_core.connect = original_connect
        conn.close()


def _test_pages(database):
    target = db_core.DatabaseTarget("postgresql", database)
    admin = db_core.query_one(
        target,
        """SELECT id_usuario, nome, nivel
             FROM usuarios
            WHERE ativo=1 AND nivel='admin'
            ORDER BY id_usuario
            LIMIT ?""",
        (1,),
    )
    if not admin:
        raise RuntimeError("Falta um usuario administrador para testar as paginas.")

    with tempfile.TemporaryDirectory(prefix="endemias-pg-ovitrampas-") as tmpdir:
        from app import create_app

        log_path = str(Path(tmpdir) / "teste.log")
        try:
            flask_app = create_app(
                {
                    "DB_BACKEND": "postgresql",
                    "PG_DATABASE": database,
                    "TESTING": True,
                    "WTF_CSRF_ENABLED": False,
                    "LOG_PATH": log_path,
                    "SECRET_KEY_PATH": str(Path(tmpdir) / "secret.key"),
                }
            )
            client = flask_app.test_client()
            with client.session_transaction() as flask_session:
                flask_session["uid"] = admin["id_usuario"]
                flask_session["nome"] = admin["nome"]
                flask_session["nivel"] = admin["nivel"]

            checks = {
                "/ovitrampas": b"Ovitrampas",
                "/api/ovitrampas": b'"totais"',
                "/api/ovitrampas/listar?limite=2": b'"registros"',
                "/api/ovitrampas/armadilhas?limite=2": b'"registros"',
                "/api/ovitrampas/monitoramento": b'"ranking_positivas"',
                "/api/ovitrampas/diarios": b'"diarios"',
                "/api/ovitrampas/calendario?ano=2026": b'"eventos"',
                "/laboratorio/lancamentos": b"Leitura",
                "/api/laboratorio/lancamentos/pendentes": b'"pendentes"',
                "/api/laboratorio/lancamentos/historico?limite=2": b'"registros"',
            }
            for route, marker in checks.items():
                response = client.get(route)
                if response.status_code != 200:
                    raise RuntimeError(
                        f"{route} respondeu HTTP {response.status_code}."
                    )
                if marker not in response.data:
                    raise RuntimeError(
                        f"{route} nao apresentou o conteudo esperado."
                    )
        finally:
            for handler in list(logging.getLogger().handlers):
                if (
                    getattr(handler, "baseFilename", None)
                    == os.path.abspath(log_path)
                ):
                    logging.getLogger().removeHandler(handler)
                    handler.close()


def main():
    args = _parser().parse_args()
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
        raise SystemExit(
            "Banco nao autorizado. Use --confirmar-banco com o mesmo nome."
        )
    target = db_core.DatabaseTarget("postgresql", args.database)
    total_publicas = _test_temporary_data(target)
    _test_pages(args.database)
    print(
        "OK: pagina de Ovitrampas homologada no PostgreSQL; "
        f"{total_publicas} tabelas publicas preservadas."
    )


if __name__ == "__main__":
    main()
