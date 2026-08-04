import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app_core import contaovos_fila
from app_core import db as db_core
from app_core import ovitrampas
from app_core import schema_metadata
from scripts import verificar_semanas_contaovos
from scripts import testar_contaovos_fila_postgresql
from unittest import mock


class ContaOvosFilaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "fila.db"
        self.conn = db_core.connect(self.db_path)
        self.conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE ovitrampas_laboratorio_lotes (
                id_lote INTEGER PRIMARY KEY,
                data_movimento TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE ovitrampas_laboratorio_itens (
                id_item INTEGER PRIMARY KEY,
                id_lote INTEGER NOT NULL REFERENCES ovitrampas_laboratorio_lotes(id_lote),
                ovitrampa_id TEXT NOT NULL,
                ovos INTEGER NOT NULL,
                ocorrencia INTEGER
            );
            CREATE TABLE ovitrampas_armadilhas (
                ovitrampa_id TEXT PRIMARY KEY,
                latitude REAL,
                longitude REAL
            );
            CREATE TABLE ovitrampas_ocorrencias_conta_ovos (
                id_contagem TEXT PRIMARY KEY,
                ovitrampa_id TEXT NOT NULL,
                data TEXT,
                ano INTEGER,
                semana INTEGER,
                ovos INTEGER,
                ocorrencia_codigo INTEGER
            );
            """
        )
        contaovos_fila.ensure_schema_connection(self.conn)
        self.conn.execute(
            "INSERT INTO ovitrampas_laboratorio_lotes VALUES (1,'2026-08-02','concluido')"
        )
        self.conn.execute(
            "INSERT INTO ovitrampas_laboratorio_itens VALUES (11,1,'97',7,5)"
        )
        self.conn.execute(
            "INSERT INTO ovitrampas_armadilhas VALUES ('97',-25.1,-49.2)"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_mapeamento_de_ocorrencia_deriva_fonte_existente(self):
        for remote, local in ovitrampas.CONTA_OVOS_OCORRENCIAS.items():
            if local <= 8:
                self.assertEqual(remote, contaovos_fila.occurrence_code_for_api(local))
        self.assertEqual(1, contaovos_fila.occurrence_code_for_api(None))
        with self.assertRaises(contaovos_fila.ContaOvosQueueError):
            contaovos_fila.occurrence_code_for_api(9)

    def test_prepara_pendente_sem_qualquer_envio_remoto(self):
        result = contaovos_fila.prepare_and_reconcile(
            self.conn, 1, now=datetime(2026, 8, 3, 12, 0, 0)
        )
        self.conn.commit()
        self.assertEqual(
            {"id_lote": 1, "total": 1, "pendentes": 1, "confirmados": 0, "erros": 0},
            result,
        )
        row = self.conn.execute(
            "SELECT status, tentativas, id_remoto, length(payload_hash) AS tamanho "
            "FROM contaovos_fila_contagens WHERE id_item=11"
        ).fetchone()
        self.assertEqual("pendente", row["status"])
        self.assertEqual(0, row["tentativas"])
        self.assertIsNone(row["id_remoto"])
        self.assertEqual(64, row["tamanho"])

    def test_reconcilia_leitura_igual_como_confirmada(self):
        self.conn.execute(
            "INSERT INTO ovitrampas_ocorrencias_conta_ovos "
            "VALUES ('900','97','2026-08-02',2026,31,7,5)"
        )
        result = contaovos_fila.prepare_and_reconcile(self.conn, 1)
        self.conn.commit()
        self.assertEqual(1, result["confirmados"])
        row = self.conn.execute(
            "SELECT status, id_remoto, confirmado_em "
            "FROM contaovos_fila_contagens WHERE id_item=11"
        ).fetchone()
        self.assertEqual("confirmado", row["status"])
        self.assertEqual("900", row["id_remoto"])
        self.assertTrue(row["confirmado_em"])

    def test_divergencia_remota_vira_erro_sem_confirmar(self):
        self.conn.execute(
            "INSERT INTO ovitrampas_ocorrencias_conta_ovos "
            "VALUES ('901','97','2026-08-02',2026,31,99,5)"
        )
        result = contaovos_fila.prepare_and_reconcile(self.conn, 1)
        self.conn.commit()
        self.assertEqual(1, result["erros"])
        row = self.conn.execute(
            "SELECT status, erro_sanitizado FROM contaovos_fila_contagens"
        ).fetchone()
        self.assertEqual("erro", row["status"])
        self.assertIn("ovos", row["erro_sanitizado"])

    def test_coordenada_ausente_bloqueia_lote_antes_da_fila(self):
        self.conn.execute(
            "UPDATE ovitrampas_armadilhas SET latitude=NULL WHERE ovitrampa_id='97'"
        )
        with self.assertRaises(contaovos_fila.ContaOvosQueueError) as ctx:
            contaovos_fila.prepare_and_reconcile(self.conn, 1)
        self.assertEqual("validation_failed", ctx.exception.kind)
        self.assertEqual("missing_coordinates", ctx.exception.issues[0]["tipo"])
        count = self.conn.execute(
            "SELECT COUNT(*) FROM contaovos_fila_contagens"
        ).fetchone()[0]
        self.assertEqual(0, count)

    def test_alteracao_de_item_confirmado_exige_revisao_humana(self):
        self.conn.execute(
            "INSERT INTO ovitrampas_ocorrencias_conta_ovos "
            "VALUES ('902','97','2026-08-02',2026,31,7,5)"
        )
        contaovos_fila.prepare_and_reconcile(self.conn, 1)
        self.conn.commit()
        self.conn.execute(
            "UPDATE ovitrampas_laboratorio_itens SET ovos=8 WHERE id_item=11"
        )
        with self.assertRaises(contaovos_fila.ContaOvosQueueError) as ctx:
            contaovos_fila.prepare_and_reconcile(self.conn, 1)
        self.conn.rollback()
        self.assertEqual("confirmed_payload_changed", ctx.exception.kind)
        row = self.conn.execute(
            "SELECT status, id_remoto FROM contaovos_fila_contagens"
        ).fetchone()
        self.assertEqual("confirmado", row["status"])
        self.assertEqual("902", row["id_remoto"])

    def test_envio_interrompido_sem_reconciliacao_vira_erro(self):
        contaovos_fila.prepare_and_reconcile(self.conn, 1)
        self.conn.execute(
            "UPDATE contaovos_fila_contagens SET status='enviando' WHERE id_item=11"
        )
        self.conn.commit()
        result = contaovos_fila.prepare_and_reconcile(self.conn, 1)
        self.conn.commit()
        self.assertEqual(1, result["erros"])
        row = self.conn.execute(
            "SELECT status, erro_sanitizado FROM contaovos_fila_contagens"
        ).fetchone()
        self.assertEqual("erro", row["status"])
        self.assertIn("tentativa anterior", row["erro_sanitizado"])

    def test_confere_semana_epidemiologica_com_dados_sincronizados(self):
        self.conn.execute(
            "INSERT INTO ovitrampas_ocorrencias_conta_ovos "
            "VALUES ('903','97','2026-08-02',2026,31,7,5)"
        )
        ok = contaovos_fila.check_epidemiological_weeks(self.conn)
        self.assertTrue(ok["ok"])
        self.assertEqual(1, ok["comparados"])
        self.conn.execute(
            "UPDATE ovitrampas_ocorrencias_conta_ovos SET semana=30"
        )
        mismatch = contaovos_fila.check_epidemiological_weeks(self.conn)
        self.assertFalse(mismatch["ok"])
        self.assertEqual(1, mismatch["divergencias"])

    def test_confere_date_year_week_brutos_da_api(self):
        calls = []

        def fetcher(key, **params):
            calls.append(params)
            if params["page"] > 1:
                return []
            return [
                {
                    "counting_id": 1,
                    "ovitrap_id": "97",
                    "municipality_code": "4100400",
                    "state_code": "PR",
                    "date": "2026-08-02",
                    "year": 2026,
                    "week": 31,
                }
            ]

        result = contaovos_fila.check_remote_epidemiological_weeks(
            "chave-falsa",
            date_start="2026-08-01",
            date_end="2026-08-03",
            page_fetcher=fetcher,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["comparados"])
        self.assertEqual("2026-08-01", calls[0]["date_start"])

    def test_semana_remota_divergente_e_contada(self):
        def fetcher(key, **params):
            if params["page"] > 1:
                return []
            return [
                {
                    "counting_id": 2,
                    "ovitrap_id": "97",
                    "municipality_code": "4100400",
                    "state_code": "PR",
                    "date": "2026-08-02",
                    "year": 2026,
                    "week": 30,
                }
            ]

        result = contaovos_fila.check_remote_epidemiological_weeks(
            "chave-falsa",
            date_start="2026-08-01",
            date_end="2026-08-03",
            page_fetcher=fetcher,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(1, result["divergencias"])

    def test_script_de_semana_exige_confirmacoes_sem_conectar(self):
        with mock.patch.object(
            verificar_semanas_contaovos.contaovos_credencial, "read_key"
        ) as read_key:
            self.assertEqual(2, verificar_semanas_contaovos.main([]))
        read_key.assert_not_called()

    def test_script_de_semana_usa_get_em_periodos_mensais(self):
        with (
            mock.patch.object(
                verificar_semanas_contaovos.contaovos_credencial,
                "read_key",
                return_value="chave-falsa",
            ),
            mock.patch.object(
                verificar_semanas_contaovos.contaovos_fila,
                "check_remote_epidemiological_weeks",
                return_value={
                    "ok": True,
                    "comparados": 10,
                    "divergencias": 0,
                    "paginas": 2,
                    "exemplos": [],
                },
            ) as check,
            mock.patch("builtins.print"),
        ):
            result = verificar_semanas_contaovos.main(
                [
                    "--data-inicial",
                    "2026-01-01",
                    "--data-final",
                    "2026-02-02",
                    "--confirmar-leitura",
                    verificar_semanas_contaovos.READ_CONFIRMATION,
                ]
            )
        self.assertEqual(0, result)
        self.assertEqual(2, check.call_count)

    def test_migracao_postgresql_declara_fila_restrita(self):
        sql = (
            Path(__file__).resolve().parents[1]
            / "migrations/postgresql/0004_contaovos_fila_contagens.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE contaovos_fila_contagens", sql)
        self.assertIn("FOREIGN KEY (id_item)", sql)
        self.assertIn("CHECK (status IN", sql)
        self.assertNotIn("postcounting", sql.lower())
        self.assertIn("contaovos_fila_contagens", schema_metadata.INTERNAL_TABLES)

    def test_ensaio_postgresql_recusa_banco_oficial(self):
        with mock.patch.object(
            testar_contaovos_fila_postgresql.postgresql, "connect"
        ) as connect:
            result = testar_contaovos_fila_postgresql.main(
                ["--database", "endemias"]
            )
        self.assertEqual(2, result)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
