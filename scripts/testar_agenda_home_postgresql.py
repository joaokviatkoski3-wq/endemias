"""Homologa Agenda, Pagina Inicial e Meteorologia no PostgreSQL."""

import argparse
import logging
import os
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import meteorologia  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "agenda_eventos",
    "meteorologia_estacoes",
    "meteorologia_resumos_diarios",
    "meteorologia_condicoes_atuais",
    "meteorologia_previsoes_horarias",
    "meteorologia_alertas_config",
    "meteorologia_sincronizacoes",
)


class _SharedConnection:
    """Mantem as tabelas temporarias disponiveis entre as chamadas."""

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
            "Testa Agenda, Pagina Inicial e Meteorologia em tabelas "
            "PostgreSQL temporarias."
        )
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio para qualquer banco diferente de endemias_teste.",
    )
    return parser


def _public_counts(conn):
    return {
        table: conn.execute(
            f"SELECT COUNT(*) FROM public.{table}"
        ).fetchone()[0]
        for table in TEMP_TABLES
    }


def _temporary_schema(conn):
    for table in TEMP_TABLES:
        conn.execute(
            f"""CREATE TEMPORARY TABLE {table}
                (LIKE public.{table} INCLUDING ALL)
                ON COMMIT PRESERVE ROWS"""
        )
    conn.commit()


def _fake_fetch(url):
    if url.startswith("https://api.open-meteo.com/"):
        return {
            "latitude": -25.32,
            "longitude": -49.31,
            "timezone": "America/Sao_Paulo",
            "current": {
                "time": "2026-07-15T14:15",
                "interval": 900,
                "temperature_2m": 16.4,
                "relative_humidity_2m": 72,
                "apparent_temperature": 15.8,
                "is_day": 1,
                "precipitation": 0.0,
                "weather_code": 2,
                "wind_speed_10m": 7.1,
            },
            "hourly": {
                "time": [
                    "2026-07-15T08:00",
                    "2026-07-15T09:00",
                    "2026-07-15T19:00",
                    "2026-07-16T08:00",
                    "2026-07-16T09:00",
                ],
                "temperature_2m": [15, 16, 13, 17, 19],
                "apparent_temperature": [14, 15, 10, 17, 19],
                "relative_humidity_2m": [80, 78, 90, 70, 65],
                "precipitation_probability": [20, 60, 95, 10, 10],
                "precipitation": [0, 1, 8, 0, 0],
                "weather_code": [2, 61, 95, 1, 1],
                "wind_speed_10m": [10, 20, 70, 8, 9],
                "wind_gusts_10m": [20, 45, 100, 15, 18],
            },
        }
    if url.endswith("/estacoes/T"):
        return [
            {
                "CD_ESTACAO": "B806",
                "DC_NOME": "COLOMBO",
                "SG_ESTADO": "PR",
                "CD_SITUACAO": "Operante",
                "TP_ESTACAO": "Automatica",
                "VL_LATITUDE": "-25.32249999",
                "VL_LONGITUDE": "-49.15777777",
                "VL_ALTITUDE": "950",
            },
            {
                "CD_ESTACAO": "A807",
                "DC_NOME": "CURITIBA",
                "SG_ESTADO": "PR",
                "CD_SITUACAO": "Operante",
                "TP_ESTACAO": "Automatica",
                "VL_LATITUDE": "-25.4486111",
                "VL_LONGITUDE": "-49.23055554",
                "VL_ALTITUDE": "922.91",
            },
        ]
    return [
        {
            "CAPITAL": "CURITIBA",
            "TMIN18": "8,3*",
            "TMAX18": "17.9*",
            "UMIN18": "60*",
            "PMAX12": "2.5*",
        }
    ]


def _test_meteorologia(target, conn):
    for _ in range(2):
        result = meteorologia.sincronizar(
            target,
            dias=2,
            hoje=date(2026, 7, 15),
            fetch_json=_fake_fetch,
        )
        if result["status"] != "concluido" or result["resumos"] != 2:
            raise RuntimeError("A sincronizacao meteorologica divergiu.")

    expected_counts = {
        "meteorologia_estacoes": 2,
        "meteorologia_resumos_diarios": 2,
        "meteorologia_condicoes_atuais": 1,
        "meteorologia_previsoes_horarias": 5,
        "meteorologia_sincronizacoes": 2,
    }
    for table, expected in expected_counts.items():
        actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if actual != expected:
            raise RuntimeError(
                f"{table} retornou {actual}; esperado: {expected}."
            )

    painel = meteorologia.obter_painel(target)
    if painel["condicao_atual"]["descricao"] != "Parcialmente nublado":
        raise RuntimeError("A condicao meteorologica atual divergiu.")

    trabalho = meteorologia.resumo_trabalho(
        target,
        inicio=date(2026, 7, 15),
        dias_uteis=3,
    )
    levels = [item["nivel"] for item in trabalho["dias"]]
    if levels != ["atencao", "favoravel", "sem_dados"]:
        raise RuntimeError(f"Os alertas de trabalho divergiram: {levels!r}.")

    config = meteorologia.atualizar_configuracao_alertas(
        target,
        {
            "chuva_atencao_pct": 65,
            "expediente_inicio": 7,
            "expediente_fim": 16,
        },
    )
    if config["chuva_atencao_pct"] != 65:
        raise RuntimeError("A configuracao meteorologica nao foi persistida.")


def _admin(target):
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
        raise RuntimeError("Nao existe administrador para testar as paginas.")
    return admin


def _assert_response(client, route, marker):
    response = client.get(route)
    if response.status_code != 200:
        raise RuntimeError(f"{route} respondeu HTTP {response.status_code}.")
    if marker not in response.data:
        raise RuntimeError(f"{route} nao apresentou o conteudo esperado.")
    return response


def _test_pages(database, target, create_app):
    admin = _admin(target)
    with tempfile.TemporaryDirectory(
        prefix="endemias-pg-agenda-home-"
    ) as tmpdir:
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
                    "BACKUP_DIR": str(Path(tmpdir) / "backups"),
                }
            )
            client = flask_app.test_client()
            with client.session_transaction() as flask_session:
                flask_session["uid"] = admin["id_usuario"]
                flask_session["nome"] = admin["nome"]
                flask_session["nivel"] = admin["nivel"]

            _assert_response(client, "/", b"Painel operacional")
            _assert_response(client, "/agenda", b"Agenda")
            _assert_response(client, "/meteorologia", b"Meteorologia")

            payload = {
                "titulo": "Planejamento PostgreSQL",
                "descricao": "Evento temporario de homologacao",
                "tipo": "planejamento",
                "data_inicio": "2026-07-16T09:00",
                "data_fim": "2026-07-16T10:00",
                "dia_inteiro": False,
                "lembrete_min": 30,
                "recorrencia": "semanal",
                "recorrencia_fim": "2026-07-30",
                "atividade_externa": True,
            }
            created = client.post("/api/agenda/eventos", json=payload)
            if created.status_code != 201:
                raise RuntimeError(
                    "A criacao do evento respondeu "
                    f"HTTP {created.status_code}: {created.get_data(as_text=True)}"
                )
            event_id = created.get_json()["id_evento"]

            listed = client.get(
                "/api/agenda/eventos"
                "?start=2026-07-01&end=2026-08-01"
            )
            if listed.status_code != 200:
                raise RuntimeError(
                    f"A Agenda respondeu HTTP {listed.status_code}."
                )
            events = listed.get_json()
            manual = [
                item
                for item in events
                if (item.get("extendedProps") or {}).get("id_evento")
                == event_id
            ]
            if len(manual) != 3:
                raise RuntimeError(
                    "A recorrencia semanal nao gerou tres ocorrencias."
                )

            payload["titulo"] = "Planejamento PostgreSQL revisado"
            updated = client.put(
                f"/api/agenda/eventos/{event_id}", json=payload
            )
            if updated.status_code != 200:
                raise RuntimeError("A edicao do evento falhou.")

            _assert_response(
                client,
                "/agenda/imprimir?ano=2026&mes=7",
                b"Planejamento PostgreSQL revisado",
            )
            _assert_response(
                client,
                "/api/agenda/clima-trabalho"
                "?dias=3",
                b'"dias"',
            )
            _assert_response(
                client,
                "/api/agenda/clima-config",
                b'"expediente_inicio"',
            )
            _assert_response(
                client,
                "/api/agenda/lembretes",
                b"[",
            )

            deleted = client.delete(f"/api/agenda/eventos/{event_id}")
            if deleted.status_code != 200:
                raise RuntimeError("A exclusao do evento falhou.")
        finally:
            for handler in list(logging.getLogger().handlers):
                if (
                    getattr(handler, "baseFilename", None)
                    == os.path.abspath(log_path)
                ):
                    logging.getLogger().removeHandler(handler)
                    handler.close()


def _test_temporary_data(database, create_app):
    target = db_core.DatabaseTarget("postgresql", database)
    conn = db_core.connect(target)
    original_connect = db_core.connect
    try:
        public_before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        _test_meteorologia(target, conn)
        _test_pages(database, target, create_app)

        public_after = _public_counts(conn)
        if public_before != public_after:
            raise RuntimeError("Uma tabela publica foi alterada pelo ensaio.")
    finally:
        db_core.connect = original_connect
        conn.close()


def main(argv=None):
    args = _parser().parse_args(argv)
    if (
        args.database != SAFE_DATABASE
        and args.confirmar_banco != args.database
    ):
        print(
            "[ERRO] Para testar outro banco, informe "
            f"--confirmar-banco {args.database}"
        )
        return 2

    try:
        from app import create_app

        _test_temporary_data(args.database, create_app)
    except Exception as exc:
        print(f"[ERRO] {exc}")
        traceback.print_exc()
        return 1

    print("Teste da Agenda, Pagina Inicial e Meteorologia no PostgreSQL")
    print("=" * 62)
    print(f"Banco: {args.database}")
    print("Sincronizacao meteorologica idempotente: OK")
    print("Condicao atual, previsao e alertas de campo: OK")
    print("Configuracao dos alertas: OK")
    print("Agenda manual, recorrencia, edicao e exclusao: OK")
    print("Agenda automatica, impressao e lembretes: OK")
    print("Pagina Inicial e paginas do lote: OK")
    print("Tabelas publicas: preservadas")
    print("\n[OK] Modulos validados somente em tabelas temporarias.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
