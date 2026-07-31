"""Homologa Mapa, Notificacoes e Relatorios no PostgreSQL sem dados publicos."""

import argparse
import json
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


SAFE_DATABASE = "endemias_teste"
ADMIN = {
    "id_usuario": 950001,
    "nome": "Admin Relatorios PG",
    "nivel": "admin",
}
ID_AGENTE = 950001
ID_LOCALIDADE = 950001


class _SharedConnection:
    """Mantem as tabelas temporarias visiveis entre as rotas Flask."""

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
            "Testa Mapa, Notificacoes e Relatorio por Servidor somente em "
            "tabelas PostgreSQL temporarias."
        )
    )
    parser.add_argument("--database", default=SAFE_DATABASE)
    parser.add_argument(
        "--confirmar-banco",
        help="Obrigatorio para qualquer banco diferente de endemias_teste.",
    )
    return parser


def _public_tables(conn):
    return [
        row[0]
        for row in conn.execute(
            """SELECT table_name
                 FROM information_schema.tables
                WHERE table_schema='public'
                  AND table_type='BASE TABLE'
                ORDER BY table_name"""
        ).fetchall()
    ]


def _public_counts(conn, tables):
    return {
        table: conn.execute(
            f'SELECT COUNT(*) FROM public."{table}"'
        ).fetchone()[0]
        for table in tables
    }


def _temporary_schema(conn, tables):
    for table in tables:
        conn.execute(
            f'''CREATE TEMPORARY TABLE "{table}"
                (LIKE public."{table}" INCLUDING ALL)
                ON COMMIT PRESERVE ROWS'''
        )
    conn.commit()


def _fixtures(conn):
    conn.execute(
        """INSERT INTO usuarios
           (id_usuario, usuario, nome, senha_hash, nivel, ativo, criado_em,
            acesso_laboratorio, somente_laboratorio)
           VALUES (?, 'admin_relatorios_pg', ?, 'teste', 'admin', 1,
                   '2026-07-31T08:00:00', 1, 0)""",
        (ADMIN["id_usuario"], ADMIN["nome"]),
    )
    conn.execute(
        """INSERT INTO agentes(id_agente, nome, nome_completo, ativo)
           VALUES (?, 'agente_pg', 'Agente PostgreSQL', 1)""",
        (ID_AGENTE,),
    )
    conn.execute(
        """INSERT INTO localidades(id_localidade, nome, cod_localidade)
           VALUES (?, 'Localidade PostgreSQL', 'LPG')""",
        (ID_LOCALIDADE,),
    )
    conn.execute(
        """INSERT INTO visitas
           (id_visita, kobo_uuid, tipo, data, hora_inicio, hora_fim,
            localidade, id_localidade, logradouro, numero, quarteirao,
            visita, processado_em)
           VALUES ('rel-visita-1', 'rel-kobo-1', 'TBO', '2026-07-28',
                   '08:00', '08:30', 'Localidade PostgreSQL', ?,
                   'Rua PostgreSQL', '10', 12, 'normal',
                   '2026-07-28T09:00:00')""",
        (ID_LOCALIDADE,),
    )
    conn.execute(
        "INSERT INTO visita_agentes(id_visita, id_agente) VALUES ('rel-visita-1', ?)",
        (ID_AGENTE,),
    )
    conn.execute(
        """INSERT INTO depositos_inspecionados
           (id_visita, tipo_deposito, inspecionado, eliminado, tratado)
           VALUES ('rel-visita-1', 'A1', 3, 1, 1)"""
    )
    conn.execute(
        """INSERT INTO tratamentos
           (id_visita, tipo, quantidade_carga, qtd_depositos_tratados)
           VALUES ('rel-visita-1', 'larvicida', 1, 2)"""
    )
    conn.execute(
        """INSERT INTO coletas
           (id_coleta, id_visita, num_tubo, deposito_eliminado)
           VALUES ('rel-coleta-1', 'rel-visita-1', 'PG-001', 0)"""
    )
    conn.execute(
        """INSERT INTO resultados_laboratorio
           (id_coleta, num_tubo, data_coleta, laboratorista, data_leitura,
            aegypt_larvas, id_laboratorista, origem)
           VALUES ('rel-coleta-1', 'PG-001', '2026-07-28', 'agente_pg',
                   '2026-07-29', 2, ?, 'sistema')""",
        (ID_AGENTE,),
    )
    conn.execute(
        """INSERT INTO focos_positivos
           (id_foco, id_visita, id_coleta, num_tubo, origem, tipo_trabalho,
            data, id_localidade, localidade, quarteirao, logradouro, numero,
            nome_morador, agentes, gera_notificacao, status_notificacao,
            codigo)
           VALUES ('rel-foco-1', 'rel-visita-1', 'rel-coleta-1', 'PG-001',
                   'sistema', 'TBO', '2026-07-28', ?,
                   'Localidade PostgreSQL', 12, 'Rua PostgreSQL', '10',
                   'Morador PostgreSQL', 'Agente PostgreSQL', 1,
                   'pendente', 'NOT-PG-001')""",
        (ID_LOCALIDADE,),
    )
    conn.execute(
        """INSERT INTO pontos_estrategicos
           (codigo_pe, localidade, id_localidade, quarteirao, nome,
            situacao, latitude, longitude, chave_origem, criado_em,
            atualizado_em)
           VALUES ('PE-PG-001', 'Localidade PostgreSQL', ?, 12,
                   'Ponto temporario PG', 1, -25.12, -49.45,
                   'pe-rel-pg-1', '2026-07-01T08:00:00',
                   '2026-07-01T08:00:00')""",
        (ID_LOCALIDADE,),
    )
    conn.execute(
        """INSERT INTO esporotricose_visitas
           (id_visita, kobo_uuid, data, hora_inicio, hora_fim, localidade,
            id_localidade, quarteirao, visita, processado_em)
           VALUES ('rel-esporo-1', 'rel-esporo-kobo-1', '2026-07-29',
                   '09:00', '09:20', 'Localidade PostgreSQL', ?, 12,
                   'normal', '2026-07-29T10:00:00')""",
        (ID_LOCALIDADE,),
    )
    conn.execute(
        """INSERT INTO esporotricose_visita_agentes(id_visita, id_agente)
           VALUES ('rel-esporo-1', ?)""",
        (ID_AGENTE,),
    )
    conn.execute(
        """INSERT INTO esporotricose_animais
           (id_animal, id_visita, kobo_uuid, especie, feridas, processado_em)
           VALUES ('rel-animal-1', 'rel-esporo-1', 'rel-animal-kobo-1',
                   'gato', 'sim', '2026-07-29T10:00:00')"""
    )
    conn.execute(
        """INSERT INTO ovitrampas_armadilhas
           (ovitrampa_id, rua, numero, localidade, responsavel, quarteirao,
            latitude, longitude, atualizado_em, ativo)
           VALUES ('OV-PG-2', 'Rua PostgreSQL', '10',
                   'Localidade PostgreSQL', 'Agente PostgreSQL', '12A',
                   -25.13, -49.46, '2026-07-28T08:00:00', 1)"""
    )
    conn.execute(
        """INSERT INTO ovitrampas_leituras
           (id_leitura, ovitrampa_id, ano, semana, data_envio_contagem,
            ovos, data_instalacao, data_coleta, importado_em,
            id_laboratorista, data_leitura)
           VALUES ('rel-ovi-leitura-1', 'OV-PG-2', 2026, 31,
                   '2026-07-30', 8, '2026-07-23', '2026-07-30',
                   '2026-07-30T12:00:00', ?, '2026-07-31')""",
        (ID_AGENTE,),
    )
    conn.execute(
        """INSERT INTO ovitrampas_calendario_grupos
           (id_grupo, nome, localidades, cor, ativo, criado_em)
           VALUES (950001, 'Grupo PostgreSQL', 'Localidade PostgreSQL',
                   '#0f766e', 1, '2026-07-01T08:00:00')"""
    )
    conn.execute(
        """INSERT INTO ovitrampas_calendario_eventos
           (id_evento, data, movimento, titulo, id_grupo, ciclo, criado_em)
           VALUES (950001, '2026-07-30', 'troca', 'Troca PostgreSQL',
                   950001, '31', '2026-07-30T08:00:00')"""
    )
    conn.execute(
        """INSERT INTO ovitrampas_calendario_agentes(id_evento, id_agente)
           VALUES (950001, ?)""",
        (ID_AGENTE,),
    )
    conn.execute(
        """INSERT INTO acoes_setor
           (id_acao, tipo, situacao, data, localidade, publico_aproximado,
            criado_em)
           VALUES (950001, 'educativa', 'realizada', '2026-07-30',
                   'Localidade PostgreSQL', 20, '2026-07-30T08:00:00')"""
    )
    conn.execute(
        "INSERT INTO acoes_setor_agentes(id_acao, id_agente) VALUES (950001, ?)",
        (ID_AGENTE,),
    )
    conn.execute(
        """INSERT INTO registro_geografico_imoveis
           (id_imovel, id_quarteirao, id_localidade, localidade, quarteirao,
            logradouro, numero, tipo, data_atualizacao, chave_origem,
            criado_em, atualizado_em, ordem)
           VALUES (950001, 950001, ?, 'Localidade PostgreSQL', '12A',
                   'Rua PostgreSQL', '10', 'R', '2026-07-30',
                   'rel-rg-pg-1', '2026-07-30T08:00:00',
                   '2026-07-30T08:00:00', 1)""",
        (ID_LOCALIDADE,),
    )
    conn.execute(
        """INSERT INTO registro_geografico_imovel_agentes
           (id_imovel, id_agente) VALUES (950001, ?)""",
        (ID_AGENTE,),
    )
    conn.commit()


def _login(client):
    with client.session_transaction() as flask_session:
        flask_session["uid"] = ADMIN["id_usuario"]
        flask_session["nome"] = ADMIN["nome"]
        flask_session["nivel"] = ADMIN["nivel"]


def _assert_status(response, expected, label):
    if response.status_code != expected:
        raise RuntimeError(
            f"{label} respondeu HTTP {response.status_code}: "
            f"{response.get_data(as_text=True)}"
        )
    return response


def _test_routes(database, conn, create_app):
    with tempfile.TemporaryDirectory(prefix="endemias-pg-relatorios-") as tmpdir:
        temp_path = Path(tmpdir)
        log_path = str(temp_path / "teste.log")
        try:
            flask_app = create_app({
                "DB_BACKEND": "postgresql",
                "PG_DATABASE": database,
                "TESTING": True,
                "WTF_CSRF_ENABLED": False,
                "LOG_PATH": log_path,
                "SECRET_KEY_PATH": str(temp_path / "secret.key"),
                "ANEXOS_DIR": str(temp_path / "anexos"),
                "BACKUP_DIR": str(temp_path / "backups"),
            })
            client = flask_app.test_client()
            _login(client)

            _assert_status(client.get("/mapa"), 200, "Pagina do Mapa")
            mapa_data = _assert_status(
                client.get("/api/mapa?localidade=Localidade+PostgreSQL"),
                200,
                "API do Mapa",
            ).get_json()
            if mapa_data["950001:12"]["ultimo_trabalho"] != "2026-07-28":
                raise RuntimeError("A data nativa do Mapa nao foi serializada.")
            if mapa_data["950001:12"]["pes_atrasados"] != 1:
                raise RuntimeError("O calculo portavel de PE atrasado divergiu.")

            pontos = _assert_status(
                client.get(
                    "/api/mapa/ovitrampas?busca=postgresql&positivas=1&min_ovos=5"
                ),
                200,
                "Camada de ovitrampas do Mapa",
            ).get_json()
            if pontos["resumo"]["armadilhas"] != 1:
                raise RuntimeError("A ovitrampa temporaria nao apareceu no Mapa.")
            if pontos["pontos"][0]["ultima_coleta"] != "2026-07-30":
                raise RuntimeError("A coleta da ovitrampa nao foi serializada.")

            pagina_notificacoes = _assert_status(
                client.get(
                    "/notificacoes?busca=postgresql&agente=agente+postgresql"
                ),
                200,
                "Pagina de Notificacoes filtrada",
            ).get_data(as_text=True).lower()
            if "not-pg-001" not in pagina_notificacoes:
                raise RuntimeError("A busca portavel de Notificacoes divergiu.")
            _assert_status(
                client.get("/notificacoes/foco/rel-foco-1"),
                200,
                "Detalhe da Notificacao",
            )
            impressao_html = _assert_status(
                client.post("/notificacoes/foco/rel-foco-1/imprimir-html"),
                200,
                "Impressao HTML da Notificacao",
            ).get_data(as_text=True)
            if "Morador PostgreSQL" not in impressao_html:
                raise RuntimeError("A impressao HTML da Notificacao divergiu.")
            status_response = _assert_status(
                client.post(
                    "/notificacoes/foco/rel-foco-1/status",
                    json={"status": "entregue"},
                ),
                200,
                "Atualizacao da Notificacao",
            ).get_json()
            if status_response["status"] != "entregue":
                raise RuntimeError("O status da Notificacao nao foi atualizado.")

            _assert_status(
                client.get("/relatorio-agente"),
                200,
                "Pagina do Relatorio por Servidor",
            )
            relatorio = _assert_status(
                client.get(
                    "/api/relatorio-agente?agente=agente_pg"
                    "&d_ini=2026-07-01&d_fim=2026-07-31"
                ),
                200,
                "API do Relatorio por Servidor",
            ).get_json()
            if relatorio["totais"]["total"] != 1:
                raise RuntimeError("O total de visitas do servidor divergiu.")
            if relatorio["por_dia"][0]["data"] != "2026-07-28":
                raise RuntimeError("A data do Relatorio nao foi serializada.")
            if relatorio["tbo_duracao"]["media"] != 30.0:
                raise RuntimeError("A duracao PostgreSQL do TBO divergiu.")
            if relatorio["esporotricose"]["totais"]["visitas"] != 1:
                raise RuntimeError("O bloco de Esporotricose divergiu.")
            if relatorio["ovitrampas"]["totais"]["eventos"] != 1:
                raise RuntimeError("O bloco de Ovitrampas divergiu.")
            if relatorio["registro_geografico"]["totais"]["imoveis"] != 1:
                raise RuntimeError("O Registro Geografico divergiu.")
            if relatorio["laboratorio"]["totais"]["leituras"] != 2:
                raise RuntimeError("O bloco de Laboratorio divergiu.")

            setor_pdf = _assert_status(
                client.get(
                    "/relatorio-agente/setor/pdf"
                    "?d_ini=2026-07-01&d_fim=2026-07-31"
                ),
                200,
                "Relatorio consolidado do Setor",
            ).get_data(as_text=True)
            if "Agente PostgreSQL" not in setor_pdf:
                raise RuntimeError("O servidor nao apareceu no relatorio do setor.")

            foco = conn.execute(
                "SELECT status_notificacao FROM focos_positivos WHERE id_foco='rel-foco-1'"
            ).fetchone()
            if foco[0] != "entregue":
                raise RuntimeError("A escrita temporaria da Notificacao nao persistiu.")
            historico = conn.execute(
                """SELECT COUNT(*) FROM focos_historico
                    WHERE id_foco='rel-foco-1' AND campo='status_notificacao'"""
            ).fetchone()[0]
            if historico != 1:
                raise RuntimeError("O historico da Notificacao nao foi gravado.")
            evento = conn.execute(
                """SELECT detalhes_json FROM auditoria_eventos
                    WHERE acao='notificacao_status_atualizado'
                    ORDER BY id_evento DESC LIMIT 1"""
            ).fetchone()
            if not evento or json.loads(evento[0])["status_novo"] != "entregue":
                raise RuntimeError("A auditoria atomica da Notificacao divergiu.")
        except Exception:
            if os.path.exists(log_path):
                print(Path(log_path).read_text(encoding="utf-8", errors="replace"))
            raise
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
        tables = _public_tables(conn)
        public_before = _public_counts(conn, tables)
        conn.rollback()
        _temporary_schema(conn, tables)
        _fixtures(conn)
        shared = _SharedConnection(conn)
        db_core.connect = lambda unused_target: shared

        _test_routes(database, conn, create_app)

        conn.rollback()
        public_after = _public_counts(conn, tables)
        if public_before != public_after:
            raise RuntimeError("Uma tabela publica foi alterada pelo ensaio.")
        return len(tables)
    finally:
        db_core.connect = original_connect
        conn.close()


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.database != SAFE_DATABASE and args.confirmar_banco != args.database:
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

    print("Teste de Mapa, Notificacoes e Relatorios no PostgreSQL")
    print("=" * 57)
    print(f"Banco: {args.database}")
    print("Mapa geral, PE e camada de ovitrampas: OK")
    print("Listagem, detalhe, escrita e auditoria de Notificacoes: OK")
    print("Relatorio individual, setor e blocos complementares: OK")
    print(f"Tabelas publicas preservadas: {total_publicas}")
    print("\n[OK] Lote validado somente em tabelas temporarias.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
