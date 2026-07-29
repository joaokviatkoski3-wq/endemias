"""Homologa o cadastro clinico de Esporotricose no PostgreSQL."""

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
    "esporotricose_visitas",
    "esporotricose_animais",
    "esporotricose_doentes_status",
    "esporotricose_doentes_animais",
    "esporotricose_doentes_receitas",
    "esporotricose_doentes_entregas",
    "esporotricose_doentes_anexos",
    "esporotricose_doentes_origens",
    "esporotricose_estoque_medicacao",
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
            "Testa o cadastro clinico de Esporotricose sem alterar "
            "tabelas publicas."
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


def _insert_visit_fixture(conn):
    conn.execute(
        """INSERT INTO esporotricose_visitas(
               id_visita, kobo_uuid, data, agentes_texto, localidade,
               quarteirao, logradouro, numero, morador, telefone, visita,
               origem_estrutura, processado_em
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "visita-clinica-pg",
            "uuid-visita-clinica-pg",
            "2026-07-28",
            "Agente A",
            "Tamboara",
            1405,
            "Rua das Flores",
            "25",
            "Maria Origem",
            "41999991111",
            "Normal",
            "nova",
            "2026-07-28T10:00:00",
        ),
    )
    conn.execute(
        """INSERT INTO esporotricose_animais(
               id_animal, id_visita, kobo_uuid, especie, nome, sexo,
               feridas, regiao_ferida, processado_em
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            "animal-clinica-pg",
            "visita-clinica-pg",
            "uuid-animal-clinica-pg",
            "Gato",
            "Mimi",
            "Femea",
            "Sim",
            "Face",
            "2026-07-28T10:00:00",
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
        _insert_visit_fixture(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        id_animal = esporotricose.salvar_doente(
            target,
            {
                "tutor": "Maria Silva",
                "nome": "Tilapia",
                "especie": "Gato",
                "sexo": "Femea",
                "telefone": "41999990000",
                "cpf": "12345678900",
                "localidade": "Tamboara",
                "quarteirao": "1405",
                "endereco": "Rua das Flores, 25",
                "status": "Em tratamento",
                "data_notificacao": "2026-07-29",
            },
        )
        id_receita = esporotricose.salvar_receita_doente(
            target,
            id_animal,
            {
                "data_receita": "2026-07-29",
                "capsulas_total": 90,
                "capsulas_por_dia": 1,
                "status": "Em tratamento",
            },
        )
        id_entrega = esporotricose.salvar_entrega_doente(
            target,
            id_receita,
            {
                "quantidade": 30,
                "data_entrega": "2026-07-29",
                "baixa_zoomed": "Sim",
            },
        )
        id_movimento = esporotricose.salvar_estoque_medicacao(
            target,
            {
                "data": "2026-07-29",
                "tipo": "Entrada",
                "quantidade": 180,
                "descricao": "Carga temporaria",
            },
        )
        ids_anexos = esporotricose.salvar_anexos_doente(
            target,
            id_animal,
            [
                {
                    "nome_original": "receita.pdf",
                    "nome_arquivo": "receita.pdf",
                    "caminho_rel": "teste/receita.pdf",
                    "mime_type": "application/pdf",
                    "tamanho": 120,
                }
            ],
            "Joao",
        )

        lista = esporotricose.listar_doentes(
            target, {"busca": "MARIA"}
        )
        if lista["total"] != 1:
            raise RuntimeError("A busca de doentes sem diferenca de caixa falhou.")
        item = lista["registros"][0]
        if item["capsulas_receitadas"] != 90:
            raise RuntimeError("O total receitado divergiu.")
        if item["capsulas_entregues"] != 30:
            raise RuntimeError("O total entregue divergiu.")
        if item["capsulas_restantes"] != 60:
            raise RuntimeError("O saldo da receita divergiu.")
        if item["proxima_entrega"] != "2026-08-28":
            raise RuntimeError("A proxima entrega divergiu.")

        detalhe = esporotricose.obter_doente(target, id_animal)
        if len(detalhe["receitas"]) != 1:
            raise RuntimeError("O detalhe nao retornou a receita.")
        if len(detalhe["receitas"][0]["entregas"]) != 1:
            raise RuntimeError("O detalhe nao retornou a entrega.")
        if len(detalhe["anexos"]) != 1:
            raise RuntimeError("O detalhe nao retornou o anexo.")

        estoque = esporotricose.estoque_medicacao(target)
        if estoque["totais"]["saldo_setor"] != 150:
            raise RuntimeError("O saldo do estoque divergiu.")
        if len(estoque["movimentos_automaticos"]) != 1:
            raise RuntimeError("A saida automatica nao foi exibida.")

        esporotricose.salvar_doente(
            target,
            {
                "id_animal_doente": id_animal,
                "tutor": "Maria Silva",
                "nome": "Tilapia",
                "status": "Em tratamento",
                "observacoes_entomologica": "Revisado",
            },
        )
        esporotricose.atualizar_receita_doente(
            target,
            id_receita,
            {"data_receita": "2026-07-29", "capsulas_total": 120},
        )
        esporotricose.atualizar_entrega_doente(
            target,
            id_entrega,
            {
                "quantidade": 20,
                "data_entrega": "2026-07-30",
                "baixa_zoomed": "Nao",
                "observacoes": "Corrigida",
            },
        )
        esporotricose.salvar_observacao_movimento_automatico(
            target, id_entrega, "Observacao do estoque"
        )

        csv_rows = esporotricose.listar_doentes_csv(
            target, {"baixa_zoomed": "Pendente"}
        )
        if len(csv_rows) != 1 or csv_rows[0]["capsulas_entregues"] != 20:
            raise RuntimeError("A exportacao clinica divergiu.")

        cadastro = esporotricose.preparar_doente_de_visita(
            target, "animal-clinica-pg"
        )
        if cadastro["animal"]["nome"] != "Mimi":
            raise RuntimeError("A origem da visita nao foi preparada.")
        id_origem = esporotricose.salvar_doente(
            target, cadastro["animal"]
        )
        origem = esporotricose.obter_doente(target, id_origem)
        if len(origem["origens_visita"]) != 1:
            raise RuntimeError("O vinculo com a visita nao foi salvo.")

        anexo = esporotricose.obter_anexo_doente(
            target, ids_anexos[0]
        )
        if anexo["nome_original"] != "receita.pdf":
            raise RuntimeError("O metadado do anexo divergiu.")
        esporotricose.excluir_anexo_doente(target, ids_anexos[0])
        esporotricose.excluir_estoque_medicacao(target, id_movimento)
        esporotricose.excluir_entrega_doente(target, id_entrega)
        esporotricose.excluir_receita_doente(target, id_receita)
        esporotricose.excluir_doente(target, id_animal)
        esporotricose.excluir_doente(target, id_origem)

        if esporotricose.listar_doentes(target, {})["total"] != 0:
            raise RuntimeError("A exclusao do cadastro clinico falhou.")

        after = _public_counts(conn)
        if before != after:
            raise RuntimeError("Uma tabela publica foi alterada.")
    finally:
        db_core.connect = original_connect
        conn.close()


def _test_public_data(target):
    dados = esporotricose.listar_doentes(target, {})
    if "registros" not in dados or "totais" not in dados:
        raise RuntimeError("A lista publica retornou formato invalido.")
    esporotricose.listar_doentes_csv(target, {})
    esporotricose.status_doentes(target)
    esporotricose.estoque_medicacao(target)
    if dados["registros"]:
        esporotricose.obter_doente(
            target, dados["registros"][0]["id_animal_doente"]
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
    primeiro = db_core.query_one(
        target,
        """SELECT id_animal_doente
             FROM esporotricose_doentes_animais
            ORDER BY id_animal_doente
            LIMIT ?""",
        (1,),
    )
    if not admin or not primeiro:
        raise RuntimeError("Faltam dados publicos para testar as paginas.")

    with tempfile.TemporaryDirectory(
        prefix="endemias-pg-esporo-clinica-"
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
                    "ANEXOS_DIR": str(Path(tmpdir) / "anexos"),
                }
            )
            client = flask_app.test_client()
            with client.session_transaction() as flask_session:
                flask_session["uid"] = admin["id_usuario"]
                flask_session["nome"] = admin["nome"]
                flask_session["nivel"] = admin["nivel"]

            id_animal = primeiro["id_animal_doente"]
            checks = {
                "/esporotricose/doentes/novo": b"Esporotricose",
                f"/esporotricose/doentes/{id_animal}": b"Receitas",
                f"/esporotricose/doentes/{id_animal}/editar": b"Esporotricose",
                "/api/esporotricose/doentes": b'"registros"',
                "/api/esporotricose/doentes/status": b'"registros"',
                "/api/esporotricose/doentes/estoque": b'"saldo_setor"',
                f"/api/esporotricose/doentes/{id_animal}": b'"receitas"',
                "/esporotricose/doentes/casos.csv": b"id_animal_doente",
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

    print("Teste do cadastro clinico de Esporotricose no PostgreSQL")
    print("=" * 60)
    print(f"Banco: {args.database}")
    print("Casos, receitas e entregas: OK")
    print("Estoque e saidas automaticas: OK")
    print("Vinculos com visitas e metadados de anexos: OK")
    print("Paginas e APIs: HTTP 200")
    print(f"Tabelas publicas preservadas: {len(after)}")
    print("\n[OK] Modulo homologado sem alterar os dados publicos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
