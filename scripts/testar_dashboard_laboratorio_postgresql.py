"""Homologa Dashboard e consulta laboratorial no PostgreSQL."""

import argparse
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import dashboard  # noqa: E402
from app_core import db as db_core  # noqa: E402
from app_core import laboratorio  # noqa: E402


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
)


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Testa Dashboard e Laboratorio sem alterar tabelas publicas."
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


def _insert_fixture(conn):
    conn.execute(
        "INSERT INTO localidades(id_localidade, nome) VALUES (?,?)",
        (900001, "Lamenha"),
    )
    conn.execute(
        """INSERT INTO agentes(id_agente, nome, nome_completo)
           VALUES (?,?,?)""",
        (900001, "Agente A", "Agente A"),
    )
    conn.execute(
        """INSERT INTO agentes(id_agente, nome, nome_completo)
           VALUES (?,?,?)""",
        (900002, "Agente B", "Agente B"),
    )
    conn.execute(
        """INSERT INTO visitas (
               id_visita, kobo_uuid, tipo, data, hora_inicio, hora_fim,
               localidade, id_localidade, quarteirao, logradouro,
               numero, visita, tipo_imovel, processado_em
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "dashboard-pg-temporaria",
            "uuid-dashboard-pg-temporaria",
            "TBO",
            "2026-07-28",
            "09:00",
            "09:20",
            "Lamenha",
            900001,
            9001,
            "Rua Temporaria",
            "10",
            "Normal",
            "Residencia",
            "2026-07-28T10:00:00",
        ),
    )
    conn.execute(
        "INSERT INTO visita_agentes VALUES (?,?)",
        ("dashboard-pg-temporaria", 900001),
    )
    conn.execute(
        "INSERT INTO visita_agentes VALUES (?,?)",
        ("dashboard-pg-temporaria", 900002),
    )
    conn.execute(
        """INSERT INTO depositos_inspecionados (
               id_visita, tipo_deposito, inspecionado, eliminado, tratado
           ) VALUES (?,?,?,?,?)""",
        ("dashboard-pg-temporaria", "B", 3, 1, 1),
    )
    conn.execute(
        """INSERT INTO tratamentos (
               id_visita, tipo, quantidade_carga,
               qtd_depositos_tratados
           ) VALUES (?,?,?,?)""",
        ("dashboard-pg-temporaria", "Natular", 1, 2),
    )
    conn.execute(
        """INSERT INTO coletas (
               id_coleta, id_visita, num_tubo, tipo_deposito
           ) VALUES (?,?,?,?)""",
        (
            "coleta-dashboard-pg",
            "dashboard-pg-temporaria",
            "T-PG-200",
            "B",
        ),
    )
    conn.execute(
        """INSERT INTO resultados_laboratorio (
               id_coleta, num_tubo, data_coleta, data_leitura,
               laboratorista, aegypt_larvas, albopictus_larvas
           ) VALUES (?,?,?,?,?,?,?)""",
        (
            "coleta-dashboard-pg",
            "T-PG-200",
            "2026-07-28",
            "2026-07-29",
            "Azimir",
            2,
            1,
        ),
    )
    conn.commit()


def _test_temporary_data(target):
    conn = db_core.connect(target)
    try:
        before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)
        _insert_fixture(conn)
        filtros = {
            "d_ini": "2026-07-01",
            "d_fim": "2026-07-31",
        }

        dados_dashboard = dashboard.vetorial(conn, filtros)
        if dados_dashboard["kpi"]["total"] != 1:
            raise RuntimeError("O total vetorial divergiu.")
        if dados_dashboard["por_status"][0]["total"] != 1:
            raise RuntimeError("A visita foi duplicada por agente.")
        if dados_dashboard["depositos"]["inspecionados"] != 3:
            raise RuntimeError("Os depositos foram duplicados por agente.")
        if dados_dashboard["depositos"]["tratados"] != 3:
            raise RuntimeError("O total de tratamentos divergiu.")
        if dados_dashboard["tbo_duracao"]["n"] != 1:
            raise RuntimeError("A duracao da visita nao foi calculada.")

        dados_laboratorio = laboratorio.listar(
            conn,
            filtros,
            pagina=1,
            por_pagina=10,
        )
        if dados_laboratorio["total"] != 1:
            raise RuntimeError("O resultado laboratorial foi duplicado.")
        if dados_laboratorio["totais"]["aegypti"] != 2:
            raise RuntimeError("O total de Aedes aegypti divergiu.")
        if dados_laboratorio["totais"]["albopictus"] != 1:
            raise RuntimeError("O total de Aedes albopictus divergiu.")
        if (
            dados_laboratorio["registros"][0]["agentes"]
            != "Agente A, Agente B"
        ):
            raise RuntimeError("A agregacao dos agentes divergiu.")

        after = _public_counts(conn)
        conn.rollback()
        if before != after:
            raise RuntimeError("Uma tabela publica foi alterada.")
    finally:
        conn.close()


def _test_public_data(target):
    filtros = {
        "d_ini": "2025-01-01",
        "d_fim": "2026-12-31",
    }
    dados_dashboard = dashboard.integrado(target, filtros)
    for key in (
        "kpi",
        "esporotricose",
        "pontos_estrategicos",
        "producao_operacional",
        "ovitrampas",
        "comparativo_mensal",
    ):
        if key not in dados_dashboard:
            raise RuntimeError(f"O Dashboard nao retornou {key}.")

    dados_laboratorio = laboratorio.listar(
        target,
        filtros,
        pagina=1,
        por_pagina=5,
    )
    if "registros" not in dados_laboratorio:
        raise RuntimeError("A consulta laboratorial nao retornou registros.")


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
        raise RuntimeError("Nao existe administrador para testar as paginas.")

    with tempfile.TemporaryDirectory(
        prefix="endemias-pg-dashboard-"
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

            query = "d_ini=2025-01-01&d_fim=2026-12-31"
            checks = {
                "/dashboard": b"Dashboard Integrado",
                "/laboratorio": b"Resultados Laboratoriais",
                f"/api/dashboard?{query}": b'"comparativo_mensal"',
                f"/api/producao-operacional?{query}": b'"por_atividade"',
                f"/api/laboratorio?{query}&por_pagina=5": b'"registros"',
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
    conn = db_core.connect(target)
    try:
        before = _public_counts(conn)
    finally:
        conn.close()

    try:
        _test_temporary_data(target)
        _test_public_data(target)
        _test_pages(args.database, target)
    except Exception as exc:
        print(f"[ERRO] {exc}")
        traceback.print_exc()
        return 1

    conn = db_core.connect(target)
    try:
        after = _public_counts(conn)
    finally:
        conn.close()
    if before != after:
        print("[ERRO] As contagens publicas foram alteradas.")
        return 1

    print("Teste de Dashboard e Laboratorio no PostgreSQL")
    print("=" * 52)
    print(f"Banco: {args.database}")
    print("Dashboard vetorial sem duplicacao por agente: OK")
    print("Dashboard integrado e producao operacional: OK")
    print("Consulta e agregacao laboratorial: OK")
    print("Paginas e APIs: HTTP 200")
    print(f"Tabelas publicas preservadas: {len(after)}")
    print("\n[OK] Modulos homologados sem alterar os dados publicos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
