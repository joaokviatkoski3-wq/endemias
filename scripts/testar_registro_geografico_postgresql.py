"""Homologa o Registro Geografico no PostgreSQL sem alterar dados publicos."""

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
from app_core import registro_geografico as rg_core  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "localidades",
    "agentes",
    "registro_geografico_quarteiroes",
    "registro_geografico_imoveis",
    "registro_geografico_imovel_agentes",
)


class _SharedConnection:
    def __init__(self, conn):
        self._conn = conn
        self.backend = conn.backend

    def close(self):
        pass

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._conn.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _parser():
    parser = argparse.ArgumentParser(
        description="Testa o Registro Geografico sem alterar tabelas publicas."
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
    conn.execute(
        """INSERT INTO localidades(id_localidade, nome, cod_localidade)
           VALUES (910001, 'Localidade Teste RG', 'TRG')"""
    )
    conn.execute(
        """INSERT INTO agentes(id_agente, nome, nome_completo, ativo)
           VALUES (920001, 'Agente RG', 'Agente Teste RG', 1)"""
    )
    conn.commit()


def _novo_imovel(logradouro, numero, quarteirao="0009"):
    return {
        "id_localidade": 910001,
        "quarteirao": quarteirao,
        "logradouro": logradouro,
        "numero": numero,
        "tipo": "R",
        "condominio": 2,
        "data_atualizacao": "2026-07-29",
        "agentes_ids": [920001],
    }


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

        primeiro = rg_core.criar(
            target,
            _novo_imovel("Rua Lourenco Angelo Buzato", "10"),
            usuario_id=930001,
            usuario_nome="Usuario Teste",
        )
        segundo = rg_core.criar(
            target,
            _novo_imovel("R. Lourenco Angelo Buzatto", "12"),
            usuario_id=930001,
            usuario_nome="Usuario Teste",
        )
        alfanumerico = rg_core.criar(
            target,
            _novo_imovel("Rua Alfanumerica", "1", quarteirao="10A"),
            usuario_id=930001,
            usuario_nome="Usuario Teste",
        )

        if primeiro["id_imovel"] == segundo["id_imovel"]:
            raise RuntimeError("Os imoveis receberam a mesma identidade.")
        if alfanumerico["quarteirao_raw"] != "10A":
            raise RuntimeError("O quarteirao alfanumerico foi alterado.")

        lista = rg_core.listar(target, {"localidade": ["910001"]}, limite=None)
        if lista["total"] != 3:
            raise RuntimeError("A listagem temporaria do RG divergiu.")
        if lista["totais"]["imoveis_reais"] != 6:
            raise RuntimeError("O total com condominios divergiu.")

        detalhe = rg_core.obter(target, primeiro["id_imovel"])
        if detalhe["agentes"] != "Agente RG":
            raise RuntimeError("O agente do imovel nao foi vinculado.")

        atualizado = rg_core.salvar(
            target,
            primeiro["id_imovel"],
            {
                **_novo_imovel("Rua Lourenco Angelo Buzato", "11"),
                "observacao": "Atualizado no PostgreSQL",
            },
            usuario_id=930001,
            usuario_nome="Usuario Teste",
        )
        if atualizado["numero"] != "11":
            raise RuntimeError("A edicao individual nao foi persistida.")

        sugestoes = rg_core.sugestoes_logradouros(
            target, "lourenco", 910001, limite=10
        )
        if sugestoes["total"] != 2:
            raise RuntimeError("As sugestoes de logradouro divergiram.")

        similares = rg_core.logradouros_similares(
            target, {"localidade": ["910001"]}, score_min=75, limite=10
        )
        if not similares["pares"]:
            raise RuntimeError("Os logradouros semelhantes nao foram detectados.")

        payload_lote = {
            "campo": "logradouro",
            "modo": "exato",
            "busca": "R. Lourenco Angelo Buzatto",
            "novo": "Rua Lourenco Angelo Buzato",
            "filtros": {"localidade": ["910001"]},
        }
        preview = rg_core.preview_substituicao_lote(target, payload_lote)
        if preview["total"] != 1:
            raise RuntimeError("A previa da edicao em lote divergiu.")
        aplicado = rg_core.aplicar_substituicao_lote(
            target,
            payload_lote,
            usuario_id=930001,
            usuario_nome="Usuario Teste",
        )
        if aplicado["atualizados"] != 1:
            raise RuntimeError("A edicao em lote nao foi aplicada.")

        quadra = rg_core.quarteirao(target, 910001, "0009")
        linhas = []
        for item in quadra["registros"]:
            linhas.append(
                {
                    "id_imovel": item["id_imovel"],
                    "logradouro": item["logradouro"],
                    "numero": item["numero"],
                    "sequencia": item["sequencia"],
                    "lado": item["lado"],
                    "tipo": item["tipo"],
                    "condominio": item["condominio"],
                    "observacao": item["observacao"],
                }
            )
        linhas.append(
            {
                "logradouro": "Rua Nova do Quarteirao",
                "numero": "14",
                "tipo": "C",
            }
        )
        salva_quadra = rg_core.salvar_quarteirao(
            target,
            {
                "id_localidade": 910001,
                "quarteirao": "0009",
                "origem_id_localidade": 910001,
                "origem_quarteirao": "0009",
                "data_atualizacao": "2026-07-29",
                "agentes_ids": [920001],
                "linhas": linhas,
            },
            usuario_id=930001,
            usuario_nome="Usuario Teste",
        )
        if len(salva_quadra["registros"]) != 3:
            raise RuntimeError("A edicao completa do quarteirao divergiu.")

        acompanhamento = rg_core.acompanhamento_atualizacoes(
            target, {"localidade": ["910001"]}
        )
        if acompanhamento["totais"]["quarteiroes"] != 2:
            raise RuntimeError("O acompanhamento nao encontrou os quarteiroes.")
        if not all(
            item["atualizado_por_usuario"] == "Usuario Teste"
            for item in acompanhamento["registros"]
        ):
            raise RuntimeError("A autoria da atualizacao nao foi preservada.")

        mapa = rg_core.resumo_mapa(target)
        if mapa["total"]["quarteiroes"] != 2:
            raise RuntimeError("O resumo do mapa divergiu.")

        movido = rg_core.salvar_quarteirao(
            target,
            {
                "id_localidade": 910001,
                "quarteirao": "0011",
                "origem_id_localidade": 910001,
                "origem_quarteirao": "10A",
                "data_atualizacao": "2026-07-29",
                "agentes_ids": [920001],
                "linhas": [
                    {
                        "id_imovel": alfanumerico["id_imovel"],
                        "logradouro": alfanumerico["logradouro"],
                        "numero": alfanumerico["numero"],
                        "tipo": alfanumerico["tipo"],
                        "condominio": alfanumerico["condominio"],
                    }
                ],
            },
            usuario_id=930001,
            usuario_nome="Usuario Teste",
        )
        if movido["quarteirao_raw"] != "0011":
            raise RuntimeError("A mudanca de numero do quarteirao falhou.")
        if rg_core.quarteirao(target, 910001, "10A")["registros"]:
            raise RuntimeError("O quarteirao de origem ainda possui imoveis.")

        limpo = rg_core.limpar_quarteirao(
            target,
            {"id_localidade": 910001, "quarteirao": "0009"},
            usuario_id=930001,
            usuario_nome="Usuario Teste",
        )
        if limpo["removidos"] != 3:
            raise RuntimeError("A limpeza do quarteirao removeu quantidade incorreta.")

        excluido = rg_core.excluir_quarteirao(
            target, {"id_localidade": 910001, "quarteirao": "0011"}
        )
        if excluido["removidos"] != 1:
            raise RuntimeError("A exclusao do quarteirao removeu quantidade incorreta.")

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

    with tempfile.TemporaryDirectory(prefix="endemias-pg-rg-") as tmpdir:
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
                "/registro-geografico": b"Registro de Reconhecimento",
                "/api/registro-geografico?limite=1": b'"registros"',
                "/api/registro-geografico/acompanhamento": b'"totais"',
                "/api/registro-geografico/mapa-resumo": b'"quarteiroes"',
                "/api/registro-geografico/logradouros-sugestoes?q=rua": b'"sugestoes"',
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
        "OK: Registro Geografico homologado no PostgreSQL; "
        f"{total_publicas} tabelas publicas preservadas."
    )


if __name__ == "__main__":
    main()
