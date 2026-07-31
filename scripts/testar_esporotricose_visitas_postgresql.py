"""Homologa as visitas de Esporotricose no PostgreSQL."""

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

from app_core import db as db_core  # noqa: E402
from app_core import esporotricose  # noqa: E402


SAFE_DATABASE = "endemias_teste"
TEMP_TABLES = (
    "localidades",
    "agentes",
    "esporotricose_visitas",
    "esporotricose_visita_agentes",
    "esporotricose_animais",
    "esporotricose_doentes_origens",
    "esporotricose_buscas_ferido",
)


class _SharedConnection:
    """Mantem as tabelas temporarias visiveis entre chamadas do modulo."""

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
            "Testa visitas de Esporotricose sem alterar tabelas publicas."
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
        (900001, "Tamboara"),
    )
    conn.execute(
        """INSERT INTO agentes(id_agente, nome, nome_completo)
           VALUES (?,?,?)""",
        (900001, "Agente B", "Agente B"),
    )
    conn.execute(
        """INSERT INTO agentes(id_agente, nome, nome_completo)
           VALUES (?,?,?)""",
        (900002, "Agente A", "Agente A"),
    )
    conn.execute(
        """INSERT INTO esporotricose_visitas(
               id_visita, kobo_uuid, data, hora_inicio, agentes_texto,
               localidade, id_localidade, quarteirao, tipo_imovel,
               logradouro, numero, morador, telefone, visita,
               origem_estrutura, processado_em
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "visita-esporo-pg",
            "uuid-visita-esporo-pg",
            "2026-07-28",
            "09:00",
            "Agente A, Agente B",
            "Tamboara",
            900001,
            1405,
            "Residencia",
            "Rua das Flores",
            "25",
            "Maria",
            "41999990000",
            "Normal",
            "nova",
            "2026-07-28T10:00:00",
        ),
    )
    conn.executemany(
        """INSERT INTO esporotricose_visita_agentes(id_visita, id_agente)
           VALUES (?,?)""",
        (
            ("visita-esporo-pg", 900001),
            ("visita-esporo-pg", 900002),
        ),
    )
    conn.executemany(
        """INSERT INTO esporotricose_animais(
               id_animal, id_visita, kobo_uuid, especie, nome, feridas,
               vacinado, castrado, ambiente, processado_em
           ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            (
                "animal-esporo-pg-1",
                "visita-esporo-pg",
                "uuid-animal-esporo-pg-1",
                "Gato",
                "Tilapia",
                "Sim",
                "Sim",
                "Nao",
                "Domiciliado",
                "2026-07-28T10:00:00",
            ),
            (
                "animal-esporo-pg-2",
                "visita-esporo-pg",
                "uuid-animal-esporo-pg-2",
                "Cao",
                "Lobo",
                "Nao",
                "Desconhecido",
                "Sim",
                "Semidomiciliado",
                "2026-07-28T10:00:00",
            ),
        ),
    )
    conn.commit()


def _test_temporary_data(target):
    conn = db_core.connect(target)
    original_connect = db_core.connect
    try:
        before = _public_counts(conn)
        conn.rollback()
        _temporary_schema(conn)
        _insert_fixture(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        filtros = {"d_ini": "2026-07-01", "d_fim": "2026-07-31"}
        resumo = esporotricose.resumo(target, filtros)
        if resumo["totais"]["visitas"] != 1:
            raise RuntimeError("O resumo de visitas divergiu.")
        if resumo["animais"]["total"] != 2:
            raise RuntimeError("O resumo de animais divergiu.")

        visitas = esporotricose.listar_visitas(
            target, {**filtros, "busca": "1405"}
        )
        if visitas["total"] != 1:
            raise RuntimeError("A busca pelo quarteirao nao encontrou a visita.")
        if visitas["registros"][0]["animais"] != 2:
            raise RuntimeError("Os animais da visita foram duplicados.")
        if visitas["registros"][0]["agentes"] != "Agente A, Agente B":
            raise RuntimeError("A agregacao dos agentes divergiu.")

        animais = esporotricose.listar_animais(
            target,
            {
                **filtros,
                "busca": "Tilapia",
                "especie": ["Gato"],
                "feridas": ["Sim"],
            },
        )
        if animais["total"] != 1:
            raise RuntimeError("Os filtros de animais divergiram.")

        esporotricose.atualizar_visita(
            target,
            "visita-esporo-pg",
            {"observacoes": "Revisada no teste", "quarteirao": 1406},
        )
        esporotricose.atualizar_animal(
            target,
            "animal-esporo-pg-1",
            {"evolucao_caso": "Em acompanhamento"},
        )
        busca = esporotricose.salvar_busca_ferido(
            target,
            "animal-esporo-pg-1",
            {
                "data_busca": "2026-07-29",
                "agente": "Agente A",
                "observacoes": "Busca controlada",
            },
        )
        if not busca["id_busca"]:
            raise RuntimeError("A busca de ferido nao retornou sua identidade.")

        animais = esporotricose.listar_animais(
            target, {"busca": "Tilapia"}
        )
        if len(animais["registros"][0]["buscas_ferido"]) != 1:
            raise RuntimeError("A busca de ferido nao foi anexada ao animal.")
        if animais["registros"][0]["evolucao_caso"] != "Em acompanhamento":
            raise RuntimeError("A edicao do animal nao foi persistida.")

        eventos = esporotricose.eventos_agenda_buscas_ferido(
            target, "2026-07-29", "2026-07-29"
        )
        if len(eventos) != 1 or eventos[0]["animal"] != "Tilapia":
            raise RuntimeError("A integracao da busca com a Agenda divergiu.")

        localidades = esporotricose.resumo_localidades(target, filtros)
        if localidades["registros"][0]["animais"] != 2:
            raise RuntimeError("O resumo por localidade divergiu.")
        painel = esporotricose.dashboard(target, filtros)
        if not painel["evolucao"] or not painel["localidades"]:
            raise RuntimeError("O painel de visitas nao retornou as series.")

        visita_importada = {
            "id_visita": "visita-importada-pg",
            "kobo_uuid": "uuid-importada-pg",
            "data": "2026-07-30",
            "localidade": "Nova Localidade PG",
            "agentes_texto": "Agente A",
            "origem_estrutura": "nova",
        }
        if not esporotricose._inserir_visita(
            conn,
            visita_importada,
            "2026-07-30T10:00:00",
        ):
            raise RuntimeError("A visita importada nao foi inserida.")
        if esporotricose._inserir_visita(
            conn,
            visita_importada,
            "2026-07-30T10:00:00",
        ):
            raise RuntimeError("A visita duplicada nao foi ignorada.")
        if esporotricose._inserir_agentes(
            conn,
            "visita-importada-pg",
            "Agente A",
        ) != 1:
            raise RuntimeError("O agente importado nao foi vinculado.")
        if esporotricose._inserir_agentes(
            conn,
            "visita-importada-pg",
            "Agente A",
        ) != 0:
            raise RuntimeError("O vinculo duplicado do agente nao foi ignorado.")
        animal_importado = {
            "id_animal": "animal-importado-pg",
            "id_visita": "visita-importada-pg",
            "kobo_uuid": "uuid-animal-importado-pg",
            "especie": "Gato",
        }
        if not esporotricose._inserir_animal(
            conn,
            animal_importado,
            "2026-07-30T10:00:00",
        ):
            raise RuntimeError("O animal importado nao foi inserido.")
        if esporotricose._inserir_animal(
            conn,
            animal_importado,
            "2026-07-30T10:00:00",
        ):
            raise RuntimeError("O animal duplicado nao foi ignorado.")

        after = _public_counts(conn)
        if before != after:
            raise RuntimeError("Uma tabela publica foi alterada.")
    finally:
        db_core.connect = original_connect
        conn.close()


def _test_public_data(target):
    filtros = {"d_ini": "2025-01-01", "d_fim": "2026-12-31"}
    checks = (
        esporotricose.resumo(target, filtros),
        esporotricose.listar_visitas(target, {**filtros, "busca": "2026"}),
        esporotricose.listar_animais(target, {**filtros, "busca": "gato"}),
        esporotricose.resumo_localidades(target, filtros),
        esporotricose.dashboard(target, filtros),
    )
    if any(not isinstance(item, dict) for item in checks):
        raise RuntimeError("Uma consulta publica retornou formato invalido.")
    esporotricose.eventos_agenda_buscas_ferido(
        target, "2025-01-01", "2026-12-31"
    )


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
        prefix="endemias-pg-esporotricose-"
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
                "/esporotricose": b"Esporotricose",
                f"/api/esporotricose?{query}": b'"totais"',
                f"/api/esporotricose/visitas?{query}": b'"registros"',
                f"/api/esporotricose/animais?{query}": b'"registros"',
                f"/api/esporotricose/localidades?{query}": b'"registros"',
                f"/api/esporotricose/dashboard?{query}": b'"evolucao"',
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

    print("Teste de visitas de Esporotricose no PostgreSQL")
    print("=" * 54)
    print(f"Banco: {args.database}")
    print("Resumo, filtros e painel: OK")
    print("Edicao em tabelas temporarias: OK")
    print("Busca de ferido e integracao com a Agenda: OK")
    print("Pagina e APIs: HTTP 200")
    print(f"Tabelas publicas preservadas: {len(after)}")
    print("\n[OK] Modulo homologado sem alterar os dados publicos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
