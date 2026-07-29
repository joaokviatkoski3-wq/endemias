"""Homologa o espelho Conta Ovos/SisPNCD no PostgreSQL."""

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
from app_core import sispncd  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "visitas",
    "visita_agentes",
    "depositos_inspecionados",
    "tratamentos",
    "coletas",
    "resultados_laboratorio",
    "bri_registros",
    "bri_agentes",
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
            "Testa Conta Ovos/SisPNCD sem alterar as tabelas publicas."
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


def _fixtures(conn):
    visitas = (
        (
            "visita-tbo-pg",
            "uuid-tbo-pg",
            "TBO",
            "2026-07-20",
            "Tamboara",
            "Rua Teste",
            "10",
            1201,
            "Residencia",
            "Normal",
            None,
            0,
        ),
        (
            "visita-pe-pg",
            "uuid-pe-pg",
            "PE",
            "2026-07-21",
            "Tamboara",
            "Rua Teste",
            "20",
            1202,
            "Comercio",
            "Normal",
            None,
            None,
        ),
    )
    conn.executemany(
        """INSERT INTO visitas(
               id_visita, kobo_uuid, tipo, data, localidade, logradouro,
               numero, quarteirao, tipo_imovel, visita, sispncd,
               contaovos_status, processado_em
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, '2026-07-29T10:00:00')""",
        visitas,
    )
    conn.execute(
        """INSERT INTO depositos_inspecionados(
               id_visita, tipo_deposito, inspecionado, eliminado, tratado,
               tipo_tratamento, qtd_carga
           ) VALUES ('visita-tbo-pg','D1 - Pneu',3,1,2,'Larvicida',0.5)"""
    )
    conn.execute(
        """INSERT INTO tratamentos(
               id_visita, tipo, quantidade_carga, qtd_depositos_tratados
           ) VALUES ('visita-pe-pg','Larvicida',1.25,4)"""
    )
    conn.execute(
        """INSERT INTO coletas(
               id_coleta, id_visita, num_tubo, codigo_deposito,
               tipo_deposito, deposito_eliminado
           ) VALUES ('coleta-pg','visita-tbo-pg','77','D1','Pneu',0)"""
    )
    conn.execute(
        """INSERT INTO resultados_laboratorio(
               id_coleta, num_tubo, data_coleta, laboratorista, data_leitura,
               aegypt_larvas, origem, criado_em
           ) VALUES (
               'coleta-pg','77','2026-07-20','Teste','2026-07-21',
               2,'sistema','2026-07-21T10:00:00'
           )"""
    )
    conn.execute(
        """INSERT INTO bri_registros(
               id_bri, kobo_uuid, data, destino_tratamento, localidade,
               quarteirao, quantidade_carga, quantidade_carga_extra,
               tratou_imovel_extra, origem_estrutura, processado_em
           ) VALUES (
               'bri-pg','uuid-bri-pg','2026-07-22','Ovitrampa','Tamboara',
               1203,0.75,0,'Nao','nova','2026-07-22T10:00:00'
           )"""
    )
    agente = conn.execute(
        "SELECT id_agente FROM public.agentes WHERE ativo=1 ORDER BY id_agente LIMIT 1"
    ).fetchone()
    if agente:
        conn.execute(
            "INSERT INTO visita_agentes(id_visita,id_agente) VALUES ('visita-tbo-pg',?)",
            (agente[0],),
        )
        conn.execute(
            "INSERT INTO bri_agentes(id_bri,id_agente) VALUES ('bri-pg',?)",
            (agente[0],),
        )
    conn.commit()


def _test_temporary_data(target):
    conn = db_core.connect(target)
    original_connect = db_core.connect
    try:
        before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)
        _fixtures(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        default = sispncd.get_default_conta_ovos(target)
        if default["quarteirao"] != 1201:
            raise RuntimeError("O quarteirao pendente do Conta Ovos divergiu.")

        pendencias = sispncd.pendencias_envio(target)
        if pendencias["conta_ovos"]["total"] != 1:
            raise RuntimeError("A pendencia do Conta Ovos nao foi identificada.")
        if pendencias["sispncd"]["total"] != 3:
            raise RuntimeError("As pendencias SisPNCD divergiram.")

        conta = sispncd.conta_ovos(target, "2026-07-20", 1201)
        if conta["total_visitas"] != 1:
            raise RuntimeError("O espelho do Conta Ovos nao retornou a visita.")
        if conta["depositos"]["d1"]["quantidade"] != 3:
            raise RuntimeError("O deposito D1 nao foi normalizado.")
        if conta["depositos"]["d1"]["larvicida_mg"] != 0.5:
            raise RuntimeError("A carga do deposito divergiu.")

        resumo = sispncd.sispncd(
            target, 2026, 29, ["TBO", "PE", "BRI"]
        )
        gerais = resumo["dados_gerais"]
        if gerais["imoveis_inspecionados"] != 2:
            raise RuntimeError("Os imoveis inspecionados divergiram.")
        if gerais["imoveis_tratados"] != 2:
            raise RuntimeError("Os imoveis tratados divergiram.")
        if resumo["laboratorio"]["exemplares_aegypti"]["larvas"] != 2:
            raise RuntimeError("O resultado laboratorial nao foi consolidado.")
        if gerais["bri"]["registros"] != 1:
            raise RuntimeError("O registro BRI nao foi consolidado.")

        baixa = sispncd.salvar_status_conta_ovos(
            target, "2026-07-20", 1201
        )
        if baixa["atualizados"] != 1:
            raise RuntimeError("A baixa do Conta Ovos nao foi persistida.")

        salvo = sispncd.salvar_sispncd(
            target, 2026, 29, ["TBO", "PE", "BRI"], "LOTE-PG"
        )
        if salvo["visitas_atualizadas"] != 2 or salvo["bri_atualizados"] != 1:
            raise RuntimeError("A marcacao SisPNCD nao atualizou todos os registros.")

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
        raise RuntimeError("Falta um administrador para testar as paginas.")

    with tempfile.TemporaryDirectory(prefix="endemias-pg-sispncd-") as tmpdir:
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
                "/conta-ovos-sispncd": b"SisPNCD",
                "/api/conta-ovos-sispncd/pendencias": b'"sispncd"',
                "/api/sispncd/pesquisar?ano=2026&semana=29&tipo=PE": b'"dados_gerais"',
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
        "OK: Conta Ovos/SisPNCD homologado no PostgreSQL; "
        f"{total_publicas} tabelas publicas preservadas."
    )


if __name__ == "__main__":
    main()
