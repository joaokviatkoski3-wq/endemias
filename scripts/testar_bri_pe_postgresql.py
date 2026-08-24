"""Valida BRI e Pontos Estrategicos no PostgreSQL."""

import argparse
from datetime import date
import logging
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import bri  # noqa: E402
from app_core import db as db_core  # noqa: E402
from app_core import pontos_estrategicos as pe  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "localidades",
    "agentes",
    "pontos_estrategicos",
    "pontos_estrategicos_alias",
    "visitas",
    "bri_registros",
    "bri_agentes",
    "focos_positivos",
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Testa BRI e Pontos Estrategicos em tabelas temporarias."
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


def _test_data(target):
    conn = db_core.connect(target)
    try:
        before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)

        payload = {
            "codigo_pe": "PE-9001",
            "nome": "PE Temporario",
            "localidade": "Tamboara",
            "quarteirao": 9001,
            "logradouro": "Rua Alfa",
            "numero": "10",
            "tipo": "Ferro velho",
            "telefone": "41999990000",
            "latitude": -25.0,
            "longitude": -49.0,
            "situacao": 1,
        }
        if not pe.salvar(conn, payload):
            raise RuntimeError("O PE temporario nao foi criado.")
        if pe.salvar(conn, payload):
            raise RuntimeError("O PE duplicado foi inserido.")

        registro_pe = conn.execute(
            """SELECT id_pe, id_localidade
                 FROM pontos_estrategicos
                WHERE codigo_pe='PE-9001'"""
        ).fetchone()
        id_pe = registro_pe["id_pe"]
        id_localidade = registro_pe["id_localidade"]

        payload["data_inclusao"] = "NaT"
        payload["data_desativacao"] = " "
        if not pe.salvar(conn, payload, id_pe=id_pe):
            raise RuntimeError("A normalizacao de datas vazias do PE falhou.")
        datas_vazias = conn.execute(
            """SELECT data_inclusao, data_desativacao
                 FROM pontos_estrategicos WHERE id_pe=?""",
            (id_pe,),
        ).fetchone()
        if datas_vazias["data_inclusao"] is not None or datas_vazias["data_desativacao"] is not None:
            raise RuntimeError("Datas vazias/NaT do PE nao foram gravadas como NULL.")
        payload["data_inclusao"] = "2026-08-20"
        payload["data_desativacao"] = None

        vinculo = pe.resolver_alias_visita(
            conn,
            "Rua Alfa - PE Temporario",
            "Tamboara",
        )
        if not vinculo or vinculo["id_pe"] != id_pe:
            raise RuntimeError("O alias automatico do PE nao foi resolvido.")

        hoje = date.today().isoformat()
        conn.execute(
            """INSERT INTO visitas (
                   id_visita, kobo_uuid, tipo, data, localidade,
                   id_localidade, quarteirao, logradouro, processado_em
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                "visita-pe-pg",
                "uuid-visita-pe-pg",
                "PE",
                hoje,
                "Tamboara",
                id_localidade,
                9001,
                "Rua Alfa - PE Temporario",
                f"{hoje}T10:00:00",
            ),
        )
        vinculacao = pe.vincular_visitas_existentes_por_alias(conn)
        visita = conn.execute(
            """SELECT id_pe, codigo_pe
                 FROM visitas
                WHERE id_visita='visita-pe-pg'"""
        ).fetchone()
        if vinculacao["atualizadas"] != 1 or visita["id_pe"] != id_pe:
            raise RuntimeError("A visita PE nao foi vinculada pelo alias.")

        registro_bri = {
            "id_bri": "bri-pg-1",
            "kobo_uuid": "uuid-bri-pg-1",
            "data": hoje,
            "hora": "13:30",
            "agentes_texto": "Fernando",
            "destino_tratamento": "Ponto Estratégico",
            "local_tratamento": "PE Temporario",
            "localidade": "Tamboara",
            "logradouro": "Rua Alfa - PE Temporario",
            "quarteirao": 9001,
            "numero": "10",
            "quantidade_carga": 1.5,
            "quantidade_carga_extra": 0,
        }
        if not bri._inserir_bri(
            conn, registro_bri, f"{hoje}T14:00:00"
        ):
            raise RuntimeError("O BRI temporario nao foi inserido.")
        if bri._inserir_bri(
            conn, registro_bri, f"{hoje}T14:00:00"
        ):
            raise RuntimeError("O BRI duplicado foi inserido.")
        bri._inserir_agentes(conn, registro_bri["id_bri"], "Fernando")

        conn.execute(
            """INSERT INTO focos_positivos (
                   id_foco, data, id_localidade, quarteirao,
                   gera_notificacao
               ) VALUES (?,?,?,?,?)""",
            ("foco-pg-1", hoje, id_localidade, 9001, 1),
        )
        conn.commit()

        bri_resumo = bri.resumo(conn)
        bri_lista = bri.listar(conn, {"busca": "PE TEMPORARIO"})
        pe_lista = pe.listar(conn, {"busca": "pe temporario"}, limite=None)
        pe_resumo = pe.resumo_operacional(
            conn,
            {"d_ini": hoje, "d_fim": hoje},
        )

        if bri_resumo["totais"]["registros"] != 1:
            raise RuntimeError("O resumo BRI divergiu.")
        if bri_lista["total"] != 1:
            raise RuntimeError("A busca BRI sem diferenca de caixa falhou.")
        if bri_lista["registros"][0]["codigo_pe"] != "PE-9001":
            raise RuntimeError("O BRI nao preservou o vinculo direto com PE.")
        if pe_lista["total"] != 1:
            raise RuntimeError("A busca de PE sem diferenca de caixa falhou.")
        if pe_lista["registros"][0]["visitas_pe_total"] != 1:
            raise RuntimeError("A visita nao apareceu no resumo do PE.")
        if pe_lista["registros"][0]["bri_total"] != 1:
            raise RuntimeError("O BRI nao apareceu no resumo do PE.")
        if pe_lista["registros"][0]["focos_total"] != 1:
            raise RuntimeError("O foco nao apareceu no resumo do PE.")
        if pe_resumo["totais"]["atrasados"] != 0:
            raise RuntimeError("Uma visita de hoje foi marcada como atrasada.")

        payload["nome"] = "PE Temporario Atualizado"
        if not pe.salvar(conn, payload, id_pe=id_pe):
            raise RuntimeError("O PE temporario nao foi atualizado.")
        atualizado = pe.obter(conn, id_pe)
        if atualizado["nome"] != "PE Temporario Atualizado":
            raise RuntimeError("A atualizacao do PE divergiu.")

        try:
            pe.salvar(
                conn,
                {**payload, "data_inclusao": "31/02/2026"},
                id_pe=id_pe,
            )
        except pe.DataValidationError:
            pass
        else:
            raise RuntimeError("A data invalida do PE nao foi recusada.")
        data_apos_erro = pe.obter(conn, id_pe)["data_inclusao"]
        if str(data_apos_erro) != "2026-08-20":
            raise RuntimeError("A data invalida alterou o PE temporario.")

        if not pe.definir_situacao(conn, id_pe, 0):
            raise RuntimeError("A situacao do PE nao foi alterada.")
        inativo = pe.obter(conn, id_pe)
        if inativo["situacao"] != 0 or not inativo["data_desativacao"]:
            raise RuntimeError("A desativacao do PE divergiu.")

        after = _public_counts(conn)
        conn.rollback()
        if before != after:
            raise RuntimeError("Uma tabela publica foi alterada.")
        return id_pe
    finally:
        conn.close()


def _test_pages(database, target):
    admin = db_core.query_one(
        target,
        """
        SELECT id_usuario, nome, nivel
          FROM usuarios
         WHERE ativo=1 AND nivel='admin'
         ORDER BY id_usuario
         LIMIT ?
        """,
        (1,),
    )
    if not admin:
        raise RuntimeError("Nao existe administrador para o teste das paginas.")

    sample_pe = db_core.query_one(
        target,
        "SELECT id_pe FROM pontos_estrategicos ORDER BY id_pe LIMIT ?",
        (1,),
    )
    if not sample_pe:
        raise RuntimeError("Nao existe PE publico para o teste de consulta.")

    with tempfile.TemporaryDirectory(prefix="endemias-pg-bri-pe-") as tmpdir:
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
                "/bri": b"Borrifamento Residual Intradomiciliar",
                "/api/bri": b'"totais"',
                "/api/bri/listar": b'"registros"',
                "/pontos-estrategicos": b"Pontos Estrat",
                "/api/pontos-estrategicos": b'"registros"',
                "/api/pontos-estrategicos/opcoes": b'"localidades"',
                f"/api/pontos-estrategicos/{sample_pe['id_pe']}": b'"codigo_pe"',
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

            resposta_data_invalida = client.post(
                "/api/pontos-estrategicos",
                json={"nome": "PE com data invalida", "data_inclusao": "31/02/2026"},
            )
            if resposta_data_invalida.status_code != 400:
                raise RuntimeError(
                    "A API de PE nao respondeu HTTP 400 para data invalida."
                )
            if b"Data de inclusao invalida" not in resposta_data_invalida.data:
                raise RuntimeError("A API de PE nao informou claramente a data invalida.")
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
        id_pe = _test_data(target)
        _test_pages(args.database, target)
    except Exception as exc:
        print(f"[ERRO] {exc}")
        return 1

    print("Teste de BRI e Pontos Estrategicos no PostgreSQL")
    print("=" * 52)
    print(f"Banco: {args.database}")
    print(f"Identidade temporaria do PE: {id_pe}")
    print("Cadastro, edicao e situacao do PE: OK")
    print("Datas vazias/NaT como NULL e data invalida com HTTP 400: OK")
    print("Aliases e vinculos de visita/BRI: OK")
    print("Filtros, resumos, focos e atrasos: OK")
    print("Paginas e APIs: HTTP 200")
    print("Tabelas publicas: preservadas")
    print("\n[OK] Modulos homologados sem alterar os dados publicos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
