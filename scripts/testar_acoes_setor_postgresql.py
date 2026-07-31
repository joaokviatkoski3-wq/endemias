"""Homologa Acoes e Atendimentos no PostgreSQL sem alterar dados publicos."""

import argparse
import io
import logging
import os
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core import db as db_core  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "usuarios",
    "agentes",
    "acoes_setor",
    "acoes_setor_agentes",
    "acoes_setor_anexos",
    "auditoria_eventos",
)
ADMIN = {"id_usuario": 930001, "nome": "Admin Acoes PG", "nivel": "admin"}
OPERADOR = {
    "id_usuario": 930002,
    "nome": "Operador Acoes PG",
    "nivel": "operador",
}
VISUALIZADOR = {
    "id_usuario": 930003,
    "nome": "Visualizador Acoes PG",
    "nivel": "visualizador",
}
ID_AGENTE = 920001


class _SharedConnection:
    """Mantem as tabelas temporarias disponiveis entre as rotas Flask."""

    def __init__(self, conn):
        self._conn = conn
        self.backend = conn.backend

    def close(self):
        pass

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback_obj):
        return self._conn.__exit__(exc_type, exc_value, traceback_obj)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Testa Acoes e Atendimentos somente em tabelas PostgreSQL "
            "temporarias."
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
    conn.execute(
        """ALTER TABLE acoes_setor_agentes
           ADD CONSTRAINT temp_acoes_agentes_acao_fk
           FOREIGN KEY (id_acao) REFERENCES acoes_setor(id_acao)
           ON DELETE CASCADE"""
    )
    conn.execute(
        """ALTER TABLE acoes_setor_agentes
           ADD CONSTRAINT temp_acoes_agentes_agente_fk
           FOREIGN KEY (id_agente) REFERENCES agentes(id_agente)"""
    )
    conn.execute(
        """ALTER TABLE acoes_setor_anexos
           ADD CONSTRAINT temp_acoes_anexos_acao_fk
           FOREIGN KEY (id_acao) REFERENCES acoes_setor(id_acao)
           ON DELETE CASCADE"""
    )
    conn.commit()


def _fixtures(conn):
    usuarios = (
        (ADMIN, "admin_acoes_pg"),
        (OPERADOR, "operador_acoes_pg"),
        (VISUALIZADOR, "visualizador_acoes_pg"),
    )
    for usuario, login in usuarios:
        conn.execute(
            """INSERT INTO usuarios
               (id_usuario, usuario, nome, senha_hash, nivel, ativo, criado_em,
                acesso_laboratorio, somente_laboratorio)
               VALUES (?, ?, ?, 'teste', ?, 1, '2026-07-31T08:00:00', 0, 0)""",
            (
                usuario["id_usuario"],
                login,
                usuario["nome"],
                usuario["nivel"],
            ),
        )
    conn.execute(
        """INSERT INTO agentes(id_agente, nome, nome_completo, ativo)
           VALUES (?, 'Agente Acoes PG', 'Agente Teste Acoes PG', 1)""",
        (ID_AGENTE,),
    )
    conn.commit()


def _login(client, usuario):
    with client.session_transaction() as flask_session:
        flask_session["uid"] = usuario["id_usuario"]
        flask_session["nome"] = usuario["nome"]
        flask_session["nivel"] = usuario["nivel"]


def _assert_status(response, expected, label):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label} respondeu HTTP {response.status_code}: "
            f"{response.get_data(as_text=True)}"
        )
    return response


def _payload():
    return {
        "tipo": "educativa",
        "situacao": "em_acompanhamento",
        "data": "2026-07-29",
        "data_fim": "2026-07-31",
        "periodo": "manha",
        "hora_inicio": "09:00",
        "hora_fim": "10:30",
        "caso": "Homologacao PostgreSQL",
        "localidade": "Localidade Acoes PG",
        "local": "Escola temporaria",
        "publico_aproximado": 35,
        "tipo_atividade_realizada": ["palestra"],
        "publico_alvo": ["comunidade_escolar"],
        "recurso_utilizado": ["banner"],
        "tema": "Prevencao de endemias",
        "contexto": "Registro criado somente em tabela temporaria.",
        "resultados": "Fluxo dual homologado.",
        "agentes": [ID_AGENTE],
    }


def _test_routes(database, conn, create_app):
    with tempfile.TemporaryDirectory(prefix="endemias-pg-acoes-setor-") as tmpdir:
        temp_path = Path(tmpdir)
        log_path = str(temp_path / "teste.log")
        try:
            flask_app = create_app(
                {
                    "DB_BACKEND": "postgresql",
                    "PG_DATABASE": database,
                    "TESTING": True,
                    "WTF_CSRF_ENABLED": False,
                    "LOG_PATH": log_path,
                    "SECRET_KEY_PATH": str(temp_path / "secret.key"),
                    "ANEXOS_DIR": str(temp_path / "anexos"),
                    "BACKUP_DIR": str(temp_path / "backups"),
                }
            )
            admin_client = flask_app.test_client()
            operador_client = flask_app.test_client()
            visualizador_client = flask_app.test_client()
            _login(admin_client, ADMIN)
            _login(operador_client, OPERADOR)
            _login(visualizador_client, VISUALIZADOR)

            _assert_status(
                admin_client.get("/acoes-setor"),
                200,
                "Pagina de Acoes e Atendimentos",
            )
            _assert_status(
                visualizador_client.get("/acoes-setor"),
                403,
                "Bloqueio do visualizador",
            )

            created = _assert_status(
                admin_client.post("/api/acoes-setor", json=_payload()),
                201,
                "Criacao do registro",
            )
            id_acao = created.get_json()["id_acao"]

            listed = _assert_status(
                admin_client.get(
                    "/api/acoes-setor"
                    "?busca=prevencao&id_agente=920001"
                    "&data_inicio=2026-07-30&data_fim=2026-07-30"
                ),
                200,
                "Listagem filtrada",
            ).get_json()
            if listed["total"] != 1:
                raise RuntimeError("Os filtros do registro temporario divergiram.")
            registro = listed["registros"][0]
            if registro["agentes"][0]["nome"] != "Agente Acoes PG":
                raise RuntimeError("O vinculo com o servidor nao foi retornado.")

            payload_atualizado = {
                **_payload(),
                "tipo": "vistoria",
                "situacao": "realizada",
                "tema": "Vistoria PostgreSQL revisada",
                "tipo_atividade_realizada": [],
                "publico_alvo": [],
                "recurso_utilizado": [],
            }
            _assert_status(
                admin_client.put(
                    f"/api/acoes-setor/{id_acao}",
                    json=payload_atualizado,
                ),
                200,
                "Edicao do registro",
            )
            detail = _assert_status(
                admin_client.get(f"/api/acoes-setor/{id_acao}"),
                200,
                "Detalhe do registro",
            ).get_json()
            if detail["tipo"] != "vistoria":
                raise RuntimeError("A edicao do registro nao foi persistida.")

            public_upload = _assert_status(
                admin_client.post(
                    f"/api/acoes-setor/{id_acao}/anexos",
                    data={
                        "arquivos": (
                            io.BytesIO(b"imagem temporaria"),
                            "foto-homologacao.png",
                        )
                    },
                    content_type="multipart/form-data",
                ),
                201,
                "Upload publico",
            ).get_json()
            id_imagem = next(
                item["id_anexo"]
                for item in public_upload["anexos"]
                if item["nome_original"] == "foto-homologacao.png"
            )

            restricted_upload = _assert_status(
                admin_client.post(
                    f"/api/acoes-setor/{id_acao}/anexos",
                    data={
                        "restrito": "1",
                        "arquivos": (
                            io.BytesIO(b"documento temporario"),
                            "documento-restrito.pdf",
                        ),
                    },
                    content_type="multipart/form-data",
                ),
                201,
                "Upload restrito",
            ).get_json()
            restrito = next(
                item
                for item in restricted_upload["anexos"]
                if item["nome_original"] == "documento-restrito.pdf"
            )

            _assert_status(
                operador_client.post(
                    f"/api/acoes-setor/{id_acao}/anexos",
                    data={
                        "restrito": "1",
                        "arquivos": (io.BytesIO(b"bloqueado"), "bloqueado.pdf"),
                    },
                    content_type="multipart/form-data",
                ),
                403,
                "Bloqueio de anexo restrito para operador",
            )
            anexos_operador = _assert_status(
                operador_client.get(f"/api/acoes-setor/{id_acao}/anexos"),
                200,
                "Listagem de anexos do operador",
            ).get_json()["anexos"]
            if len(anexos_operador) != 1:
                raise RuntimeError("O anexo restrito ficou visivel ao operador.")
            _assert_status(
                operador_client.get(
                    f"/acoes-setor/anexos/{restrito['id_anexo']}/download"
                ),
                403,
                "Bloqueio do download restrito",
            )
            _assert_status(
                operador_client.delete(f"/api/acoes-setor/{id_acao}"),
                403,
                "Bloqueio da exclusao com anexo restrito",
            )

            gallery = _assert_status(
                admin_client.get(
                    "/api/acoes-setor/anexos"
                    "?tipo_arquivo=imagem&busca=homologacao"
                ),
                200,
                "Galeria de imagens",
            ).get_json()
            if gallery["total"] != 1:
                raise RuntimeError("A galeria nao retornou a imagem esperada.")

            image_response = _assert_status(
                admin_client.get(
                    f"/acoes-setor/anexos/{id_imagem}/download?inline=1"
                ),
                200,
                "Download da imagem",
            )
            if image_response.data != b"imagem temporaria":
                raise RuntimeError("O conteudo do anexo baixado divergiu.")
            image_response.close()

            zip_response = _assert_status(
                admin_client.get(
                    f"/api/acoes-setor/{id_acao}/anexos/baixar-todos"
                ),
                200,
                "Download ZIP",
            )
            with zipfile.ZipFile(io.BytesIO(zip_response.data)) as archive:
                if set(archive.namelist()) != {
                    "foto-homologacao.png",
                    "documento-restrito.pdf",
                }:
                    raise RuntimeError("O ZIP nao reuniu os anexos esperados.")
            zip_response.close()

            report = _assert_status(
                admin_client.get(
                    "/acoes-setor/relatorio/pdf"
                    "?busca=vistoria&imagens=1"
                ),
                200,
                "Relatorio tecnico",
            ).get_data(as_text=True)
            if (
                "Vistoria PostgreSQL revisada" not in report
                or "foto-homologacao.png" not in report
            ):
                raise RuntimeError("O relatorio nao apresentou o registro e a imagem.")

            _assert_status(
                admin_client.put(
                    f"/api/acoes-setor/anexos/{restrito['id_anexo']}",
                    json={"restrito": False},
                ),
                200,
                "Liberacao do anexo restrito",
            )
            anexos_liberados = _assert_status(
                operador_client.get(f"/api/acoes-setor/{id_acao}/anexos"),
                200,
                "Listagem apos liberacao",
            ).get_json()["anexos"]
            if len(anexos_liberados) != 2:
                raise RuntimeError("O anexo liberado nao apareceu ao operador.")

            _assert_status(
                admin_client.delete(
                    f"/api/acoes-setor/anexos/{restrito['id_anexo']}"
                ),
                200,
                "Exclusao do anexo",
            )
            _assert_status(
                admin_client.delete(f"/api/acoes-setor/{id_acao}"),
                200,
                "Exclusao do registro",
            )

            if conn.execute("SELECT COUNT(*) FROM acoes_setor").fetchone()[0] != 0:
                raise RuntimeError("O registro temporario nao foi excluido.")
            if conn.execute(
                "SELECT COUNT(*) FROM acoes_setor_agentes"
            ).fetchone()[0] != 0:
                raise RuntimeError("O vinculo temporario nao foi removido em cascata.")
            if conn.execute(
                "SELECT COUNT(*) FROM acoes_setor_anexos"
            ).fetchone()[0] != 0:
                raise RuntimeError("O anexo temporario nao foi removido em cascata.")

            audit_actions = {
                row[0]
                for row in conn.execute(
                    "SELECT acao FROM auditoria_eventos"
                ).fetchall()
            }
            expected_actions = {
                "acoes_setor_criou",
                "acoes_setor_atualizou",
                "acoes_setor_anexos_adicionou",
                "acoes_setor_anexo_restricao_atualizou",
                "acoes_setor_anexo_excluiu",
                "acoes_setor_excluiu",
            }
            if not expected_actions <= audit_actions:
                raise RuntimeError("A auditoria do modulo ficou incompleta.")
        finally:
            for handler in list(logging.getLogger().handlers):
                if getattr(handler, "baseFilename", None) == os.path.abspath(log_path):
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
        _fixtures(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        _test_routes(database, conn, create_app)

        public_after = _public_counts(conn)
        if public_before != public_after:
            raise RuntimeError("Uma tabela publica foi alterada pelo ensaio.")
        return len(public_before)
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

        total_publicas = _test_temporary_data(args.database, create_app)
    except Exception as exc:
        print(f"[ERRO] {exc}")
        traceback.print_exc()
        return 1

    print("Teste de Acoes e Atendimentos no PostgreSQL")
    print("=" * 51)
    print(f"Banco: {args.database}")
    print("Pagina, CRUD, filtros e vinculos com servidores: OK")
    print("Anexos, galeria, ZIP, download e relatorio tecnico: OK")
    print("Permissoes de operador, administrador e visualizador: OK")
    print("Auditoria das alteracoes: OK")
    print(f"Tabelas publicas preservadas: {total_publicas}")
    print("\n[OK] Modulo validado somente em tabelas temporarias.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
