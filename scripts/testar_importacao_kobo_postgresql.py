"""Homologa o ETL principal da Importacao Kobo no PostgreSQL."""

import argparse
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import etl  # noqa: E402
from app_core import db as db_core  # noqa: E402
from app_core import kobo_api as kobo_api_core  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "localidades",
    "agentes",
    "visitas",
    "visita_agentes",
    "depositos_inspecionados",
    "tratamentos",
    "coletas",
    "resultados_laboratorio",
    "focos_positivos",
    "laboratorio_coletas_status",
)


class _SharedConnection:
    """Mantem as tabelas temporarias visiveis durante todo o ensaio."""

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
            "Testa a Importacao Kobo usando tabelas PostgreSQL temporarias."
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


def _workbook_visita(tmpdir):
    record = {
        "_uuid": "pg-kobo-visita-1",
        "_id": 990001,
        "_submission_time": "2026-07-29T10:00:00",
        "Digite a data": "2026-07-29",
        "Nome_do_s_agente_s": "joao",
        "group_zn1kq42/localidade": "Tamboara",
        "group_zn1kq42/logradouro": "RUA TESTE IMPORTACAO PG",
        "group_zn1kq42/quarteirao": "0999",
        "group_zn1kq42/numero": "10",
        "group_zn1kq42/Visita": "normal",
    }
    return kobo_api_core.write_etl_workbooks(
        {"PE": [record]},
        str(ROOT / "config.json"),
        tmpdir,
        prefix="postgresql",
    )


def _workbook_larvas(tmpdir):
    path = Path(tmpdir) / "LARVAS_postgresql.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "_uuid",
            "Número do tubito",
            "Data da coleta",
            "Nome do laboratorista",
            "Data da leitura",
            "Aegypt Larvas",
            "Aegypt Pupas",
            "Aegypt Exúvias",
            "Aegypt Adulto",
            "Albopictus Larvas",
            "Albopictus Pupas",
            "Albopictus Exúvias",
            "Albopictus Adulto",
            "Outra Espécie Larvas",
            "Outra Espécie Pupas",
            "Outra Espécie Exúvias",
            "Outra Espécie Adulto",
        ]
    )
    sheet.append(
        [
            "pg-kobo-larva-1",
            "T-PG-001",
            "2026-07-29",
            "Azimir",
            "2026-07-30",
            2,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    workbook.save(path)
    return str(path)


def _assert_summary(summary, *, new=0, updated=0, results=0):
    if not summary:
        raise RuntimeError("O ETL nao retornou resumo do processamento.")
    item = summary[0]
    if item.get("visitas_novas", 0) != new:
        raise RuntimeError("A contagem de visitas novas divergiu.")
    if item.get("visitas_atualizadas", 0) != updated:
        raise RuntimeError("A contagem de visitas atualizadas divergiu.")
    if item.get("resultados_novos", 0) != results:
        raise RuntimeError("A contagem de resultados novos divergiu.")


def _test_temporary_data(target):
    conn = db_core.connect(target)
    original_connect = db_core.connect
    try:
        public_before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        with tempfile.TemporaryDirectory(
            prefix="endemias-pg-kobo-"
        ) as tmpdir:
            workbooks = _workbook_visita(tmpdir)
            config = str(ROOT / "config.json")

            ok, dry_summary = etl.processar_upload(
                workbooks,
                [],
                target,
                config,
                etl.Logger(),
                dry_run=True,
            )
            if not ok:
                raise RuntimeError("A simulacao da visita Kobo falhou.")
            _assert_summary(dry_summary, new=1)
            if conn.execute("SELECT COUNT(*) FROM visitas").fetchone()[0]:
                raise RuntimeError("O dry-run deixou dados nas tabelas.")

            ok, import_summary = etl.processar_upload(
                workbooks,
                [],
                target,
                config,
                etl.Logger(),
                dry_run=False,
                backup_confirmado=True,
            )
            if not ok:
                raise RuntimeError("A gravacao da visita Kobo falhou.")
            _assert_summary(import_summary, new=1)

            visita = conn.execute(
                """SELECT id_visita, data, localidade, quarteirao
                     FROM visitas
                    WHERE kobo_uuid=?""",
                ("pg-kobo-visita-1",),
            ).fetchone()
            if not visita:
                raise RuntimeError("A visita importada nao foi localizada.")
            if visita["localidade"] != "Tamboara" or visita["quarteirao"] != 999:
                raise RuntimeError("A normalizacao da visita divergiu.")
            agente = conn.execute(
                """SELECT a.nome
                     FROM visita_agentes va
                     JOIN agentes a ON a.id_agente=va.id_agente
                    WHERE va.id_visita=?""",
                (visita["id_visita"],),
            ).fetchone()
            if not agente or agente["nome"] != "João":
                raise RuntimeError("O agente da visita nao foi normalizado.")

            ok, repeat_summary = etl.processar_upload(
                workbooks,
                [],
                target,
                config,
                etl.Logger(),
                dry_run=False,
                backup_confirmado=True,
            )
            if not ok:
                raise RuntimeError("A reimportacao identica falhou.")
            _assert_summary(repeat_summary)

            conn.execute(
                """INSERT INTO coletas(
                       id_coleta, id_visita, num_tubo, tipo_deposito
                   ) VALUES (?,?,?,?)""",
                (
                    "pg-kobo-coleta-1",
                    visita["id_visita"],
                    "T-PG-001",
                    "A1",
                ),
            )
            conn.execute(
                """INSERT INTO laboratorio_coletas_status(
                       id_coleta, status, motivo, encerrado_em
                   ) VALUES (?,?,?,?)""",
                (
                    "pg-kobo-coleta-1",
                    "sem_resultado",
                    "Pendente no ensaio",
                    "2026-07-29T12:00:00",
                ),
            )
            conn.commit()

            ok, larvae_summary = etl.processar_upload(
                [],
                [_workbook_larvas(tmpdir)],
                target,
                config,
                etl.Logger(),
                dry_run=False,
                backup_confirmado=True,
            )
            if not ok:
                raise RuntimeError("A importacao do resultado de larvas falhou.")
            _assert_summary(larvae_summary, results=1)

            resultado = conn.execute(
                """SELECT num_tubo, aegypt_larvas, kobo_uuid
                     FROM resultados_laboratorio
                    WHERE id_coleta=?""",
                ("pg-kobo-coleta-1",),
            ).fetchone()
            if not resultado or tuple(resultado) != (
                "T-PG-001",
                2,
                "pg-kobo-larva-1",
            ):
                raise RuntimeError("O resultado laboratorial divergiu.")
            foco = conn.execute(
                """SELECT tipo_trabalho, gera_notificacao
                     FROM focos_positivos
                    WHERE id_visita=?""",
                (visita["id_visita"],),
            ).fetchone()
            if (
                not foco
                or foco["tipo_trabalho"] != "PE"
                or foco["gera_notificacao"] != 0
            ):
                raise RuntimeError(
                    f"O foco positivo nao foi criado corretamente: {foco!r}"
                )
            status = conn.execute(
                """SELECT COUNT(*)
                     FROM laboratorio_coletas_status
                    WHERE id_coleta=?""",
                ("pg-kobo-coleta-1",),
            ).fetchone()[0]
            if status:
                raise RuntimeError("O tubo continuou marcado sem resultado.")

        public_after = _public_counts(conn)
        if public_before != public_after:
            raise RuntimeError("Uma tabela publica foi alterada pelo ensaio.")
    finally:
        db_core.connect = original_connect
        conn.close()


def _test_pages(database, target):
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
        raise RuntimeError("Nao existe administrador para testar a pagina.")

    with tempfile.TemporaryDirectory(
        prefix="endemias-pg-kobo-page-"
    ) as tmpdir:
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
                "/processar": b"Consolidados",
                "/api/kobo/config": b"assets",
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

    target = db_core.DatabaseTarget("postgresql", args.database)
    try:
        _test_temporary_data(target)
        _test_pages(args.database, target)
    except Exception as exc:
        print(f"[ERRO] {exc}")
        traceback.print_exc()
        return 1

    print("Teste da Importacao Kobo no PostgreSQL")
    print("=" * 50)
    print(f"Banco: {args.database}")
    print("Dry-run transacional: OK")
    print("Importacao e normalizacao: OK")
    print("Reimportacao identica: sem duplicacao ou falsa atualizacao")
    print("Resultados de larvas e foco positivo: OK")
    print("Pagina e configuracao Kobo: OK")
    print("Tabelas publicas: preservadas")
    print("\n[OK] Modulo validado somente em tabelas temporarias.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
