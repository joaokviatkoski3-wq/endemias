"""Homologa consultas e edicao de visitas no PostgreSQL."""

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402
from app_core import visitas  # noqa: E402


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
)


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Testa as consultas e a edicao de visitas em tabelas "
            "temporarias do PostgreSQL."
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


def _insert_fixture(conn):
    conn.execute(
        """INSERT INTO localidades(id_localidade, nome)
           VALUES (?, ?)""",
        (900001, "Lamenha"),
    )
    conn.execute(
        """INSERT INTO agentes(id_agente, nome, nome_completo)
           VALUES (?, ?, ?)""",
        (900001, "Fernando", "Fernando"),
    )
    conn.execute(
        """INSERT INTO visitas (
               id_visita, kobo_uuid, tipo, data, hora_inicio,
               localidade, id_localidade, logradouro, numero,
               quarteirao, morador, tipo_imovel, visita,
               agua_sanepar, observacoes, processado_em
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "visita-pg-temporaria",
            "uuid-visita-pg-temporaria",
            "PVE",
            "2026-07-28",
            "09:30",
            "Lamenha",
            900001,
            "Rua Temporaria",
            "10",
            9001,
            "Maria",
            "Residencia",
            "Normal",
            1,
            "Observacao temporaria",
            "2026-07-28T10:00:00",
        ),
    )
    conn.execute(
        """INSERT INTO visita_agentes(id_visita, id_agente)
           VALUES (?,?)""",
        ("visita-pg-temporaria", 900001),
    )
    conn.execute(
        """INSERT INTO depositos_inspecionados (
               id_visita, tipo_deposito, inspecionado, eliminado,
               tratado, tipo_tratamento, qtd_carga
           ) VALUES (?,?,?,?,?,?,?)""",
        ("visita-pg-temporaria", "B", 3, 1, 2, "Natular", 4),
    )
    conn.execute(
        """INSERT INTO tratamentos (
               id_visita, tipo, quantidade_carga,
               qtd_depositos_tratados
           ) VALUES (?,?,?,?)""",
        ("visita-pg-temporaria", "Natular", 4, 2),
    )
    conn.execute(
        """INSERT INTO coletas (
               id_coleta, id_visita, num_tubo, codigo_deposito,
               tipo_deposito, deposito_eliminado
           ) VALUES (?,?,?,?,?,?)""",
        (
            "coleta-pg-temporaria",
            "visita-pg-temporaria",
            "T-PG-100",
            "B1",
            "B",
            0,
        ),
    )
    conn.execute(
        """INSERT INTO resultados_laboratorio (
               id_coleta, num_tubo, data_coleta, data_leitura,
               aegypt_larvas
           ) VALUES (?,?,?,?,?)""",
        (
            "coleta-pg-temporaria",
            "T-PG-100",
            "2026-07-28",
            "2026-07-29",
            2,
        ),
    )
    conn.execute(
        """INSERT INTO focos_positivos (
               id_foco, id_visita, id_coleta, num_tubo,
               gera_notificacao
           ) VALUES (?,?,?,?,?)""",
        (
            "foco-pg-temporario",
            "visita-pg-temporaria",
            "coleta-pg-temporaria",
            "T-PG-100",
            1,
        ),
    )
    conn.commit()


def _test_data(target):
    conn = db_core.connect(target)
    try:
        before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)
        _insert_fixture(conn)

        opcoes = visitas.filter_options(conn)
        if "Lamenha" not in opcoes["localidades"]:
            raise RuntimeError("As localidades nao apareceram nos filtros.")
        if "Fernando" not in opcoes["agentes"]:
            raise RuntimeError("Os agentes nao apareceram nos filtros.")

        lista = visitas.listar(
            conn,
            {
                "busca": "RUA TEMPORARIA",
                "localidade": "Lamenha",
                "laboratorio": "positivo",
            },
            pagina=1,
            por_pagina=10,
        )
        if lista["total"] != 1:
            raise RuntimeError("A busca sem diferenca de caixa divergiu.")
        registro = lista["registros"][0]
        if registro["agentes"] != "Fernando":
            raise RuntimeError("A agregacao de agentes divergiu.")
        if registro["laboratorio_status"] != "positivo":
            raise RuntimeError("O estado laboratorial divergiu.")
        if registro["data"] != "2026-07-28":
            raise RuntimeError("A data nao foi serializada para a API.")

        detalhe = visitas.detalhar(conn, "visita-pg-temporaria")
        if detalhe["visita"]["hora_inicio"] != "09:30:00":
            raise RuntimeError("O horario nao foi serializado para a API.")
        if detalhe["coletas"][0]["aegypt_larvas"] != 2:
            raise RuntimeError("O resultado laboratorial nao foi detalhado.")

        auditoria = visitas.editar(
            conn,
            "visita-pg-temporaria",
            {
                "data": "2026-07-29",
                "localidade": "grasiela",
                "agentes": "viviane_1, cecon",
                "observacoes": "Revisada no PostgreSQL",
                "depositos": [
                    {
                        "tipo_deposito": "A2",
                        "inspecionado": 5,
                        "eliminado": 2,
                        "tratado": 1,
                        "tipo_tratamento": "Pyriproxyfen",
                        "qtd_carga": 3,
                    }
                ],
                "tratamentos": [
                    {
                        "tipo": "Pyriproxyfen",
                        "quantidade_carga": 3,
                        "qtd_depositos_tratados": 1,
                    }
                ],
                "coletas": [
                    {
                        "id_coleta": "coleta-pg-temporaria",
                        "num_tubo": "T-PG-101",
                        "codigo_deposito": "A2-1",
                        "tipo_deposito": "A2",
                        "deposito_eliminado": True,
                    },
                    {
                        "num_tubo": "T-PG-102",
                        "codigo_deposito": "A2-2",
                        "tipo_deposito": "A2",
                        "deposito_eliminado": False,
                    },
                ],
            },
        )
        if auditoria["depois"]["localidade"] != "Graziela":
            raise RuntimeError("A normalizacao da localidade divergiu.")
        if auditoria["agentes"] != ["Viviane", "Ceccon"]:
            raise RuntimeError("A normalizacao dos agentes divergiu.")

        detalhe = visitas.detalhar(conn, "visita-pg-temporaria")
        if detalhe["visita"]["data"] != "2026-07-29":
            raise RuntimeError("A edicao da visita nao foi persistida.")
        if detalhe["coletas"][0]["num_tubo"] != "T-PG-101":
            raise RuntimeError("A edicao do tubo nao foi persistida.")
        if detalhe["coletas"][0]["aegypt_larvas"] != 2:
            raise RuntimeError("A edicao removeu o resultado laboratorial.")

        try:
            visitas.editar(
                conn,
                "visita-pg-temporaria",
                {"data": "2026-07-29", "coletas": []},
            )
        except visitas.ColetaComResultado:
            pass
        else:
            raise RuntimeError(
                "Uma coleta com resultado foi removida indevidamente."
            )
        protegida = conn.execute(
            """SELECT num_tubo
                 FROM coletas
                WHERE id_coleta='coleta-pg-temporaria'"""
        ).fetchone()
        if not protegida or protegida["num_tubo"] != "T-PG-101":
            raise RuntimeError("O rollback da coleta protegida falhou.")

        after = _public_counts(conn)
        conn.rollback()
        if before != after:
            raise RuntimeError("Uma tabela publica foi alterada.")
    finally:
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
        raise RuntimeError("Nao existe administrador para testar as paginas.")

    sample = db_core.query_one(
        target,
        """SELECT id_visita
             FROM visitas
            ORDER BY data DESC, id_visita
            LIMIT ?""",
        (1,),
    )
    if not sample:
        raise RuntimeError("Nao existe visita publica para consulta.")

    with tempfile.TemporaryDirectory(prefix="endemias-pg-visitas-") as tmpdir:
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
                "/visitas": b"Visitas arboviroses",
                "/api/visitas?pagina=1&por_pagina=5": b'"registros"',
                f"/api/visitas/{sample['id_visita']}": b'"visita"',
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
        _test_data(target)
        _test_pages(args.database, target)
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1

    print("Teste de Visitas de Arboviroses no PostgreSQL")
    print("=" * 52)
    print(f"Banco: {args.database}")
    print("Filtros, listagem e detalhes: OK")
    print("Edicao e auditoria retornada: OK")
    print("Coleta com resultado e rollback: OK")
    print("Paginas e APIs: HTTP 200")
    print("Tabelas publicas: preservadas")
    print("\n[OK] Modulo homologado sem alterar os dados publicos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
